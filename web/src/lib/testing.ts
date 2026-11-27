/**
 * Test helpers: an in-memory daemon that applies RFC 7386 merge patches the way
 * `PUT /api/config` does, and fixtures for a MIDICRAFT-like device.
 */

import { vi } from 'vitest';

import { ApiError, type ApiClient, type DeviceEntry } from './api';
import { ConfigStore } from './configStore.svelte';
import { StatusStore as StatusStoreImpl, type StatusStore, type WebSocketLike } from './status';

type Json = Record<string, any>;

/** RFC 7386: objects merge recursively, arrays and scalars replace, null deletes. */
export function applyMergePatch(target: unknown, patch: unknown): unknown {
  if (patch === null || typeof patch !== 'object' || Array.isArray(patch)) return patch;
  const base: Json =
    target !== null && typeof target === 'object' && !Array.isArray(target)
      ? { ...(target as Json) }
      : {};
  for (const [key, value] of Object.entries(patch as Json)) {
    if (value === null) delete base[key];
    else base[key] = applyMergePatch(base[key], value);
  }
  return base;
}

export interface FakeDaemon {
  api: ApiClient;
  /** Current configuration of the fake daemon. */
  config: () => Json;
  generation: () => number;
  /** Patches received by `updateConfig`, in order. */
  patches: () => Json[];
  /** Change the configuration behind the client's back (another client). */
  externalWrite: (patch: Json) => void;
  setDevices: (devices: DeviceEntry[]) => void;
  /** State `GET /api/device-learn` reports (events are pushed separately). */
  setDeviceLearn: (status: Json) => void;
}

export function fakeDaemon(initial: Json, devices: DeviceEntry[]): FakeDaemon {
  let config = structuredClone(initial);
  let generation = 1;
  let deviceList = devices;
  let deviceLearn: Json = { active: false };
  const received: Json[] = [];
  const api = {
    configSnapshot: vi.fn(async () => ({ config: structuredClone(config), generation })),
    config: vi.fn(async () => structuredClone(config)),
    devices: vi.fn(async () => structuredClone(deviceList)),
    updateConfig: vi.fn(async (patch: Json, options: { generation?: number | null } = {}) => {
      if (
        options.generation !== undefined &&
        options.generation !== null &&
        options.generation !== generation
      ) {
        throw new ApiError(412, 'stale_config', 'Konfiguration wurde inzwischen geändert');
      }
      received.push(structuredClone(patch));
      config = applyMergePatch(config, patch) as Json;
      generation += 1;
      return { generation, config: structuredClone(config) };
    }),
    deviceLearnStatus: vi.fn(async () => structuredClone(deviceLearn)),
    startDeviceLearn: vi.fn(async () => ({ active: true })),
    skipDeviceLearn: vi.fn(async () => ({ active: true })),
    cancelDeviceLearn: vi.fn(async () => ({ cancelled: true })),
    finishDeviceLearn: vi.fn(async () => ({})),
    startLearn: vi.fn(async (kind: string, device?: string) => ({
      kind,
      status: 'active',
      control: null,
      device: device ?? null,
      raw: null,
      direction: 0,
      detents: 0,
      elapsed: 0,
      timed_out: false,
    })),
    cancelLearn: vi.fn(async () => ({ cancelled: true, learn: null })),
  } as unknown as ApiClient;
  return {
    api,
    config: () => structuredClone(config),
    generation: () => generation,
    patches: () => received,
    externalWrite: (patch) => {
      config = applyMergePatch(config, patch) as Json;
      generation += 1;
    },
    setDevices: (next) => {
      deviceList = next;
    },
    setDeviceLearn: (status) => {
      deviceLearn = status;
    },
  };
}

export const midicraft: DeviceEntry = {
  name: 'midicraft',
  backend: 'midi',
  profile: 'midicraft',
  vendor_id: 0x04d8,
  product_id: 0x1234,
  vendor_product: '04d8:1234',
  name_contains: 'MIDICRAFT',
  detected: { path: '/dev/snd/midiC1D0' },
  layout: null,
  bank_size: 5,
  controls: {
    keys: [],
    notes: [],
    encoders: [],
    midi_encoders: [],
    values: [],
    inventory: [
      { id: 'mc_click_1', kind: 'button', label: 'Klick 1' },
      { id: 'mc_click_2', kind: 'button', label: 'Klick 2' },
      { id: 'mc_fader_1', kind: 'fader', label: 'Fader 1' },
      { id: 'mc_encoder_1', kind: 'encoder', label: 'Encoder 1' },
      { id: 'encoder.1', kind: 'relative-encoder', label: 'Dreh 1', encoder_id: 1 },
    ],
    banks: [
      { number: 1, channel: 1, notes: { '60': 'mc_click_1', '70': 'mc_fader_1' } },
      { number: 2, channel: 2, notes: { '62': 'mc_click_2', '71': 'mc_fader_1' } },
      { number: 3, channel: 3, notes: { '64': 'mc_bank3_only' } },
    ],
    logical: ['mc_click_1', 'mc_click_2', 'mc_fader_1', 'mc_encoder_1', 'encoder.1'],
  },
};

export function baseConfig(mapping: Json = {}): Json {
  return {
    profiles: {
      midicraft: {
        banks: [
          { number: 1, channel: 1, notes: { '60': 'mc_click_1', '70': 'mc_fader_1' } },
          { number: 2, channel: 2, notes: { '62': 'mc_click_2', '71': 'mc_fader_1' } },
          { number: 3, channel: 3, notes: { '64': 'mc_bank3_only' } },
        ],
      },
    },
    midi_remote: { enabled: false },
    mapping: {
      keys: {},
      playbacks: {},
      encoders: [],
      screen_encoders: {},
      modifiers: {},
      device_banks: { midicraft: { bank_size: 5 } },
      ...mapping,
    },
  };
}

/** A loaded store on a fake daemon, with the device and bank selected. */
export async function loadedStore(
  initial: Json = baseConfig(),
  options: { bank?: number; status?: StatusStore; devices?: DeviceEntry[] } = {},
): Promise<{ store: ConfigStore; daemon: FakeDaemon }> {
  const daemon = fakeDaemon(initial, options.devices ?? [midicraft]);
  const store = new ConfigStore(daemon.api, options.status);
  await store.load();
  if (options.bank) store.selectBank(options.bank);
  return { store, daemon };
}

/** A `StatusStore` on a fake socket; `push` delivers a WebSocket event. */
export function fakeStatus(): { status: StatusStore; push: (type: string, data: unknown) => void } {
  let socket: WebSocketLike | null = null;
  const status = new StatusStoreImpl({
    factory: () => {
      socket = { onopen: null, onmessage: null, onclose: null, onerror: null, close: () => undefined };
      return socket;
    },
  });
  status.connect();
  return {
    status,
    push: (type, data) => socket?.onmessage?.({ data: JSON.stringify({ type, data }) }),
  };
}

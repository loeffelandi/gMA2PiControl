import { describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient, type DeviceEntry } from './api';
import { ConfigStore, SaveError } from './configStore.svelte';
import { controlsOf } from './deviceControls';
import { StatusStore, type WebSocketLike } from './status';
import { baseConfig, loadedStore, midicraft } from './testing';

function entry(name: string, detected = true, banks = [1, 2]): DeviceEntry {
  return {
    name,
    backend: 'midi',
    profile: name,
    vendor_id: 1,
    product_id: 1,
    vendor_product: '0001:0001',
    name_contains: null,
    detected: detected ? { path: '/dev/x' } : null,
    layout: null,
    bank_size: 5,
    controls: {
      keys: [],
      notes: [],
      encoders: [],
      midi_encoders: [],
      values: [],
      inventory: [],
      banks: banks.map((number) => ({ number, channel: number, notes: {} })),
      logical: [],
    },
  };
}

function fakeApi(overrides: Record<string, unknown> = {}) {
  return {
    configSnapshot: vi
      .fn()
      .mockResolvedValue({ config: { mapping: { keys: {} } }, generation: 3 }),
    devices: vi.fn().mockResolvedValue([entry('a'), entry('b', false)]),
    updateConfig: vi.fn().mockResolvedValue({
      generation: 4,
      config: { mapping: { keys: { x: { hardkey: 'GOTO' } } } },
    }),
    ...overrides,
  } as unknown as ApiClient;
}

describe('ConfigStore', () => {
  it('loads configuration, generation and only the detected devices', async () => {
    const store = new ConfigStore(fakeApi());
    await store.load();
    expect(store.generation).toBe(3);
    expect(store.visibleDevices.map((d) => d.name)).toEqual(['a']);
    expect(store.selectedDevice).toBe('a');
    expect(store.loaded).toBe(true);
  });

  it('shares a saved change with every consumer without reloading', async () => {
    const api = fakeApi();
    const store = new ConfigStore(api);
    await store.load();
    const other = store; // both tabs hold the same instance
    await store.save({ mapping: { keys: { x: { hardkey: 'GOTO' } } } });
    expect(other.config?.mapping.keys.x).toEqual({ hardkey: 'GOTO' });
    expect(other.generation).toBe(4);
    expect(api.configSnapshot).toHaveBeenCalledTimes(1);
    expect(api.updateConfig).toHaveBeenCalledWith(expect.anything(), { generation: 3 });
  });

  it('flags a stale draft as conflict and keeps the configuration', async () => {
    const api = fakeApi({
      updateConfig: vi
        .fn()
        .mockRejectedValue(new ApiError(412, 'stale_config', 'Konfiguration wurde inzwischen geändert')),
    });
    const store = new ConfigStore(api);
    await store.load();
    const before = store.config;
    await expect(store.save({ mapping: {} })).rejects.toMatchObject({ stale: true });
    expect(store.conflict).toBe(true);
    expect(store.config).toBe(before);
    expect(store.saving).toBe(false);
  });

  it('resolves a conflict by reloading, and by discarding the draft', async () => {
    const api = fakeApi({
      updateConfig: vi.fn().mockRejectedValue(new ApiError(412, 'stale_config', 'alt')),
    });
    const store = new ConfigStore(api);
    await store.load();
    await store.save({ mapping: {} }).catch(() => undefined);
    vi.mocked(api.configSnapshot).mockResolvedValue({ config: { mapping: { fresh: true } }, generation: 9 });

    await store.resolveConflict('reload');
    expect(store.conflict).toBe(false);
    expect(store.generation).toBe(9);
    expect(store.discardEpoch).toBe(0);

    await store.save({ mapping: {} }).catch(() => undefined);
    await store.resolveConflict('discard');
    expect(store.discardEpoch).toBe(1);
  });

  it('maps a daemon validation error to the field', async () => {
    const api = fakeApi({
      updateConfig: vi
        .fn()
        .mockRejectedValue(
          new ApiError(422, 'validation_error', 'Executor muss mindestens 1 sein', 'mapping.playbacks.x.executor'),
        ),
    });
    const store = new ConfigStore(api);
    await store.load();
    let caught: unknown;
    try {
      await store.save({ mapping: {} });
    } catch (cause) {
      caught = cause;
    }
    expect(caught).toBeInstanceOf(SaveError);
    expect((caught as SaveError).field).toBe('mapping.playbacks.x.executor');
    expect(store.fieldError).toEqual({
      field: 'mapping.playbacks.x.executor',
      message: 'Executor muss mindestens 1 sein',
    });
    expect(store.conflict).toBe(false);
  });

  it('keeps device and bank across tabs while the device stays detected', async () => {
    const api = fakeApi({
      devices: vi.fn().mockResolvedValue([entry('a'), entry('c')]),
    });
    const store = new ConfigStore(api);
    await store.load();
    store.selectDevice('c');
    store.selectBank(2);
    await store.refreshDevices();
    expect(store.selectedDevice).toBe('c');
    expect(store.bank).toBe(2);
  });

  it('drops the selection when the device disappears', async () => {
    const devices = vi.fn().mockResolvedValue([entry('a'), entry('c')]);
    const store = new ConfigStore(fakeApi({ devices }));
    await store.load();
    store.selectDevice('c');
    devices.mockResolvedValue([entry('a'), entry('c', false)]);
    await store.refreshDevices();
    expect(store.selectedDevice).toBe('a');
  });

  it('falls back to the first bank when the bank does not exist on the new device', async () => {
    const store = new ConfigStore(
      fakeApi({ devices: vi.fn().mockResolvedValue([entry('a', true, [1, 2, 3]), entry('c', true, [1])]) }),
    );
    await store.load();
    store.selectBank(3);
    store.selectDevice('c');
    expect(store.bank).toBe(1);
  });

  it('follows device presence of the status store', async () => {
    let socket: WebSocketLike | null = null;
    const status = new StatusStore({
      factory: () => {
        socket = {
          onopen: null,
          onmessage: null,
          onclose: null,
          onerror: null,
          close: () => undefined,
        };
        return socket;
      },
    });
    status.connect();
    const store = new ConfigStore(fakeApi(), status);
    await store.load();
    expect(store.visibleDevices.map((d) => d.name)).toEqual(['a']);

    socket!.onmessage?.({
      data: JSON.stringify({
        type: 'status',
        data: {
          presence: {
            a: { connected: false, path: null, seen: false },
            b: { connected: true, path: '/dev/y', seen: true },
          },
        },
      }),
    });
    expect(store.visibleDevices.map((d) => d.name)).toEqual(['b']);
    expect(store.selectedDevice).toBe('b');
  });

  it('reloads when another client changed the configuration', async () => {
    let socket: WebSocketLike | null = null;
    const status = new StatusStore({
      factory: () => {
        socket = { onopen: null, onmessage: null, onclose: null, onerror: null, close: () => undefined };
        return socket;
      },
    });
    status.connect();
    const api = fakeApi();
    const store = new ConfigStore(api, status);
    await store.load();
    vi.mocked(api.configSnapshot).mockResolvedValue({ config: { mapping: { other: 1 } }, generation: 5 });

    socket!.onmessage?.({ data: JSON.stringify({ type: 'config', data: { generation: 5 } }) });
    await vi.waitFor(() => expect(store.generation).toBe(5));
    expect(store.config?.mapping.other).toBe(1);
  });
});

describe('ConfigStore priority', () => {
  const control = (id: string, bank = 1) => controlsOf(midicraft, bank).find((entry) => entry.id === id)!;

  it('lets a layer key beat a playback target of the same control', async () => {
    const { store } = await loadedStore(
      baseConfig({
        playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
        device_banks: {
          midicraft: { bank_size: 5, '1': { keys: { mc_click_1: { hardkey: 'GO' } } } },
        },
      }),
    );
    const resolved = store.resolve(control('mc_click_1'));
    expect(resolved.conflict).toEqual({ winner: 'layer-key', shadowed: ['playback'] });
    expect(resolved.assignment).toMatchObject({ kind: 'key', hardkey: 'GO' });
  });

  it('lets a playback target beat a global key and a modifier', async () => {
    const { store } = await loadedStore(
      baseConfig({
        playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
        keys: { mc_click_1: { hardkey: 'GO' } },
        modifiers: { mc_click_1: { hardkey: 'SHIFT' } },
      }),
    );
    const resolved = store.resolve(control('mc_click_1'));
    expect(resolved.conflict).toEqual({ winner: 'playback', shadowed: ['modifier', 'key'] });
  });

  it('lets a modifier beat a layer key', async () => {
    const { store } = await loadedStore(
      baseConfig({
        modifiers: { mc_click_1: { hardkey: 'SHIFT' } },
        device_banks: {
          midicraft: { bank_size: 5, '1': { keys: { mc_click_1: { hardkey: 'GO' } } } },
        },
      }),
    );
    expect(store.resolve(control('mc_click_1')).conflict).toEqual({
      winner: 'modifier',
      shadowed: ['layer-key'],
    });
  });

  it('reports no layer-key conflict for value and encoder controls', async () => {
    const { store } = await loadedStore(
      baseConfig({
        playbacks: {
          mc_fader_1: { page: 1, executor: 1, kind: 'fader' },
          'encoder.1': { page: 1, executor: 2, kind: 'fader' },
        },
        encoders: [{ id: 1, slot: 1 }],
        device_banks: {
          midicraft: {
            bank_size: 5,
            '1': { keys: { mc_fader_1: { hardkey: 'GO' }, 'encoder.1': { hardkey: 'GO' } } },
          },
        },
      }),
    );
    expect(store.resolve(control('mc_fader_1')).conflict).toBeNull();
    expect(store.resolve(control('encoder.1')).conflict).toBeNull();
    expect(store.resolve(control('encoder.1')).assignment).toMatchObject({ kind: 'playback', executor: 2 });
  });

  it('explains the conflict through the marker', async () => {
    const { store } = await loadedStore(
      baseConfig({
        playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
        keys: { mc_click_1: { hardkey: 'GO' } },
      }),
    );
    expect(store.markerFor(control('mc_click_1')).conflict).toBe(
      'Playback-Ziel hat Vorrang vor der globalen Taste.',
    );
    expect(store.markerFor(control('mc_click_2')).conflict).toBeNull();
  });
});

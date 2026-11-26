import { render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import StatusPage from './StatusPage.svelte';
import { StatusStore, type WebSocketLike } from './status';

class FakeSocket implements WebSocketLike {
  static last: FakeSocket | null = null;

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public readonly url: string) {
    FakeSocket.last = this;
  }

  close(): void {
    this.closed = true;
  }

  emitOpen(): void {
    this.onopen?.();
  }

  emitMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  drop(): void {
    this.onclose?.();
  }
}

const devices = [
  {
    name: 'cherry',
    backend: 'evdev',
    profile: 'cherry-g86',
    vendor_id: 0x046a,
    product_id: 0,
    vendor_product: '046a:0000',
    name_contains: 'Cherry',
    detected: { path: '/dev/input/event0' },
    controls: {
      logical: ['fix'],
      keys: [],
      notes: [],
      encoders: [],
      midi_encoders: [],
      values: [],
      inventory: [],
      banks: [],
    },
    layout: null,
    bank_size: 1,
  },
];

const activity = {
  devices: {
    cherry: { rx: 12, tx: 0, last_rx: 1700000000.5, last_tx: null },
  },
  log: [
    {
      seq: 11,
      ts: 1700000000.5,
      direction: 'rx' as const,
      device: 'cherry',
      kind: 'key',
      summary: 'ch_pg_plus · value 1',
    },
  ],
};

const status = {
  connected: true,
  authenticated: true,
  session: 7,
  queue_depth: 2,
  rate: 25,
  screen_mode: false,
  frames_sent: 42,
  last_frame_types: ['keyname', 'encoder'],
  reconnects: 1,
  last_error: null,
  generation: 3,
  busy: false,
  activity,
};

describe('StatusPage', () => {
  it('shows device activity, merges log deltas and follows live status', async () => {
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
      reconnectBaseMs: 10,
    });
    const { container } = render(StatusPage, {
      props: { store, devicesLoader: async () => devices },
    });

    store.connect();
    const socket = FakeSocket.last!;
    socket.emitOpen();
    socket.emitMessage({ type: 'status', data: status });
    socket.emitMessage({
      type: 'network',
      data: {
        pending: null,
        last_result: { status: 'rolled_back', at: '2026-01-01T00:00:00Z', detail: null },
      },
    });
    expect(store.state.network?.last_result?.status).toBe('rolled_back');

    await waitFor(() => {
      expect(screen.getByTestId('connection').textContent).toContain('verbunden');
    });
    expect(screen.getByTestId('ma2-state').textContent).toContain('Session 7');
    expect(screen.getByText('42')).toBeTruthy();
    expect(screen.getByText('Attribut (rot)')).toBeTruthy();
    expect(screen.getByText(/RX vom Gerät/)).toBeTruthy();
    expect(screen.getByText(/12 rx \/ 0 tx/)).toBeTruthy();
    expect(screen.getByText('ch_pg_plus · value 1')).toBeTruthy();

    await waitFor(() => {
      expect(container.querySelector('.device-id')?.textContent).toBe('cherry');
    });
    expect(container.querySelector('.device-state')?.textContent?.trim()).toBe(
      'verbunden',
    );

    // A delta grows the RX counter and appends exactly one log line.
    socket.emitMessage({
      type: 'activity',
      data: {
        devices: {
          cherry: { rx: 13, tx: 0, last_rx: 1700000000.9, last_tx: null },
        },
        entries: [
          {
            seq: 12,
            ts: 1700000000.9,
            direction: 'rx',
            device: 'cherry',
            kind: 'key',
            summary: 'note 70 · velocity 127',
          },
        ],
      },
    });
    await waitFor(() => {
      expect(screen.getByText('note 70 · velocity 127')).toBeTruthy();
    });

    const rxLed = container.querySelector('.device-row .activity-led.rx');
    await waitFor(() => {
      expect(rxLed?.className).toContain('pulse');
    });

    // Resending the same sequence number must not duplicate the line.
    socket.emitMessage({
      type: 'activity',
      data: {
        devices: {
          cherry: { rx: 14, tx: 1, last_rx: 1700000001, last_tx: 1700000001 },
        },
        entries: [
          {
            seq: 12,
            ts: 1700000000.9,
            direction: 'rx',
            device: 'cherry',
            kind: 'key',
            summary: 'note 70 · velocity 127',
          },
        ],
      },
    });
    await waitFor(() => {
      expect(screen.getAllByText('note 70 · velocity 127')).toHaveLength(1);
    });

    // A status snapshot replaces the log and updates the screen mode.
    socket.emitMessage({
      type: 'status',
      data: {
        ...status,
        screen_mode: true,
        activity: {
          devices: {
            cherry: { rx: 20, tx: 3, last_rx: 1700000002, last_tx: 1700000002 },
          },
          log: [
            {
              seq: 20,
              ts: 1700000002,
              direction: 'tx',
              device: 'cherry',
              kind: 'led',
              summary: 'LED color',
            },
          ],
        },
      },
    });
    await waitFor(() => {
      expect(screen.getByText('Screen (grün)')).toBeTruthy();
      expect(screen.getByText('LED color')).toBeTruthy();
      expect(screen.queryByText('note 70 · velocity 127')).toBeNull();
    });

    socket.drop();

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain(
        'Verbindung unterbrochen',
      );
    });

    store.disconnect();
  });

  it('keeps log entries in sequence order after a delayed delta', async () => {
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
      reconnectBaseMs: 10,
    });
    const { container } = render(StatusPage, {
      props: { store, devicesLoader: async () => devices },
    });

    store.connect();
    const socket = FakeSocket.last!;
    socket.emitOpen();
    socket.emitMessage({
      type: 'status',
      data: {
        ...status,
        activity: {
          devices: {
            cherry: { rx: 1, tx: 0, last_rx: 1700000000, last_tx: null },
          },
          log: [
            {
              seq: 20,
              ts: 1700000000,
              direction: 'rx',
              device: 'cherry',
              kind: 'key',
              summary: 'seq 20',
            },
          ],
        },
      },
    });
    await waitFor(() => expect(screen.getByText('seq 20')).toBeTruthy());

    socket.emitMessage({
      type: 'activity',
      data: {
        devices: {},
        entries: [
          {
            seq: 25,
            ts: 1700000001,
            direction: 'rx',
            device: 'cherry',
            kind: 'key',
            summary: 'seq 25',
          },
          {
            seq: 15,
            ts: 1700000002,
            direction: 'rx',
            device: 'cherry',
            kind: 'key',
            summary: 'seq 15',
          },
        ],
      },
    });

    await waitFor(() => {
      expect(container.querySelectorAll('.log-summary')).toHaveLength(3);
    });
    const summaries = Array.from(container.querySelectorAll('.log-summary')).map(
      (node) => node.textContent?.trim(),
    );
    expect(summaries).toEqual(['seq 15', 'seq 20', 'seq 25']);

    store.disconnect();
  });

  it('shows an empty log hint without activity', async () => {
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
      reconnectBaseMs: 10,
    });
    render(StatusPage, { props: { store, devicesLoader: async () => devices } });

    store.connect();
    const socket = FakeSocket.last!;
    socket.emitOpen();
    socket.emitMessage({
      type: 'status',
      data: { ...status, activity: { devices: {}, log: [] } },
    });

    await waitFor(() => {
      expect(screen.getByText('Noch keine Aktivität.')).toBeTruthy();
    });

    store.disconnect();
  });

  it('shows Unbekannt for Encoder-Modus before the first status snapshot arrives', () => {
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
    });
    render(StatusPage, { props: { store, devicesLoader: async () => [] } });

    expect(screen.getByText('Unbekannt')).toBeTruthy();
    expect(screen.queryByText('Attribut (rot)')).toBeNull();
  });

  it('re-fetches devices on configGeneration changes and hotplug activity', async () => {
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
      reconnectBaseMs: 10,
    });
    let currentDevices = [
      {
        ...devices[0],
        detected: null as Record<string, unknown> | null,
      },
    ];
    const devicesLoader = vi.fn(async () => currentDevices);
    const { container } = render(StatusPage, {
      props: { store, devicesLoader },
    });

    store.connect();
    const socket = FakeSocket.last!;
    socket.emitOpen();
    await waitFor(() => expect(devicesLoader).toHaveBeenCalledTimes(1));
    expect(container.querySelector('.device-id')).toBeNull();

    // Hotplug in: previously unseen device appears in activity -> re-fetches devices.
    currentDevices = [{ ...devices[0], detected: { path: '/dev/input/event0' } }];
    socket.emitMessage({
      type: 'activity',
      data: {
        devices: { cherry: { rx: 1, tx: 0, last_rx: 1700000010, last_tx: null } },
        entries: [
          {
            seq: 1,
            ts: 1700000010,
            direction: 'rx',
            device: 'cherry',
            kind: 'key',
            summary: 'fix · value 1',
          },
        ],
      },
    });

    await waitFor(() => {
      expect(devicesLoader).toHaveBeenCalledTimes(2);
      expect(container.querySelector('.device-id')?.textContent).toBe('cherry');
    });

    // Hotplug out: device-lost entry appears -> re-fetches devices.
    currentDevices = [{ ...devices[0], detected: null }];
    socket.emitMessage({
      type: 'activity',
      data: {
        devices: {},
        entries: [
          {
            seq: 2,
            ts: 1700000012,
            direction: 'rx',
            device: 'system',
            kind: 'device-lost',
            summary: 'cherry: device lost',
          },
        ],
      },
    });

    await waitFor(() => {
      expect(devicesLoader).toHaveBeenCalledTimes(3);
      expect(container.querySelector('.device-id')).toBeNull();
    });

    // Config change -> re-fetches devices.
    currentDevices = [{ ...devices[0], detected: { path: '/dev/input/event1' } }];
    socket.emitMessage({
      type: 'config',
      data: { generation: 8 },
    });

    await waitFor(() => {
      expect(devicesLoader).toHaveBeenCalledTimes(4);
      expect(container.querySelector('.device-id')?.textContent).toBe('cherry');
    });

    // Disconnect again, then replug with fresh RX activity (seq > lostSeq) -> reloads!
    currentDevices = [{ ...devices[0], detected: null }];
    socket.emitMessage({
      type: 'activity',
      data: {
        entries: [
          {
            seq: 10,
            ts: 1700000010,
            direction: 'rx',
            device: 'system',
            kind: 'device-lost',
            summary: 'cherry: device lost',
          },
        ],
      },
    });
    await waitFor(() => expect(devicesLoader).toHaveBeenCalledTimes(5));

    currentDevices = [{ ...devices[0], detected: { path: '/dev/input/event2' } }];
    socket.emitMessage({
      type: 'activity',
      data: {
        devices: { cherry: { rx: 2, tx: 0, last_rx: 1700000012, last_tx: null } },
        entries: [
          {
            seq: 11,
            ts: 1700000012,
            direction: 'rx',
            device: 'cherry',
            kind: 'key',
            summary: 'ch_pg_plus · value 1',
          },
        ],
      },
    });
    await waitFor(() => expect(devicesLoader).toHaveBeenCalledTimes(6));

    store.disconnect();
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
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
  it('announces a held shutdown chord and a running shutdown', async () => {
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
      data: {
        ...status,
        power: {
          enabled: true,
          available: true,
          state: 'holding',
          confirm_remaining: 2,
        },
      },
    });
    await waitFor(() => {
      expect(screen.getByText(/Ausschalten: noch 2× Please drücken/)).toBeTruthy();
    });

    socket.emitMessage({
      type: 'status',
      data: { ...status, power: { enabled: true, available: true, state: 'shutting_down' } },
    });
    await waitFor(() => {
      expect(screen.getByText('Der Pi fährt herunter.')).toBeTruthy();
    });
    expect(screen.queryByText(/Ausschalten: noch/)).toBeNull();

    socket.emitMessage({
      type: 'status',
      data: { ...status, power: { enabled: true, available: true, state: 'idle' } },
    });
    await waitFor(() => {
      expect(screen.queryByText('Der Pi fährt herunter.')).toBeNull();
    });
  });

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

  describe('MIDI-Remote', () => {
    const midiSession = {
      state: 'connected',
      detail: '192.168.178.72:5004',
      host: '192.168.178.72',
      port: 5004,
      latency_ms: 2.84,
    };
    const midiSync = {
      mode: 'auto',
      running: false,
      targets: 245,
      synced: 245,
      created: 3,
      changed: 0,
      removed: 1,
      failed: 0,
      deviations: 0,
      error: null,
      at: 1764200000.5,
    };

    function renderWithStatus(data: Record<string, unknown>): StatusStore {
      const store = new StatusStore({
        factory: (url) => new FakeSocket(url),
        reconnectBaseMs: 10,
      });
      render(StatusPage, { props: { store, devicesLoader: async () => [] } });
      store.connect();
      const socket = FakeSocket.last!;
      socket.emitOpen();
      socket.emitMessage({ type: 'status', data });
      return store;
    }

    it.each([
      ['missing', status],
      ['disabled', { ...status, midi_remote: { enabled: false } }],
    ])('hides the MIDI-Remote entries when %s', async (_label, data) => {
      const store = renderWithStatus(data);
      await waitFor(() => {
        expect(screen.getByTestId('ma2-state').textContent).toContain('Session 7');
      });
      expect(screen.queryByText('MIDI-Remote')).toBeNull();
      expect(screen.queryByText('Remote-Abgleich')).toBeNull();
      expect(screen.queryByTestId('midi-remote-session')).toBeNull();
      expect(screen.queryByTestId('midi-remote-sync')).toBeNull();
      expect(screen.queryByTestId('midi-remote-error')).toBeNull();
      store.disconnect();
    });

    it('shows a connected session with latency and the sync counts', async () => {
      const store = renderWithStatus({
        ...status,
        midi_remote: { enabled: true, session: midiSession, sync: midiSync },
      });
      const time = new Intl.DateTimeFormat('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      }).format(new Date(1764200000.5 * 1000));

      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-session').textContent?.trim()).toBe(
          'verbunden · 2.8 ms',
        );
      });
      expect(screen.getByText('MIDI-Remote')).toBeTruthy();
      expect(screen.getByText('Remote-Abgleich')).toBeTruthy();
      expect(screen.getByTestId('midi-remote-sync').textContent?.trim()).toBe(
        `245/245 abgeglichen · zuletzt ${time} · +3 ~0 −1`,
      );
      expect(screen.queryByTestId('midi-remote-error')).toBeNull();
      expect(screen.queryByTestId('midi-remote-retrigger')).toBeNull();
      store.disconnect();
    });

    it('retriggers the MIDI-remote sync from the status page', async () => {
      const retriggerMidiSync = vi.fn().mockResolvedValue({ enabled: true });
      const store = new StatusStore({
        factory: (url) => new FakeSocket(url),
        reconnectBaseMs: 10,
      });
      render(StatusPage, {
        props: {
          store,
          devicesLoader: async () => [],
          retriggerMidiSync,
        },
      });
      store.connect();
      FakeSocket.last!.emitOpen();
      FakeSocket.last!.emitMessage({
        type: 'status',
        data: {
          ...status,
          midi_remote: { enabled: true, session: midiSession, sync: midiSync },
        },
      });

      const button = await screen.findByTestId('midi-remote-retrigger');
      expect(button.textContent?.trim()).toBe('Remotes ausrollen');
      await fireEvent.click(button);
      expect(retriggerMidiSync).toHaveBeenCalledTimes(1);
      store.disconnect();
    });

    it('shows an incomplete sync and disables the retrigger while running', async () => {
      const retriggerMidiSync = vi.fn();
      const store = new StatusStore({
        factory: (url) => new FakeSocket(url),
        reconnectBaseMs: 10,
      });
      render(StatusPage, {
        props: {
          store,
          devicesLoader: async () => [],
          retriggerMidiSync,
        },
      });
      store.connect();
      FakeSocket.last!.emitOpen();
      FakeSocket.last!.emitMessage({
        type: 'status',
        data: {
          ...status,
          midi_remote: {
            enabled: true,
            session: midiSession,
            sync: { ...midiSync, synced: 240, failed: 5, running: true },
          },
        },
      });

      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-incomplete').textContent).toContain(
          '5 von 245 fehlen',
        );
      });
      expect(screen.getByTestId('midi-remote-incomplete').textContent).toContain(
        'Abgleich läuft',
      );
      expect(
        (screen.getByTestId('midi-remote-retrigger') as HTMLButtonElement).disabled,
      ).toBe(true);
      store.disconnect();
    });

    it('hides the retrigger when sync is off or the session is dry-run', async () => {
      const retriggerMidiSync = vi.fn();
      const store = new StatusStore({
        factory: (url) => new FakeSocket(url),
        reconnectBaseMs: 10,
      });
      render(StatusPage, {
        props: {
          store,
          devicesLoader: async () => [],
          retriggerMidiSync,
        },
      });
      store.connect();
      FakeSocket.last!.emitOpen();
      FakeSocket.last!.emitMessage({
        type: 'status',
        data: {
          ...status,
          midi_remote: {
            enabled: true,
            session: { ...midiSession, state: 'dry-run', latency_ms: null },
            sync: midiSync,
          },
        },
      });
      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-session').textContent?.trim()).toBe(
          'Dry-Run',
        );
      });
      expect(screen.queryByTestId('midi-remote-retrigger')).toBeNull();

      FakeSocket.last!.emitMessage({
        type: 'status',
        data: {
          ...status,
          midi_remote: {
            enabled: true,
            session: midiSession,
            sync: { ...midiSync, mode: 'off' },
          },
        },
      });
      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-sync').textContent?.trim()).toBe(
          'aus (alle Ziele aktiv)',
        );
      });
      expect(screen.queryByTestId('midi-remote-retrigger')).toBeNull();
      store.disconnect();
    });

    it('shows the disconnect detail and the sync error', async () => {
      const error = 'Telnet 192.168.178.72:30000 nicht erreichbar: timeout';
      const store = renderWithStatus({
        ...status,
        midi_remote: {
          enabled: true,
          session: {
            ...midiSession,
            state: 'disconnected',
            detail: 'Connection refused',
            latency_ms: null,
          },
          sync: {
            ...midiSync,
            synced: 0,
            created: 0,
            removed: 0,
            failed: 245,
            error,
            at: null,
          },
        },
      });

      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-session').textContent?.trim()).toBe(
          'getrennt (Connection refused)',
        );
      });
      expect(screen.getByTestId('midi-remote-sync').textContent?.trim()).toBe(
        '0/245 abgeglichen · +0 ~0 −0 · 245 fehlerhaft',
      );
      const errorLine = screen.getByTestId('midi-remote-error');
      expect(errorLine.className).toContain('error');
      expect(errorLine.textContent?.trim()).toBe(`MIDI-Remote-Abgleich: ${error}`);
      store.disconnect();
    });

    it('labels check mode, running syncs and disabled sync', async () => {
      const store = renderWithStatus({
        ...status,
        midi_remote: {
          enabled: true,
          session: { ...midiSession, state: 'dry-run', latency_ms: null },
          sync: {
            ...midiSync,
            mode: 'check',
            running: true,
            synced: 240,
            created: 0,
            removed: 0,
          },
        },
      });

      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-sync').textContent?.trim()).toBe(
          '240/245 abgeglichen · nur prüfen · läuft',
        );
      });
      expect(screen.getByTestId('midi-remote-session').textContent?.trim()).toBe(
        'Dry-Run',
      );

      FakeSocket.last!.emitMessage({
        type: 'status',
        data: {
          ...status,
          midi_remote: {
            enabled: true,
            session: midiSession,
            sync: { ...midiSync, mode: 'off' },
          },
        },
      });
      await waitFor(() => {
        expect(screen.getByTestId('midi-remote-sync').textContent?.trim()).toBe(
          'aus (alle Ziele aktiv)',
        );
      });
      store.disconnect();
    });
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

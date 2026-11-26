import { describe, expect, it, vi } from 'vitest';

import { LOG_LIMIT, StatusStore, type WebSocketLike } from './status';

class FakeSocket implements WebSocketLike {
  static instances: FakeSocket[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public readonly url: string) {
    FakeSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

describe('StatusStore', () => {
  it('starts with an empty closed state', () => {
    const store = new StatusStore({ factory: (url) => new FakeSocket(url) });

    expect(store.state).toEqual({
      connection: 'closed',
      reconnecting: false,
      status: null,
      learn: null,
      deviceLearn: null,
      network: null,
      activity: { devices: {}, entries: [] },
      configGeneration: null,
      backup: null,
      backupRestored: null,
      lastError: null,
    });
  });

  it('processes status snapshots and deduplicates/caps activity deltas', () => {
    const store = new StatusStore({ factory: (url) => new FakeSocket(url) });
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);

    store.receive(
      JSON.stringify({
        type: 'status',
        data: {
          connected: true,
          authenticated: true,
          session: 3,
          queue_depth: 0,
          rate: 25,
          screen_mode: false,
          frames_sent: 10,
          last_frame_types: [],
          reconnects: 0,
          last_error: null,
          generation: 1,
          busy: false,
          activity: {
            devices: { cherry: { rx: 1, tx: 0, last_rx: 100, last_tx: null } },
            log: [
              {
                seq: 1,
                ts: 100,
                direction: 'rx',
                device: 'cherry',
                kind: 'key',
                summary: 'first',
              },
            ],
          },
        },
      }),
    );

    expect(store.state.status?.session).toBe(3);
    expect(store.state.activity.entries).toHaveLength(1);
    expect(listener).toHaveBeenCalledTimes(1);

    const bulkEntries = Array.from({ length: LOG_LIMIT + 10 }, (_, idx) => ({
      seq: idx + 1,
      ts: 100 + idx,
      direction: 'rx' as const,
      device: 'cherry',
      kind: 'key',
      summary: `entry-${idx + 1}`,
    }));
    // Include duplicate seq=1 and seq=5 to verify deduplication and cap.
    store.receive(
      JSON.stringify({
        type: 'activity',
        data: {
          devices: { cherry: { rx: LOG_LIMIT + 10, tx: 0, last_rx: 300, last_tx: null } },
          entries: [bulkEntries[0], bulkEntries[4], ...bulkEntries],
        },
      }),
    );

    expect(store.state.activity.entries).toHaveLength(LOG_LIMIT);
    expect(store.state.activity.entries[0].seq).toBe(11);
    expect(store.state.activity.entries.at(-1)?.seq).toBe(LOG_LIMIT + 10);

    unsubscribe();
  });

  it('handles config, device_learn, backup and backup_restored events', () => {
    const store = new StatusStore({ factory: (url) => new FakeSocket(url) });

    store.receive(JSON.stringify({ type: 'config', data: { generation: 4 } }));
    expect(store.state.configGeneration).toBe(4);

    store.receive(
      JSON.stringify({
        type: 'device_learn',
        data: {
          active: true,
          device: 'midicraft',
          bank: 2,
          channel: 2,
          current: 'mc_fader_1',
          total: 4,
          index: 0,
        },
      }),
    );
    expect(store.state.deviceLearn).toMatchObject({
      active: true,
      device: 'midicraft',
      bank: 2,
      current: 'mc_fader_1',
    });

    store.receive(
      JSON.stringify({
        type: 'backup',
        data: {
          id: 'config-20260101-120000.toml',
          size: 512,
          modified: '2026-01-01T12:00:00',
          last_good: false,
        },
      }),
    );
    expect(store.state.backup?.id).toBe('config-20260101-120000.toml');

    store.receive(
      JSON.stringify({
        type: 'backup_restored',
        data: { id: 'config-20260101-120000.toml', generation: 9 },
      }),
    );
    expect(store.state.backupRestored).toEqual({
      id: 'config-20260101-120000.toml',
      generation: 9,
    });
    expect(store.state.configGeneration).toBe(9);
  });

  it('disconnects cleanly and clears cached snapshots on reset() or disconnect({ clear: true })', () => {
    FakeSocket.instances = [];
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
      reconnectBaseMs: 50,
    });

    store.connect();
    const socket = FakeSocket.instances.at(-1)!;
    socket.onopen?.();
    expect(store.state.connection).toBe('open');

    socket.onmessage?.({
      data: JSON.stringify({
        type: 'device_learn',
        data: { active: true, device: 'midicraft', bank: 1 },
      }),
    });
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'network',
        data: { pending: null, last_result: { status: 'confirmed', at: null, detail: null } },
      }),
    });
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'config',
        data: { generation: 5 },
      }),
    });

    // Plain disconnect keeps cached snapshots but closes the socket.
    store.disconnect();
    expect(socket.closed).toBe(true);
    expect(store.state.connection).toBe('closed');
    expect(store.state.deviceLearn?.active).toBe(true);

    // reset() clears all cached snapshots (e.g. on logout / session expiry).
    store.reset();
    expect(store.state).toEqual({
      connection: 'closed',
      reconnecting: false,
      status: null,
      learn: null,
      deviceLearn: null,
      network: null,
      activity: { devices: {}, entries: [] },
      configGeneration: null,
      backup: null,
      backupRestored: null,
      lastError: null,
    });
  });
});

import { render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

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
    controls: { logical: ['fix'], keys: [], notes: [], encoders: [], midi_encoders: [] },
  },
];

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
};

describe('StatusPage', () => {
  it('follows live status changes and shows the reconnect indicator', async () => {
    const store = new StatusStore({
      factory: (url) => new FakeSocket(url),
      reconnectBaseMs: 10,
    });
    render(StatusPage, {
      props: { store, devicesLoader: async () => devices },
    });

    store.connect();
    const socket = FakeSocket.last!;
    socket.emitOpen();
    socket.emitMessage({ type: 'status', data: status });

    await waitFor(() => {
      expect(screen.getByTestId('connection').textContent).toContain('verbunden');
    });
    expect(screen.getByTestId('ma2-state').textContent).toContain('Session 7');
    expect(screen.getByText('keyname')).toBeTruthy();
    expect(screen.getByText('42')).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText('cherry')).toBeTruthy();
    });
    expect(screen.getByText('erkannt')).toBeTruthy();

    socket.drop();

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain(
        'Verbindung unterbrochen',
      );
    });

    store.disconnect();
  });
});

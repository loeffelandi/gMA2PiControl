import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App.svelte';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const network = {
  backend: 'networkmanager',
  available: true,
  can_manage: true,
  interface: {
    name: 'eth0',
    type: 'ethernet',
    state: 'connected',
    connection: 'Wired connection 1',
  },
  mode: 'dhcp',
  current: {
    address: '192.168.10.50',
    subnet_mask: '255.255.255.0',
    gateway: '192.168.10.1',
    dns: ['192.168.10.1'],
  },
  pending: null,
  last_result: null,
  self_connection: false,
  error: null,
  warnings: [],
};

class QuietSocket {
  static instances: QuietSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor() {
    QuietSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

describe('App navigation', () => {
  afterEach(() => {
    QuietSocket.instances = [];
    vi.unstubAllGlobals();
  });

  it('opens the network page from the navigation', async () => {
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith('/api/auth/status')) {
        return json({ pin_enabled: false, authenticated: true });
      }
      if (url.endsWith('/api/version')) {
        return json({ api: '1', package: '0.1.0', ui: 'x' });
      }
      if (url.endsWith('/api/network')) {
        return json(network);
      }
      if (url.endsWith('/api/status')) {
        return json({ connected: false });
      }
      if (url.endsWith('/api/devices')) {
        return json({ devices: [] });
      }
      return json({});
    });
    vi.stubGlobal('fetch', fetchImpl);
    vi.stubGlobal('WebSocket', QuietSocket);

    render(App);

    await waitFor(() => {
      expect(screen.getByText('Netzwerk')).toBeTruthy();
    });
    await fireEvent.click(screen.getByText('Netzwerk'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Netzwerk' })).toBeTruthy();
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
  });

  it('renders a retry card when initial authStatus fails and recovers on retry', async () => {
    let online = false;
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith('/api/auth/status')) {
        if (!online) throw new Error('Dienst nicht erreichbar');
        return json({ pin_enabled: false, pin_set: false, authenticated: true });
      }
      if (url.endsWith('/api/version')) {
        return json({ api: '1', package: '0.1.0', ui: 'x' });
      }
      if (url.endsWith('/api/devices')) {
        return json({ devices: [] });
      }
      return json({});
    });
    vi.stubGlobal('fetch', fetchImpl);
    vi.stubGlobal('WebSocket', QuietSocket);

    render(App);

    await waitFor(() => {
      expect(screen.getByText('Verbindung zum Dienst fehlgeschlagen')).toBeTruthy();
    });
    expect(screen.queryByText('Netzwerk')).toBeNull();

    online = true;
    await fireEvent.click(screen.getByText('Erneut versuchen'));

    await waitFor(() => {
      expect(screen.getByText('Netzwerk')).toBeTruthy();
    });
  });

  it('transitions back to PinGate and disconnects WS when an API call returns 401', async () => {
    let sessionValid = true;
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith('/api/auth/status')) {
        return json({
          pin_enabled: true,
          pin_set: true,
          authenticated: sessionValid,
        });
      }
      if (url.endsWith('/api/version')) {
        return json({ api: '1', package: '0.1.0', ui: 'x' });
      }
      if (url.endsWith('/api/devices')) {
        return json({ devices: [] });
      }
      if (url.endsWith('/api/backups')) {
        return json({ error: 'pin_required', detail: 'PIN erforderlich' }, 401);
      }
      return json({});
    });
    vi.stubGlobal('fetch', fetchImpl);
    vi.stubGlobal('WebSocket', QuietSocket);

    render(App);

    await waitFor(() => {
      expect(screen.getByText('Backups')).toBeTruthy();
    });
    const socket = QuietSocket.instances.at(-1)!;
    expect(socket.closed).toBe(false);

    sessionValid = false;
    await fireEvent.click(screen.getByText('Backups'));

    await waitFor(() => {
      expect(
        screen.getByText('Bitte PIN eingeben, um die Oberfläche zu entsperren.'),
      ).toBeTruthy();
    });
    expect(socket.closed).toBe(true);
  });

  it('handles offline logout cleanly without unhandled rejections', async () => {
    let offline = false;
    const fetchImpl = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (offline) throw new Error('offline');
      if (url.endsWith('/api/auth/status')) {
        return json({ pin_enabled: true, pin_set: true, authenticated: true });
      }
      if (url.endsWith('/api/version')) {
        return json({ api: '1', package: '0.1.0', ui: 'x' });
      }
      if (url.endsWith('/api/devices')) {
        return json({ devices: [] });
      }
      return json({});
    });
    vi.stubGlobal('fetch', fetchImpl);
    vi.stubGlobal('WebSocket', QuietSocket);

    render(App);

    await waitFor(() => {
      expect(screen.getByText('Abmelden')).toBeTruthy();
    });

    offline = true;
    await fireEvent.click(screen.getByText('Abmelden'));

    await waitFor(() => {
      expect(
        screen.getByText('Bitte PIN eingeben, um die Oberfläche zu entsperren.'),
      ).toBeTruthy();
    });
  });
});

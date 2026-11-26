import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

import App from './App.svelte';

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
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
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close(): void {
    // no-op
  }
}

describe('App navigation', () => {
  afterEach(() => {
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
});

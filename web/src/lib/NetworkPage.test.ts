import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import {
  ApiError,
  type ApiClient,
  type NetworkStatus,
} from './api';
import NetworkPage from './NetworkPage.svelte';

function status(overrides: Partial<NetworkStatus> = {}): NetworkStatus {
  return {
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
    ...overrides,
  };
}

function fakeApi(initial: NetworkStatus = status()) {
  return {
    network: vi.fn(async () => initial),
    validateNetwork: vi.fn(async () => ({
      valid: true,
      target_url: 'http://192.168.10.60:8080/',
      warnings: [],
    })),
    applyNetwork: vi.fn(async () => ({
      pending: {
        mode: 'static' as const,
        address: '192.168.10.60',
        subnet_mask: '255.255.255.0',
        phase: 'activating',
        started_at: new Date().toISOString(),
        deadline: null,
        target_url: 'http://192.168.10.60:8080/',
        error: null,
      },
      target_url: 'http://192.168.10.60:8080/',
    })),
    confirmNetwork: vi.fn(async () =>
      status({
        mode: 'static',
        current: {
          address: '192.168.10.60',
          subnet_mask: '255.255.255.0',
          gateway: '192.168.10.1',
          dns: ['192.168.10.1'],
        },
      }),
    ),
    rollbackNetwork: vi.fn(async () =>
      status({
        last_result: {
          status: 'rolled_back',
          at: new Date().toISOString(),
          detail: 'Manueller Rollback',
        },
      }),
    ),
    emergencyNetwork: vi.fn(async () =>
      status({
        current: {
          address: '192.168.178.254',
          subnet_mask: '255.255.255.0',
          gateway: null,
          dns: [],
        },
        last_result: {
          status: 'fallback',
          at: new Date().toISOString(),
          detail: 'Notfall-Adresse 192.168.178.254/24 aktiv',
        },
      }),
    ),
  } as unknown as ApiClient;
}

describe('NetworkPage', () => {
  it('shows the DHCP address and disables static fields in DHCP mode', async () => {
    const api = fakeApi();
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
    expect((screen.getByLabelText('IPv4-Adresse') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Subnetzmaske') as HTMLInputElement).disabled).toBe(true);

    await fireEvent.click(screen.getByLabelText('Statisch'));
    expect((screen.getByLabelText('IPv4-Adresse') as HTMLInputElement).disabled).toBe(false);
    expect((screen.getByLabelText('Subnetzmaske') as HTMLInputElement).disabled).toBe(false);
  });

  it('shows a field error returned by the API', async () => {
    const api = fakeApi();
    (api.validateNetwork as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(
        422,
        'validation_error',
        'keine gültige zusammenhängende Maske',
        'subnet_mask',
      ),
    );
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
    await fireEvent.click(screen.getByLabelText('Statisch'));
    await fireEvent.input(screen.getByLabelText('Subnetzmaske'), {
      target: { value: '255.255.0.255' },
    });
    await fireEvent.click(screen.getByText('Anwenden …'));

    await waitFor(() => {
      expect(screen.getAllByText('keine gültige zusammenhängende Maske').length).toBeGreaterThan(0);
    });
    expect(api.applyNetwork).not.toHaveBeenCalled();
  });

  it('requires the confirmation dialog before applying', async () => {
    const api = fakeApi();
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
    await fireEvent.click(screen.getByLabelText('Statisch'));
    await fireEvent.input(screen.getByLabelText('IPv4-Adresse'), {
      target: { value: '192.168.10.60' },
    });
    await fireEvent.click(screen.getByText('Anwenden …'));

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });
    expect(screen.getByText(/Ziel:/)).toBeTruthy();
    expect(api.applyNetwork).not.toHaveBeenCalled();

    await fireEvent.click(screen.getByText('Jetzt anwenden'));
    await waitFor(() => {
      expect(api.applyNetwork).toHaveBeenCalledWith(
        expect.objectContaining({ mode: 'static', address: '192.168.10.60' }),
      );
    });
    expect(screen.getByText(/Aktivierung läuft/)).toBeTruthy();
  });

  it('shows the pending countdown and confirms the change', async () => {
    const api = fakeApi();
    const deadline = new Date(Date.now() + 60_000).toISOString();
    (api.applyNetwork as ReturnType<typeof vi.fn>).mockResolvedValue({
      pending: {
        mode: 'static',
        address: '192.168.10.60',
        subnet_mask: '255.255.255.0',
        phase: 'awaiting_confirmation',
        started_at: new Date().toISOString(),
        deadline,
        target_url: 'http://192.168.10.60:8080/',
        error: null,
      },
      target_url: 'http://192.168.10.60:8080/',
    });
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
    await fireEvent.click(screen.getByLabelText('Statisch'));
    await fireEvent.input(screen.getByLabelText('IPv4-Adresse'), {
      target: { value: '192.168.10.60' },
    });
    await fireEvent.click(screen.getByText('Anwenden …'));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });
    await fireEvent.click(screen.getByText('Jetzt anwenden'));

    await waitFor(() => {
      expect(screen.getByText(/Warte auf Bestätigung/)).toBeTruthy();
    });
    expect(screen.getByText(/1:00/)).toBeTruthy();
    await fireEvent.click(screen.getByText('Ich bin verbunden – bestätigen'));

    await waitFor(() => {
      expect(api.confirmNetwork).toHaveBeenCalled();
    });
    expect(screen.getByRole('status').textContent).toContain('gespeichert');
  });

  it('rolls back and shows the last result', async () => {
    const api = fakeApi();
    (api.applyNetwork as ReturnType<typeof vi.fn>).mockResolvedValue({
      pending: {
        mode: 'static',
        address: '192.168.10.60',
        subnet_mask: '255.255.255.0',
        phase: 'awaiting_confirmation',
        started_at: new Date().toISOString(),
        deadline: new Date(Date.now() + 60_000).toISOString(),
        target_url: 'http://192.168.10.60:8080/',
        error: null,
      },
      target_url: 'http://192.168.10.60:8080/',
    });
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
    await fireEvent.click(screen.getByLabelText('Statisch'));
    await fireEvent.input(screen.getByLabelText('IPv4-Adresse'), {
      target: { value: '192.168.10.60' },
    });
    await fireEvent.click(screen.getByText('Anwenden …'));
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });
    await fireEvent.click(screen.getByText('Jetzt anwenden'));
    await waitFor(() => {
      expect(screen.getByText('Zurückrollen')).toBeTruthy();
    });
    await fireEvent.click(screen.getByText('Zurückrollen'));

    await waitFor(() => {
      expect(api.rollbackNetwork).toHaveBeenCalled();
    });
    expect(screen.getByText(/zurückgerollt/)).toBeTruthy();
  });

  it('requires confirmation before activating the emergency address', async () => {
    const api = fakeApi();
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('192.168.10.50')).toBeTruthy();
    });
    await fireEvent.click(screen.getByText('Notfall-IP …'));
    expect(screen.getByRole('dialog').textContent).toContain('192.168.178.254/24');
    expect(api.emergencyNetwork).not.toHaveBeenCalled();

    await fireEvent.click(screen.getByText('Ja, Notfall-IP aktivieren'));
    await waitFor(() => {
      expect(api.emergencyNetwork).toHaveBeenCalled();
    });
    expect(screen.getByText(/Notfall-Adresse 192.168.178.254\/24 ist aktiv/)).toBeTruthy();
  });

  it('warns when the change affects the current browser connection', async () => {
    const api = fakeApi(status({ self_connection: true }));
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain(
        'über die du gerade verbunden bist',
      );
    });
  });

  it('shows a read-only message when the backend is unavailable', async () => {
    const api = fakeApi(
      status({
        available: false,
        can_manage: false,
        interface: null,
        error: 'NetworkManager ist nicht verfügbar',
      }),
    );
    render(NetworkPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain(
        'NetworkManager ist nicht verfügbar',
      );
    });
    expect(screen.queryByText('Anwenden …')).toBeNull();
  });
});

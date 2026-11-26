import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient } from './api';
import Ma2Page from './Ma2Page.svelte';

function fakeApi() {
  return {
    config: vi.fn(async () => ({
      ma2: {
        host: '10.0.0.5',
        port: 80,
        path: '/?ma=1',
        username: 'svt',
        password_set: true,
      },
    })),
    testConnection: vi.fn(async () => ({
      session: 7,
      username: 'svt',
      target: 'ws://10.0.0.5',
      reused: false,
    })),
    updateConfig: vi.fn(async () => ({ generation: 1 })),
  } as unknown as ApiClient;
}

describe('Ma2Page', () => {
  it('never shows the password and sends it write-only', async () => {
    const api = fakeApi();
    render(Ma2Page, { props: { api } });

    await waitFor(() => {
      expect((screen.getByLabelText('Host') as HTMLInputElement).value).toBe(
        '10.0.0.5',
      );
    });

    const password = screen.getByLabelText('Passwort') as HTMLInputElement;
    expect(password.type).toBe('password');
    expect(password.value).toBe('');
    expect(screen.getByText(/Aktuell ist ein Passwort gesetzt/)).toBeTruthy();

    await fireEvent.input(password, { target: { value: 's3cret' } });
    await fireEvent.click(screen.getByText('Testen'));

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain(
        'Verbindung erfolgreich',
      );
    });
    expect(api.testConnection).toHaveBeenCalledWith(
      expect.objectContaining({ password: 's3cret', host: '10.0.0.5' }),
    );
    expect(document.body.textContent).not.toContain('s3cret');

    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain(
        'Zugangsdaten gespeichert',
      );
    });
    expect(api.updateConfig).toHaveBeenCalledWith({
      ma2: expect.objectContaining({ password: 's3cret' }),
    });
    expect(password.value).toBe('');
    expect(document.body.textContent).not.toContain('s3cret');
  });

  it('shows a validation error from the API', async () => {
    const api = fakeApi();
    (api.updateConfig as ReturnType<typeof vi.fn>).mockRejectedValue(
      Object.assign(new Error('validation_error: ma2.port'), {
        name: 'ApiError',
        detail: 'ma2.port: muss zwischen 1 und 65535 liegen',
      }),
    );
    render(Ma2Page, { props: { api } });

    await waitFor(() => {
      expect((screen.getByLabelText('Host') as HTMLInputElement).value).toBe(
        '10.0.0.5',
      );
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('ma2.port');
    });
  });
});

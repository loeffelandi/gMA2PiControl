import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient } from './api';
import PinGate from './PinGate.svelte';

function fakeApi(login: () => Promise<{ ok: boolean }>): ApiClient {
  return { login: vi.fn(login) } as unknown as ApiClient;
}

describe('PinGate', () => {
  it('unlocks with a valid PIN and keeps the input masked', async () => {
    const api = fakeApi(async () => ({ ok: true }));
    const unlocked = vi.fn();
    render(PinGate, { props: { api, onUnlocked: unlocked } });

    const input = screen.getByLabelText('PIN') as HTMLInputElement;
    expect(input.type).toBe('password');
    await fireEvent.input(input, { target: { value: '123456' } });
    await fireEvent.click(screen.getByText('Entsperren'));

    await waitFor(() => {
      expect(unlocked).toHaveBeenCalledOnce();
    });
    expect(api.login).toHaveBeenCalledWith('123456');
    expect(input.value).toBe('');
  });

  it('shows an error for a wrong PIN', async () => {
    const api = fakeApi(async () => {
      throw new ApiError(401, 'pin_invalid', 'PIN falsch');
    });
    render(PinGate, { props: { api, onUnlocked: vi.fn() } });

    await fireEvent.input(screen.getByLabelText('PIN'), {
      target: { value: '000000' },
    });
    await fireEvent.click(screen.getByText('Entsperren'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('PIN falsch');
    });
  });

  it('displays the lockout message on 429 pin_locked with role="alert"', async () => {
    const api = fakeApi(async () => {
      throw new ApiError(
        429,
        'pin_locked',
        'Zu viele Fehlversuche – bitte 15 s warten',
        undefined,
        15,
      );
    });
    const unlocked = vi.fn();
    render(PinGate, { props: { api, onUnlocked: unlocked } });

    const input = screen.getByLabelText('PIN') as HTMLInputElement;
    await fireEvent.input(input, { target: { value: '000000' } });
    await fireEvent.click(screen.getByText('Entsperren'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain(
        'Zu viele Fehlversuche – bitte 15 s warten',
      );
    });
    expect(unlocked).not.toHaveBeenCalled();
    expect(input.value).toBe('');
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient } from './api';
import AdvancedPage from './AdvancedPage.svelte';

function fakeApi(power: Record<string, unknown> | undefined = undefined) {
  return {
    config: vi.fn(async () => ({
      rate_limit: { messages_per_second: 25, burst: 10 },
      logging: { level: 'INFO' },
      web: { pin_enabled: true, pin_set: true },
      ...(power ? { power } : {}),
    })),
    updateConfig: vi.fn(async () => ({ generation: 1 })),
    shutdown: vi.fn(async () => ({ state: 'shutting_down' })),
  } as unknown as ApiClient;
}

describe('AdvancedPage', () => {
  it('saves rate and logging settings', async () => {
    const api = fakeApi();
    render(AdvancedPage, { props: { api } });

    await waitFor(() => {
      expect((screen.getByLabelText('Frames pro Sekunde') as HTMLInputElement).value).toBe(
        '25',
      );
    });
    await fireEvent.input(screen.getByLabelText('Frames pro Sekunde'), {
      target: { value: '40' },
    });
    await fireEvent.click(screen.getByText('Einstellungen speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        rate_limit: { messages_per_second: 40, burst: 10 },
        logging: { level: 'INFO' },
        web: { pin_enabled: true },
      });
    });
  });

  it('shows PIN and rate/logging settings', async () => {
    const api = fakeApi();
    render(AdvancedPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('PIN-Sperre')).toBeTruthy();
    });
    expect(screen.getByText('Rate & Logging')).toBeTruthy();
    expect(screen.queryByText('Konfigurations-Backups')).toBeNull();
  });

  it('exposes rate bounds 5..40, CRITICAL log level and notifies onAuthChange', async () => {
    const api = fakeApi();
    const onAuthChange = vi.fn();
    render(AdvancedPage, { props: { api, onAuthChange } });

    await waitFor(() => {
      expect(screen.getByLabelText('Frames pro Sekunde')).toBeTruthy();
    });

    const rateInput = screen.getByLabelText('Frames pro Sekunde') as HTMLInputElement;
    expect(rateInput.min).toBe('5');
    expect(rateInput.max).toBe('40');

    const levelSelect = screen.getByLabelText('Log-Level') as HTMLSelectElement;
    await fireEvent.change(levelSelect, { target: { value: 'CRITICAL' } });
    await fireEvent.click(screen.getByText('Einstellungen speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith(
        expect.objectContaining({ logging: { level: 'CRITICAL' } }),
      );
    });
    expect(onAuthChange).toHaveBeenCalledOnce();
  });

  it('asks twice before shutting the Pi down', async () => {
    const api = fakeApi();
    render(AdvancedPage, { props: { api } });

    await fireEvent.click(await screen.findByText('Pi herunterfahren'));
    expect(api.shutdown).not.toHaveBeenCalled();
    expect(screen.getByText(/Pi wirklich herunterfahren\?/)).toBeTruthy();

    // Backing out keeps the daemon untouched.
    await fireEvent.click(screen.getByText('Abbrechen'));
    expect(screen.getByText('Pi herunterfahren')).toBeTruthy();

    await fireEvent.click(screen.getByText('Pi herunterfahren'));
    await fireEvent.click(screen.getByText('Ja, herunterfahren'));
    await waitFor(() => {
      expect(screen.getByText(/Der Pi fährt herunter/)).toBeTruthy();
    });
    expect(api.shutdown).toHaveBeenCalledOnce();
    expect(screen.queryByText('Pi herunterfahren')).toBeNull();
  });

  it('shows the daemon error when the shutdown is refused', async () => {
    const api = fakeApi();
    (api.shutdown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError(403, 'power_disabled', 'Herunterfahren ist in [power] abgeschaltet'),
    );
    render(AdvancedPage, { props: { api } });

    await fireEvent.click(await screen.findByText('Pi herunterfahren'));
    await fireEvent.click(screen.getByText('Ja, herunterfahren'));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('abgeschaltet');
    });
  });

  it('describes the Cherry chord from the configuration', async () => {
    const api = fakeApi({
      enabled: true,
      combo: true,
      hold_controls: ['ma', 'off'],
      confirm_control: 'please_big',
      confirm_presses: 2,
    });
    render(AdvancedPage, { props: { api } });

    await waitFor(() => {
      expect(
        screen.getByText(/MA \+ Off gedrückt halten und dabei 2× Please drücken/),
      ).toBeTruthy();
    });
  });

  it('disables the button when [power] is switched off', async () => {
    const api = fakeApi({ enabled: false, combo: false });
    render(AdvancedPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText('Herunterfahren ist in [power] abgeschaltet.')).toBeTruthy();
    });
    expect((screen.getByText('Pi herunterfahren') as HTMLButtonElement).disabled).toBe(true);
  });
});

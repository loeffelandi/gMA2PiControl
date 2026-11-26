import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient } from './api';
import AdvancedPage from './AdvancedPage.svelte';

function fakeApi() {
  return {
    config: vi.fn(async () => ({
      rate_limit: { messages_per_second: 25, burst: 10 },
      logging: { level: 'INFO' },
      web: { pin_enabled: true, pin_set: true },
    })),
    updateConfig: vi.fn(async () => ({ generation: 1 })),
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

  it('shows the LAN port hint and PIN settings', async () => {
    const api = fakeApi();
    render(AdvancedPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText(/Dienstneustart wirksam/)).toBeTruthy();
    });
    expect(screen.getByText('PIN-Sperre')).toBeTruthy();
    expect(screen.getByText('Rate & Logging')).toBeTruthy();
    expect(screen.queryByText('Konfigurations-Backups')).toBeNull();
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient } from './api';
import BackupsPage from './BackupsPage.svelte';

const backups = [
  {
    id: 'config-20260101-120000.toml',
    size: 1024,
    modified: '2026-01-01T12:00:00',
    last_good: false,
  },
];

function fakeApi() {
  return {
    backups: vi.fn(async () => backups),
    config: vi.fn(async () => ({
      rate_limit: { messages_per_second: 25, burst: 10 },
      logging: { level: 'INFO' },
    })),
    createBackup: vi.fn(async () => backups[0]),
    restoreBackup: vi.fn(async () => ({ ok: true })),
    updateConfig: vi.fn(async () => ({ generation: 1 })),
  } as unknown as ApiClient;
}

describe('BackupsPage', () => {
  it('requires a confirmation before restoring', async () => {
    const api = fakeApi();
    render(BackupsPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText(backups[0].id)).toBeTruthy();
    });

    await fireEvent.click(screen.getByText('Wiederherstellen'));
    expect(api.restoreBackup).not.toHaveBeenCalled();
    expect(screen.getByTestId('restore-confirm')).toBeTruthy();

    await fireEvent.click(screen.getByText('Ja, wiederherstellen'));

    await waitFor(() => {
      expect(api.restoreBackup).toHaveBeenCalledWith(backups[0].id);
    });
    expect(screen.getByRole('status').textContent).toContain('wiederhergestellt');
    expect(screen.queryByTestId('restore-confirm')).toBeNull();
  });

  it('shows a restore error and keeps the confirmation', async () => {
    const api = fakeApi();
    (api.restoreBackup as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(422, 'invalid_backup', 'Backup ist beschädigt'),
    );
    render(BackupsPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText(backups[0].id)).toBeTruthy();
    });
    await fireEvent.click(screen.getByText('Wiederherstellen'));
    await fireEvent.click(screen.getByText('Ja, wiederherstellen'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('beschädigt');
    });
    expect(screen.getByTestId('restore-confirm')).toBeTruthy();
  });

  it('saves rate and logging settings', async () => {
    const api = fakeApi();
    render(BackupsPage, { props: { api } });

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
      });
    });
  });
});

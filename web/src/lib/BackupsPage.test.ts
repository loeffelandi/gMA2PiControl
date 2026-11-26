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
    createBackup: vi.fn(async () => backups[0]),
    restoreBackup: vi.fn(async () => ({ ok: true })),
  } as unknown as ApiClient;
}

describe('BackupsPage', () => {
  it('requires a confirmation before restoring', async () => {
    const api = fakeApi();
    const onAuthChange = vi.fn();
    render(BackupsPage, { props: { api, onAuthChange } });

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
    expect(onAuthChange).toHaveBeenCalledOnce();
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

  it('does not render the advanced settings', async () => {
    const api = fakeApi();
    render(BackupsPage, { props: { api } });

    await waitFor(() => {
      expect(screen.getByText(backups[0].id)).toBeTruthy();
    });
    expect(screen.queryByText('PIN-Sperre')).toBeNull();
    expect(screen.queryByText('Rate & Logging')).toBeNull();
  });
});

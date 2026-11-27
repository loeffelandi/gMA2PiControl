import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import AssignmentDialog from './AssignmentDialog.svelte';
import ConflictNotice from './ConflictNotice.svelte';
import { ConfigStore } from './configStore.svelte';
import { controlsOf } from './deviceControls';
import { baseConfig, fakeDaemon, midicraft } from './testing';

async function twoStores() {
  const daemon = fakeDaemon(baseConfig(), [midicraft]);
  const first = new ConfigStore(daemon.api);
  const second = new ConfigStore(daemon.api);
  await Promise.all([first.load(), second.load()]);
  return { daemon, first, second };
}

describe('ConflictNotice', () => {
  it('shows nothing without a conflict', async () => {
    const { first } = await twoStores();
    render(ConflictNotice, { props: { store: first } });
    expect(screen.queryByTestId('config-conflict')).toBeNull();
  });

  it('reports a stale draft, overwrites nothing and reloads on request', async () => {
    const { daemon, first, second } = await twoStores();
    render(ConflictNotice, { props: { store: first } });

    await second.save({ mapping: { keys: { mc_click_1: { hardkey: 'FIRST' } } } });
    await expect(
      first.save({ mapping: { keys: { mc_click_1: { hardkey: 'STALE' } } } }),
    ).rejects.toMatchObject({ stale: true });

    expect(await screen.findByTestId('config-conflict')).toBeTruthy();
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ hardkey: 'FIRST' });

    await fireEvent.click(screen.getByText('Neu laden'));
    await waitFor(() => expect(screen.queryByTestId('config-conflict')).toBeNull());
    expect(first.config?.mapping.keys.mc_click_1).toEqual({ hardkey: 'FIRST' });
    expect(first.discardEpoch).toBe(0);

    await first.save({ mapping: { keys: { mc_click_1: { hardkey: 'SECOND' } } } });
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ hardkey: 'SECOND' });
  });

  it('discards the draft and closes an open dialog', async () => {
    const { daemon, first, second } = await twoStores();
    const onClose = vi.fn();
    render(AssignmentDialog, {
      props: {
        store: first,
        controls: controlsOf(midicraft, 1).filter((entry) => entry.id === 'mc_click_1'),
        onClose,
      },
    });
    await second.save({ mapping: { keys: { other: { hardkey: 'X' } } } });
    await fireEvent.click(screen.getByText('Speichern'));
    await screen.findByTestId('config-conflict');
    expect(daemon.config().mapping.playbacks).toEqual({});
    expect(onClose).not.toHaveBeenCalled();

    await fireEvent.click(screen.getByText('Verwerfen'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(daemon.config().mapping.playbacks).toEqual({});
  });
});

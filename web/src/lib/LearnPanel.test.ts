import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import { ApiError } from './api';
import LearnPanel from './LearnPanel.svelte';
import { fakeStatus, loadedStore } from './testing';

const session = {
  active: true,
  device: 'midicraft',
  bank: 2,
  channel: 2,
  current: 'mc_fader_1',
  total: 3,
  index: 0,
  captured: [],
  paused: false,
  error: null,
};

async function setup() {
  const live = fakeStatus();
  const { store, daemon } = await loadedStore(undefined, { status: live.status });
  return { store, daemon, ...live };
}

describe('LearnPanel', () => {
  it('starts a session for the selected device and bank', async () => {
    const { store, daemon } = await setup();
    render(LearnPanel, { props: { store, device: 'midicraft', bank: 2 } });
    await fireEvent.click(screen.getByText('Learn starten'));
    expect(daemon.api.startDeviceLearn).toHaveBeenCalledWith('midicraft', 2);
  });

  it('does not poll: progress arrives through device_learn events', async () => {
    vi.useFakeTimers();
    try {
      const { store, daemon, push } = await setup();
      render(LearnPanel, { props: { store, device: 'midicraft', bank: 2 } });
      await vi.advanceTimersByTimeAsync(3000);
      // One read when the panel opens, none afterwards.
      expect(daemon.api.deviceLearnStatus).toHaveBeenCalledTimes(1);

      push('device_learn', session);
      await vi.advanceTimersByTimeAsync(0);
      expect(screen.getByText('mc_fader_1')).toBeTruthy();
      await vi.advanceTimersByTimeAsync(3000);
      expect(daemon.api.deviceLearnStatus).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows progress from an event and supports skipping', async () => {
    const { store, daemon, push } = await setup();
    render(LearnPanel, { props: { store, device: 'midicraft', bank: 2 } });
    push('device_learn', session);
    await waitFor(() => expect(screen.getByText('mc_fader_1')).toBeTruthy());
    await fireEvent.click(screen.getByText('Überspringen'));
    expect(daemon.api.skipDeviceLearn).toHaveBeenCalled();
  });

  it('disables Überspringen when there is no current control left', async () => {
    const { store, push } = await setup();
    render(LearnPanel, { props: { store, device: 'midicraft', bank: 2 } });
    push('device_learn', { ...session, current: null, index: 3 });
    await waitFor(() => expect(screen.getByText('Überspringen')).toBeTruthy());
    expect((screen.getByText('Überspringen') as HTMLButtonElement).disabled).toBe(true);
  });

  it('always offers Abbrechen when another bank has an active session', async () => {
    const onDone = vi.fn();
    const { store, daemon, push } = await setup();
    render(LearnPanel, { props: { store, device: 'midicraft', bank: 3, onDone } });
    push('device_learn', session);
    await waitFor(() => expect(screen.getByText(/Bank 2/)).toBeTruthy());
    await fireEvent.click(screen.getByText('Abbrechen'));
    await waitFor(() => expect(daemon.api.cancelDeviceLearn).toHaveBeenCalledOnce());
    expect(onDone).toHaveBeenCalledOnce();
  });

  it('cancels a session started by this panel on destroy even if the bank changed', async () => {
    const { store, daemon } = await setup();
    vi.mocked(daemon.api.startDeviceLearn).mockResolvedValue(session);
    const { rerender, unmount } = render(LearnPanel, {
      props: { store, device: 'midicraft', bank: 2 },
    });
    await fireEvent.click(screen.getByText('Learn starten'));
    await waitFor(() => expect(daemon.api.startDeviceLearn).toHaveBeenCalledWith('midicraft', 2));

    await rerender({ store, device: 'midicraft', bank: 3 });
    await waitFor(() => expect(screen.getByText(/Anlernen · midicraft · Bank 3/)).toBeTruthy());

    unmount();
    expect(daemon.api.cancelDeviceLearn).toHaveBeenCalledOnce();
  });

  it('shows ApiError detail and becomes operable again when the session ends', async () => {
    const { store, daemon, push } = await setup();
    vi.mocked(daemon.api.startDeviceLearn).mockResolvedValue(session);
    vi.mocked(daemon.api.skipDeviceLearn).mockRejectedValue(
      new ApiError(409, 'conflict', 'Sitzung bereits beendet'),
    );
    const { unmount } = render(LearnPanel, { props: { store, device: 'midicraft', bank: 2 } });
    await fireEvent.click(screen.getByText('Learn starten'));
    await waitFor(() => expect(screen.getByText('Überspringen')).toBeTruthy());
    await fireEvent.click(screen.getByText('Überspringen'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Sitzung bereits beendet'));

    // Timeout on the daemon: the event resets the panel.
    push('device_learn', { active: false, abandoned: true });
    await waitFor(() => expect(screen.getByText('Learn starten')).toBeTruthy());
    expect((screen.getByText('Learn starten') as HTMLButtonElement).disabled).toBe(false);
    unmount();
    expect(daemon.api.cancelDeviceLearn).not.toHaveBeenCalled();
  });

  it('rejects a second start while the control detection runs', async () => {
    const { store, push } = await setup();
    render(LearnPanel, { props: { store, device: 'midicraft', bank: 2 } });
    push('learn', { kind: 'key', status: 'active', control: null, device: 'midicraft' });
    await waitFor(() =>
      expect((screen.getByText('Learn starten') as HTMLButtonElement).disabled).toBe(true),
    );
  });
});

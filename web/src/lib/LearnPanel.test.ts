import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import LearnPanel from './LearnPanel.svelte';
import type { ApiClient } from './api';

function fakeApi(overrides: Record<string, unknown>) {
  return {
    deviceLearnStatus: vi.fn().mockResolvedValue({ active: false }),
    startDeviceLearn: vi.fn(),
    skipDeviceLearn: vi.fn(),
    cancelDeviceLearn: vi.fn().mockResolvedValue({ cancelled: true }),
    finishDeviceLearn: vi.fn().mockResolvedValue({ saved: true }),
    ...overrides,
  } as unknown as ApiClient;
}

describe('LearnPanel', () => {
  it('starts a session for the selected device and bank', async () => {
    const api = fakeApi({
      startDeviceLearn: vi.fn().mockResolvedValue({ active: true }),
    });
    render(LearnPanel, { props: { api, device: 'midicraft', bank: 2 } });
    await waitFor(() => expect(screen.getByText('Learn starten')).toBeTruthy());
    await fireEvent.click(screen.getByText('Learn starten'));
    expect(api.startDeviceLearn).toHaveBeenCalledWith('midicraft', 2);
  });

  it('shows progress and supports skipping', async () => {
    const api = fakeApi({
      deviceLearnStatus: vi.fn().mockResolvedValue({
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
      }),
      skipDeviceLearn: vi.fn().mockResolvedValue({}),
    });
    render(LearnPanel, { props: { api, device: 'midicraft', bank: 2 } });
    await waitFor(() => expect(screen.getByText('mc_fader_1')).toBeTruthy());
    await fireEvent.click(screen.getByText('Überspringen'));
    expect(api.skipDeviceLearn).toHaveBeenCalled();
  });

  it('disables Überspringen when there is no current control left', async () => {
    const api = fakeApi({
      deviceLearnStatus: vi.fn().mockResolvedValue({
        active: true,
        device: 'midicraft',
        bank: 2,
        channel: 2,
        current: null,
        total: 3,
        index: 3,
        captured: [],
        paused: false,
        error: null,
      }),
    });
    render(LearnPanel, { props: { api, device: 'midicraft', bank: 2 } });
    await waitFor(() => expect(screen.getByText('Überspringen')).toBeTruthy());
    expect((screen.getByText('Überspringen') as HTMLButtonElement).disabled).toBe(true);
  });

  it('reports the active status to the parent', async () => {
    const onStatus = vi.fn();
    const api = fakeApi({
      deviceLearnStatus: vi.fn().mockResolvedValue({
        active: true,
        device: 'midicraft',
        bank: 2,
        channel: 2,
        current: 'mc_row1_1',
        total: 2,
        index: 0,
        captured: [],
        paused: false,
        error: null,
      }),
    });

    render(LearnPanel, { props: { api, device: 'midicraft', bank: 2, onStatus } });

    await waitFor(() =>
      expect(onStatus).toHaveBeenCalledWith(
        expect.objectContaining({ current: 'mc_row1_1' }),
      ),
    );
  });

  it('always offers Abbrechen when another bank has an active session', async () => {
    const onDone = vi.fn();
    const api = fakeApi({
      deviceLearnStatus: vi.fn().mockResolvedValue({
        active: true,
        device: 'midicraft',
        bank: 1,
        channel: 1,
        current: 'mc_row1_1',
        total: 2,
        index: 0,
        captured: [],
        paused: false,
        error: null,
      }),
    });

    render(LearnPanel, { props: { api, device: 'midicraft', bank: 2, onDone } });

    await waitFor(() => {
      expect(screen.getByText(/Bank 1/)).toBeTruthy();
      expect(screen.getByText('Abbrechen')).toBeTruthy();
    });

    await fireEvent.click(screen.getByText('Abbrechen'));

    await waitFor(() => {
      expect(api.cancelDeviceLearn).toHaveBeenCalledOnce();
    });
    expect(onDone).toHaveBeenCalledOnce();
  });

  it('cancels a session started by this panel on destroy even if bank changed', async () => {
    let activeSession = false;
    const api = fakeApi({
      deviceLearnStatus: vi.fn(async () =>
        activeSession
          ? {
              active: true,
              device: 'midicraft',
              bank: 2,
              channel: 2,
              current: 'mc_fader_1',
              total: 2,
              index: 0,
              captured: [],
              paused: false,
              error: null,
            }
          : { active: false },
      ),
      startDeviceLearn: vi.fn(async () => {
        activeSession = true;
        return {
          active: true,
          device: 'midicraft',
          bank: 2,
          channel: 2,
          current: 'mc_fader_1',
          total: 2,
          index: 0,
        };
      }),
    });

    const { rerender, unmount } = render(LearnPanel, {
      props: { api, device: 'midicraft', bank: 2 },
    });
    await waitFor(() => expect(screen.getByText('Learn starten')).toBeTruthy());
    await fireEvent.click(screen.getByText('Learn starten'));
    await waitFor(() => expect(api.startDeviceLearn).toHaveBeenCalledWith('midicraft', 2));

    // Switch to another bank so activeHere becomes false before unmounting.
    await rerender({ api, device: 'midicraft', bank: 3 });
    await waitFor(() => expect(screen.getByText(/Anlernen · midicraft · Bank 3/)).toBeTruthy());

    unmount();
    expect(api.cancelDeviceLearn).toHaveBeenCalledOnce();
  });
});

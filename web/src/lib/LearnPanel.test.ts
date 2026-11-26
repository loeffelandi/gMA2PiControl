import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import LearnPanel from './LearnPanel.svelte';
import type { ApiClient } from './api';

function fakeApi(overrides: Record<string, unknown>) {
  return {
    deviceLearnStatus: vi.fn().mockResolvedValue({ active: false }),
    startDeviceLearn: vi.fn(),
    skipDeviceLearn: vi.fn(),
    cancelDeviceLearn: vi.fn().mockResolvedValue({}),
    finishDeviceLearn: vi.fn(),
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
});

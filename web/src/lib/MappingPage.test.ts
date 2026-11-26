import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type ApiClient, type DeviceEntry, type LearnResult } from './api';
import MappingPage from './MappingPage.svelte';
import type { StatusStore } from './status';

const devices = [
  {
    name: 'cherry',
    backend: 'evdev',
    profile: 'cherry-g86',
    vendor_id: 0x046a,
    product_id: 0,
    vendor_product: '046a:0000',
    name_contains: 'Cherry',
    detected: { path: '/dev/input/event0' },
    controls: {
      keys: [
        { code: 'KEY_HOME', control: 'fix' },
        { code: 'KEY_HANGUEL', control: 'store_big' },
        { code: 'KEY_F1', control: 'fine_mod' },
      ],
      notes: [],
      encoders: [],
      midi_encoders: [],
      values: [],
      inventory: [
        { id: 'fix', kind: 'button', label: null },
        { id: 'store_big', kind: 'button', label: null },
        { id: 'fine_mod', kind: 'button', label: null },
      ],
      banks: [],
      logical: ['fine_mod', 'fix', 'store_big'],
    },
  },
  {
    name: 'asl',
    backend: 'midi',
    profile: 'asl-mk2-e4b3',
    vendor_id: 0x04d8,
    product_id: 0xe817,
    vendor_product: '04d8:e817',
    name_contains: 'ASL MK2',
    detected: { path: '/dev/snd/midiC1D0' },
    controls: {
      keys: [],
      notes: [{ note: 5, control: 'asl_click_1' }],
      encoders: [],
      midi_encoders: [
        { id: 1, control: 'encoder.1', note: 1 },
        { id: 2, control: 'encoder.2', note: 2 },
        { id: 3, control: 'encoder.3', note: 3 },
        { id: 4, control: 'encoder.4', note: 4 },
      ],
      values: [],
      inventory: [
        { id: 'asl_click_1', kind: 'button', label: null },
        { id: 'encoder.1', kind: 'relative-encoder', label: null },
        { id: 'encoder.2', kind: 'relative-encoder', label: null },
        { id: 'encoder.3', kind: 'relative-encoder', label: null },
        { id: 'encoder.4', kind: 'relative-encoder', label: null },
      ],
      banks: [],
      logical: ['asl_click_1', 'encoder.1', 'encoder.2', 'encoder.3', 'encoder.4'],
    },
  },
  {
    name: 'midicraft',
    backend: 'midi',
    profile: 'midicraft-enc',
    vendor_id: 0x04d8,
    product_id: 0xe78c,
    vendor_product: '04d8:e78c',
    name_contains: 'MIDICRAFT ENC',
    detected: { path: '/dev/snd/midiC4D0' },
    controls: {
      keys: [],
      notes: [],
      encoders: [],
      midi_encoders: [],
      values: [],
      inventory: [
        { id: 'mc_click_1', kind: 'button', label: 'B1' },
        { id: 'mc_fader_1', kind: 'fader', label: 'F1' },
        { id: 'mc_encoder_1', kind: 'encoder', label: 'E1' },
      ],
      banks: [
        {
          number: 1,
          channel: 1,
          notes: {
            '55': 'mc_click_1',
            '60': 'mc_encoder_1',
            '70': 'mc_fader_1',
          },
        },
        { number: 2, channel: 2, notes: {} },
      ],
      logical: ['mc_click_1', 'mc_encoder_1', 'mc_fader_1'],
    },
  },
] as unknown as DeviceEntry[];

const config = {
  mapping: {
    keys: {
      fix: { hardkey: 'Fix' },
      oops: { command: 'Clear' },
    },
    encoders: [
      { id: 1, slot: 1 },
      { id: 2, slot: 2 },
      { id: 3, slot: 3 },
      { id: 4, slot: 4 },
    ],
    modifiers: {
      ma: { hardkey: 'MA' },
      fine_mod: { local: true },
    },
    screen_encoders: { '1': 5, '2': 6, '3': 7, '4': 8 },
    playbacks: {
      mc_fader_1: { page: 1, executor: 2, kind: 'fader' },
      mc_click_1: { page: 1, executor: 1, kind: 'button', button: 2 },
    },
  },
};

function fakeApi() {
  return {
    config: vi.fn(async () => structuredClone(config)),
    devices: vi.fn(async () => structuredClone(devices)),
    updateConfig: vi.fn(async () => ({ generation: 1 })),
    startLearn: vi.fn(async () => ({ kind: 'key', status: 'active' })),
    cancelLearn: vi.fn(async () => ({ cancelled: true, learn: null })),
  } as unknown as ApiClient;
}

async function renderPage(api: ApiClient) {
  render(MappingPage, { props: { api } });
  await waitFor(() => {
    expect(screen.getByDisplayValue('Fix')).toBeTruthy();
  });
}

function playbackRow(control: string): HTMLTableRowElement {
  const row = document.querySelector(`tr[data-control="${control}"]`);
  if (!(row instanceof HTMLTableRowElement)) {
    throw new Error(`Playback-Zeile für ${control} nicht gefunden`);
  }
  return row;
}

describe('MappingPage', () => {
  it('edits a key mapping and tracks unsaved changes', async () => {
    const api = fakeApi();
    await renderPage(api);

    const value = screen.getByDisplayValue('Fix') as HTMLInputElement;
    await fireEvent.input(value, { target: { value: 'Store' } });

    expect(screen.getByTestId('dirty')).toBeTruthy();
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(screen.getByRole('status').textContent).toContain('Mapping gespeichert');
    });
    expect(api.updateConfig).toHaveBeenCalledWith({
      mapping: expect.objectContaining({
        keys: expect.objectContaining({
          fix: {
            hardkey: 'Store',
            command: null,
            screen_mode: null,
            encoder_press: null,
            screen: null,
          },
        }),
      }),
    });
    expect(screen.queryByTestId('dirty')).toBeNull();
  });

  it('emits null tombstones on union switches for keys, playbacks, and modifiers', async () => {
    const api = fakeApi();
    await renderPage(api);

    // Switch key `fix` from `hardkey` to `command`
    const keyKinds = screen.getAllByTestId('key-kind') as HTMLSelectElement[];
    await fireEvent.change(keyKinds[0], { target: { value: 'command' } });
    const keyValues = screen.getAllByTestId('key-value') as HTMLInputElement[];
    await fireEvent.input(keyValues[0], { target: { value: 'Macro 1' } });

    // Switch playback `mc_click_1` from `button` to `fader`
    const clickRow = playbackRow('mc_click_1');
    await fireEvent.change(within(clickRow).getByTestId('playback-kind'), {
      target: { value: 'fader' },
    });

    // Enable `mc_encoder_1` and switch it to `button` (must emit accelerated: null)
    const encRow = playbackRow('mc_encoder_1');
    await fireEvent.click(within(encRow).getByTestId('playback-enabled'));
    await fireEvent.change(within(encRow).getByTestId('playback-kind'), {
      target: { value: 'button' },
    });
    await fireEvent.input(within(encRow).getByTestId('playback-page'), {
      target: { value: '1' },
    });
    await fireEvent.input(within(encRow).getByTestId('playback-executor'), {
      target: { value: '5' },
    });

    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(1));
    expect(api.updateConfig).toHaveBeenCalledWith({
      mapping: expect.objectContaining({
        keys: expect.objectContaining({
          fix: {
            hardkey: null,
            command: 'Macro 1',
            screen_mode: null,
            encoder_press: null,
            screen: null,
          },
        }),
        modifiers: {
          ma: { hardkey: 'MA', local: null },
          fine_mod: { local: true, hardkey: null },
        },
        playbacks: expect.objectContaining({
          mc_click_1: {
            page: 1,
            executor: 1,
            kind: 'fader',
            button: null,
            accelerated: null,
          },
          mc_encoder_1: {
            page: 1,
            executor: 5,
            kind: 'button',
            button: 1,
            accelerated: null,
          },
        }),
      }),
    });
  });

  it('refreshes original sets after save so add -> save -> delete -> save emits null deletions', async () => {
    const api = fakeApi();
    await renderPage(api);

    // Add a new key row `store_big` -> `Store`
    await fireEvent.click(screen.getByText('Taste hinzufügen'));
    const keySelects = screen
      .getAllByTestId('key-kind')
      .map((el) => el.closest('tr')!.querySelector('select') as HTMLSelectElement);
    await fireEvent.change(keySelects[2], { target: { value: 'store_big' } });
    const keyValues = screen.getAllByTestId('key-value') as HTMLInputElement[];
    await fireEvent.input(keyValues[2], { target: { value: 'Store' } });

    // Enable fixed playback row `mc_encoder_1`
    const encRow = playbackRow('mc_encoder_1');
    await fireEvent.click(within(encRow).getByTestId('playback-enabled'));
    await fireEvent.input(within(encRow).getByTestId('playback-page'), {
      target: { value: '1' },
    });
    await fireEvent.input(within(encRow).getByTestId('playback-executor'), {
      target: { value: '9' },
    });

    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(1));

    // Now delete the newly added key row and deactivate `mc_encoder_1`, then save again
    const addedKeyRow = keySelects[2].closest('tr')!;
    await fireEvent.click(within(addedKeyRow).getByText('Entfernen'));
    await fireEvent.click(within(encRow).getByTestId('playback-remove'));

    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(2));

    expect(api.updateConfig).toHaveBeenNthCalledWith(2, {
      mapping: expect.objectContaining({
        keys: expect.objectContaining({
          store_big: null,
        }),
        playbacks: expect.objectContaining({
          mc_encoder_1: null,
        }),
      }),
    });
  });

  it('edits an encoder slot', async () => {
    const api = fakeApi();
    await renderPage(api);

    const value = screen.getAllByTestId('encoder-value')[0] as HTMLInputElement;
    await fireEvent.input(value, { target: { value: '3' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        mapping: expect.objectContaining({
          encoders: expect.arrayContaining([
            expect.objectContaining({ id: 1, slot: 3 }),
          ]),
        }),
      });
    });
  });

  it('edits the screen target per physical encoder without duplicating options 9 and 10', async () => {
    const api = fakeApi();
    (api.config as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...config,
      mapping: {
        ...config.mapping,
        screen_encoders: { '1': 9, '2': 10, '3': 7, '4': 8 },
      },
    });
    await renderPage(api);

    const targets = screen.getAllByTestId(
      'screen-encoder-target',
    ) as HTMLSelectElement[];
    expect(targets[0].value).toBe('9');
    expect(targets[1].value).toBe('10');
    // Ensure option 9 and 10 appear only once each
    expect(Array.from(targets[0].options).filter((o) => o.value === '9')).toHaveLength(1);
    expect(Array.from(targets[1].options).filter((o) => o.value === '10')).toHaveLength(1);

    await fireEvent.change(targets[3], { target: { value: '' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        mapping: expect.objectContaining({
          screen_encoders: { '1': 9, '2': 10, '3': 7, '4': null },
        }),
      });
    });
  });

  it('shows a server validation error for an invalid wheel', async () => {
    const api = fakeApi();
    (api.updateConfig as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError(
        422,
        'validation_error',
        'mapping.encoders[0].slot: muss zwischen 1 und 8 liegen',
      ),
    );
    await renderPage(api);

    const value = screen.getAllByTestId('encoder-value')[0] as HTMLInputElement;
    await fireEvent.input(value, { target: { value: '11' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain(
        'muss zwischen 1 und 8 liegen',
      );
    });
    expect(screen.getByTestId('dirty')).toBeTruthy();
  });

  it('starts learn for a key and an encoder, keeping stable row uid across row deletion', async () => {
    const api = fakeApi();
    const listeners = new Set<() => void>();
    const learnStore = {
      state: { learn: null as LearnResult | null },
      subscribe(listener: () => void) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    };
    render(MappingPage, {
      props: { api, learnStore: learnStore as unknown as StatusStore },
    });
    await waitFor(() => {
      expect(screen.getByDisplayValue('Fix')).toBeTruthy();
    });

    // Start learn on the SECOND key row (`oops` -> `Clear`), then delete the FIRST key row (`fix`)
    await fireEvent.click(screen.getAllByTestId('key-learn')[1]);
    expect(api.startLearn).toHaveBeenNthCalledWith(1, 'key', undefined);

    const firstRow = screen.getByDisplayValue('Fix').closest('tr')!;
    await fireEvent.click(within(firstRow).getByText('Entfernen'));

    learnStore.state.learn = {
      kind: 'key',
      status: 'captured',
      control: 'mc_click_1',
      device: 'midicraft',
      raw: '55',
      direction: 0,
      detents: 0,
      elapsed: 0.1,
      timed_out: false,
    };
    for (const listener of listeners) listener();

    // Remaining row should have updated its control to `mc_click_1`, and resolving deviceForControl works for banked inventory!
    await fireEvent.click(screen.getAllByTestId('key-learn')[0]);
    expect(api.startLearn).toHaveBeenNthCalledWith(2, 'key', 'midicraft');

    learnStore.state.learn = {
      kind: 'key',
      status: 'cancelled',
      control: null,
      device: 'midicraft',
      raw: null,
      direction: 0,
      detents: 0,
      elapsed: 0.2,
      timed_out: false,
    };
    for (const listener of listeners) listener();

    await fireEvent.click(screen.getAllByTestId('encoder-learn')[0]);
    expect(api.startLearn).toHaveBeenNthCalledWith(3, 'encoder', 'asl');
  });

  it('handles learn timeout, manual Abbrechen button, and cancelLearn on unmount', async () => {
    const api = fakeApi();
    const listeners = new Set<() => void>();
    const learnStore = {
      state: { learn: null as LearnResult | null },
      subscribe(listener: () => void) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    };
    const { unmount } = render(MappingPage, {
      props: { api, learnStore: learnStore as unknown as StatusStore },
    });
    await waitFor(() => {
      expect(screen.getByDisplayValue('Fix')).toBeTruthy();
    });

    const learnButtons = () => screen.getAllByTestId('key-learn') as HTMLButtonElement[];
    await fireEvent.click(learnButtons()[0]);
    expect(learnButtons()[0].disabled).toBe(true);
    expect(screen.getByTestId('learn-cancel')).toBeTruthy();

    // Timeout resets pendingLearn, re-enables Lernen buttons, and shows a status message
    learnStore.state.learn = {
      kind: 'key',
      status: 'timeout',
      control: null,
      device: 'cherry',
      raw: null,
      direction: 0,
      detents: 0,
      elapsed: 5.0,
      timed_out: true,
    };
    for (const listener of listeners) listener();

    await waitFor(() => {
      expect(learnButtons()[0].disabled).toBe(false);
    });
    expect(screen.queryByTestId('learn-cancel')).toBeNull();
    expect(screen.getByRole('status').textContent).toContain('Learn');

    // Manual Abbrechen calls cancelLearn and resets pendingLearn
    await fireEvent.click(learnButtons()[0]);
    expect(learnButtons()[0].disabled).toBe(true);
    await fireEvent.click(screen.getByText('Abbrechen'));
    await waitFor(() => {
      expect(api.cancelLearn).toHaveBeenCalledTimes(1);
      expect(learnButtons()[0].disabled).toBe(false);
    });

    // Unmounting while learn is active triggers cancelLearn in onDestroy
    await fireEvent.click(learnButtons()[0]);
    expect(learnButtons()[0].disabled).toBe(true);
    unmount();
    expect(api.cancelLearn).toHaveBeenCalledTimes(2);
  });

  it('enables an absolute banked inventory control as a fader playback target', async () => {
    const api = fakeApi();
    await renderPage(api);

    const row = playbackRow('mc_encoder_1');
    expect(within(row).queryByTestId('playback-button')).toBeNull();
    await fireEvent.click(within(row).getByTestId('playback-enabled'));
    await fireEvent.input(within(row).getByTestId('playback-page'), {
      target: { value: '2' },
    });
    await fireEvent.input(within(row).getByTestId('playback-executor'), {
      target: { value: '4' },
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        mapping: expect.objectContaining({
          playbacks: expect.objectContaining({
            mc_encoder_1: {
              page: 2,
              executor: 4,
              kind: 'fader',
              button: null,
              accelerated: false,
            },
          }),
        }),
      });
    });
  });

  it('saves current as a page-relative playback target', async () => {
    const api = fakeApi();
    await renderPage(api);

    const row = playbackRow('mc_encoder_1');
    await fireEvent.click(within(row).getByTestId('playback-enabled'));
    await fireEvent.input(within(row).getByTestId('playback-page'), {
      target: { value: 'current' },
    });
    await fireEvent.input(within(row).getByTestId('playback-executor'), {
      target: { value: '4' },
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        mapping: expect.objectContaining({
          playbacks: expect.objectContaining({
            mc_encoder_1: {
              page: 'current',
              executor: 4,
              kind: 'fader',
              button: null,
              accelerated: false,
            },
          }),
        }),
      });
    });
  });

  it('shows acceleration only for absolute encoders including banked inventory encoders', async () => {
    const api = fakeApi();
    await renderPage(api);

    expect(
      within(playbackRow('mc_encoder_1')).getByTestId('playback-accelerated'),
    ).toBeTruthy();
    expect(
      within(playbackRow('mc_fader_1')).queryByTestId('playback-accelerated'),
    ).toBeNull();
    expect(
      within(playbackRow('mc_click_1')).queryByTestId('playback-accelerated'),
    ).toBeNull();
  });

  it('loads the saved acceleration state', async () => {
    const api = fakeApi();
    (api.config as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...config,
      mapping: {
        ...config.mapping,
        playbacks: {
          ...config.mapping.playbacks,
          mc_encoder_1: {
            page: 1,
            executor: 2,
            kind: 'fader',
            accelerated: true,
          },
        },
      },
    });
    await renderPage(api);

    const checkbox = within(playbackRow('mc_encoder_1')).getByTestId(
      'playback-accelerated',
    ) as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
  });

  it('saves acceleration for a banked inventory encoder', async () => {
    const api = fakeApi();
    await renderPage(api);

    const row = playbackRow('mc_encoder_1');
    await fireEvent.click(within(row).getByTestId('playback-enabled'));
    await fireEvent.click(within(row).getByTestId('playback-accelerated'));
    await fireEvent.input(within(row).getByTestId('playback-page'), {
      target: { value: '1' },
    });
    await fireEvent.input(within(row).getByTestId('playback-executor'), {
      target: { value: '2' },
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        mapping: expect.objectContaining({
          playbacks: expect.objectContaining({
            mc_encoder_1: {
              page: 1,
              executor: 2,
              kind: 'fader',
              button: null,
              accelerated: true,
            },
          }),
        }),
      });
    });
  });

  it('blocks saving an invalid playback page', async () => {
    const api = fakeApi();
    await renderPage(api);

    const row = playbackRow('mc_encoder_1');
    await fireEvent.click(within(row).getByTestId('playback-enabled'));
    await fireEvent.input(within(row).getByTestId('playback-page'), {
      target: { value: '0' },
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('Zahl ab 1 oder "current"');
    });
    expect(api.updateConfig).not.toHaveBeenCalled();
  });
});

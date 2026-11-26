import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
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
      ],
      notes: [],
      encoders: [],
      midi_encoders: [],
      logical: ['fix', 'store_big'],
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
      logical: ['asl_click_1', 'encoder.1', 'encoder.2', 'encoder.3', 'encoder.4'],
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
    modifiers: { ma: { hardkey: 'MA' } },
    screen_encoders: { '1': 5, '2': 6, '3': 7, '4': 8 },
  },
};

function fakeApi() {
  return {
    config: vi.fn(async () => config),
    devices: vi.fn(async () => devices),
    updateConfig: vi.fn(async () => ({ generation: 1 })),
    startLearn: vi.fn(async () => ({ kind: 'key', status: 'active' })),
  } as unknown as ApiClient;
}

async function renderPage(api: ApiClient) {
  render(MappingPage, { props: { api } });
  await waitFor(() => {
    expect(screen.getByDisplayValue('Fix')).toBeTruthy();
  });
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
        keys: expect.objectContaining({ fix: { hardkey: 'Store' } }),
      }),
    });
    expect(screen.queryByTestId('dirty')).toBeNull();
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

  it('edits the screen target per physical encoder', async () => {
    const api = fakeApi();
    await renderPage(api);

    const targets = screen.getAllByTestId(
      'screen-encoder-target',
    ) as HTMLSelectElement[];
    expect(targets[0].value).toBe('5');
    expect(targets[3].value).toBe('8');
    await fireEvent.change(targets[0], { target: { value: '9' } });
    await fireEvent.change(targets[3], { target: { value: '' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => {
      expect(api.updateConfig).toHaveBeenCalledWith({
        mapping: expect.objectContaining({
          screen_encoders: { '1': 9, '2': 6, '3': 7, '4': null },
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

  it('starts learn for a key and an encoder', async () => {
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

    await fireEvent.click(screen.getAllByTestId('key-learn')[0]);
    expect(api.startLearn).toHaveBeenNthCalledWith(1, 'key', 'cherry');

    learnStore.state.learn = {
      kind: 'key',
      status: 'captured',
      control: 'store_big',
      device: 'cherry',
      raw: 'KEY_HANGUEL',
      direction: 0,
      detents: 0,
      elapsed: 0.1,
      timed_out: false,
    };
    for (const listener of listeners) listener();

    await fireEvent.click(screen.getAllByTestId('encoder-learn')[0]);
    expect(api.startLearn).toHaveBeenNthCalledWith(2, 'encoder', 'asl');
  });
});

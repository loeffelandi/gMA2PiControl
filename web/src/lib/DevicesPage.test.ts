import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import DevicesPage from './DevicesPage.svelte';
import type { ApiClient, DeviceEntry } from './api';

const device: DeviceEntry = {
  name: 'banktest',
  backend: 'midi',
  profile: 'bank-test',
  vendor_id: 0x04d8,
  product_id: 0x1234,
  vendor_product: '04d8:1234',
  name_contains: 'Bank Test',
  detected: { path: '/dev/snd/midiC9D0' },
  layout: {
    profile: 'bank-test',
    columns: 2,
    rows: [
      {
        cells: [
          { label: 'F', control: 'bt_fader', col_span: 1, row_span: 1, color: 'green', row: 1, col: 1 },
          { label: 'B', control: 'bt_button', col_span: 1, row_span: 1, color: null, row: 1, col: 2 },
        ],
      },
    ],
  },
  bank_size: 5,
  controls: {
    keys: [],
    notes: [],
    encoders: [],
    midi_encoders: [],
    values: [],
    inventory: [
      { id: 'bt_fader', kind: 'fader', label: 'Fader' },
      { id: 'bt_button', kind: 'button', label: null },
    ],
    banks: [
      { number: 1, channel: 1, notes: { '70': 'bt_fader' } },
      { number: 2, channel: 2, notes: {} },
    ],
    logical: ['bt_fader', 'bt_button'],
  },
};

const config = {
  profiles: {
    'bank-test': {
      banks: [
        { number: 1, channel: 1, notes: { 70: 'bt_fader' } },
        { number: 2, channel: 2, notes: {} },
      ],
    },
  },
  layouts: { 'bank-test': device.layout },
  mapping: {
    keys: { bt_button: { hardkey: 'Goto' } },
    playbacks: {},
    device_banks: { banktest: { bank_size: 5 } },
  },
};

function fakeApi(devices: DeviceEntry[], cfg = config) {
  return {
    devices: vi.fn().mockResolvedValue(devices),
    config: vi.fn().mockResolvedValue(cfg),
    updateConfig: vi.fn().mockResolvedValue({}),
    deviceLearnStatus: vi.fn().mockResolvedValue({ active: false }),
    startDeviceLearn: vi.fn(),
    skipDeviceLearn: vi.fn(),
    cancelDeviceLearn: vi.fn(),
    finishDeviceLearn: vi.fn(),
  } as unknown as ApiClient;
}

describe('DevicesPage', () => {
  it('renders the surface and offers banks', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });

    await waitFor(() => expect(screen.getByTestId('device-surface')).toBeTruthy());
    expect(screen.getByText('Bank 1 · Kanal 1')).toBeTruthy();
    expect(screen.getByText('Goto')).toBeTruthy();
  });

  it('switches the visible bank without touching the API', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getAllByRole('option').length).toBe(2));
    const select = screen.getByLabelText('Bank') as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: '2' } });
    expect(api.updateConfig).not.toHaveBeenCalled();
  });

  it('falls back to a table without a layout', async () => {
    const api = fakeApi([{ ...device, layout: null }]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Control')).toBeTruthy());
    expect(screen.queryByTestId('device-surface')).toBeNull();
  });
});


describe('DevicesPage filtering', () => {
  it('hides configured but disconnected devices', async () => {
    const offline = { ...device, name: 'offline', profile: 'offline', detected: null };
    const api = fakeApi([device, offline]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getAllByText('banktest').length).toBeGreaterThan(0));
    expect(screen.queryByText('offline')).toBeNull();
  });
});


describe('DevicesPage encoder assignments', () => {
  const encoderDevice: DeviceEntry = {
    ...device,
    layout: {
      profile: 'bank-test',
      columns: 2,
      rows: [
        {
          cells: [
            { label: 'E1', control: 'encoder.1', col_span: 1, row_span: 1, color: 'blue', row: 1, col: 1 },
            { label: 'B', control: 'bt_button', col_span: 1, row_span: 1, color: null, row: 1, col: 2 },
          ],
        },
      ],
    },
    controls: {
      ...device.controls,
      encoders: [{ id: 1, axis: 'ABS_X', detents_per_revolution: 24, direction: 1, threshold: 1 }],
      inventory: [
        { id: 'encoder.1', kind: 'relative-encoder', label: 'Encoder 1' },
        { id: 'bt_button', kind: 'button', label: null },
      ],
    },
  };

  const encoderConfig = {
    ...config,
    mapping: {
      ...config.mapping,
      encoders: [{ id: 1, slot: 1 }],
      screen_encoders: { 1: 8 },
    },
  };

  it('shows attribute encoders and their screen encoder switch', async () => {
    const api = fakeApi([encoderDevice], encoderConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() =>
      expect(screen.getByText('Attribut 1 · Screen 8 (MA/Bank)')).toBeTruthy(),
    );
  });

  it('stores slot and screen encoder through the encoder action', async () => {
    const api = fakeApi([encoderDevice], encoderConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('E1')).toBeTruthy());
    await fireEvent.click(screen.getByText('E1'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    const screenInput = screen.getByLabelText(/Screen-Encoder/) as HTMLInputElement;
    await fireEvent.input(screenInput, { target: { value: '7' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(api.updateConfig).toHaveBeenCalledWith({
      mapping: {
        encoders: [{ id: 1, slot: 1 }],
        screen_encoders: { '1': 7 },
      },
    });
  });
});


describe('DevicesPage special key assignments', () => {
  it('stores a screen-mode toggle without a hardkey', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('B')).toBeTruthy());
    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    const select = screen.getByLabelText('Aktion') as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: 'screen_mode' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(api.updateConfig).toHaveBeenCalledWith({
      mapping: {
        keys: {
          bt_button: {
            hardkey: null,
            command: null,
            screen_mode: true,
            encoder_press: null,
            screen: null,
          },
        },
        playbacks: { bt_button: null },
      },
    });
  });
});


describe('DevicesPage bank offset', () => {
  it('shows and preselects the effective executor in bank 2', async () => {
    const withPlayback = {
      ...config,
      mapping: {
        ...config.mapping,
        playbacks: {
          bt_fader: { page: 1, executor: 1, kind: 'fader', button: 1 },
        },
      },
    };
    const api = fakeApi([device], withPlayback);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Exec 1 Fader')).toBeTruthy());
    const select = screen.getByLabelText('Bank') as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: '2' } });
    expect(screen.getByText('Exec 6 Fader')).toBeTruthy();

    await fireEvent.click(screen.getByText('F'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    expect((screen.getByLabelText('Executor') as HTMLInputElement).value).toBe('6');
  });
});

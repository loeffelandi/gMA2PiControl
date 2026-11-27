import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import DevicesPage from './DevicesPage.svelte';
import { ApiError, type ApiClient, type DeviceEntry } from './api';

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
        { number: 1, channel: 1, notes: { '70': 'bt_fader' } },
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

function fakeApi(devices: DeviceEntry[], cfg: Record<string, unknown> = config) {
  return {
    devices: vi.fn().mockResolvedValue(devices),
    config: vi.fn().mockResolvedValue(cfg),
    configSnapshot: vi.fn().mockResolvedValue({ config: cfg, generation: 1 }),
    updateConfig: vi.fn().mockResolvedValue({}),
    deviceLearnStatus: vi.fn().mockResolvedValue({ active: false }),
    startDeviceLearn: vi.fn(),
    skipDeviceLearn: vi.fn(),
    cancelDeviceLearn: vi.fn().mockResolvedValue({}),
    finishDeviceLearn: vi.fn(),
  } as unknown as ApiClient;
}

/** Merge patch of the last `updateConfig` call. */
function sentPatch(api: ApiClient): unknown {
  const calls = vi.mocked(api.updateConfig).mock.calls;
  return calls[calls.length - 1]?.[0];
}

describe('DevicesPage', () => {
  it('renders the surface and offers banks', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });

    await waitFor(() => expect(screen.getByTestId('device-surface')).toBeTruthy());
    expect(screen.getByText('Bank 1 · Kanal 1')).toBeTruthy();
    expect(screen.getByText('Goto')).toBeTruthy();
  });

  it('switches the visible bank without touching the API or overwriting unsaved bankSize', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getAllByRole('option').length).toBe(2));

    const sizeInput = screen.getByLabelText('Bankgröße') as HTMLInputElement;
    await fireEvent.input(sizeInput, { target: { value: '8' } });

    const select = screen.getByLabelText('Bank') as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: '2' } });
    expect(api.updateConfig).not.toHaveBeenCalled();
    expect(sizeInput.value).toBe('8');
    expect((screen.getByLabelText('Kanal') as HTMLInputElement).value).toBe('2');
  });

  it('falls back to a table without a layout', async () => {
    const api = fakeApi([{ ...device, layout: null }]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Control')).toBeTruthy());
    expect(screen.queryByTestId('device-surface')).toBeNull();
  });

  it('formats ApiError detail cleanly without raw error codes', async () => {
    const api = fakeApi([device]);
    vi.mocked(api.updateConfig).mockRejectedValue(
      new ApiError(422, 'validation_error', 'Kanal bereits vergeben'),
    );
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Einstellungen speichern')).toBeTruthy());

    await fireEvent.click(screen.getByText('Einstellungen speichern'));
    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toBe('Kanal bereits vergeben');
    });
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
      columns: 3,
      rows: [
        {
          cells: [
            { label: 'E1', control: 'encoder.1', col_span: 1, row_span: 1, color: 'blue', row: 1, col: 1 },
            { label: 'E2', control: 'encoder.2', col_span: 1, row_span: 1, color: 'blue', row: 1, col: 2 },
            { label: 'B', control: 'bt_button', col_span: 1, row_span: 1, color: null, row: 1, col: 3 },
          ],
        },
      ],
    },
    controls: {
      ...device.controls,
      encoders: [
        { id: 1, axis: 'ABS_X', detents_per_revolution: 24, direction: 1, threshold: 1 },
        { id: 2, axis: 'ABS_Y', detents_per_revolution: 24, direction: 1, threshold: 1 },
      ],
      inventory: [
        { id: 'encoder.1', kind: 'relative-encoder', label: 'Encoder 1' },
        { id: 'encoder.2', kind: 'relative-encoder', label: 'Encoder 2' },
        { id: 'bt_button', kind: 'button', label: null },
      ],
    },
  };

  const encoderConfig = {
    ...config,
    mapping: {
      ...config.mapping,
      encoders: [{ id: 1, slot: 1 }],
      screen_encoders: { '1': 8 },
    },
  };

  it('shows attribute encoders and their screen encoder switch', async () => {
    const api = fakeApi([encoderDevice], encoderConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() =>
      expect(screen.getByText('Attribut 1 · Screen 8 (MA/Bank)')).toBeTruthy(),
    );
  });

  it('stores slot and screen encoder through the encoder select', async () => {
    const api = fakeApi([encoderDevice], encoderConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('E1')).toBeTruthy());
    await fireEvent.click(screen.getByText('E1'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    const screenSelect = screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement;
    await fireEvent.change(screenSelect, { target: { value: '7' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        encoders: [{ id: 1, slot: 1 }],
        screen_encoders: { '1': 7 },
      },
    });
  });

  it('saves an encoder with screen = 0 (keiner) and clears an existing screen_encoders entry', async () => {
    const api = fakeApi([encoderDevice], encoderConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('E1')).toBeTruthy());
    await fireEvent.click(screen.getByText('E1'));
    await fireEvent.click(screen.getByText('Zuweisen'));

    const screenSelect = screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement;
    await fireEvent.change(screenSelect, { target: { value: '0' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        encoders: [{ id: 1, slot: 1 }],
        screen_encoders: { '1': null },
      },
    });
  });

  it('clears previous slot screen_encoders entry when switching encoder to attribute', async () => {
    const api = fakeApi([encoderDevice], encoderConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('E1')).toBeTruthy());
    await fireEvent.click(screen.getByText('E1'));
    await fireEvent.click(screen.getByText('Zuweisen'));

    await fireEvent.change(screen.getByLabelText('Ziel'), {
      target: { value: 'attribute' },
    });
    await fireEvent.input(screen.getByLabelText('Attributname'), {
      target: { value: 'Dimmer' },
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        encoders: [{ id: 1, attribute: 'Dimmer' }],
        screen_encoders: { '1': null },
      },
    });
  });

  it('loads and preserves canonical flat device_banks with ma_page and multiple encoders', async () => {
    const bankedCfg = {
      ...encoderConfig,
      mapping: {
        ...encoderConfig.mapping,
        device_banks: {
          banktest: {
            bank_size: 5,
            '2': {
              ma_page: 3,
              encoders: [
                { id: 1, slot: 2 },
                { id: 2, attribute: 'Pan' },
              ],
            },
          },
        },
      },
    };
    const api = fakeApi([encoderDevice], bankedCfg);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('E1')).toBeTruthy());

    await fireEvent.change(screen.getByLabelText('Bank'), { target: { value: '2' } });
    expect((screen.getByLabelText('MA-Page') as HTMLInputElement).value).toBe('3');
    expect(screen.getByText('Attribut 2')).toBeTruthy();
    expect(screen.getByText('Attribut Pan')).toBeTruthy();

    await fireEvent.click(screen.getByText('E1'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    await fireEvent.input(screen.getByLabelText('Slot'), { target: { value: '4' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        device_banks: {
          banktest: {
            '2': {
              encoders: [
                { id: 1, slot: 4 },
                { id: 2, attribute: 'Pan' },
              ],
            },
          },
        },
      },
    });
  });
});

describe('DevicesPage special key assignments and deletion', () => {
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
    expect(sentPatch(api)).toEqual({
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

  it('deletes a global assignment on Bank 1 via Belegung entfernen', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('B')).toBeTruthy());

    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    await fireEvent.click(screen.getByText('Belegung entfernen'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        keys: { bt_button: null },
        playbacks: { bt_button: null },
      },
    });
  });

  it('deletes a Bank 2 override to restore inheritance without touching Bank 1', async () => {
    const withOverride = {
      ...config,
      mapping: {
        ...config.mapping,
        playbacks: {
          bt_fader: { page: 1, executor: 1, kind: 'fader' },
        },
        device_banks: {
          banktest: {
            bank_size: 5,
            '2': {
              playbacks: {
                bt_fader: { page: 2, executor: 99, kind: 'fader' },
              },
            },
          },
        },
      },
    };
    const api = fakeApi([device], withOverride);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Exec 1 Fader')).toBeTruthy());

    await fireEvent.change(screen.getByLabelText('Bank'), { target: { value: '2' } });
    expect(screen.getByText('Exec 99 Fader')).toBeTruthy();

    await fireEvent.click(screen.getByText('F'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    await fireEvent.click(screen.getByText('Belegung entfernen'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        device_banks: {
          banktest: {
            '2': {
              keys: { bt_fader: null },
              playbacks: { bt_fader: null },
            },
          },
        },
      },
    });
  });

  it('edits an existing Bank 1 layer entry instead of writing a global entry beside it', async () => {
    const withBank1Layer = {
      ...config,
      mapping: {
        ...config.mapping,
        device_banks: {
          banktest: {
            bank_size: 5,
            '1': {
              keys: { bt_button: { hardkey: 'Store' } },
            },
          },
        },
      },
    };
    const api = fakeApi([device], withBank1Layer);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Store')).toBeTruthy());

    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    expect((screen.getByLabelText('Geltungsbereich') as HTMLSelectElement).value).toBe('bank');
    await fireEvent.input(screen.getByLabelText('Hardkey'), {
      target: { value: 'Clear' },
    });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        device_banks: {
          banktest: {
            '1': {
              keys: {
                bt_button: {
                  hardkey: 'Clear',
                  command: null,
                  screen_mode: null,
                  encoder_press: null,
                  screen: null,
                },
              },
              playbacks: { bt_button: null },
            },
          },
        },
      },
    });
  });

  it('writes the global entry on Bank 1 without a layer and replaces a layer on explicit global scope', async () => {
    const api = fakeApi([device]);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('B')).toBeTruthy());
    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    expect((screen.getByLabelText('Geltungsbereich') as HTMLSelectElement).value).toBe('global');
    await fireEvent.input(screen.getByLabelText('Hardkey'), { target: { value: 'Clear' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toMatchObject({
      mapping: { keys: { bt_button: { hardkey: 'Clear' } } },
    });
    expect((sentPatch(api) as any).mapping.device_banks).toBeUndefined();
  });
});

describe('DevicesPage bank offset', () => {
  it('shows inherited hint in bank 2 and writes un-offset base executor in Global scope', async () => {
    const withPlayback = {
      ...config,
      mapping: {
        ...config.mapping,
        playbacks: {
          bt_fader: { page: 1, executor: 1, kind: 'fader' },
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
    expect(screen.getByTestId('assignment-source').textContent).toContain(
      'geerbt mit Bank-Offset (Offset +5)',
    );

    const execInput = screen.getByLabelText('Executor') as HTMLInputElement;
    expect(execInput.value).toBe('6');
    await fireEvent.input(execInput, { target: { value: '7' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        keys: { bt_fader: null },
        playbacks: {
          bt_fader: {
            page: 1,
            executor: 2,
            kind: 'fader',
            button: null,
            accelerated: null,
            transport: null,
          },
        },
      },
    });
  });
});

describe('DevicesPage bank fader under a global MIDI button', () => {
  it('writes web so the override does not inherit midi', async () => {
    const midiConfig = {
      ...config,
      midi_remote: { enabled: true, port: 5004, channels: [16], sync: 'auto', telnet_port: 30000 },
      mapping: {
        ...config.mapping,
        keys: {},
        playbacks: {
          bt_button: { page: 1, executor: 3, kind: 'button', button: 1, transport: 'midi' },
        },
      },
    };
    const api = fakeApi([device], midiConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Exec 3 Btn 1 · midi')).toBeTruthy());
    await fireEvent.change(screen.getByLabelText('Bank'), { target: { value: '2' } });

    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    await fireEvent.change(screen.getByLabelText('Geltungsbereich'), {
      target: { value: 'bank' },
    });
    await fireEvent.change(screen.getByLabelText('Art'), { target: { value: 'fader' } });
    await fireEvent.change(screen.getByLabelText('Transport'), { target: { value: '' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    const patch = (api.updateConfig as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(patch.mapping.device_banks.banktest['2'].playbacks.bt_button).toMatchObject({
      kind: 'fader',
      transport: 'web',
    });
  });
});

describe('DevicesPage playback transport', () => {
  const transportConfig = {
    ...config,
    midi_remote: { enabled: true, port: 5004, channels: [16], sync: 'auto', telnet_port: 30000 },
    mapping: {
      ...config.mapping,
      keys: {},
      playbacks: {
        bt_button: { page: 1, executor: 3, kind: 'button', button: 1, transport: 'midi' },
        bt_fader: { page: 1, executor: 1, kind: 'fader' },
      },
    },
  };

  it('shows the transport hint and saves a changed transport', async () => {
    const api = fakeApi([device], transportConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Exec 3 Btn 1 · midi')).toBeTruthy());
    expect(screen.getByText('Exec 1 Fader')).toBeTruthy();

    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    const select = screen.getByLabelText('Transport') as HTMLSelectElement;
    expect(select.value).toBe('midi');
    await fireEvent.change(select, { target: { value: 'web' } });
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        keys: { bt_button: null },
        playbacks: {
          bt_button: {
            page: 1,
            executor: 3,
            kind: 'button',
            button: 1,
            accelerated: null,
            transport: 'web',
          },
        },
      },
    });
  });

  it('writes null for Standard and offers no MIDI option for faders', async () => {
    const api = fakeApi([device], transportConfig);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('Exec 3 Btn 1 · midi')).toBeTruthy());

    await fireEvent.click(screen.getByText('F'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    const faderSelect = screen.getByLabelText('Transport') as HTMLSelectElement;
    expect(faderSelect.value).toBe('');
    expect(Array.from(faderSelect.options).map((option) => option.value)).toEqual(['', 'web']);
    expect(faderSelect.options[0].textContent?.trim()).toBe('Standard (Web)');
    await fireEvent.click(screen.getByText('Abbrechen'));
    await fireEvent.click(screen.getByText('F'));

    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    const select = screen.getByLabelText('Transport') as HTMLSelectElement;
    await fireEvent.change(select, { target: { value: '' } });
    expect(select.options[0].textContent?.trim()).toBe('Standard (MIDI)');
    await fireEvent.click(screen.getByText('Speichern'));

    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    expect(sentPatch(api)).toEqual({
      mapping: {
        keys: { bt_button: null },
        playbacks: {
          bt_button: {
            page: 1,
            executor: 3,
            kind: 'button',
            button: 1,
            accelerated: null,
            transport: null,
          },
        },
      },
    });
  });
});

describe('DevicesPage learn highlight', () => {
  it('marks the active learn control on the surface', async () => {
    const api = fakeApi([device]);
    vi.mocked(api.deviceLearnStatus).mockResolvedValue({
      active: true,
      device: 'banktest',
      bank: 1,
      channel: 1,
      current: 'bt_button',
      total: 2,
      index: 0,
      captured: [],
      paused: false,
      error: null,
    });

    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByTestId('device-surface')).toBeTruthy());
    await fireEvent.click(screen.getByText('Anlernen'));

    await waitFor(() =>
      expect(screen.getByText(/das markierte Feld/)).toBeTruthy(),
    );
    const cell = screen.getByText('B').closest('button')!;
    expect(cell.classList.contains('active')).toBe(true);
  });

  it('saves custom-named relative-encoder via encoder_id and clears modifiers on Bank 1', async () => {
    const customEncDevice = {
      ...device,
      name: 'wheeldev',
      profile: 'wheelprof',
      controls: {
        ...device.controls,
        inventory: [
          { id: 'wheel_pan', kind: 'relative-encoder' as const, label: 'W1', encoder_id: 8 },
          { id: 'bt_button', kind: 'button' as const, label: 'B' },
        ],
      },
      layout: {
        profile: 'wheelprof',
        columns: 2,
        rows: [
          {
            cells: [
              { label: 'W1', control: 'wheel_pan', col_span: 1, row_span: 1, color: null, row: null, col: null },
              { label: 'B', control: 'bt_button', col_span: 1, row_span: 1, color: null, row: null, col: null },
            ],
          },
        ],
      },
    };
    const cfgWithMod = {
      ...config,
      profiles: {
        ...config.profiles,
        wheelprof: {
          controls: [
            { id: 'wheel_pan', kind: 'relative-encoder', encoder_id: 8 },
            { id: 'bt_button', kind: 'button' },
          ],
          banks: [{ number: 1, channel: 1, notes: { '40': 'wheel_pan', '41': 'bt_button' } }],
        },
      },
      mapping: {
        ...config.mapping,
        keys: {},
        modifiers: { bt_button: { hardkey: 'MA' } },
      },
    };
    const api = fakeApi([customEncDevice], cfgWithMod);
    render(DevicesPage, { props: { api } });
    await waitFor(() => expect(screen.getByText('W1')).toBeTruthy());

    // Save custom-named relative-encoder -> uses encoder_id: 8
    await fireEvent.click(screen.getByText('W1'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    await fireEvent.input(screen.getByLabelText('Slot'), { target: { value: '3' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(1));
    expect(sentPatch(api)).toEqual({
      mapping: {
        encoders: expect.arrayContaining([{ id: 8, slot: 3 }]),
      },
    });

    await waitFor(() => expect(document.querySelector('dialog')).toBeNull());

    // Clear modifier on Bank 1 -> emits modifiers.bt_button = null
    await fireEvent.click(screen.getByText('B'));
    await fireEvent.click(screen.getByText('Zuweisen'));
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalledTimes(2));
    expect(sentPatch(api)).toEqual({
      mapping: {
        keys: { bt_button: null },
        playbacks: { bt_button: null },
        modifiers: { bt_button: null },
      },
    });
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import AssignmentDialog from './AssignmentDialog.svelte';
import { ApiError } from './api';
import type { ConfigStore } from './configStore.svelte';
import { controlsOf, type ControlInfo } from './deviceControls';
import { baseConfig, loadedStore, midicraft, type FakeDaemon } from './testing';

function control(id: string, bank = 1): ControlInfo {
  const found = controlsOf(midicraft, bank).find((entry) => entry.id === id);
  if (!found) throw new Error(`unknown control ${id}`);
  return found;
}

async function open(
  store: ConfigStore,
  ids: string[],
  bank = store.bank,
): Promise<{ onClose: ReturnType<typeof vi.fn> }> {
  const onClose = vi.fn();
  render(AssignmentDialog, {
    props: { store, controls: ids.map((id) => control(id, bank)), onClose },
  });
  return { onClose };
}

async function choose(label: string, value: string): Promise<void> {
  await fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function save(): Promise<void> {
  await fireEvent.click(screen.getByText('Speichern'));
}

function lastPatch(daemon: FakeDaemon): Record<string, any> {
  const patches = daemon.patches();
  return patches[patches.length - 1];
}

describe('AssignmentDialog actions', () => {
  it('saves a hardkey with all unused key fields as null', async () => {
    const { store, daemon } = await loadedStore();
    const { onClose } = await open(store, ['mc_click_1']);
    await choose('Aktion', 'hardkey');
    await fireEvent.input(screen.getByLabelText('Hardkey'), { target: { value: 'GO' } });
    await save();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(lastPatch(daemon).mapping.keys.mc_click_1).toEqual({
      hardkey: 'GO',
      command: null,
      screen_mode: null,
      encoder_press: null,
      screen: null,
    });
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ hardkey: 'GO' });
  });

  it('saves a command', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'command');
    await fireEvent.input(screen.getByLabelText('Command'), { target: { value: 'Go+' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ command: 'Go+' });
  });

  it('saves the screen mode toggle', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'screen_mode');
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ screen_mode: true });
  });

  it('saves a screen selection', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'screen');
    await fireEvent.input(screen.getByLabelText('Screen'), { target: { value: '3' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ screen: 3 });
  });

  it('saves an encoder click', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'encoder_press');
    await fireEvent.input(screen.getByLabelText('Encoder-Slot'), { target: { value: '2' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ encoder_press: 2 });
  });

  it('saves a playback target with transport', async () => {
    const { store, daemon } = await loadedStore({ ...baseConfig(), midi_remote: { enabled: true } });
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'executor');
    await fireEvent.input(screen.getByLabelText('Page'), { target: { value: '2' } });
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '7' } });
    await choose('Transport', 'midi');
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.playbacks.mc_click_1).toEqual({
      page: 2,
      executor: 7,
      kind: 'button',
      button: 1,
      transport: 'midi',
    });
  });

  it('saves a modifier as hardkey or local and nulls the key fields', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'modifier');
    await fireEvent.input(screen.getByLabelText('Hardkey'), { target: { value: 'SHIFT' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(lastPatch(daemon).mapping).toEqual({
      modifiers: { mc_click_1: { hardkey: 'SHIFT', local: null } },
      keys: { mc_click_1: null },
      playbacks: { mc_click_1: null },
    });
  });

  it('saves a local modifier', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'modifier');
    await choose('Modifier-Art', 'local');
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.modifiers.mc_click_1).toEqual({ local: true });
  });

  it('saves an encoder target by attribute name', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['encoder.1']);
    await choose('Ziel', 'attribute');
    await fireEvent.input(screen.getByLabelText('Attributname'), { target: { value: 'Dimmer' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.encoders).toEqual([{ id: 1, attribute: 'Dimmer' }]);
  });

  it('switching hardkey to command leaves no hardkey behind', async () => {
    const { store, daemon } = await loadedStore(
      baseConfig({ keys: { mc_click_1: { hardkey: 'GO' } } }),
    );
    await open(store, ['mc_click_1']);
    expect((screen.getByLabelText('Hardkey') as HTMLInputElement).value).toBe('GO');
    await choose('Aktion', 'command');
    await fireEvent.input(screen.getByLabelText('Command'), { target: { value: 'Go+' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ command: 'Go+' });
  });

  it('switching a playback from button to fader drops button and midi transport', async () => {
    const { store, daemon } = await loadedStore({
      ...baseConfig({
        playbacks: {
          mc_click_1: { page: 1, executor: 1, kind: 'button', button: 2, transport: 'midi' },
        },
      }),
      midi_remote: { enabled: true },
    });
    await open(store, ['mc_click_1']);
    await choose('Art', 'fader');
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    const entry = daemon.config().mapping.playbacks.mc_click_1;
    expect(entry.kind).toBe('fader');
    expect(entry.button).toBeUndefined();
    expect(entry.transport).toBeUndefined();
  });

  it('removes an assignment through the dialog', async () => {
    const { store, daemon } = await loadedStore(
      baseConfig({ keys: { mc_click_1: { hardkey: 'GO' } } }),
    );
    const { onClose } = await open(store, ['mc_click_1']);
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(daemon.config().mapping.keys.mc_click_1).toBeUndefined();
  });

  it('offers acceleration only for an absolute encoder fader target', async () => {
    const { store } = await loadedStore();
    await open(store, ['mc_encoder_1']);
    expect(screen.getByText('Beschleunigt')).toBeTruthy();
  });

  it('offers no acceleration for a fader control', async () => {
    const { store } = await loadedStore();
    await open(store, ['mc_fader_1']);
    expect(screen.queryByText('Beschleunigt')).toBeNull();
    expect((screen.getByLabelText('Art') as HTMLSelectElement).value).toBe('fader');
  });

  it('previews stepped executors for a multi assignment in click order', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1', 'mc_click_2']);
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '3' } });
    expect(screen.getByText('Vorschau: 3, 4')).toBeTruthy();
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    const playbacks = daemon.config().mapping.playbacks;
    expect(playbacks.mc_click_1.executor).toBe(3);
    expect(playbacks.mc_click_2.executor).toBe(4);
  });
});

describe('AssignmentDialog scope and source', () => {
  const inheritedConfig = () =>
    baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
    });

  it('shows an inherited target with the bank offset', async () => {
    const { store } = await loadedStore(inheritedConfig(), { bank: 2 });
    await open(store, ['mc_click_1']);
    expect((screen.getByLabelText('Executor') as HTMLInputElement).value).toBe('6');
    expect(screen.getByTestId('assignment-source').textContent).toContain(
      'geerbt mit Bank-Offset (Offset +5)',
    );
    expect((screen.getByLabelText('Geltungsbereich') as HTMLSelectElement).value).toBe('global');
  });

  it('does not store an inherited target as explicit when saved unchanged', async () => {
    const { store, daemon } = await loadedStore(inheritedConfig(), { bank: 2 });
    await open(store, ['mc_click_1']);
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    const patch = lastPatch(daemon);
    expect(patch.mapping.device_banks).toBeUndefined();
    expect(patch.mapping.playbacks.mc_click_1.executor).toBe(1);
    expect(daemon.config().mapping.device_banks.midicraft['2']).toBeUndefined();
  });

  it('writes an explicit bank entry only after choosing "nur diese Bank"', async () => {
    const { store, daemon } = await loadedStore(inheritedConfig(), { bank: 2 });
    await open(store, ['mc_click_1']);
    await choose('Geltungsbereich', 'bank');
    expect(screen.getByText(/folgt nicht mehr dem Bank-Offset/)).toBeTruthy();
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.device_banks.midicraft['2'].playbacks.mc_click_1.executor).toBe(6);
    expect(daemon.config().mapping.playbacks.mc_click_1.executor).toBe(1);
  });

  it('shows the raw global executor while editing an offset target globally', async () => {
    const { store, daemon } = await loadedStore(inheritedConfig(), { bank: 2 });
    await open(store, ['mc_click_1']);
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '8' } });
    expect(screen.getByTestId('raw-executor').textContent).toContain('Executor 3');
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.playbacks.mc_click_1.executor).toBe(3);
  });

  it('starts bank 1 without a layer on the global scope and offers the bank as alternative', async () => {
    const { store } = await loadedStore(inheritedConfig(), { bank: 1 });
    await open(store, ['mc_click_1']);
    expect((screen.getByLabelText('Geltungsbereich') as HTMLSelectElement).value).toBe('global');
    expect(screen.getByText('Nur Bank 1 (Override)')).toBeTruthy();
  });

  it('edits an existing bank 1 layer instead of writing beside it', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      device_banks: {
        midicraft: {
          bank_size: 5,
          '1': { playbacks: { mc_click_1: { page: 1, executor: 9, kind: 'button', button: 1 } } },
        },
      },
    });
    const { store, daemon } = await loadedStore(config, { bank: 1 });
    await open(store, ['mc_click_1']);
    expect((screen.getByLabelText('Geltungsbereich') as HTMLSelectElement).value).toBe('bank');
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '12' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.device_banks.midicraft['1'].playbacks.mc_click_1.executor).toBe(12);
    expect(daemon.config().mapping.playbacks.mc_click_1.executor).toBe(1);
  });

  it('removes a bank override and the inherited target is visible again', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      device_banks: {
        midicraft: {
          bank_size: 5,
          '2': { playbacks: { mc_click_1: { page: 1, executor: 20, kind: 'button', button: 1 } } },
        },
      },
    });
    const { store, daemon } = await loadedStore(config, { bank: 2 });
    await open(store, ['mc_click_1']);
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.playbacks.mc_click_1.executor).toBe(1);
    expect(store.resolve(control('mc_click_1', 2)).assignment).toMatchObject({ executor: 6 });
  });

  it('removes a global entry but keeps bank overrides', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      device_banks: {
        midicraft: {
          bank_size: 5,
          '2': { playbacks: { mc_click_1: { page: 1, executor: 20, kind: 'button', button: 1 } } },
        },
      },
    });
    const { store, daemon } = await loadedStore(config, { bank: 3 });
    await open(store, ['mc_click_1']);
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.playbacks.mc_click_1).toBeUndefined();
    expect(daemon.config().mapping.device_banks.midicraft['2'].playbacks.mc_click_1.executor).toBe(20);
  });
});

describe('AssignmentDialog screen encoders', () => {
  const encoderConfig = () =>
    baseConfig({
      encoders: [{ id: 1, slot: 2 }],
      screen_encoders: { '2': 7 },
    });

  it('shows the mapped screen encoder of the slot and clears it with "keiner"', async () => {
    const { store, daemon } = await loadedStore(encoderConfig());
    await open(store, ['encoder.1']);
    expect((screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement).value).toBe('7');
    await fireEvent.change(screen.getByLabelText(/Screen-Encoder/), { target: { value: '0' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.screen_encoders).toEqual({});
    expect(daemon.config().mapping.encoders).toEqual([{ id: 1, slot: 2 }]);
  });

  it('moves the screen encoder when the slot changes', async () => {
    const { store, daemon } = await loadedStore(encoderConfig());
    await open(store, ['encoder.1']);
    await fireEvent.input(screen.getByLabelText('Slot'), { target: { value: '3' } });
    expect((screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement).value).toBe('0');
    await fireEvent.change(screen.getByLabelText(/Screen-Encoder/), { target: { value: '9' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.screen_encoders).toEqual({ '3': 9 });
  });

  it('clears the screen encoder when switching to an attribute', async () => {
    const { store, daemon } = await loadedStore(encoderConfig());
    await open(store, ['encoder.1']);
    await choose('Ziel', 'attribute');
    await fireEvent.input(screen.getByLabelText('Attributname'), { target: { value: 'Dimmer' } });
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.screen_encoders).toEqual({});
    expect(daemon.config().mapping.encoders).toEqual([{ id: 1, attribute: 'Dimmer' }]);
  });

  it('does not offer screen encoders for a bank override', async () => {
    const { store } = await loadedStore(encoderConfig(), { bank: 2 });
    await open(store, ['encoder.1']);
    expect(screen.getByLabelText(/Screen-Encoder/)).toBeTruthy();
    await choose('Geltungsbereich', 'bank');
    expect(screen.queryByLabelText(/Screen-Encoder/)).toBeNull();
  });
});

describe('AssignmentDialog errors', () => {
  it('shows a backend field error at the field and keeps the configuration', async () => {
    const { store, daemon } = await loadedStore();
    vi.mocked(daemon.api.updateConfig).mockRejectedValueOnce(
      new ApiError(
        422,
        'validation_error',
        'Executor 99 existiert nicht',
        'mapping.playbacks.mc_click_1.executor',
      ),
    );
    const { onClose } = await open(store, ['mc_click_1']);
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '99' } });
    await save();
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toBe('Executor 99 existiert nicht');
    expect(alert.getAttribute('data-field')).toBe('executor');
    expect(onClose).not.toHaveBeenCalled();
    expect(daemon.config().mapping.playbacks).toEqual({});
  });

  it.each([
    ['page', 'mapping.playbacks.mc_click_1.page'],
    ['transport', 'mapping.playbacks.mc_click_1.transport'],
  ])('shows a rejected %s at its own field', async (field, path) => {
    const { store, daemon } = await loadedStore();
    vi.mocked(daemon.api.updateConfig).mockRejectedValueOnce(
      new ApiError(422, 'validation_error', `${field} abgelehnt`, path),
    );
    await open(store, ['mc_click_1']);
    await save();
    const alert = await screen.findByRole('alert');
    expect(alert.getAttribute('data-field')).toBe(field);
    expect(alert.textContent).toBe(`${field} abgelehnt`);
  });

  it('shows an invalid screen encoder at the screen encoder field', async () => {
    const { store, daemon } = await loadedStore();
    vi.mocked(daemon.api.updateConfig).mockRejectedValueOnce(
      new ApiError(
        422,
        'validation_error',
        'Screen-Encoder 11 ungültig',
        'mapping.screen_encoders.1',
      ),
    );
    await open(store, ['encoder.1']);
    await save();
    const alert = await screen.findByRole('alert');
    expect(alert.getAttribute('data-field')).toBe('encoderScreen');
    expect(daemon.config().mapping.screen_encoders).toEqual({});
  });

  it('validates locally before sending', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    await choose('Aktion', 'command');
    await save();
    const alert = await screen.findByRole('alert');
    expect(alert.getAttribute('data-field')).toBe('command');
    expect(daemon.patches().length).toBe(0);
  });

  it('reports a stale configuration without overwriting anything', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['mc_click_1']);
    daemon.externalWrite({ mapping: { keys: { other: { hardkey: 'X' } } } });
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '4' } });
    await save();
    await waitFor(() => expect(store.conflict).toBe(true));
    expect(daemon.config().mapping.playbacks).toEqual({});
    expect((await screen.findByRole('alert')).textContent).toContain('geändert');
  });
});

describe('AssignmentDialog behaviour', () => {
  it('renders inside a native dialog and closes on Escape', async () => {
    const { store } = await loadedStore();
    const onClose = vi.fn();
    const { container } = render(AssignmentDialog, {
      props: { store, controls: [control('mc_click_1')], onClose },
    });
    const dialog = container.querySelector('dialog');
    expect(dialog?.hasAttribute('open')).toBe(true);
    await fireEvent.keyDown(dialog!, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('allows encoder targets only for a single control', async () => {
    const { store, daemon } = await loadedStore();
    await open(store, ['encoder.1', 'encoder.1']);
    expect(screen.getByText('Encoder-Ziele nur für ein einzelnes Control.')).toBeTruthy();
    const submit = screen.getByRole('button', { name: 'Speichern' }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    expect(daemon.patches().length).toBe(0);
  });

  it('rejects an empty attribute name and refreshes the screen encoder on slot change', async () => {
    const { store, daemon } = await loadedStore(
      baseConfig({ encoders: [{ id: 1, slot: 1 }], screen_encoders: { '1': 8, '2': 6 } }),
    );
    await open(store, ['encoder.1']);
    await fireEvent.input(screen.getByLabelText('Slot'), { target: { value: '2' } });
    expect((screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement).value).toBe('6');
    await choose('Ziel', 'attribute');
    await save();
    expect((await screen.findByRole('alert')).textContent).toContain('Attributname');
    expect(daemon.patches().length).toBe(0);
  });

  it('keeps a screen-mode mapping when saved unchanged', async () => {
    const { store, daemon } = await loadedStore(
      baseConfig({ keys: { mc_click_1: { screen_mode: true } } }),
    );
    await open(store, ['mc_click_1']);
    expect((screen.getByLabelText('Aktion') as HTMLSelectElement).value).toBe('screen_mode');
    await save();
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.keys.mc_click_1).toEqual({ screen_mode: true });
  });
});

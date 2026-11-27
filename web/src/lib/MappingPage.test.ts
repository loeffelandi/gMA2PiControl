import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import DevicesPage from './DevicesPage.svelte';
import MappingPage from './MappingPage.svelte';
import { ConfigStore } from './configStore.svelte';
import type { DeviceEntry } from './api';
import { baseConfig, fakeDaemon, fakeStatus, midicraft } from './testing';

function row(id: string): HTMLElement {
  const found = document.querySelector<HTMLElement>(`tr[data-control="${id}"]`);
  if (!found) throw new Error(`row ${id} missing`);
  return found;
}

async function mount(
  config = baseConfig(),
  options: { bank?: number; devices?: DeviceEntry[] } = {},
) {
  const live = fakeStatus();
  const daemon = fakeDaemon(config, options.devices ?? [midicraft]);
  const configStore = new ConfigStore(daemon.api, live.status);
  const onOpenDevices = vi.fn();
  const view = render(MappingPage, { props: { api: daemon.api, configStore, onOpenDevices } });
  await waitFor(() => expect(configStore.loaded).toBe(true));
  if (options.bank) configStore.selectBank(options.bank);
  return { daemon, configStore, onOpenDevices, view, ...live };
}

describe('MappingPage control source', () => {
  it('lists inventory controls and the controls bound only in another bank', async () => {
    const { configStore } = await mount();
    for (const id of ['mc_click_1', 'mc_fader_1', 'mc_encoder_1', 'encoder.1']) {
      expect(row(id)).toBeTruthy();
    }
    configStore.selectBank(3);
    await waitFor(() => expect(row('mc_bank3_only')).toBeTruthy());
    expect(row('mc_bank3_only').textContent).not.toContain('nicht in Bank 3 gebunden');
    expect(row('mc_click_1').textContent).toContain('nicht in Bank 3 gebunden');
  });

  it('offers the same controls as the device tab', async () => {
    const daemon = fakeDaemon(baseConfig(), [midicraft]);
    const configStore = new ConfigStore(daemon.api);
    const mapping = render(MappingPage, { props: { api: daemon.api, configStore } });
    const devices = render(DevicesPage, { props: { api: daemon.api, configStore } });
    await waitFor(() => expect(configStore.loaded).toBe(true));
    for (const id of ['mc_fader_1', 'mc_encoder_1', 'encoder.1']) {
      expect(within(mapping.container).getByText(id, { exact: false })).toBeTruthy();
      expect(within(devices.container).getByRole('button', { name: id })).toBeTruthy();
    }
    configStore.selectBank(3);
    await waitFor(() =>
      expect(within(devices.container).getByRole('button', { name: 'mc_bank3_only' })).toBeTruthy(),
    );
    expect(within(mapping.container).getByText('mc_bank3_only', { exact: false })).toBeTruthy();
  });

  it('hides a configured but disconnected device', async () => {
    const offline: DeviceEntry = { ...midicraft, name: 'offline', detected: null };
    await mount(baseConfig(), { devices: [midicraft, offline] });
    expect(screen.queryByText('offline')).toBeNull();
    expect(screen.getAllByText('midicraft').length).toBeGreaterThan(0);
  });
});

describe('MappingPage effective assignment', () => {
  const inherited = () =>
    baseConfig({ playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } } });

  it('shows the inherited executor of bank 2 with its offset', async () => {
    await mount(inherited(), { bank: 2 });
    await waitFor(() => expect(row('mc_click_1').textContent).toContain('Exec 6 Btn 1'));
    expect(within(row('mc_click_1')).getByTestId('source-badge').textContent).toBe(
      'geerbt mit Bank-Offset (Offset +5)',
    );
  });

  it('shows an explicit bank entry as such and leaves global untouched', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      device_banks: {
        midicraft: {
          bank_size: 5,
          '2': { playbacks: { mc_click_1: { page: 1, executor: 20, kind: 'button', button: 1 } } },
        },
      },
    });
    await mount(config, { bank: 2 });
    await waitFor(() => expect(row('mc_click_1').textContent).toContain('Exec 20 Btn 1'));
    expect(within(row('mc_click_1')).getByTestId('source-badge').textContent).toBe('Bank-Eintrag');
  });

  it('shows the same bank settings read-only', async () => {
    const { configStore } = await mount(inherited(), { bank: 2 });
    const readonly = await screen.findByTestId('bank-settings-readonly');
    expect(readonly.textContent).toContain('5');
    expect(readonly.textContent).toContain('2');
    expect(screen.queryByText('Einstellungen speichern')).toBeNull();
    expect(configStore.bank).toBe(2);
  });
});

describe('MappingPage editing through the shared dialog', () => {
  it('removes a bank override and shows the inherited target again', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      device_banks: {
        midicraft: {
          bank_size: 5,
          '2': { playbacks: { mc_click_1: { page: 1, executor: 20, kind: 'button', button: 1 } } },
        },
      },
    });
    const { daemon } = await mount(config, { bank: 2 });
    await fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten mc_click_1' }));
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(row('mc_click_1').textContent).toContain('Exec 6 Btn 1'));
    expect(daemon.config().mapping.playbacks.mc_click_1.executor).toBe(1);
  });

  it('removes a global entry', async () => {
    const { daemon } = await mount(baseConfig({ keys: { mc_click_1: { hardkey: 'GO' } } }));
    await waitFor(() => expect(row('mc_click_1').textContent).toContain('GO'));
    await fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten mc_click_1' }));
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(daemon.config().mapping.keys.mc_click_1).toBeUndefined());
    await waitFor(() => expect(row('mc_click_1').textContent).toContain('–'));
  });

  it('switches hardkey to command without leftovers', async () => {
    const { daemon } = await mount(baseConfig({ keys: { mc_click_1: { hardkey: 'GO' } } }));
    await fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten mc_click_1' }));
    await fireEvent.change(screen.getByLabelText('Aktion'), { target: { value: 'command' } });
    await fireEvent.input(screen.getByLabelText('Command'), { target: { value: 'Go+' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(daemon.config().mapping.keys.mc_click_1).toEqual({ command: 'Go+' }));
    await waitFor(() => expect(row('mc_click_1').textContent).toContain('Go+'));
  });

  it('overrides an inherited target only after choosing the bank scope', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
    });
    const { daemon } = await mount(config, { bank: 2 });
    await fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten mc_click_1' }));
    await fireEvent.change(screen.getByLabelText('Geltungsbereich'), { target: { value: 'bank' } });
    await fireEvent.input(screen.getByLabelText('Executor'), { target: { value: '9' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() =>
      expect(daemon.config().mapping.device_banks.midicraft['2'].playbacks.mc_click_1.executor).toBe(9),
    );
    expect(daemon.config().mapping.playbacks.mc_click_1.executor).toBe(1);
    await waitFor(() =>
      expect(within(row('mc_click_1')).getByTestId('source-badge').textContent).toBe('Bank-Eintrag'),
    );
  });

  it('removes entries of a device that is not connected', async () => {
    const config = baseConfig({ keys: { ghost_key: { hardkey: 'GO' } } });
    const { daemon } = await mount(config);
    await fireEvent.click(await screen.findByRole('button', { name: 'Entfernen ghost_key' }));
    await waitFor(() => expect(daemon.config().mapping.keys.ghost_key).toBeUndefined());
  });
});

describe('MappingPage acceleration and transport', () => {
  const config = () => ({
    ...baseConfig({
      playbacks: {
        mc_encoder_1: { page: 1, executor: 3, kind: 'fader', accelerated: true },
        mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1, transport: 'midi' },
      },
    }),
    midi_remote: { enabled: true },
  });

  it('shows the active acceleration checkbox for an inventory encoder', async () => {
    await mount(config());
    await fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten mc_encoder_1' }));
    expect((screen.getByLabelText('Beschleunigt') as HTMLInputElement).checked).toBe(true);
    expect(row('mc_encoder_1').textContent).toContain('acc');
  });

  it('shows a midi button target and saves a changed transport', async () => {
    const { daemon } = await mount(config());
    expect(row('mc_click_1').textContent).toContain('Exec 1 Btn 1 · midi');
    await fireEvent.click(screen.getByRole('button', { name: 'Bearbeiten mc_click_1' }));
    expect((screen.getByLabelText('Transport') as HTMLSelectElement).value).toBe('midi');
    await fireEvent.change(screen.getByLabelText('Transport'), { target: { value: 'web' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(daemon.config().mapping.playbacks.mc_click_1.transport).toBe('web'));
  });
});

describe('MappingPage learn', () => {
  it('starts note learning for device and bank, shows progress and links to the device tab', async () => {
    const { daemon, push, onOpenDevices } = await mount(baseConfig(), { bank: 2 });
    await fireEvent.click(screen.getByText('Noten anlernen (Bank 2)'));
    expect(daemon.api.startDeviceLearn).toHaveBeenCalledWith('midicraft', 2);

    push('device_learn', {
      active: true,
      device: 'midicraft',
      bank: 2,
      channel: 2,
      current: 'mc_fader_1',
      total: 3,
      index: 0,
    });
    const status = await screen.findByTestId('note-learn-active');
    expect(status.textContent).toContain('mc_fader_1');
    await fireEvent.click(within(status).getByText('Zum Geräte-Tab'));
    expect(onOpenDevices).toHaveBeenCalled();
  });

  it('shows a control detected elsewhere and offers to assign it', async () => {
    const { push } = await mount();
    push('learn', {
      kind: 'key',
      status: 'captured',
      control: 'mc_click_2',
      device: 'midicraft',
    });
    const detected = await screen.findByTestId('learn-detected');
    expect(detected.textContent).toContain('mc_click_2');
    expect(row('mc_click_2').className).toContain('detected');
    await fireEvent.click(within(detected).getByText('Zuweisen'));
    expect(screen.getByText(/mc_click_2 · Bank 1/)).toBeTruthy();
  });

  it('resets after a timeout without touching the configuration', async () => {
    const { daemon, push } = await mount();
    await fireEvent.click(screen.getByText('Taste erkennen'));
    expect(daemon.api.startLearn).toHaveBeenCalledWith('key', 'midicraft');
    push('learn', { kind: 'key', status: 'active', control: null, device: 'midicraft' });
    await screen.findByTestId('learn-active');
    expect((screen.getByText('Encoder erkennen') as HTMLButtonElement).disabled).toBe(true);

    push('learn', { kind: 'key', status: 'timeout', control: null, device: 'midicraft' });
    await screen.findByTestId('learn-ended');
    expect((screen.getByText('Encoder erkennen') as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByText('Taste erkennen') as HTMLButtonElement).disabled).toBe(false);
    expect(daemon.patches()).toEqual([]);
  });

  it('refuses a second session while one runs', async () => {
    const { daemon, push } = await mount();
    push('device_learn', { active: true, device: 'midicraft', bank: 1, current: 'mc_click_1' });
    await screen.findByTestId('note-learn-active');
    expect((screen.getByText('Taste erkennen') as HTMLButtonElement).disabled).toBe(true);
    expect(daemon.api.startLearn).not.toHaveBeenCalled();
  });
});

describe('MappingPage priority', () => {
  it('flags a layer key that shadows a playback target, with the layers involved', async () => {
    const config = baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      device_banks: {
        midicraft: { bank_size: 5, '1': { keys: { mc_click_1: { hardkey: 'GO' } } } },
      },
    });
    await mount(config);
    const badge = await within(row('mc_click_1')).findByTestId('conflict-badge');
    expect(badge.getAttribute('title')).toBe('Bank-Taste hat Vorrang vor dem Playback-Ziel.');
    expect(within(row('mc_click_1')).getByTestId('conflict-explanation').textContent).toBe(
      'Bank-Taste hat Vorrang vor dem Playback-Ziel.',
    );
  });

  it('shows no conflict badge for an encoder with a playback target', async () => {
    const config = baseConfig({
      playbacks: { 'encoder.1': { page: 1, executor: 1, kind: 'fader' } },
      encoders: [{ id: 1, slot: 1 }],
    });
    await mount(config);
    expect(within(row('encoder.1')).queryByTestId('conflict-badge')).toBeNull();
  });
});

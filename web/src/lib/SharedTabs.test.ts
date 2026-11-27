import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

import DevicesPage from './DevicesPage.svelte';
import MappingPage from './MappingPage.svelte';
import { ConfigStore } from './configStore.svelte';
import type { DeviceEntry } from './api';
import { baseConfig, fakeDaemon, fakeStatus, midicraft } from './testing';

const withLayout: DeviceEntry = {
  ...midicraft,
  layout: {
    profile: 'midicraft',
    columns: 2,
    rows: [
      {
        cells: [
          { label: 'K1', control: 'mc_click_1', col_span: 1, row_span: 1, color: null, row: 1, col: 1 },
          { label: 'F1', control: 'mc_fader_1', col_span: 1, row_span: 1, color: null, row: 1, col: 2 },
        ],
      },
    ],
  },
};

async function bothTabs(config = baseConfig(), devices: DeviceEntry[] = [midicraft]) {
  const live = fakeStatus();
  const daemon = fakeDaemon(config, devices);
  const configStore = new ConfigStore(daemon.api, live.status);
  const mapping = render(MappingPage, { props: { api: daemon.api, configStore } });
  const devicesTab = render(DevicesPage, { props: { api: daemon.api, store: live.status, configStore } });
  await waitFor(() => expect(configStore.loaded).toBe(true));
  return { daemon, configStore, mapping, devicesTab, ...live };
}

function mappingRow(view: { container: HTMLElement }, id: string): HTMLElement {
  const found = view.container.querySelector<HTMLElement>(`tr[data-control="${id}"]`);
  if (!found) throw new Error(`row ${id} missing`);
  return found;
}

function deviceRow(view: { container: HTMLElement }, id: string): HTMLElement {
  const button = within(view.container).getByRole('button', { name: id });
  return button.closest('tr') as HTMLElement;
}

describe('shared configuration state', () => {
  it('shows a change saved in one tab in the other without reloading', async () => {
    const { daemon, mapping, devicesTab } = await bothTabs();
    await fireEvent.click(within(devicesTab.container).getByRole('button', { name: 'mc_click_1' }));
    await fireEvent.click(within(devicesTab.container).getByText('Zuweisen'));
    await fireEvent.change(screen.getByLabelText('Aktion'), { target: { value: 'hardkey' } });
    await fireEvent.input(screen.getByLabelText('Hardkey'), { target: { value: 'GO' } });
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(mappingRow(mapping, 'mc_click_1').textContent).toContain('GO'));
    expect(deviceRow(devicesTab, 'mc_click_1').textContent).toContain('GO');
    expect(daemon.api.configSnapshot).toHaveBeenCalledTimes(1);
  });

  it('removes in the device tab and in the mapping tab alike', async () => {
    const config = baseConfig({ keys: { mc_click_1: { hardkey: 'GO' } } });
    const { daemon, mapping, devicesTab } = await bothTabs(config);
    await fireEvent.click(within(devicesTab.container).getByRole('button', { name: 'mc_click_1' }));
    await fireEvent.click(within(devicesTab.container).getByText('Zuweisen'));
    await fireEvent.click(screen.getByText('Belegung entfernen'));
    await waitFor(() => expect(daemon.config().mapping.keys.mc_click_1).toBeUndefined());
    await waitFor(() => expect(mappingRow(mapping, 'mc_click_1').textContent).not.toContain('GO'));
    expect(deviceRow(devicesTab, 'mc_click_1').textContent).not.toContain('GO');
  });

  it('keeps device and bank when the tab changes', async () => {
    const live = fakeStatus();
    const daemon = fakeDaemon(baseConfig(), [midicraft]);
    const configStore = new ConfigStore(daemon.api, live.status);
    const first = render(MappingPage, { props: { api: daemon.api, configStore } });
    await waitFor(() => expect(configStore.loaded).toBe(true));
    await fireEvent.change(within(first.container).getByLabelText('Bank'), { target: { value: '2' } });
    first.unmount();
    const second = render(DevicesPage, { props: { api: daemon.api, store: live.status, configStore } });
    await waitFor(() =>
      expect((within(second.container).getByLabelText('Bank') as HTMLSelectElement).value).toBe('2'),
    );
  });

  it('drops the selection when the device disappears from both tabs', async () => {
    const other: DeviceEntry = { ...midicraft, name: 'second', profile: 'second' };
    const { configStore, mapping, devicesTab, push } = await bothTabs(baseConfig(), [midicraft, other]);
    configStore.selectDevice('second');
    await waitFor(() => expect(within(mapping.container).getAllByText('second').length).toBeGreaterThan(0));
    push('status', {
      presence: {
        midicraft: { connected: true, path: '/dev/x', seen: true },
        second: { connected: false, path: null, seen: false },
      },
    });
    await waitFor(() => expect(configStore.selectedDevice).toBe('midicraft'));
    expect(within(mapping.container).queryByText('second')).toBeNull();
    expect(within(devicesTab.container).queryByText('second')).toBeNull();
  });
});

describe('device tab on the shared model', () => {
  it('shows the same bank settings in both tabs', async () => {
    const config = baseConfig({
      device_banks: { midicraft: { bank_size: 7, '2': { ma_page: 4 } } },
    });
    const { configStore, mapping, devicesTab } = await bothTabs(config, [
      { ...midicraft, bank_size: 7 },
    ]);
    configStore.selectBank(2);
    const readonly = await within(mapping.container).findByTestId('bank-settings-readonly');
    await waitFor(() =>
      expect((within(devicesTab.container).getByLabelText('MA-Page') as HTMLInputElement).value).toBe('4'),
    );
    expect(readonly.textContent).toContain('4');
    expect((within(devicesTab.container).getByLabelText('Bankgröße') as HTMLInputElement).value).toBe('7');
    expect(readonly.textContent).toContain('7');
    expect((within(devicesTab.container).getByLabelText('Kanal') as HTMLInputElement).value).toBe('2');
  });

  it('does not freeze an inherited encoder target of bank 2 into the bank layer', async () => {
    const config = baseConfig({ encoders: [{ id: 1, slot: 1 }], screen_encoders: { '1': 8 } });
    const { daemon, configStore, devicesTab } = await bothTabs(config);
    configStore.selectBank(2);
    await fireEvent.click(within(devicesTab.container).getByRole('button', { name: 'encoder.1' }));
    await fireEvent.click(within(devicesTab.container).getByText('Zuweisen'));
    await fireEvent.click(screen.getByText('Speichern'));
    await waitFor(() => expect(daemon.patches().length).toBe(1));
    expect(daemon.config().mapping.device_banks.midicraft['2']).toBeUndefined();
    expect(daemon.config().mapping.screen_encoders).toEqual({ '1': 8 });
  });
});

describe('learn across both tabs', () => {
  it('starts detection in the device tab and shows the result in both', async () => {
    const { daemon, mapping, devicesTab, push } = await bothTabs();
    await fireEvent.click(within(devicesTab.container).getByText('Taste erkennen'));
    expect(daemon.api.startLearn).toHaveBeenCalledWith('key', 'midicraft');
    push('learn', { kind: 'key', status: 'active', control: null, device: 'midicraft' });
    await within(mapping.container).findByTestId('learn-active');
    await within(devicesTab.container).findByTestId('learn-active');

    push('learn', { kind: 'key', status: 'captured', control: 'mc_click_2', device: 'midicraft' });
    const inMapping = await within(mapping.container).findByTestId('learn-detected');
    const inDevices = await within(devicesTab.container).findByTestId('learn-detected');
    expect(inMapping.textContent).toContain('mc_click_2');
    expect(inDevices.textContent).toContain('mc_click_2');
    expect(daemon.patches()).toEqual([]);
  });

  it('resets both tabs on timeout and on cancel', async () => {
    const { daemon, mapping, devicesTab, push } = await bothTabs();
    push('learn', { kind: 'encoder', status: 'active', control: null, device: 'midicraft' });
    await within(devicesTab.container).findByTestId('learn-active');
    for (const view of [mapping, devicesTab]) {
      expect((within(view.container).getByText('Taste erkennen') as HTMLButtonElement).disabled).toBe(true);
    }
    push('learn', { kind: 'encoder', status: 'timeout', control: null, device: 'midicraft' });
    await waitFor(() => expect(within(devicesTab.container).queryByTestId('learn-active')).toBeNull());
    for (const view of [mapping, devicesTab]) {
      expect((within(view.container).getByText('Taste erkennen') as HTMLButtonElement).disabled).toBe(false);
    }

    push('learn', { kind: 'key', status: 'active', control: null, device: 'midicraft' });
    await within(mapping.container).findByTestId('learn-active');
    await fireEvent.click(within(mapping.container).getByText('Abbrechen'));
    expect(daemon.api.cancelLearn).toHaveBeenCalled();
    await waitFor(() => expect(within(devicesTab.container).queryByTestId('learn-active')).toBeNull());
    expect((within(devicesTab.container).getByText('Encoder erkennen') as HTMLButtonElement).disabled).toBe(false);
    expect(daemon.patches()).toEqual([]);
  });

  it('shows a note session started in the mapping tab on the device tab', async () => {
    const { daemon, mapping, devicesTab, push } = await bothTabs();
    await fireEvent.click(within(mapping.container).getByText('Noten anlernen (Bank 1)'));
    expect(daemon.api.startDeviceLearn).toHaveBeenCalledWith('midicraft', 1);
    const session = {
      active: true,
      device: 'midicraft',
      bank: 1,
      channel: 1,
      current: 'mc_fader_1',
      total: 2,
      index: 0,
    };
    daemon.setDeviceLearn(session);
    push('device_learn', session);
    await waitFor(() =>
      expect(within(devicesTab.container).getAllByText('mc_fader_1', { selector: 'strong' }).length).toBe(2),
    );
    expect(within(devicesTab.container).getByText('Überspringen')).toBeTruthy();
  });
});

describe('priority in the device tab', () => {
  const conflicting = () =>
    baseConfig({
      playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 } },
      keys: { mc_click_1: { hardkey: 'GO' } },
    });

  it('marks a playback target over a global key in the table and explains the layers', async () => {
    const { devicesTab } = await bothTabs(conflicting());
    const row = deviceRow(devicesTab, 'mc_click_1');
    expect(within(row).getByTestId('conflict-badge')).toBeTruthy();
    expect(within(row).getByTestId('conflict-explanation').textContent).toBe(
      'Playback-Ziel hat Vorrang vor der globalen Taste.',
    );
  });

  it('marks the conflict on the device surface with the explanation as tooltip', async () => {
    const { devicesTab } = await bothTabs(conflicting(), [withLayout]);
    const surface = within(devicesTab.container).getByTestId('device-surface');
    const badge = within(surface).getByTestId('conflict-badge');
    expect(badge.getAttribute('title')).toBe('Playback-Ziel hat Vorrang vor der globalen Taste.');
    expect(within(surface).getAllByTestId('conflict-badge').length).toBe(1);
  });
});

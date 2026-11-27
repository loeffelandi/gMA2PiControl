import { fireEvent, render, screen, waitFor, within } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';

import DevicesPage from './DevicesPage.svelte';
import MappingPage from './MappingPage.svelte';
import { ConfigStore } from './configStore.svelte';
import { controlsOf } from './deviceControls';
import { baseConfig, fakeDaemon, fakeStatus, midicraft } from './testing';

type Tab = 'mapping' | 'devices';

interface Scenario {
  name: string;
  control: string;
  scope: 'global' | 'bank' | null;
  config?: () => Record<string, any>;
  /** Fill the dialog; `remove` clicks "Belegung entfernen" instead of saving. */
  steps: () => Promise<void>;
  remove?: boolean;
}

async function set(label: string | RegExp, value: string): Promise<void> {
  await fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
async function type(label: string | RegExp, value: string): Promise<void> {
  await fireEvent.input(screen.getByLabelText(label), { target: { value } });
}

const midiRemote = () => ({ ...baseConfig(), midi_remote: { enabled: true } });

const scenarios: Scenario[] = [
  ...(['global', 'bank'] as const).flatMap((scope): Scenario[] => [
    {
      name: `hardkey (${scope})`,
      control: 'mc_click_1',
      scope,
      steps: async () => {
        await set('Aktion', 'hardkey');
        await type('Hardkey', 'GO');
      },
    },
    {
      name: `command (${scope})`,
      control: 'mc_click_1',
      scope,
      steps: async () => {
        await set('Aktion', 'command');
        await type('Command', 'Go+');
      },
    },
    {
      name: `screen mode (${scope})`,
      control: 'mc_click_1',
      scope,
      steps: () => set('Aktion', 'screen_mode'),
    },
    {
      name: `screen selection (${scope})`,
      control: 'mc_click_1',
      scope,
      steps: async () => {
        await set('Aktion', 'screen');
        await type('Screen', '3');
      },
    },
    {
      name: `encoder click (${scope})`,
      control: 'mc_click_1',
      scope,
      steps: async () => {
        await set('Aktion', 'encoder_press');
        await type('Encoder-Slot', '2');
      },
    },
    {
      name: `playback button with midi transport (${scope})`,
      control: 'mc_click_1',
      scope,
      config: midiRemote,
      steps: async () => {
        await type('Page', '2');
        await type('Executor', '8');
        await set('Transport', 'midi');
      },
    },
    {
      name: `accelerated encoder fader (${scope})`,
      control: 'mc_encoder_1',
      scope,
      steps: async () => {
        await type('Executor', '7');
        await fireEvent.click(screen.getByLabelText('Beschleunigt'));
      },
    },
    {
      name: `fader under a global midi button (${scope})`,
      control: 'mc_fader_1',
      scope,
      config: () => ({
        ...midiRemote(),
        mapping: {
          ...baseConfig().mapping,
          playbacks: { mc_fader_1: { page: 1, executor: 1, kind: 'button', button: 1, transport: 'midi' } },
        },
      }),
      steps: async () => {
        await set('Art', 'fader');
        await type('Executor', '9');
      },
    },
    {
      name: `encoder by attribute (${scope})`,
      control: 'encoder.1',
      scope,
      steps: async () => {
        await set('Ziel', 'attribute');
        await type('Attributname', 'Dimmer');
      },
    },
    {
      name: `encoder slot (${scope})`,
      control: 'encoder.1',
      scope,
      steps: async () => {
        await type('Slot', '2');
      },
    },
    {
      name: `remove (${scope})`,
      control: 'mc_click_1',
      scope,
      remove: true,
      config: () =>
        baseConfig({
          keys: { mc_click_1: { hardkey: 'GO' } },
          device_banks: {
            midicraft: {
              bank_size: 5,
              '2': { keys: { mc_click_1: { command: 'Go+' } } },
            },
          },
        }),
      steps: async () => undefined,
    },
  ]),
  {
    name: 'encoder slot with screen encoder (global)',
    control: 'encoder.1',
    scope: 'global',
    steps: async () => {
      await type('Slot', '3');
      await set(/Screen-Encoder/, '9');
    },
  },
  {
    name: 'modifier hardkey',
    control: 'mc_click_1',
    scope: null,
    steps: async () => {
      await set('Aktion', 'modifier');
      await type('Hardkey', 'SHIFT');
    },
  },
  {
    name: 'local modifier',
    control: 'mc_click_1',
    scope: null,
    steps: async () => {
      await set('Aktion', 'modifier');
      await set('Modifier-Art', 'local');
    },
  },
];

async function run(tab: Tab, scenario: Scenario) {
  const live = fakeStatus();
  const daemon = fakeDaemon((scenario.config ?? baseConfig)(), [midicraft]);
  const store = new ConfigStore(daemon.api, live.status);
  const view =
    tab === 'mapping'
      ? render(MappingPage, { props: { api: daemon.api, configStore: store } })
      : render(DevicesPage, { props: { api: daemon.api, store: live.status, configStore: store } });
  await waitFor(() => expect(store.loaded).toBe(true));
  store.selectBank(2);

  if (tab === 'mapping') {
    await fireEvent.click(
      await within(view.container).findByRole('button', { name: `Bearbeiten ${scenario.control}` }),
    );
  } else {
    await fireEvent.click(await within(view.container).findByRole('button', { name: scenario.control }));
    await fireEvent.click(within(view.container).getByText('Zuweisen'));
  }
  if (scenario.scope) await set('Geltungsbereich', scenario.scope);
  await scenario.steps();
  if (scenario.remove) await fireEvent.click(screen.getByText('Belegung entfernen'));
  else await fireEvent.click(screen.getByText('Speichern'));
  await waitFor(() => expect(document.querySelector('dialog')).toBeNull());

  const info = controlsOf(midicraft, 2).find((entry) => entry.id === scenario.control)!;
  const result = {
    config: daemon.config(),
    patch: daemon.patches(),
    bank2: store.resolve(info),
    label: store.labelFor(info),
  };
  view.unmount();
  return result;
}

describe('parity matrix: both tabs write and show the same', () => {
  it.each(scenarios)('$name', async (scenario) => {
    const fromMapping = await run('mapping', scenario);
    const fromDevices = await run('devices', scenario);
    expect(fromDevices.patch).toEqual(fromMapping.patch);
    expect(fromDevices.config).toEqual(fromMapping.config);
    expect(fromDevices.bank2).toEqual(fromMapping.bank2);
    expect(fromDevices.label).toEqual(fromMapping.label);
    expect(fromMapping.patch.length).toBe(1);
  });

  it('shows an accelerated inventory encoder with the active checkbox in both tabs', async () => {
    const config = baseConfig({
      playbacks: { mc_encoder_1: { page: 1, executor: 3, kind: 'fader', accelerated: true } },
    });
    for (const tab of ['mapping', 'devices'] as const) {
      const live = fakeStatus();
      const daemon = fakeDaemon(config, [midicraft]);
      const store = new ConfigStore(daemon.api, live.status);
      const view =
        tab === 'mapping'
          ? render(MappingPage, { props: { api: daemon.api, configStore: store } })
          : render(DevicesPage, { props: { api: daemon.api, store: live.status, configStore: store } });
      await waitFor(() => expect(store.loaded).toBe(true));
      if (tab === 'mapping') {
        await fireEvent.click(
          await within(view.container).findByRole('button', { name: 'Bearbeiten mc_encoder_1' }),
        );
      } else {
        await fireEvent.click(await within(view.container).findByRole('button', { name: 'mc_encoder_1' }));
        await fireEvent.click(within(view.container).getByText('Zuweisen'));
      }
      expect((screen.getByLabelText('Beschleunigt') as HTMLInputElement).checked).toBe(true);
      view.unmount();
    }
  });

  it('shows a midi button target the same in both tabs', async () => {
    const config = {
      ...baseConfig({
        playbacks: { mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1, transport: 'midi' } },
      }),
      midi_remote: { enabled: true },
    };
    const texts: string[] = [];
    for (const tab of ['mapping', 'devices'] as const) {
      const live = fakeStatus();
      const daemon = fakeDaemon(config, [midicraft]);
      const store = new ConfigStore(daemon.api, live.status);
      const view =
        tab === 'mapping'
          ? render(MappingPage, { props: { api: daemon.api, configStore: store } })
          : render(DevicesPage, { props: { api: daemon.api, store: live.status, configStore: store } });
      await waitFor(() => expect(store.loaded).toBe(true));
      texts.push(await within(view.container).findByText('Exec 1 Btn 1 · midi').then((el) => el.textContent ?? ''));
      view.unmount();
    }
    expect(texts[0]).toBe(texts[1]);
  });
});

<script lang="ts">
  import { onMount } from 'svelte';

  import type {
    ApiClient,
    DeviceBank,
    DeviceEntry,
    DeviceLearnStatus,
  } from './api';
  import AssignDialog from './AssignDialog.svelte';
  import DeviceSurface from './DeviceSurface.svelte';
  import LearnPanel from './LearnPanel.svelte';

  interface Props {
    api: ApiClient;
  }

  let { api }: Props = $props();

  type AnyConfig = Record<string, any>;

  let devices = $state<DeviceEntry[]>([]);
  let config = $state<AnyConfig | null>(null);
  let selectedDevice = $state<string | null>(null);
  let bank = $state(1);
  let selection = $state<string[]>([]);
  let dialog = $state<{ control: string; initial: Record<string, any> | null } | null>(null);
  let showLearn = $state(false);
  let learnControl = $state<string | null>(null);
  let learnStatus = $state<DeviceLearnStatus | null>(null);
  let error = $state<string | null>(null);
  let bankSize = $state(1);
  let channel = $state(1);
  let maPage = $state<number | ''>('');

  const device = $derived(
    devices.find((entry) => entry.name === selectedDevice) ?? null,
  );
  const profile = $derived(
    device && config ? config.profiles?.[device.profile] ?? null : null,
  );
  const banks = $derived<DeviceBank[]>(device?.controls.banks ?? []);
  const activeBank = $derived(
    banks.find((entry) => entry.number === bank) ?? {
      number: bank,
      channel: bank,
      notes: {},
    },
  );
  const bound = $derived(new Set(Object.values(activeBank.notes ?? {})));
  const inventory = $derived(device?.controls.inventory ?? []);
  const learningHere = $derived(
    learnStatus?.active === true &&
      learnStatus.device === device?.name &&
      learnStatus.bank === bank,
  );
  const activeLearn = $derived(learningHere ? learnStatus?.current ?? null : null);
  const activeLearnKind = $derived(
    inventory.find((item) => item.id === activeLearn)?.kind ?? null,
  );

  function learnVerb(kind: string | null): string {
    if (kind === 'encoder' || kind === 'relative-encoder' || kind === 'poti') {
      return 'drehen';
    }
    if (kind === 'fader') return 'bewegen';
    return 'drücken';
  }

  async function reload(): Promise<void> {
    error = null;
    try {
      const [nextDevices, nextConfig] = await Promise.all([
        api.devices(),
        api.config(),
      ]);
      devices = nextDevices.filter((entry) => entry.detected !== null);
      config = nextConfig;
      if (!selectedDevice || !devices.some((entry) => entry.name === selectedDevice)) {
        selectedDevice = devices[0]?.name ?? null;
      }
      syncBankSettings();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Laden fehlgeschlagen';
    }
  }

  onMount(() => {
    void reload();
  });

  $effect(() => {
    if (device) {
      bankSize = device.bank_size;
      selection = [];
      if (banks.length && !banks.some((entry) => entry.number === bank)) {
        bank = banks[0].number;
      }
      syncBankSettings();
    }
  });

  $effect(() => {
    bank;
    syncBankSettings();
  });

  function syncBankSettings(): void {
    channel = activeBank.channel;
    const layer = layerFor(bank);
    maPage = layer?.ma_page ?? '';
  }

  function layerFor(number: number): AnyConfig | null {
    if (!device || !config) return null;
    return config.mapping?.device_banks?.[device.name]?.[String(number)] ?? null;
  }

  function keyFor(control: string): AnyConfig | null {
    if (!config) return null;
    return layerFor(bank)?.keys?.[control] ?? config.mapping?.keys?.[control] ?? null;
  }

  function bankOffset(): number {
    if (!device || bank <= 1) return 0;
    const settings = config?.mapping?.device_banks?.[device.name];
    if (!settings) return 0;
    const layer = layerFor(bank);
    if (layer?.ma_page !== undefined && layer?.ma_page !== null) return 0;
    return (bank - 1) * (device.bank_size ?? 1);
  }

  function playbackFor(control: string): AnyConfig | null {
    if (!config) return null;
    const base = config.mapping?.playbacks?.[control] ?? null;
    const layer = layerFor(bank);
    const override = layer?.playbacks?.[control] ?? null;
    if (!base && !override) return null;
    const offset = override?.executor !== undefined && override?.executor !== null
      ? 0
      : bankOffset();
    const executor = override?.executor ?? base?.executor;
    return {
      page: override?.page ?? base?.page ?? 'current',
      executor: executor === undefined || executor === null ? null : executor + offset,
      kind: override?.kind ?? base?.kind ?? 'button',
      button: override?.button ?? base?.button ?? 1,
      accelerated: override?.accelerated ?? base?.accelerated ?? false,
    };
  }

  function encoderFor(control: string): AnyConfig | null {
    if (!config || !control.startsWith('encoder.')) return null;
    const id = Number(control.slice('encoder.'.length));
    const layer = layerFor(bank)?.encoders;
    const override = layer?.[String(id)] ?? layer?.[id];
    if (override) return override;
    return (config.mapping?.encoders ?? []).find((entry: AnyConfig) => entry.id === id) ?? null;
  }

  function screenEncoderFor(slot: number): number | null {
    const screens = config?.mapping?.screen_encoders ?? {};
    const value = screens[String(slot)] ?? screens[slot];
    return value === undefined || value === null ? null : Number(value);
  }

  function keyAssignment(key: AnyConfig): string | undefined {
    if (key.hardkey) return key.hardkey;
    if (key.command) return key.command;
    if (key.screen_mode) return 'Screen-Modus (Toggle)';
    if (key.encoder_press) return `Enc ${key.encoder_press}`;
    if (key.screen) return `Screen ${key.screen}`;
    return undefined;
  }

  function assignmentFor(control: string): string | undefined {
    const modifier = config?.mapping?.modifiers?.[control];
    if (modifier) {
      if (modifier.local) return 'Modifier (lokal)';
      if (modifier.hardkey) return `Modifier ${modifier.hardkey}`;
    }
    const layerKey = layerFor(bank)?.keys?.[control];
    if (layerKey) return keyAssignment(layerKey);
    const playback = playbackFor(control);
    if (playback) {
      const kind = playback.kind ?? 'button';
      const suffix = kind === 'fader' ? 'Fader' : `Btn ${playback.button ?? 1}`;
      const acc = playback.accelerated ? ' · acc' : '';
      return `Exec ${playback.executor ?? '?'} ${suffix}${acc}`;
    }
    const encoder = encoderFor(control);
    if (encoder) {
      if (encoder.slot !== undefined && encoder.slot !== null) {
        const slot = encoder.slot;
        const screen = screenEncoderFor(slot);
        return screen
          ? `Attribut ${slot} · Screen ${screen} (MA/Bank)`
          : `Attribut ${slot}`;
      }
      if (encoder.attribute) return `Attribut ${encoder.attribute}`;
    }
    const key = keyFor(control);
    if (!key) {
      const note = (device?.controls.notes ?? []).find(
        (entry) => entry.control === control,
      )?.note;
      const led = config?.led;
      if (
        note !== undefined &&
        led &&
        (note === led.nipple_note || note === led.note)
      ) {
        return 'LED';
      }
      return undefined;
    }
    return keyAssignment(key);
  }

  function toggle(control: string): void {
    selection = selection.includes(control)
      ? selection.filter((entry) => entry !== control)
      : [...selection, control];
  }

  function keyInitial(key: AnyConfig): AnyConfig {
    if (key.screen_mode) return { action: 'screen_mode' };
    if (key.screen !== undefined && key.screen !== null) {
      return { action: 'screen', screen: key.screen };
    }
    if (key.encoder_press !== undefined && key.encoder_press !== null) {
      return { action: 'encoder_press', slot: key.encoder_press };
    }
    if (key.command) return { action: 'command', command: key.command };
    return { action: 'hardkey', hardkey: key.hardkey ?? 'GOTO' };
  }

  function openDialog(control: string): void {
    const layerKey = layerFor(bank)?.keys?.[control] ?? null;
    const playback = playbackFor(control);
    const encoder = control.startsWith('encoder.') ? encoderFor(control) : null;
    const key = keyFor(control);
    const initial = layerKey
      ? keyInitial(layerKey)
      : playback
        ? {
            action: 'executor',
            page: String(playback.page ?? 'current'),
            executor: playback.executor ?? 1,
            targetKind: playback.kind ?? 'button',
            button: playback.button ?? 1,
            accelerated: Boolean(playback.accelerated),
          }
        : encoder
          ? {
              action: 'encoder',
              slot: encoder.slot ?? 1,
              attribute: encoder.attribute ?? '',
              screen: encoder.slot != null ? screenEncoderFor(encoder.slot) ?? 0 : 0,
            }
          : key
            ? keyInitial(key)
            : null;
    dialog = {
      control: selection.length > 1 ? selection[0] : control,
      initial,
    };
  }

  function clearFields(): AnyConfig {
    return {
      hardkey: null,
      command: null,
      screen_mode: null,
      encoder_press: null,
      screen: null,
      page: null,
      executor: null,
      kind: null,
      button: null,
      accelerated: null,
    };
  }

  async function saveAssignment(values: AnyConfig): Promise<void> {
    const controls = selection.length ? selection : dialog ? [dialog.control] : [];
    if (!controls.length || !device) return;
    if (values.action === 'encoder') {
      if (controls.length > 1) {
        throw new Error('Encoder-Ziele nur für ein einzelnes Control.');
      }
      const control = controls[0];
      if (!control.startsWith('encoder.')) {
        throw new Error('Control ist kein Attribut-Encoder.');
      }
      const id = Number(control.slice('encoder.'.length));
      const attribute = String(values.attribute ?? '').trim();
      const slot = Number(values.slot);
      const target: AnyConfig = attribute ? { id, attribute } : { id, slot };
      const mappingPatch: AnyConfig = {};
      const layerEntries = Object.values(layerFor(bank)?.encoders ?? {}) as AnyConfig[];
      const layerHasEncoder = layerEntries.some((entry) => entry.id === id);
      if (bank !== 1 || layerHasEncoder) {
        const next = layerEntries
          .filter((entry) => entry.id !== id)
          .concat(target)
          .sort((a, b) => a.id - b.id);
        mappingPatch.device_banks = {
          [device.name]: { [String(bank)]: { encoders: next } },
        };
      } else {
        const next = (config?.mapping?.encoders ?? [])
          .filter((entry: AnyConfig) => entry.id !== id)
          .concat(target)
          .sort((a: AnyConfig, b: AnyConfig) => a.id - b.id);
        mappingPatch.encoders = next;
      }
      const screen = Number(values.screen);
      if (!attribute && screen >= 5) {
        mappingPatch.screen_encoders = { [String(slot)]: screen };
      }
      await api.updateConfig({ mapping: mappingPatch });
      dialog = null;
      selection = [];
      await reload();
      return;
    }
    const patch: AnyConfig = { mapping: {} };
    for (let index = 0; index < controls.length; index += 1) {
      const control = controls[index];
      const area =
        bank === 1
          ? patch.mapping
          : (patch.mapping.device_banks ??= {}) &&
            ((patch.mapping.device_banks[device.name] ??= {}) &&
              ((patch.mapping.device_banks[device.name][String(bank)] ??= {})));
      area.keys ??= {};
      area.playbacks ??= {};
      area.keys[control] = null;
      area.playbacks[control] = null;
      if (values.action === 'hardkey') {
        area.keys[control] = {
          hardkey: values.hardkey,
          command: null,
          screen_mode: null,
          encoder_press: null,
          screen: null,
        };
      } else if (values.action === 'command') {
        area.keys[control] = {
          command: values.command,
          hardkey: null,
          screen_mode: null,
          encoder_press: null,
          screen: null,
        };
      } else if (values.action === 'screen_mode') {
        area.keys[control] = {
          hardkey: null,
          command: null,
          screen_mode: true,
          encoder_press: null,
          screen: null,
        };
      } else if (values.action === 'screen') {
        area.keys[control] = {
          hardkey: null,
          command: null,
          screen_mode: null,
          encoder_press: null,
          screen: Number(values.screen),
        };
      } else if (values.action === 'encoder_press') {
        area.keys[control] = {
          hardkey: null,
          command: null,
          screen_mode: null,
          encoder_press: Number(values.slot),
          screen: null,
        };
      } else {
        const executor = values.start + index * values.step;
        const entry: AnyConfig = {
          ...clearFields(),
          page: values.page === 'current' ? 'current' : Number(values.page),
          executor,
          kind: values.targetKind,
        };
        if (values.targetKind === 'button') entry.button = values.button;
        const kind = inventory.find((item) => item.id === control)?.kind;
        if (kind === 'encoder' && values.targetKind === 'fader') {
          entry.accelerated = Boolean(values.accelerated);
        }
        area.playbacks[control] = entry;
      }
    }
    await api.updateConfig(patch);
    dialog = null;
    selection = [];
    await reload();
  }

  async function saveBankSettings(): Promise<void> {
    if (!device || !config) return;
    const size = Number(bankSize);
    const channelValue = Number(channel);
    const pageNumber =
      maPage === '' || maPage === null ? null : Number(maPage);
    if (!Number.isInteger(size) || size < 1) {
      error = 'Bankgröße muss eine ganze Zahl ab 1 sein';
      return;
    }
    if (!Number.isInteger(channelValue) || channelValue < 1 || channelValue > 16) {
      error = 'Kanal muss zwischen 1 und 16 liegen';
      return;
    }
    if (pageNumber !== null && (!Number.isInteger(pageNumber) || pageNumber < 1)) {
      error = 'MA-Page muss eine ganze Zahl ab 1 sein';
      return;
    }
    const profileBanks = (profile?.banks ?? []).map((entry: AnyConfig) => ({
      number: entry.number,
      channel: entry.number === bank ? channelValue : entry.channel,
      notes: entry.notes ?? {},
    }));
    let latest: AnyConfig;
    try {
      latest = await api.config();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Laden fehlgeschlagen';
      return;
    }
    const currentBanks = latest.profiles?.[device.profile]?.banks ?? profileBanks;
    const mergedBanks = currentBanks.map((entry: AnyConfig) => ({
      number: entry.number,
      channel: entry.number === bank ? channelValue : entry.channel,
      notes: entry.notes ?? {},
    }));
    const patch: AnyConfig = {
      profiles: { [device.profile]: { banks: mergedBanks } },
      mapping: {
        device_banks: {
          [device.name]: {
            bank_size: size,
            [String(bank)]: { ma_page: pageNumber },
          },
        },
      },
    };
    try {
      await api.updateConfig(patch);
      await reload();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Speichern fehlgeschlagen';
    }
  }
</script>

<section class="page devices-page">
  <h1>Geräte</h1>

  {#if error}
    <p class="banner" role="alert">{error}</p>
  {/if}

  <div class="layout">
    <aside>
      <h2>Geräte</h2>
      <ul class="device-list">
        {#each devices as entry (entry.name)}
          <li>
            <button
              type="button"
              class:active={entry.name === selectedDevice}
              onclick={() => (selectedDevice = entry.name)}
            >
              <strong>{entry.name}</strong>
              <span>{entry.vendor_product}</span>
              <span class:missing={entry.detected === null}>
                {entry.detected ? 'verbunden' : 'verbindung verloren'}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    </aside>

    <div class="surface-area">
      {#if device}
        <header class="surface-head">
          <div>
            <h2>{device.name}</h2>
            <p class="muted">Profil {device.profile} · {device.vendor_product}</p>
          </div>
          <label>
            Bank
            <select bind:value={bank} onchange={syncBankSettings}>
              {#each banks.length ? banks : [{ number: 1, channel: 1, notes: {} }] as entry}
                <option value={entry.number}>
                  Bank {entry.number} · Kanal {entry.channel}
                </option>
              {/each}
            </select>
          </label>
        </header>

        {#if selection.length}
          <div class="selection">
            <span>{selection.length} ausgewählt</span>
            <div class="chips">
              {#each selection as control, index (control)}
                <button type="button" onclick={() => toggle(control)}>
                  {index + 1}. {control} ×
                </button>
              {/each}
            </div>
            <button type="button" onclick={() => openDialog(selection[0])}>
              Zuweisen
            </button>
            {#if selection.length === 1 && device.backend === 'midi' && banks.length}
              <button
                type="button"
                onclick={() => {
                  learnControl = selection[0];
                  showLearn = true;
                }}
              >
                Erneut anlernen
              </button>
            {/if}
          </div>
        {/if}

        {#if activeLearn}
          <p class="learn-hint" role="status">
            Jetzt <strong>{activeLearn}</strong> {learnVerb(activeLearnKind)} – das
            markierte Feld auf der Fläche zeigt die Stelle.
          </p>
        {/if}

        {#if device.layout}
          <DeviceSurface
            layout={device.layout}
            assignments={Object.fromEntries(
              inventory.map((item) => [item.id, assignmentFor(item.id) ?? 'frei']),
            )}
            selected={selection}
            activeControl={activeLearn}
            activeKind={activeLearnKind}
            interactive={!learningHere}
            onToggle={toggle}
          />
        {:else}
          <table>
            <thead>
              <tr><th>Control</th><th>Art</th><th>Gebunden</th><th>Belegung</th></tr>
            </thead>
            <tbody>
              {#each inventory as item (item.id)}
                <tr class:active={item.id === activeLearn}>
                  <td><button type="button" onclick={() => toggle(item.id)}>{item.id}</button></td>
                  <td>{item.kind}</td>
                  <td>{bound.has(item.id) ? 'ja' : 'nein'}</td>
                  <td>{assignmentFor(item.id) ?? '–'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        {#if banks.length}
          <div class="settings">
            <label>Bankgröße <input type="number" min="1" bind:value={bankSize} /></label>
            <label>Kanal <input type="number" min="1" max="16" bind:value={channel} /></label>
            <label>MA-Page <input type="number" min="1" placeholder="—" bind:value={maPage} /></label>
            <button type="button" onclick={saveBankSettings}>Einstellungen speichern</button>
          </div>
        {/if}

        <div class="actions">
          {#if device.backend === 'midi' && banks.length}
            <button
              type="button"
              onclick={() => {
                learnControl = null;
                showLearn = !showLearn;
              }}
            >
              Anlernen
            </button>
          {/if}
        </div>

        {#if showLearn}
          <LearnPanel
            {api}
            device={device.name}
            {bank}
            control={learnControl}
            onFinished={() => void reload()}
            onStatus={(next) => (learnStatus = next)}
          />
        {/if}
      {:else}
        <p class="muted">Keine Geräte konfiguriert.</p>
      {/if}
    </div>
  </div>

  {#if dialog && device}
    <div class="dialog">
      <AssignDialog
        control={dialog.control}
        {bank}
        kind={inventory.find((item) => item.id === (dialog?.control ?? ''))?.kind ?? 'button'}
        count={selection.length || 1}
        initial={dialog.initial}
        onSave={saveAssignment}
        onClose={() => (dialog = null)}
      />
    </div>
  {/if}
</section>

<style>
  .layout {
    display: grid;
    grid-template-columns: 11rem minmax(0, 1fr);
    gap: 1rem;
  }

  .devices-page {
    max-width: none;
  }

  .device-list {
    display: grid;
    gap: 0.4rem;
    padding: 0;
    list-style: none;
  }

  .device-list button {
    display: grid;
    width: 100%;
    gap: 0.15rem;
    padding: 0.5rem;
    text-align: left;
  }

  .device-list button.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
    outline: 2px solid var(--accent-hover);
  }

  .device-list button.active:hover:not(:disabled) {
    color: var(--on-accent);
  }

  .device-list button.active span {
    color: var(--on-accent);
    opacity: 0.72;
  }

  .device-list span {
    font-size: 0.7rem;
    color: var(--text-muted);
  }

  .missing {
    color: var(--danger);
  }

  .surface-head {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 1rem;
    margin-bottom: 0.75rem;
  }

  .surface-head h2,
  .surface-head p {
    margin: 0;
  }

  .selection {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.6rem;
    font-size: 0.8rem;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }

  .settings {
    display: flex;
    align-items: end;
    gap: 0.6rem;
    margin-top: 0.9rem;
  }

  .settings label {
    display: grid;
    gap: 0.2rem;
    font-size: 0.75rem;
  }

  .actions {
    margin-top: 0.8rem;
  }

  .dialog {
    position: fixed;
    inset: 0;
    display: grid;
    place-items: center;
    background: rgb(10 10 10 / 0.65);
    padding: 1rem;
  }

  input,
  select {
    padding: 0.3rem;
    background: var(--surface-inset);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    color: inherit;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }

  th,
  td {
    padding: 0.3rem 0.4rem;
    border-bottom: 1px solid var(--border);
    text-align: left;
  }

  tr.active {
    outline: 2px solid #ffd166;
    outline-offset: -2px;
    background: rgba(255, 209, 102, 0.12);
  }

  .learn-hint {
    margin: 0 0 0.6rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d4a72c;
    border-radius: var(--radius);
    background: rgba(255, 209, 102, 0.12);
    color: #ffe08a;
    font-size: 0.85rem;
  }

  .learn-hint strong {
    color: #fff3c4;
  }
</style>

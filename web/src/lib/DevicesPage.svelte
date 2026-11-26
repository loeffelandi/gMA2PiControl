<script lang="ts">
  import { onMount } from 'svelte';

  import {
    ApiError,
    type ApiClient,
    type DeviceBank,
    type DeviceEntry,
    type DeviceLearnStatus,
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
  let savingBank = $state(false);
  let lastSyncedDevice: string | null = null;

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

  function bankNotesRecord(notes: unknown): Record<string, string> {
    if (!notes) return {};
    if (Array.isArray(notes)) {
      const out: Record<string, string> = {};
      for (const entry of notes) {
        if (entry && typeof entry === 'object' && 'note' in entry && 'control' in entry) {
          out[String((entry as { note: unknown }).note)] = String(
            (entry as { control: unknown }).control,
          );
        }
      }
      return out;
    }
    return notes as Record<string, string>;
  }

  const bound = $derived(new Set(Object.values(bankNotesRecord(activeBank.notes))));
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

  function errorMessage(cause: unknown, fallback: string): string {
    if (cause instanceof ApiError) return cause.detail || fallback;
    if (cause instanceof Error) return cause.message || fallback;
    return fallback;
  }

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
      const active = devices.find((entry) => entry.name === selectedDevice) ?? null;
      if (active) {
        if (active.name !== lastSyncedDevice) {
          bankSize = active.bank_size;
          lastSyncedDevice = active.name;
        }
        const nextBanks = active.controls.banks ?? [];
        if (nextBanks.length && !nextBanks.some((entry) => entry.number === bank)) {
          bank = nextBanks[0].number;
        }
      } else {
        lastSyncedDevice = null;
      }
      syncBankSettings();
    } catch (cause) {
      error = errorMessage(cause, 'Laden fehlgeschlagen');
    }
  }

  onMount(() => {
    void reload();
  });

  function selectDevice(name: string): void {
    if (selectedDevice === name) return;
    selectedDevice = name;
    lastSyncedDevice = name;
    selection = [];
    const target = devices.find((entry) => entry.name === name) ?? null;
    if (target) {
      bankSize = target.bank_size;
      const targetBanks = target.controls.banks ?? [];
      if (targetBanks.length && !targetBanks.some((entry) => entry.number === bank)) {
        bank = targetBanks[0].number;
      }
    }
    syncBankSettings();
  }

  function syncBankSettings(): void {
    channel = activeBank.channel;
    const layer = layerFor(bank);
    maPage = layer?.ma_page ?? '';
  }

  function layerFor(number: number): AnyConfig | null {
    if (!device || !config) return null;
    const devBanks = config.mapping?.device_banks?.[device.name];
    if (!devBanks) return null;
    return (
      devBanks[String(number)] ??
      devBanks[number] ??
      devBanks.banks?.[String(number)] ??
      devBanks.banks?.[number] ??
      null
    );
  }

  function normalizeEncoderEntry(entry: AnyConfig, fallbackId?: number): AnyConfig | null {
    if (!entry || typeof entry !== 'object') return null;
    const id = entry.id !== undefined ? Number(entry.id) : fallbackId;
    if (id === undefined || !Number.isInteger(id)) return null;
    if (entry.attribute !== undefined && entry.attribute !== null && entry.attribute !== '') {
      return { id, attribute: String(entry.attribute) };
    }
    if (entry.slot !== undefined && entry.slot !== null) {
      return { id, slot: Number(entry.slot) };
    }
    return null;
  }

  function layerEncoderList(number: number): AnyConfig[] {
    const raw = layerFor(number)?.encoders;
    if (!raw) return [];
    if (Array.isArray(raw)) {
      return raw
        .map((entry) => normalizeEncoderEntry(entry))
        .filter((entry): entry is AnyConfig => entry !== null);
    }
    if (typeof raw === 'object') {
      return Object.entries(raw)
        .map(([key, entry]) => normalizeEncoderEntry(entry as AnyConfig, Number(key)))
        .filter((entry): entry is AnyConfig => entry !== null);
    }
    return [];
  }

  function globalEncoderList(): AnyConfig[] {
    const raw = config?.mapping?.encoders;
    if (!Array.isArray(raw)) return [];
    return raw
      .map((entry) => normalizeEncoderEntry(entry))
      .filter((entry): entry is AnyConfig => entry !== null);
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
    const offset =
      override?.executor !== undefined && override?.executor !== null
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
    const override = layerEncoderList(bank).find((entry) => entry.id === id);
    if (override) return override;
    return globalEncoderList().find((entry) => entry.id === id) ?? null;
  }

  function screenEncoderFor(slot: number): number | null {
    const screens = config?.mapping?.screen_encoders ?? {};
    const value = screens[String(slot)] ?? screens[slot];
    return value === undefined || value === null ? null : Number(value);
  }

  function hasLayerOverrideFor(number: number, control: string): boolean {
    const layer = layerFor(number);
    if (layer?.keys?.[control] !== undefined || layer?.playbacks?.[control] !== undefined) {
      return true;
    }
    if (control.startsWith('encoder.')) {
      const id = Number(control.slice('encoder.'.length));
      return layerEncoderList(number).some((entry) => entry.id === id);
    }
    return false;
  }

  function hasRemovableAssignment(control: string): boolean {
    if (hasLayerOverrideFor(bank, control)) return true;
    if (bank >= 2) return false;
    if (config?.mapping?.keys?.[control] !== undefined) return true;
    if (config?.mapping?.playbacks?.[control] !== undefined) return true;
    if (control.startsWith('encoder.')) {
      const id = Number(control.slice('encoder.'.length));
      return globalEncoderList().some((entry) => entry.id === id);
    }
    return false;
  }

  const dialogControls = $derived(
    selection.length ? selection : dialog ? [dialog.control] : [],
  );
  const dialogHasAssignment = $derived(
    dialogControls.some((ctrl) => hasRemovableAssignment(ctrl)),
  );
  const dialogInherited = $derived.by(() => {
    if (!dialog || bank < 2) return false;
    const ctrl = dialog.control;
    const override = layerFor(bank)?.playbacks?.[ctrl];
    const base = config?.mapping?.playbacks?.[ctrl];
    return (
      !hasLayerOverrideFor(bank, ctrl) &&
      Boolean(base) &&
      (override?.executor === undefined || override?.executor === null) &&
      bankOffset() > 0
    );
  });

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
    const target = selection.length > 1 ? selection[0] : control;
    const layerKey = layerFor(bank)?.keys?.[target] ?? null;
    const playback = playbackFor(target);
    const encoder = target.startsWith('encoder.') ? encoderFor(target) : null;
    const key = keyFor(target);
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
      control: target,
      initial,
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
      const layerEntries = layerEncoderList(bank);
      const layerHasEncoder = layerEntries.some((entry) => entry.id === id);

      if (bank !== 1) {
        const next = layerEntries
          .filter((entry) => entry.id !== id)
          .concat(target)
          .sort((a, b) => a.id - b.id);
        mappingPatch.device_banks = {
          [device.name]: { [String(bank)]: { encoders: next } },
        };
      } else {
        const currentGlobal = globalEncoderList();
        const prevEncoder = currentGlobal.find((entry) => entry.id === id);
        const prevSlot =
          prevEncoder?.slot !== undefined && prevEncoder?.slot !== null
            ? Number(prevEncoder.slot)
            : null;
        const next = currentGlobal
          .filter((entry) => entry.id !== id)
          .concat(target)
          .sort((a, b) => a.id - b.id);
        mappingPatch.encoders = next;

        if (layerHasEncoder) {
          mappingPatch.device_banks = {
            [device.name]: {
              '1': { encoders: layerEntries.filter((entry) => entry.id !== id) },
            },
          };
        }

        const screen = Number(values.screen);
        const screenPatch: Record<string, number | null> = {};
        if (!attribute && slot >= 1 && slot <= 4) {
          if (screen >= 5) {
            screenPatch[String(slot)] = screen;
          } else if (screenEncoderFor(slot) !== null) {
            screenPatch[String(slot)] = null;
          }
        }
        if (
          prevSlot !== null &&
          prevSlot >= 1 &&
          prevSlot <= 4 &&
          (Boolean(attribute) || prevSlot !== slot) &&
          screenEncoderFor(prevSlot) !== null &&
          !next.some((entry) => entry.slot === prevSlot)
        ) {
          screenPatch[String(prevSlot)] = null;
        }
        if (Object.keys(screenPatch).length > 0) {
          mappingPatch.screen_encoders = screenPatch;
        }
      }

      await api.updateConfig({ mapping: mappingPatch });
      dialog = null;
      selection = [];
      await reload();
      return;
    }

    const useGlobalScope =
      bank === 1 || (values.action === 'executor' && values.scope === 'global');
    const offset = useGlobalScope && bank > 1 ? bankOffset() : 0;
    if (values.action === 'executor' && useGlobalScope && values.start - offset < 1) {
      throw new Error(
        `Für globale Speicherung muss Executor mindestens ${offset + 1} sein.`,
      );
    }

    const patch: AnyConfig = { mapping: {} };
    for (let index = 0; index < controls.length; index += 1) {
      const control = controls[index];
      const area = useGlobalScope
        ? patch.mapping
        : (((patch.mapping.device_banks ??= {})[device.name] ??= {})[String(bank)] ??= {});
      area.keys ??= {};
      area.playbacks ??= {};
      area.keys[control] = null;
      area.playbacks[control] = null;

      if (useGlobalScope) {
        const layer1 = layerFor(1);
        if (
          layer1?.keys?.[control] !== undefined ||
          layer1?.playbacks?.[control] !== undefined
        ) {
          const bank1Patch =
            (((patch.mapping.device_banks ??= {})[device.name] ??= {})['1'] ??= {});
          if (layer1?.keys?.[control] !== undefined) {
            (bank1Patch.keys ??= {})[control] = null;
          }
          if (layer1?.playbacks?.[control] !== undefined) {
            (bank1Patch.playbacks ??= {})[control] = null;
          }
        }
        if (bank > 1) {
          const activeLayer = layerFor(bank);
          if (
            activeLayer?.keys?.[control] !== undefined ||
            activeLayer?.playbacks?.[control] !== undefined
          ) {
            const activePatch =
              (((patch.mapping.device_banks ??= {})[device.name] ??= {})[String(bank)] ??= {});
            if (activeLayer?.keys?.[control] !== undefined) {
              (activePatch.keys ??= {})[control] = null;
            }
            if (activeLayer?.playbacks?.[control] !== undefined) {
              (activePatch.playbacks ??= {})[control] = null;
            }
          }
        }
      }

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
        const executor = values.start - offset + index * values.step;
        const kind = inventory.find((item) => item.id === control)?.kind;
        const entry: AnyConfig = {
          page: values.page === 'current' ? 'current' : Number(values.page),
          executor,
          kind: values.targetKind,
          button: values.targetKind === 'button' ? Number(values.button) : null,
          accelerated:
            kind === 'encoder' && values.targetKind === 'fader'
              ? Boolean(values.accelerated)
              : null,
        };
        area.playbacks[control] = entry;
      }
    }
    await api.updateConfig(patch);
    dialog = null;
    selection = [];
    await reload();
  }

  async function clearAssignment(): Promise<void> {
    const controls = selection.length ? selection : dialog ? [dialog.control] : [];
    if (!controls.length || !device) return;
    const patch: AnyConfig = { mapping: {} };

    for (const control of controls) {
      const isEncoder = control.startsWith('encoder.');
      const encoderId = isEncoder ? Number(control.slice('encoder.'.length)) : null;
      const hasOverride = hasLayerOverrideFor(bank, control);

      if (bank >= 2 || hasOverride) {
        const bankPatch =
          (((patch.mapping.device_banks ??= {})[device.name] ??= {})[String(bank)] ??= {});
        if (isEncoder && encoderId !== null) {
          const baseList: AnyConfig[] = bankPatch.encoders ?? layerEncoderList(bank);
          bankPatch.encoders = baseList.filter((entry) => entry.id !== encoderId);
        } else {
          (bankPatch.keys ??= {})[control] = null;
          (bankPatch.playbacks ??= {})[control] = null;
        }
      } else if (isEncoder && encoderId !== null) {
        const baseGlobal: AnyConfig[] = patch.mapping.encoders ?? globalEncoderList();
        const removed = baseGlobal.find((entry) => entry.id === encoderId);
        const nextGlobal = baseGlobal.filter((entry) => entry.id !== encoderId);
        patch.mapping.encoders = nextGlobal;
        if (
          removed?.slot !== undefined &&
          removed?.slot !== null &&
          removed.slot >= 1 &&
          removed.slot <= 4 &&
          screenEncoderFor(removed.slot) !== null &&
          !nextGlobal.some((entry) => entry.slot === removed.slot)
        ) {
          (patch.mapping.screen_encoders ??= {})[String(removed.slot)] = null;
        }
      } else {
        (patch.mapping.keys ??= {})[control] = null;
        (patch.mapping.playbacks ??= {})[control] = null;
      }
    }

    await api.updateConfig(patch);
    dialog = null;
    selection = [];
    await reload();
  }

  async function saveBankSettings(): Promise<void> {
    if (!device || !config || savingBank) return;
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
      notes: bankNotesRecord(entry.notes),
    }));
    savingBank = true;
    error = null;
    try {
      let latest: AnyConfig;
      try {
        latest = await api.config();
      } catch (cause) {
        error = errorMessage(cause, 'Laden fehlgeschlagen');
        return;
      }
      const currentBanks = latest.profiles?.[device.profile]?.banks ?? profileBanks;
      const mergedBanks = currentBanks.map((entry: AnyConfig) => ({
        number: entry.number,
        channel: entry.number === bank ? channelValue : entry.channel,
        notes: bankNotesRecord(entry.notes),
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
        lastSyncedDevice = null;
        await reload();
      } catch (cause) {
        error = errorMessage(cause, 'Speichern fehlgeschlagen');
      }
    } finally {
      savingBank = false;
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
              class={{ active: entry.name === selectedDevice }}
              onclick={() => selectDevice(entry.name)}
            >
              <strong>{entry.name}</strong>
              <span>{entry.vendor_product}</span>
              <span class={{ missing: entry.detected === null }}>
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
              {#each banks.length ? banks : [{ number: 1, channel: 1, notes: {} }] as entry (entry.number)}
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
                <tr class={{ active: item.id === activeLearn }}>
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
            <button type="button" disabled={savingBank} onclick={saveBankSettings}>
              Einstellungen speichern
            </button>
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
            onDone={() => (showLearn = false)}
            onStatus={(next) => (learnStatus = next)}
          />
        {/if}
      {:else}
        <p class="muted">Keine Geräte konfiguriert.</p>
      {/if}
    </div>
  </div>

  {#if dialog && device}
    <AssignDialog
      control={dialog.control}
      {bank}
      kind={inventory.find((item) => item.id === (dialog?.control ?? ''))?.kind ?? 'button'}
      count={selection.length || 1}
      initial={dialog.initial}
      inherited={dialogInherited}
      hasAssignment={dialogHasAssignment}
      onSave={saveAssignment}
      onClear={clearAssignment}
      onClose={() => (dialog = null)}
    />
  {/if}
</section>

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 1rem;
  }

  .devices-page {
    max-width: none;
  }

  .device-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    padding: 0;
    list-style: none;
  }

  .device-list button {
    display: grid;
    width: auto;
    min-width: 11rem;
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

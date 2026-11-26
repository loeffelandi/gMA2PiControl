<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import {
    ApiError,
    type ApiClient,
    type DeviceEntry,
    type DevicePresence,
    type DeviceValueControl,
    type LearnResult,
  } from './api';
  import type { StatusStore } from './status';

  type KeyKind = 'hardkey' | 'command' | 'screen_mode' | 'screen' | 'encoder_press';
  type EncoderKind = 'slot' | 'attribute';
  type ModifierKind = 'hardkey' | 'local';
  type PlaybackKind = 'button' | 'fader';

  interface ValueControlInfo {
    control: string;
    note: number;
    kind: 'fader' | 'poti' | 'encoder';
  }

  interface RawBankEntry {
    number: number;
    channel: number;
    notes?: Record<string, string> | { note: number; control: string }[];
  }

  interface RawInventoryEntry {
    id: string;
    kind: 'button' | 'fader' | 'poti' | 'encoder' | 'relative-encoder';
    label?: string | null;
  }

  interface KeyRow {
    uid: number;
    control: string;
    kind: KeyKind;
    value: string;
  }

  interface EncoderRow {
    uid: number;
    id: number;
    kind: EncoderKind;
    value: string;
    screen: string;
  }

  interface ModifierRow {
    uid: number;
    control: string;
    kind: ModifierKind;
    hardkey: string;
  }

  interface PlaybackRow {
    uid: number;
    control: string;
    page: string;
    executor: string;
    kind: PlaybackKind;
    button: string;
    accelerated: boolean;
    enabled: boolean;
    fixed: boolean;
  }

  let { api, learnStore }: { api: ApiClient; learnStore?: StatusStore } = $props();

  let nextRowUid = 1;
  function allocUid(): number {
    const id = nextRowUid;
    nextRowUid += 1;
    return id;
  }

  let devices = $state<DeviceEntry[]>([]);
  let presence = $state<Record<string, DevicePresence>>({});
  let visibleDevices = $derived(
    devices.filter((device) => {
      const state = presence[device.name];
      return state ? state.seen : device.detected !== null;
    }),
  );
  let keyRows = $state<KeyRow[]>([]);
  let encoderRows = $state<EncoderRow[]>([]);
  let modifierRows = $state<ModifierRow[]>([]);
  let playbackRows = $state<PlaybackRow[]>([]);
  let originalKeys: string[] = [];
  let originalModifiers: string[] = [];
  let originalScreenSlots: string[] = [];
  let originalPlaybacks: string[] = [];
  let loading = $state(true);
  let busy = $state(false);
  let dirty = $state(false);
  let message = $state<{ ok: boolean; text: string } | null>(null);
  let learnState = $state<LearnResult | null>(null);
  let pendingLearn = $state<null | { kind: 'key' | 'encoder'; uid: number }>(null);
  let learnedControl = $state<string | null>(null);

  const keyKinds: KeyKind[] = [
    'hardkey',
    'command',
    'screen',
    'encoder_press',
    'screen_mode',
  ];

  function bankNotesList(bank: RawBankEntry | undefined): { note: number; control: string }[] {
    if (!bank?.notes) return [];
    if (Array.isArray(bank.notes)) {
      return bank.notes.map((entry) => ({
        note: Number(entry.note),
        control: String(entry.control),
      }));
    }
    return Object.entries(bank.notes).map(([note, control]) => ({
      note: Number(note),
      control: String(control),
    }));
  }

  function valueControlsOf(device: DeviceEntry): ValueControlInfo[] {
    const controls = device.controls as unknown as {
      values?: DeviceValueControl[];
      inventory?: RawInventoryEntry[];
      banks?: RawBankEntry[];
    };
    const seen: Record<string, boolean> = {};
    const out: ValueControlInfo[] = [];
    for (const entry of controls.values ?? []) {
      if (seen[entry.control]) continue;
      seen[entry.control] = true;
      out.push({
        control: entry.control,
        note: entry.note,
        kind: entry.kind,
      });
    }
    const firstBankNotes: Record<string, number> = {};
    for (const entry of bankNotesList(controls.banks?.[0])) {
      if (!(entry.control in firstBankNotes)) {
        firstBankNotes[entry.control] = entry.note;
      }
    }
    for (const item of controls.inventory ?? []) {
      if (seen[item.id]) continue;
      if (item.kind === 'fader' || item.kind === 'poti' || item.kind === 'encoder') {
        seen[item.id] = true;
        out.push({
          control: item.id,
          note: firstBankNotes[item.id] ?? 0,
          kind: item.kind,
        });
      }
    }
    return out;
  }

  const keyControls = $derived(
    [...new Set(devices.flatMap((device) => {
      const controls = device.controls as unknown as {
        keys?: { control: string }[];
        notes?: { control: string }[];
        inventory?: RawInventoryEntry[];
      };
      return [
        ...(controls.keys ?? []).map((entry) => entry.control),
        ...(controls.notes ?? []).map((entry) => entry.control),
        ...(controls.inventory ?? [])
          .filter((entry) => entry.kind === 'button')
          .map((entry) => entry.id),
      ];
    }))].sort(),
  );

  const allControls = $derived(
    [...new Set([
      ...keyControls,
      ...devices.flatMap((device) =>
        valueControlsOf(device).map((entry) => entry.control),
      ),
      ...devices.flatMap((device) => {
        const controls = device.controls as unknown as {
          inventory?: RawInventoryEntry[];
        };
        return (controls.inventory ?? [])
          .filter((entry) => entry.kind !== 'relative-encoder')
          .map((entry) => entry.id);
      }),
    ])].sort(),
  );

  const encoderIds = $derived(
    [...new Set(devices.flatMap((device) => {
      const controls = device.controls as unknown as {
        encoders?: { id: number }[];
        midi_encoders?: { id: number }[];
        inventory?: RawInventoryEntry[];
      };
      const invIds = (controls.inventory ?? [])
        .filter((entry) => entry.kind === 'relative-encoder' && entry.id.startsWith('encoder.'))
        .map((entry) => Number(entry.id.slice('encoder.'.length)))
        .filter((id) => Number.isInteger(id) && id >= 1);
      return [
        ...(controls.encoders ?? []).map((entry) => entry.id),
        ...(controls.midi_encoders ?? []).map((entry) => entry.id),
        ...invIds,
      ];
    }))].sort((left, right) => left - right),
  );

  const encoderControls = $derived(
    new Set(
      devices.flatMap((device) =>
        valueControlsOf(device)
          .filter((entry) => entry.kind === 'encoder')
          .map((entry) => entry.control),
      ),
    ),
  );

  function errorText(error: unknown): string {
    if (error instanceof ApiError) return error.detail || error.message;
    if (error instanceof Error) return error.message;
    return 'Unbekannter Fehler';
  }

  function kindOf(entry: Record<string, unknown>): KeyKind {
    if (entry.hardkey != null) return 'hardkey';
    if (entry.command != null) return 'command';
    if (entry.screen != null) return 'screen';
    if (entry.encoder_press != null) return 'encoder_press';
    return 'screen_mode';
  }

  function valueOf(entry: Record<string, unknown>, kind: KeyKind): string {
    if (kind === 'screen_mode') return '';
    const value = entry[kind];
    return value == null ? '' : String(value);
  }

  function deviceForControl(control: string): string | undefined {
    return devices.find((device) => {
      const controls = device.controls as unknown as {
        keys?: { control: string }[];
        notes?: { control: string }[];
        encoders?: { id?: number; control?: string }[];
        midi_encoders?: { id?: number; control?: string }[];
        values?: DeviceValueControl[];
        inventory?: RawInventoryEntry[];
        banks?: RawBankEntry[];
      };
      const names = [
        ...(controls.keys ?? []).map((entry) => entry.control),
        ...(controls.notes ?? []).map((entry) => entry.control),
        ...(controls.encoders ?? []).map((entry) => entry.control ?? `encoder.${entry.id}`),
        ...(controls.midi_encoders ?? []).map((entry) => entry.control ?? `encoder.${entry.id}`),
        ...(controls.values ?? []).map((entry) => entry.control),
        ...(controls.inventory ?? []).map((entry) => entry.id),
        ...(controls.banks ?? []).flatMap((bank) =>
          bankNotesList(bank).map((entry) => entry.control),
        ),
      ];
      return names.includes(control);
    })?.name;
  }

  function loadMapping(config: Record<string, unknown>, deviceList: DeviceEntry[]): void {
    const mapping = (config.mapping ?? {}) as Record<string, unknown>;
    const keys = (mapping.keys ?? {}) as Record<string, Record<string, unknown>>;
    originalKeys = Object.keys(keys);
    keyRows = Object.entries(keys).map(([control, entry]) => {
      const kind = kindOf(entry);
      return { uid: allocUid(), control, kind, value: valueOf(entry, kind) };
    });

    const screen = (mapping.screen_encoders ?? {}) as Record<string, unknown>;
    originalScreenSlots = Object.keys(screen);
    const encoders = (mapping.encoders ?? []) as Record<string, unknown>[];
    encoderRows = encoders.map((entry) => {
      const slot = entry.slot != null ? Number(entry.slot) : null;
      const screenName = slot == null ? null : screen[String(slot)];
      return {
        uid: allocUid(),
        id: Number(entry.id),
        kind: slot != null ? 'slot' : 'attribute',
        value: String(slot ?? entry.attribute ?? ''),
        screen: screenName == null ? '' : String(screenName),
      };
    });

    const modifiers = (mapping.modifiers ?? {}) as Record<string, Record<string, unknown>>;
    originalModifiers = Object.keys(modifiers);
    modifierRows = Object.entries(modifiers).map(([control, entry]) => ({
      uid: allocUid(),
      control,
      kind: entry.local === true ? 'local' : 'hardkey',
      hardkey: entry.hardkey == null ? '' : String(entry.hardkey),
    }));

    const playbacks = (mapping.playbacks ?? {}) as Record<string, Record<string, unknown>>;
    originalPlaybacks = Object.keys(playbacks);
    const absolute = new Set(
      deviceList.flatMap((device) => valueControlsOf(device).map((entry) => entry.control)),
    );
    const rows: PlaybackRow[] = Object.entries(playbacks).map(([control, entry]) => ({
      uid: allocUid(),
      control,
      page: String(entry.page ?? ''),
      executor: String(entry.executor ?? ''),
      kind: entry.kind === 'fader' ? 'fader' : 'button',
      button: String(entry.button ?? 1),
      accelerated: entry.accelerated === true,
      enabled: true,
      fixed: absolute.has(control),
    }));
    const present = new Set(rows.map((row) => row.control));
    for (const control of [...absolute].sort()) {
      if (present.has(control)) continue;
      rows.push({
        uid: allocUid(),
        control,
        page: '',
        executor: '',
        kind: 'fader',
        button: '1',
        accelerated: false,
        enabled: false,
        fixed: true,
      });
    }
    playbackRows = rows;
  }

  async function loadInitial(): Promise<void> {
    try {
      const [config, deviceList] = await Promise.all([api.config(), api.devices()]);
      devices = deviceList;
      loadMapping(config, deviceList);
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void loadInitial();
    if (!learnStore) return;
    learnState = learnStore.state.learn;
    presence = learnStore.state.status?.presence ?? {};
    return learnStore.subscribe(() => {
      learnState = learnStore.state.learn;
      presence = learnStore.state.status?.presence ?? {};
      applyLearn(learnState);
    });
  });

  onDestroy(() => {
    if (pendingLearn !== null && typeof api.cancelLearn === 'function') {
      void api.cancelLearn().catch(() => {});
    }
  });

  function applyLearn(result: LearnResult | null): void {
    if (!pendingLearn || !result) return;
    if (result.status === 'timeout') {
      pendingLearn = null;
      message = { ok: true, text: 'Learn abgelaufen – keine Eingabe erkannt.' };
      return;
    }
    if (result.status === 'cancelled') {
      pendingLearn = null;
      return;
    }
    if (result.status !== 'captured') return;
    if (result.kind !== pendingLearn.kind) return;
    const targetUid = pendingLearn.uid;
    learnedControl = result.control ?? null;
    if (result.kind === 'key' && result.control) {
      const row = keyRows.find((entry) => entry.uid === targetUid);
      if (row) {
        row.control = result.control;
        dirty = true;
      }
    } else if (result.kind === 'encoder') {
      const id = Number(result.control?.split('.')[1] ?? 0);
      const row = encoderRows.find((entry) => entry.uid === targetUid);
      if (row && id > 0) {
        row.id = id;
        dirty = true;
      }
    }
    pendingLearn = null;
  }

  async function startLearn(
    kind: 'key' | 'encoder',
    control: string,
    uid: number,
  ): Promise<void> {
    pendingLearn = { kind, uid };
    learnedControl = null;
    message = null;
    try {
      await api.startLearn(kind, deviceForControl(control));
      message = { ok: true, text: `Learn aktiv – bitte ${kind === 'key' ? 'Taste drücken' : 'Encoder drehen'}.` };
    } catch (error) {
      pendingLearn = null;
      message = { ok: false, text: errorText(error) };
    }
  }

  async function cancelActiveLearn(): Promise<void> {
    try {
      if (typeof api.cancelLearn === 'function') {
        await api.cancelLearn();
      }
      message = { ok: true, text: 'Learn abgebrochen.' };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      pendingLearn = null;
    }
  }

  function addKey(): void {
    keyRows = [...keyRows, { uid: allocUid(), control: keyControls[0] ?? '', kind: 'hardkey', value: '' }];
    dirty = true;
  }

  function addEncoder(): void {
    const next = encoderIds.find((id) => !encoderRows.some((row) => row.id === id)) ?? encoderIds[0] ?? 1;
    encoderRows = [...encoderRows, { uid: allocUid(), id: next, kind: 'slot', value: '1', screen: '' }];
    dirty = true;
  }

  function addModifier(): void {
    modifierRows = [
      ...modifierRows,
      { uid: allocUid(), control: keyControls[0] ?? '', kind: 'hardkey', hardkey: '' },
    ];
    dirty = true;
  }

  function addPlayback(): void {
    const used = new Set(playbackRows.map((row) => row.control));
    const next = allControls.find((control) => !used.has(control)) ?? '';
    if (!next) {
      message = { ok: false, text: 'Alle Controls haben bereits ein Playback-Ziel.' };
      return;
    }
    playbackRows = [
      ...playbackRows,
      {
        uid: allocUid(),
        control: next,
        page: '1',
        executor: '1',
        kind: 'button',
        button: '1',
        accelerated: false,
        enabled: true,
        fixed: false,
      },
    ];
    dirty = true;
  }

  function removePlayback(uid: number): void {
    const index = playbackRows.findIndex((entry) => entry.uid === uid);
    if (index < 0) return;
    const row = playbackRows[index];
    if (row.fixed) {
      row.enabled = false;
    } else {
      playbackRows = removeByUid(playbackRows, uid);
    }
    dirty = true;
  }

  function positiveInteger(value: string): boolean {
    const number = Number(value);
    return Number.isInteger(number) && number >= 1;
  }

  function validPage(value: string): boolean {
    return value === 'current' || positiveInteger(value);
  }

  function playbackInvalid(row: PlaybackRow): boolean {
    if (!row.enabled) return false;
    if (!row.control) return true;
    if (!validPage(row.page) || !positiveInteger(row.executor)) return true;
    if (row.kind === 'button' && !['1', '2', '3'].includes(String(Number(row.button)))) return true;
    return false;
  }

  function playbackError(): string | null {
    const seen: Record<string, boolean> = {};
    for (const row of playbackRows) {
      if (!row.enabled) continue;
      if (seen[row.control]) return `Control ${row.control} ist doppelt zugewiesen.`;
      seen[row.control] = true;
      if (!row.control) return 'Bitte für jedes aktive Playback-Ziel ein Control wählen.';
      if (!validPage(row.page) || !positiveInteger(row.executor)) {
        return `Page von ${row.control} muss eine Zahl ab 1 oder "current" sein, Executor eine Zahl ab 1.`;
      }
      if (row.kind === 'button' && !['1', '2', '3'].includes(String(Number(row.button)))) {
        return `Button von ${row.control} muss 1, 2 oder 3 sein.`;
      }
    }
    return null;
  }

  function removeByUid<T extends { uid: number }>(rows: T[], uid: number): T[] {
    return rows.filter((row) => row.uid !== uid);
  }

  function patch(): Record<string, unknown> {
    const keys: Record<string, Record<string, unknown> | null> = {};
    for (const row of keyRows) {
      if (!row.control) continue;
      const baseKey = {
        hardkey: null,
        command: null,
        screen_mode: null,
        encoder_press: null,
        screen: null,
      };
      if (row.kind === 'screen_mode') {
        keys[row.control] = { ...baseKey, screen_mode: true };
      } else if (row.kind === 'screen' || row.kind === 'encoder_press') {
        keys[row.control] = { ...baseKey, [row.kind]: Number(row.value) };
      } else {
        keys[row.control] = { ...baseKey, [row.kind]: row.value };
      }
    }
    for (const control of originalKeys) {
      if (!(control in keys)) keys[control] = null;
    }

    const encoders = encoderRows.map((row) => ({
      id: row.id,
      [row.kind]: row.kind === 'slot' ? Number(row.value) : row.value,
    }));

    const modifiers: Record<string, Record<string, unknown> | null> = {};
    for (const row of modifierRows) {
      if (!row.control) continue;
      if (row.kind === 'local') {
        modifiers[row.control] = { local: true, hardkey: null };
      } else if (row.hardkey) {
        modifiers[row.control] = { hardkey: row.hardkey, local: null };
      }
    }
    for (const control of originalModifiers) {
      if (!(control in modifiers)) modifiers[control] = null;
    }

    const screenEncoders: Record<string, number | null> = {};
    for (const row of encoderRows) {
      if (row.kind !== 'slot') continue;
      const slot = Number(row.value);
      if (!Number.isInteger(slot) || slot < 1 || slot > 4) continue;
      const number = Number(row.screen);
      if (row.screen.trim() && Number.isInteger(number)) {
        screenEncoders[String(slot)] = number;
      }
    }
    for (const slot of originalScreenSlots) {
      if (!(slot in screenEncoders)) screenEncoders[slot] = null;
    }

    const playbacks: Record<string, Record<string, unknown> | null> = {};
    for (const row of playbackRows) {
      if (!row.enabled || !row.control) continue;
      const page = row.page === 'current' ? 'current' : Number(row.page);
      if (page !== 'current' && (!Number.isInteger(page) || page < 1)) continue;
      const executor = Number(row.executor);
      if (!Number.isInteger(executor) || executor < 1) continue;
      if (row.kind === 'button') {
        playbacks[row.control] = {
          page,
          executor,
          kind: 'button',
          button: Number(row.button),
          accelerated: null,
        };
      } else {
        playbacks[row.control] = {
          page,
          executor,
          kind: 'fader',
          button: null,
          accelerated: encoderControls.has(row.control) ? row.accelerated : null,
        };
      }
    }
    for (const control of originalPlaybacks) {
      if (!(control in playbacks)) playbacks[control] = null;
    }

    const mapping: Record<string, unknown> = { keys, encoders, modifiers };
    if (Object.keys(screenEncoders).length > 0) {
      mapping.screen_encoders = screenEncoders;
    }
    if (Object.keys(playbacks).length > 0) {
      mapping.playbacks = playbacks;
    }
    return { mapping };
  }

  function refreshOriginals(
    payload: Record<string, unknown>,
    res: Record<string, unknown> | undefined,
  ): void {
    const resConfig =
      res && typeof res === 'object' && 'config' in res && res.config && typeof res.config === 'object'
        ? (res.config as Record<string, unknown>)
        : null;
    if (resConfig) {
      const savedMapping = (resConfig.mapping ?? {}) as Record<string, unknown>;
      originalKeys = Object.keys((savedMapping.keys ?? {}) as Record<string, unknown>);
      originalModifiers = Object.keys((savedMapping.modifiers ?? {}) as Record<string, unknown>);
      originalScreenSlots = Object.keys(
        (savedMapping.screen_encoders ?? {}) as Record<string, unknown>,
      );
      originalPlaybacks = Object.keys((savedMapping.playbacks ?? {}) as Record<string, unknown>);
      return;
    }
    const sent = (payload.mapping ?? {}) as Record<string, Record<string, unknown>>;
    originalKeys = Object.entries(sent.keys ?? {})
      .filter(([, value]) => value !== null)
      .map(([key]) => key);
    originalModifiers = Object.entries(sent.modifiers ?? {})
      .filter(([, value]) => value !== null)
      .map(([key]) => key);
    originalScreenSlots = Object.entries(sent.screen_encoders ?? {})
      .filter(([, value]) => value !== null)
      .map(([key]) => key);
    originalPlaybacks = Object.entries(sent.playbacks ?? {})
      .filter(([, value]) => value !== null)
      .map(([key]) => key);
  }

  async function save(): Promise<void> {
    const invalid = playbackError();
    if (invalid) {
      message = { ok: false, text: invalid };
      return;
    }
    busy = true;
    message = null;
    try {
      const payload = patch();
      const res = await api.updateConfig(payload);
      refreshOriginals(payload, res);
      dirty = false;
      message = { ok: true, text: 'Mapping gespeichert und angewendet.' };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }
</script>

<section class="page mapping-page">
  <h1>Geräte &amp; Mapping</h1>

  {#if loading}
    <p class="muted">Lade Geräte und Mapping …</p>
  {:else}
    <h2>Geräte</h2>
    <ul class="devices">
      {#each visibleDevices as device (device.name)}
        {@const state = presence[device.name]}
        {@const connected = state ? state.connected : device.detected !== null}
        <li>
          <strong>{device.name}</strong>
          <span class="muted">
            {device.vendor_product} · {device.profile} ·
            {connected ? 'verbunden' : 'verbindung verloren'}
          </span>
          {#if valueControlsOf(device).length > 0}
            <span class="muted">
              · Werte:
              {valueControlsOf(device)
                .map((entry) => `${entry.control} (${entry.note}, ${entry.kind})`)
                .join(', ')}
            </span>
          {/if}
        </li>
      {/each}
    </ul>

    <h2>Tasten</h2>
    <table>
      <thead>
        <tr>
          <th>Control</th>
          <th>Aktion</th>
          <th>Wert</th>
          <th>Lernen</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each keyRows as row (row.uid)}
          <tr>
            <td>
              <select bind:value={row.control} onchange={() => (dirty = true)}>
                {#each keyControls as control (control)}
                  <option value={control}>{control}</option>
                {/each}
                {#if !keyControls.includes(row.control)}
                  <option value={row.control}>{row.control}</option>
                {/if}
              </select>
            </td>
            <td>
              <select
                bind:value={row.kind}
                onchange={() => (dirty = true)}
                data-testid="key-kind"
              >
                {#each keyKinds as kind (kind)}
                  <option value={kind}>{kind}</option>
                {/each}
              </select>
            </td>
            <td>
              {#if row.kind === 'screen_mode'}
                <span class="muted">–</span>
              {:else}
                <input
                  bind:value={row.value}
                  oninput={() => (dirty = true)}
                  data-testid="key-value"
                />
              {/if}
            </td>
            <td>
              <button
                type="button"
                onclick={() => startLearn('key', row.control, row.uid)}
                disabled={busy || pendingLearn !== null}
                data-testid="key-learn"
              >
                Lernen
              </button>
            </td>
            <td>
              <button
                type="button"
                class="danger"
                onclick={() => {
                  keyRows = removeByUid(keyRows, row.uid);
                  dirty = true;
                }}
              >
                Entfernen
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <button type="button" onclick={addKey}>Taste hinzufügen</button>

    <h2>Encoder</h2>
    <p class="muted">
      Ziel = was der Encoder im Attribut-Modus dreht. Screen-Encoder = was
      derselbe Encoder im Screen-Modus dreht (Taste asl_bank oder MA halten).
      Standard: Encoder 1 → 8, Encoder 2 → 7, Encoder 3 → 6, Encoder 4 → 5
      (Screen-Encoder 5–10, wie bei ShowCockpit).
    </p>
    <table>
      <thead>
        <tr>
          <th>Encoder</th>
          <th>Ziel</th>
          <th>Wert</th>
          <th>Screen-Encoder</th>
          <th>Lernen</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each encoderRows as row (row.uid)}
          <tr>
            <td>
              <select bind:value={row.id} onchange={() => (dirty = true)}>
                {#each encoderIds as id (id)}
                  <option value={id}>Encoder {id}</option>
                {/each}
                {#if !encoderIds.includes(row.id)}
                  <option value={row.id}>Encoder {row.id}</option>
                {/if}
              </select>
            </td>
            <td>
              <select bind:value={row.kind} onchange={() => (dirty = true)}>
                <option value="slot">Slot</option>
                <option value="attribute">Attribut</option>
              </select>
            </td>
            <td>
              <input
                bind:value={row.value}
                oninput={() => (dirty = true)}
                data-testid="encoder-value"
              />
            </td>
            <td>
              {#if row.kind === 'slot' && Number(row.value) >= 1 && Number(row.value) <= 4}
                <select
                  bind:value={row.screen}
                  onchange={() => (dirty = true)}
                  data-testid="screen-encoder-target"
                >
                  <option value="">— keiner —</option>
                  <option value="5">Screen-Encoder 5</option>
                  <option value="6">Screen-Encoder 6</option>
                  <option value="7">Screen-Encoder 7</option>
                  <option value="8">Screen-Encoder 8</option>
                  <option value="9">Screen-Encoder 9</option>
                  <option value="10">Screen-Encoder 10</option>
                  {#if row.screen && !['5', '6', '7', '8', '9', '10'].includes(row.screen)}
                    <option value={row.screen}>{row.screen}</option>
                  {/if}
                </select>
              {:else}
                <span class="muted">–</span>
              {/if}
            </td>
            <td>
              <button
                type="button"
                onclick={() => startLearn('encoder', `encoder.${row.id}`, row.uid)}
                disabled={busy || pendingLearn !== null}
                data-testid="encoder-learn"
              >
                Lernen
              </button>
            </td>
            <td>
              <button
                type="button"
                class="danger"
                onclick={() => {
                  encoderRows = removeByUid(encoderRows, row.uid);
                  dirty = true;
                }}
              >
                Entfernen
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <button type="button" onclick={addEncoder}>Encoder hinzufügen</button>

    <h2>Modifier</h2>
    <table>
      <thead>
        <tr>
          <th>Control</th>
          <th>Art</th>
          <th>Hardkey</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each modifierRows as row (row.uid)}
          <tr>
            <td>
              <select bind:value={row.control} onchange={() => (dirty = true)}>
                {#each keyControls as control (control)}
                  <option value={control}>{control}</option>
                {/each}
                {#if !keyControls.includes(row.control)}
                  <option value={row.control}>{row.control}</option>
                {/if}
              </select>
            </td>
            <td>
              <select
                bind:value={row.kind}
                onchange={() => (dirty = true)}
                data-testid="modifier-kind"
              >
                <option value="hardkey">Hardkey</option>
                <option value="local">Lokal</option>
              </select>
            </td>
            <td>
              {#if row.kind === 'local'}
                <span class="muted">(lokal)</span>
              {:else}
                <input
                  bind:value={row.hardkey}
                  oninput={() => (dirty = true)}
                  data-testid="modifier-hardkey"
                />
              {/if}
            </td>
            <td>
              <button
                type="button"
                class="danger"
                onclick={() => {
                  modifierRows = removeByUid(modifierRows, row.uid);
                  dirty = true;
                }}
              >
                Entfernen
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <button type="button" onclick={addModifier}>Modifier hinzufügen</button>

    <h2>Playback-Ziele</h2>
    <p class="muted">
      Fader und absolute Encoder senden ihren Wert direkt an einen Executor.
      Page und Executor sind wie in der MA 1-basiert; für Page kann auch
      <code>current</code> stehen, dann folgt das Ziel der aktuell aktiven
      Master-Page. Button 1–3 entspricht den drei Executor-Buttons. Ohne PickUp
      springt ein Executor nach einem Seitenwechsel auf die physische
      Faderposition.
    </p>
    <table>
      <thead>
        <tr>
          <th>Aktiv</th>
          <th>Control</th>
          <th>Art</th>
          <th>Page</th>
          <th>Executor</th>
          <th>Button</th>
          <th>Beschl.</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each playbackRows as row (row.uid)}
          <tr data-control={row.control}>
            <td>
              <input
                type="checkbox"
                bind:checked={row.enabled}
                onchange={() => (dirty = true)}
                data-testid="playback-enabled"
              />
            </td>
            <td>
              {#if row.fixed}
                <span>{row.control}</span>
              {:else}
                <select
                  bind:value={row.control}
                  onchange={() => (dirty = true)}
                  data-testid="playback-control"
                >
                  {#each allControls as control (control)}
                    <option value={control}>{control}</option>
                  {/each}
                  {#if !allControls.includes(row.control)}
                    <option value={row.control}>{row.control}</option>
                  {/if}
                </select>
              {/if}
            </td>
            <td>
              <select
                bind:value={row.kind}
                onchange={() => (dirty = true)}
                data-testid="playback-kind"
              >
                <option value="button">Button</option>
                <option value="fader">Fader</option>
              </select>
            </td>
            <td>
              <input
                type="text"
                bind:value={row.page}
                oninput={() => (dirty = true)}
                class={{ error: playbackInvalid(row) }}
                disabled={!row.enabled}
                placeholder="1 / current"
                data-testid="playback-page"
              />
            </td>
            <td>
              <input
                type="text"
                inputmode="numeric"
                bind:value={row.executor}
                oninput={() => (dirty = true)}
                class={{ error: playbackInvalid(row) }}
                disabled={!row.enabled}
                data-testid="playback-executor"
              />
            </td>
            <td>
              {#if row.kind === 'button'}
                <input
                  type="text"
                  inputmode="numeric"
                  bind:value={row.button}
                  oninput={() => (dirty = true)}
                  class={{ error: playbackInvalid(row) }}
                  disabled={!row.enabled}
                  data-testid="playback-button"
                />
              {:else}
                <span class="muted">–</span>
              {/if}
            </td>
            <td>
              {#if row.kind === 'fader' && encoderControls.has(row.control)}
                <input
                  type="checkbox"
                  bind:checked={row.accelerated}
                  onchange={() => (dirty = true)}
                  disabled={!row.enabled}
                  title="Langsam fein, schnell weit"
                  data-testid="playback-accelerated"
                />
              {:else}
                <span class="muted">–</span>
              {/if}
            </td>
            <td>
              <button
                type="button"
                class="danger"
                onclick={() => removePlayback(row.uid)}
                data-testid="playback-remove"
              >
                {row.fixed ? 'Deaktivieren' : 'Entfernen'}
              </button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <button type="button" onclick={addPlayback} data-testid="playback-add">
      Playback-Ziel hinzufügen
    </button>

    <div class="actions">
      <button type="button" onclick={save} disabled={busy || !dirty}>
        Speichern
      </button>
      {#if pendingLearn !== null}
        <button type="button" onclick={cancelActiveLearn} data-testid="learn-cancel">
          Abbrechen
        </button>
      {/if}
      {#if dirty}
        <span class="dirty" data-testid="dirty">Ungespeicherte Änderungen</span>
      {/if}
    </div>

    {#if message}
      <p class={['message', { error: !message.ok }]} role={message.ok ? 'status' : 'alert'}>
        {message.text}
      </p>
    {/if}

    {#if learnState}
      <p class="learn">
        Learn: {learnState.kind} {learnState.status}
        {#if learnState.control}· {learnState.control}{/if}
        {#if learnedControl}· zuletzt {learnedControl}{/if}
      </p>
    {/if}
  {/if}
</section>

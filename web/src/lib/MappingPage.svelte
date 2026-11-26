<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient, type DeviceEntry, type DeviceValueControl, type LearnResult } from './api';
  import type { StatusStore } from './status';

  type KeyKind = 'hardkey' | 'command' | 'screen_mode' | 'screen' | 'encoder_press';
  type EncoderKind = 'slot' | 'attribute';
  type PlaybackKind = 'button' | 'fader';

  interface KeyRow {
    control: string;
    kind: KeyKind;
    value: string;
  }

  interface EncoderRow {
    id: number;
    kind: EncoderKind;
    value: string;
    screen: string;
  }

  interface ModifierRow {
    control: string;
    hardkey: string;
  }

  interface PlaybackRow {
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

  let devices = $state<DeviceEntry[]>([]);
  let detectedDevices = $derived(
    devices.filter((device) => device.detected !== null),
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
  let pendingLearn = $state<null | { kind: 'key' | 'encoder'; index: number }>(null);
  let learnedControl = $state<string | null>(null);

  const keyKinds: KeyKind[] = [
    'hardkey',
    'command',
    'screen',
    'encoder_press',
    'screen_mode',
  ];

  const keyControls = $derived(
    [...new Set(devices.flatMap((device) => {
      const controls = device.controls as unknown as {
        keys?: { control: string }[];
        notes?: { control: string }[];
      };
      return [
        ...(controls.keys ?? []).map((entry) => entry.control),
        ...(controls.notes ?? []).map((entry) => entry.control),
      ];
    }))].sort(),
  );

  const allControls = $derived(
    [...new Set([
      ...keyControls,
      ...devices.flatMap((device) =>
        valueControlsOf(device).map((entry) => entry.control),
      ),
    ])].sort(),
  );

  function valueControlsOf(device: DeviceEntry): DeviceValueControl[] {    return ((device.controls as { values?: DeviceValueControl[] }).values ?? []);
  }

  const encoderIds = $derived(
    [...new Set(devices.flatMap((device) => {
      const controls = device.controls as unknown as {
        encoders?: { id: number }[];
        midi_encoders?: { id: number }[];
      };
      return [
        ...(controls.encoders ?? []).map((entry) => entry.id),
        ...(controls.midi_encoders ?? []).map((entry) => entry.id),
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
        encoders?: { control: string }[];
        midi_encoders?: { control: string }[];
        values?: DeviceValueControl[];
      };
      const names = [
        ...(controls.keys ?? []).map((entry) => entry.control),
        ...(controls.notes ?? []).map((entry) => entry.control),
        ...(controls.encoders ?? []).map((entry) => entry.control),
        ...(controls.midi_encoders ?? []).map((entry) => entry.control),
        ...(controls.values ?? []).map((entry) => entry.control),
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
      return { control, kind, value: valueOf(entry, kind) };
    });

    const screen = (mapping.screen_encoders ?? {}) as Record<string, unknown>;
    originalScreenSlots = Object.keys(screen);
    const encoders = (mapping.encoders ?? []) as Record<string, unknown>[];
    encoderRows = encoders.map((entry) => {
      const slot = entry.slot != null ? Number(entry.slot) : null;
      const screenName = slot == null ? null : screen[String(slot)];
      return {
        id: Number(entry.id),
        kind: slot != null ? 'slot' : 'attribute',
        value: String(slot ?? entry.attribute ?? ''),
        screen: screenName == null ? '' : String(screenName),
      };
    });

    const modifiers = (mapping.modifiers ?? {}) as Record<string, Record<string, unknown>>;
    originalModifiers = Object.keys(modifiers).filter(
      (control) => modifiers[control].hardkey != null,
    );
    modifierRows = originalModifiers.map((control) => ({
      control,
      hardkey: String(modifiers[control].hardkey),
    }));

    const playbacks = (mapping.playbacks ?? {}) as Record<string, Record<string, unknown>>;
    originalPlaybacks = Object.keys(playbacks);
    const absolute = new Set(
      deviceList.flatMap((device) => valueControlsOf(device).map((entry) => entry.control)),
    );
    const rows: PlaybackRow[] = Object.entries(playbacks).map(([control, entry]) => ({
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

  onMount(async () => {
    try {
      const [config, deviceList] = await Promise.all([api.config(), api.devices()]);
      devices = deviceList;
      loadMapping(config, deviceList);
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      loading = false;
    }
  });

  $effect(() => {
    if (!learnStore) return;
    learnState = learnStore.state.learn;
    return learnStore.subscribe(() => {
      learnState = learnStore.state.learn;
      applyLearn(learnState);
    });
  });

  function applyLearn(result: LearnResult | null): void {
    if (!pendingLearn || !result || result.status !== 'captured') return;
    if (result.kind !== pendingLearn.kind) return;
    learnedControl = result.control ?? null;
    if (result.kind === 'key' && result.control) {
      const row = keyRows[pendingLearn.index];
      if (row) {
        row.control = result.control;
        dirty = true;
      }
    } else if (result.kind === 'encoder') {
      const id = Number(result.control?.split('.')[1] ?? 0);
      const row = encoderRows[pendingLearn.index];
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
    index: number,
  ): Promise<void> {
    pendingLearn = { kind, index };
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

  function addKey(): void {
    keyRows = [...keyRows, { control: keyControls[0] ?? '', kind: 'hardkey', value: '' }];
    dirty = true;
  }

  function addEncoder(): void {
    const next = encoderIds.find((id) => !encoderRows.some((row) => row.id === id)) ?? encoderIds[0] ?? 1;
    encoderRows = [...encoderRows, { id: next, kind: 'slot', value: '1', screen: '' }];
    dirty = true;
  }

  function addModifier(): void {
    modifierRows = [...modifierRows, { control: keyControls[0] ?? '', hardkey: '' }];
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
      { control: next, page: '1', executor: '1', kind: 'button', button: '1', accelerated: false, enabled: true, fixed: false },
    ];
    dirty = true;
  }

  function removePlayback(index: number): void {
    const row = playbackRows[index];
    if (!row) return;
    if (row.fixed) {
      row.enabled = false;
    } else {
      playbackRows = removeAt(playbackRows, index);
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
    const seen = new Set<string>();
    for (const row of playbackRows) {
      if (!row.enabled) continue;
      if (seen.has(row.control)) return `Control ${row.control} ist doppelt zugewiesen.`;
      seen.add(row.control);
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

  function removeAt<T>(rows: T[], index: number): T[] {
    return rows.filter((_, position) => position !== index);
  }

  function patch(): Record<string, unknown> {
    const keys: Record<string, Record<string, unknown> | null> = {};
    for (const row of keyRows) {
      if (!row.control) continue;
      if (row.kind === 'screen_mode') {
        keys[row.control] = { screen_mode: true };
      } else if (row.kind === 'screen' || row.kind === 'encoder_press') {
        keys[row.control] = { [row.kind]: Number(row.value) };
      } else {
        keys[row.control] = { [row.kind]: row.value };
      }
    }
    for (const control of originalKeys) {
      if (!(control in keys)) keys[control] = null;
    }
    const encoders = encoderRows.map((row) => ({
      id: row.id,
      [row.kind]: row.kind === 'slot' ? Number(row.value) : row.value,
    }));
    const modifiers: Record<string, { hardkey: string } | null> = {};
    for (const row of modifierRows) {
      if (row.control && row.hardkey) modifiers[row.control] = { hardkey: row.hardkey };
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
        const target: Record<string, unknown> = {
          page,
          executor,
          kind: 'button',
          button: Number(row.button),
        };
        if (encoderControls.has(row.control)) target.accelerated = false;
        playbacks[row.control] = target;
      } else {
        const target: Record<string, unknown> = { page, executor, kind: 'fader' };
        if (encoderControls.has(row.control)) target.accelerated = row.accelerated;
        playbacks[row.control] = target;
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

  async function save(): Promise<void> {
    const invalid = playbackError();
    if (invalid) {
      message = { ok: false, text: invalid };
      return;
    }
    busy = true;
    message = null;
    try {
      await api.updateConfig(patch());
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
    <h2>Erkannte Geräte</h2>
    <ul class="devices">
      {#each detectedDevices as device (device.name)}
        <li>
          <strong>{device.name}</strong>
          <span class="muted">
            {device.vendor_product} · {device.profile} ·
            {device.detected ? 'erkannt' : 'nicht erkannt'}
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
        {#each keyRows as row, index (index)}
          <tr>
            <td>
              <select bind:value={row.control} onchange={() => (dirty = true)}>
                {#each keyControls as control}
                  <option value={control}>{control}</option>
                {/each}
                {#if !keyControls.includes(row.control)}
                  <option value={row.control}>{row.control}</option>
                {/if}
              </select>
            </td>
            <td>
              <select bind:value={row.kind} onchange={() => (dirty = true)}>
                {#each keyKinds as kind}
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
                onclick={() => startLearn('key', row.control, index)}
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
                  keyRows = removeAt(keyRows, index);
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
        {#each encoderRows as row, index (index)}
          <tr>
            <td>
              <select bind:value={row.id} onchange={() => (dirty = true)}>
                {#each encoderIds as id}
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
                  {#if row.screen && !['5', '6', '7', '8'].includes(row.screen)}
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
                onclick={() => startLearn('encoder', `encoder.${row.id}`, index)}
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
                  encoderRows = removeAt(encoderRows, index);
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
          <th>Hardkey</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each modifierRows as row, index (index)}
          <tr>
            <td>
              <select bind:value={row.control} onchange={() => (dirty = true)}>
                {#each keyControls as control}
                  <option value={control}>{control}</option>
                {/each}
              </select>
            </td>
            <td>
              <input bind:value={row.hardkey} oninput={() => (dirty = true)} />
            </td>
            <td>
              <button
                type="button"
                class="danger"
                onclick={() => {
                  modifierRows = removeAt(modifierRows, index);
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
        {#each playbackRows as row, index (index)}
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
                  {#each allControls as control}
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
                class:error={playbackInvalid(row)}
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
                class:error={playbackInvalid(row)}
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
                  class:error={playbackInvalid(row)}
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
                onclick={() => removePlayback(index)}
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
      {#if dirty}
        <span class="dirty" data-testid="dirty">Ungespeicherte Änderungen</span>
      {/if}
    </div>

    {#if message}
      <p class:error={!message.ok} class="message" role={message.ok ? 'status' : 'alert'}>
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

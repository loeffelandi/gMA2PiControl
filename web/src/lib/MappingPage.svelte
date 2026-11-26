<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient, type DeviceEntry, type LearnResult } from './api';
  import type { StatusStore } from './status';

  type KeyKind = 'hardkey' | 'command' | 'screen_mode' | 'screen' | 'encoder_fine';
  type EncoderKind = 'slot' | 'attribute';

  interface KeyRow {
    control: string;
    kind: KeyKind;
    value: string;
  }

  interface EncoderRow {
    id: number;
    kind: EncoderKind;
    value: string;
  }

  interface ModifierRow {
    control: string;
    hardkey: string;
  }

  let { api, learnStore }: { api: ApiClient; learnStore?: StatusStore } = $props();

  let devices = $state<DeviceEntry[]>([]);
  let keyRows = $state<KeyRow[]>([]);
  let encoderRows = $state<EncoderRow[]>([]);
  let modifierRows = $state<ModifierRow[]>([]);
  let originalKeys: string[] = [];
  let originalModifiers: string[] = [];
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
    'encoder_fine',
    'screen_mode',
  ];

  const keyControls = $derived(
    [...new Set(devices.flatMap((device) => {
      const controls = device.controls as {
        keys?: { control: string }[];
        notes?: { control: string }[];
      };
      return [
        ...(controls.keys ?? []).map((entry) => entry.control),
        ...(controls.notes ?? []).map((entry) => entry.control),
      ];
    }))].sort(),
  );

  const encoderIds = $derived(
    [...new Set(devices.flatMap((device) => {
      const controls = device.controls as {
        encoders?: { id: number }[];
        midi_encoders?: { id: number }[];
      };
      return [
        ...(controls.encoders ?? []).map((entry) => entry.id),
        ...(controls.midi_encoders ?? []).map((entry) => entry.id),
      ];
    }))].sort((left, right) => left - right),
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
    if (entry.encoder_fine != null) return 'encoder_fine';
    return 'screen_mode';
  }

  function valueOf(entry: Record<string, unknown>, kind: KeyKind): string {
    if (kind === 'screen_mode') return '';
    const value = entry[kind];
    return value == null ? '' : String(value);
  }

  function deviceForControl(control: string): string | undefined {
    return devices.find((device) => {
      const controls = device.controls as {
        keys?: { control: string }[];
        notes?: { control: string }[];
        encoders?: { control: string }[];
        midi_encoders?: { control: string }[];
      };
      const names = [
        ...(controls.keys ?? []).map((entry) => entry.control),
        ...(controls.notes ?? []).map((entry) => entry.control),
        ...(controls.encoders ?? []).map((entry) => entry.control),
        ...(controls.midi_encoders ?? []).map((entry) => entry.control),
      ];
      return names.includes(control);
    })?.name;
  }

  function loadMapping(config: Record<string, unknown>): void {
    const mapping = (config.mapping ?? {}) as Record<string, unknown>;
    const keys = (mapping.keys ?? {}) as Record<string, Record<string, unknown>>;
    originalKeys = Object.keys(keys);
    keyRows = Object.entries(keys).map(([control, entry]) => {
      const kind = kindOf(entry);
      return { control, kind, value: valueOf(entry, kind) };
    });

    const encoders = (mapping.encoders ?? []) as Record<string, unknown>[];
    encoderRows = encoders.map((entry) => ({
      id: Number(entry.id),
      kind: entry.slot != null ? 'slot' : 'attribute',
      value: String(entry.slot ?? entry.attribute ?? ''),
    }));

    const modifiers = (mapping.modifiers ?? {}) as Record<string, Record<string, unknown>>;
    originalModifiers = Object.keys(modifiers).filter(
      (control) => modifiers[control].hardkey != null,
    );
    modifierRows = originalModifiers.map((control) => ({
      control,
      hardkey: String(modifiers[control].hardkey),
    }));
  }

  onMount(async () => {
    try {
      const [config, deviceList] = await Promise.all([api.config(), api.devices()]);
      devices = deviceList;
      loadMapping(config);
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
    encoderRows = [...encoderRows, { id: next, kind: 'slot', value: '1' }];
    dirty = true;
  }

  function addModifier(): void {
    modifierRows = [...modifierRows, { control: keyControls[0] ?? '', hardkey: '' }];
    dirty = true;
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
      } else if (row.kind === 'screen' || row.kind === 'encoder_fine') {
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
    return { mapping: { keys, encoders, modifiers } };
  }

  async function save(): Promise<void> {
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
      {#each devices as device (device.name)}
        <li>
          <strong>{device.name}</strong>
          <span class="muted">
            {device.vendor_product} · {device.profile} ·
            {device.detected ? 'erkannt' : 'nicht erkannt'}
          </span>
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
    <table>
      <thead>
        <tr>
          <th>Encoder</th>
          <th>Ziel</th>
          <th>Wert</th>
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

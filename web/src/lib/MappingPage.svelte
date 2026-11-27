<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte';

  import type { ApiClient } from './api';
  import AssignmentBadges from './AssignmentBadges.svelte';
  import AssignmentDialog from './AssignmentDialog.svelte';
  import BankSettings from './BankSettings.svelte';
  import { ConfigStore } from './configStore.svelte';
  import ConflictNotice from './ConflictNotice.svelte';
  import type { ControlInfo } from './deviceControls';
  import LearnStatusBar from './LearnStatusBar.svelte';
  import type { StatusStore } from './status';

  interface Props {
    api: ApiClient;
    /** Live status (presence, learn events). */
    store?: StatusStore;
    /** Shared configuration state; created here when the tab runs on its own. */
    configStore?: ConfigStore;
    /** Switch to the devices tab, e.g. to follow a note learning session. */
    onOpenDevices?: () => void;
  }

  let { api, store, configStore, onOpenDevices }: Props = $props();

  const cfg = untrack(() => configStore ?? new ConfigStore(api, store));
  const ownsStore = untrack(() => configStore === undefined);

  let dialogControls = $state.raw<ControlInfo[] | null>(null);

  const device = $derived(cfg.device);
  const controls = $derived(cfg.controls);
  const detectedHere = $derived.by(() => {
    const detected = cfg.detectedControl;
    if (!detected) return null;
    return controls.some((entry) => entry.id === detected.control) ? detected.control : null;
  });

  onMount(() => {
    void cfg.load();
  });

  onDestroy(() => {
    if (ownsStore) cfg.detach();
  });

  function edit(control: ControlInfo): void {
    dialogControls = [control];
  }

  function assignDetected(control: string): void {
    const found = controls.find((entry) => entry.id === control);
    if (!found) return;
    cfg.clearDetectedControl();
    dialogControls = [found];
  }

  function presenceText(entry: { name: string; detected: unknown }): string {
    const state = cfg.presence[entry.name];
    const connected = state ? state.connected : entry.detected !== null;
    return connected ? 'verbunden' : 'verbindung verloren';
  }

  async function startNoteLearn(): Promise<void> {
    if (!device) return;
    await cfg.startDeviceLearn(device.name, cfg.bank);
  }
</script>

<section class="page mapping-page">
  <h1>Geräte &amp; Mapping</h1>

  {#if !cfg.loaded && cfg.loading}
    <p class="muted">Lade Geräte und Mapping …</p>
  {:else}
    {#if cfg.error && !dialogControls && !cfg.conflict}
      <p class="banner" role="alert">{cfg.error}</p>
    {/if}
    {#if !dialogControls}
      <ConflictNotice store={cfg} />
    {/if}

    <h2>Geräte</h2>
    <ul class="devices">
      {#each cfg.visibleDevices as entry (entry.name)}
        <li>
          <button
            type="button"
            class={{ active: entry.name === cfg.selectedDevice }}
            onclick={() => cfg.selectDevice(entry.name)}
          >
            <strong>{entry.name}</strong>
          </button>
          <span class="muted">
            {entry.vendor_product} · {entry.profile} · {presenceText(entry)}
          </span>
        </li>
      {/each}
    </ul>
    {#if cfg.visibleDevices.length === 0}
      <p class="muted">Keine Geräte verbunden.</p>
    {/if}

    {#if device}
      <header class="head">
        <h2>{device.name}</h2>
        <label>
          Bank
          <select
            value={cfg.bank}
            onchange={(event) => cfg.selectBank(Number(event.currentTarget.value))}
          >
            {#each cfg.banks as entry (entry.number)}
              <option value={entry.number}>Bank {entry.number} · Kanal {entry.channel}</option>
            {/each}
          </select>
        </label>
      </header>

      <LearnStatusBar
        store={cfg}
        tab="mapping"
        onAssign={assignDetected}
        {onOpenDevices}
      />

      <div class="learn-actions">
        <button
          type="button"
          disabled={cfg.anyLearnActive}
          onclick={() => void cfg.startLearn('key', device.name)}
        >
          Taste erkennen
        </button>
        <button
          type="button"
          disabled={cfg.anyLearnActive}
          onclick={() => void cfg.startLearn('encoder', device.name)}
        >
          Encoder erkennen
        </button>
        {#if device.backend === 'midi'}
          <button type="button" disabled={cfg.anyLearnActive} onclick={startNoteLearn}>
            Noten anlernen (Bank {cfg.bank})
          </button>
        {/if}
      </div>

      <table>
        <thead>
          <tr>
            <th>Control</th>
            <th>Art</th>
            <th>Belegung</th>
            <th>Herkunft</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each controls as item (item.id)}
            {@const marker = cfg.markerFor(item)}
            <tr class={{ detected: item.id === detectedHere }} data-control={item.id}>
              <td>
                {item.id}
                {#if !item.bound && item.kind !== 'relative-encoder'}
                  <span class="muted">(nicht in Bank {cfg.bank} gebunden)</span>
                {/if}
              </td>
              <td>{item.kind}</td>
              <td>{cfg.labelFor(item) ?? '–'}</td>
              <td><AssignmentBadges source={marker.source} conflict={marker.conflict} /></td>
              <td>
                <button type="button" aria-label={`Bearbeiten ${item.id}`} onclick={() => edit(item)}>
                  Bearbeiten
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>

      <BankSettings store={cfg} readonly />
    {/if}

    {#if cfg.orphans.length}
      <h2>Einträge ohne verbundenes Gerät</h2>
      <table>
        <tbody>
          {#each cfg.orphans as entry (entry.control)}
            <tr>
              <td>{entry.control}</td>
              <td>{entry.text}</td>
              <td>
                <button
                  type="button"
                  class="danger"
                  aria-label={`Entfernen ${entry.control}`}
                  onclick={() => void cfg.removeOrphan(entry.control).catch(() => undefined)}
                >
                  Entfernen
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}

  {#if dialogControls && device}
    <AssignmentDialog
      store={cfg}
      controls={dialogControls}
      onClose={() => (dialogControls = null)}
    />
  {/if}
</section>

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: end;
    gap: 1rem;
    margin: 0.75rem 0;
  }

  .head h2 {
    margin: 0;
  }

  .head label {
    display: grid;
    gap: 0.2rem;
    font-size: 0.8rem;
  }

  .learn-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 0.6rem;
  }

  .devices button.active {
    outline: 2px solid var(--accent-hover);
  }

  tr.detected {
    outline: 2px solid #ffd166;
    outline-offset: -2px;
    background: rgba(255, 209, 102, 0.12);
  }
</style>

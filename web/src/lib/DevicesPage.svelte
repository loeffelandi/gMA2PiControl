<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte';

  import type { ApiClient } from './api';
  import AssignmentBadges from './AssignmentBadges.svelte';
  import AssignmentDialog from './AssignmentDialog.svelte';
  import BankSettings from './BankSettings.svelte';
  import { ConfigStore } from './configStore.svelte';
  import ConflictNotice from './ConflictNotice.svelte';
  import type { ControlInfo } from './deviceControls';
  import DeviceSurface from './DeviceSurface.svelte';
  import LearnPanel from './LearnPanel.svelte';
  import LearnStatusBar from './LearnStatusBar.svelte';
  import type { StatusStore } from './status';

  interface Props {
    api: ApiClient;
    /** Live status (presence, learn events). */
    store?: StatusStore;
    /** Shared configuration state; created here when the tab runs on its own. */
    configStore?: ConfigStore;
  }

  let { api, store, configStore }: Props = $props();

  const cfg = untrack(() => configStore ?? new ConfigStore(api, store));
  const ownsStore = untrack(() => configStore === undefined);

  let selection = $state<string[]>([]);
  let dialogControls = $state.raw<ControlInfo[] | null>(null);
  let showLearn = $state(false);
  let learnControl = $state<string | null>(null);

  const device = $derived(cfg.device);
  const controls = $derived(cfg.controls);
  const banks = $derived(cfg.banks);
  const selectedControls = $derived(
    selection
      .map((id) => controls.find((entry) => entry.id === id))
      .filter((entry): entry is ControlInfo => entry !== undefined),
  );
  const learningHere = $derived(
    cfg.deviceLearn?.active === true &&
      cfg.deviceLearn.device === device?.name &&
      cfg.deviceLearn.bank === cfg.bank,
  );
  const activeLearn = $derived(learningHere ? (cfg.deviceLearn?.current ?? null) : null);
  const activeLearnKind = $derived(
    controls.find((item) => item.id === activeLearn)?.kind ?? null,
  );
  const detectedHere = $derived.by(() => {
    const detected = cfg.detectedControl;
    if (!detected) return null;
    return controls.some((entry) => entry.id === detected.control) ? detected.control : null;
  });
  const highlighted = $derived(
    detectedHere && !selection.includes(detectedHere) ? [...selection, detectedHere] : selection,
  );

  onMount(() => {
    void cfg.load();
  });

  onDestroy(() => {
    if (ownsStore) cfg.detach();
  });

  function learnVerb(kind: string | null): string {
    if (kind === 'encoder' || kind === 'relative-encoder' || kind === 'poti') {
      return 'drehen';
    }
    if (kind === 'fader') return 'bewegen';
    return 'drücken';
  }

  function selectDevice(name: string): void {
    if (cfg.selectedDevice === name) return;
    cfg.selectDevice(name);
    selection = [];
    dialogControls = null;
    showLearn = false;
    learnControl = null;
  }

  function toggle(control: string): void {
    selection = selection.includes(control)
      ? selection.filter((entry) => entry !== control)
      : [...selection, control];
  }

  function openDialog(): void {
    if (selectedControls.length) dialogControls = selectedControls;
  }

  function assignDetected(control: string): void {
    const found = controls.find((entry) => entry.id === control);
    if (!found) return;
    selection = [control];
    cfg.clearDetectedControl();
    dialogControls = [found];
  }

  function entryText(control: ControlInfo): string {
    return cfg.labelFor(control) ?? '–';
  }
</script>

<section class="page devices-page">
  <h1>Geräte</h1>

  {#if cfg.error && !dialogControls && !cfg.conflict}
    <p class="banner" role="alert">{cfg.error}</p>
  {/if}
  {#if !dialogControls}
    <ConflictNotice store={cfg} />
  {/if}

  <div class="layout">
    <aside>
      <h2>Geräte</h2>
      <ul class="device-list">
        {#each cfg.visibleDevices as entry (entry.name)}
          <li>
            <button
              type="button"
              class={{ active: entry.name === cfg.selectedDevice }}
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
            <select
              value={cfg.bank}
              onchange={(event) => cfg.selectBank(Number(event.currentTarget.value))}
            >
              {#each banks as entry (entry.number)}
                <option value={entry.number}>
                  Bank {entry.number} · Kanal {entry.channel}
                </option>
              {/each}
            </select>
          </label>
        </header>

        <LearnStatusBar store={cfg} tab="devices" onAssign={assignDetected} />

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
            <button type="button" onclick={openDialog}>Zuweisen</button>
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
              controls.map((item) => [item.id, cfg.labelFor(item) ?? 'frei']),
            )}
            markers={Object.fromEntries(controls.map((item) => [item.id, cfg.markerFor(item)]))}
            selected={highlighted}
            activeControl={activeLearn}
            activeKind={activeLearnKind}
            interactive={!learningHere}
            onToggle={toggle}
          />
        {:else}
          <table>
            <thead>
              <tr>
                <th>Control</th><th>Art</th><th>Gebunden</th><th>Belegung</th><th>Herkunft</th>
              </tr>
            </thead>
            <tbody>
              {#each controls as item (item.id)}
                {@const marker = cfg.markerFor(item)}
                <tr class={{ active: item.id === activeLearn || item.id === detectedHere }}>
                  <td><button type="button" onclick={() => toggle(item.id)}>{item.id}</button></td>
                  <td>{item.kind}</td>
                  <td>{item.bound ? 'ja' : 'nein'}</td>
                  <td>{entryText(item)}</td>
                  <td><AssignmentBadges source={marker.source} conflict={marker.conflict} /></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        <BankSettings store={cfg} />

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
        </div>

        {#if (showLearn || learningHere) && device.backend === 'midi' && banks.length}
          <LearnPanel
            store={cfg}
            device={device.name}
            bank={cfg.bank}
            control={learnControl}
            onDone={() => (showLearn = false)}
          />
        {/if}
      {:else}
        <p class="muted">Keine Geräte konfiguriert.</p>
      {/if}
    </div>
  </div>

  {#if dialogControls && device}
    <AssignmentDialog
      store={cfg}
      controls={dialogControls}
      onDone={() => (selection = [])}
      onClose={() => (dialogControls = null)}
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

  .actions {
    margin-top: 0.8rem;
  }

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

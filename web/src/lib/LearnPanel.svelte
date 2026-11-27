<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import type { ConfigStore } from './configStore.svelte';

  interface Props {
    store: ConfigStore;
    device: string;
    bank: number;
    control?: string | null;
    onFinished?: () => void;
    onDone?: () => void;
  }

  let { store, device, bank, control = null, onFinished, onDone }: Props = $props();

  let busy = $state(false);
  let startedSession = $state(false);

  const status = $derived(store.deviceLearn);
  const error = $derived(store.learnError);
  const activeHere = $derived(
    status?.active === true && status.device === device && status.bank === bank,
  );
  const ownsOpenSession = $derived(
    activeHere || (startedSession && status?.active === true),
  );
  // Only one session runs at a time, across both tabs.
  const detecting = $derived(store.learn?.status === 'active');

  onMount(() => {
    // One read for a session that started before this view; events keep it current.
    void store.syncLearn();
  });

  onDestroy(() => {
    if (ownsOpenSession) {
      void store.cancelDeviceLearn();
    }
  });

  async function run(action: () => Promise<void>): Promise<void> {
    busy = true;
    try {
      await action();
    } finally {
      busy = false;
    }
  }

  function startSession(): Promise<void> {
    return run(async () => {
      await store.startDeviceLearn(device, bank, control ?? undefined);
      startedSession = store.deviceLearn?.active === true;
    });
  }

  function skipControl(): Promise<void> {
    return run(() => store.skipDeviceLearn());
  }

  function cancelSession(): Promise<void> {
    return run(async () => {
      await store.cancelDeviceLearn();
      startedSession = false;
      onDone?.();
    });
  }

  function finishSession(): Promise<void> {
    return run(async () => {
      await store.finishDeviceLearn();
      startedSession = false;
      onFinished?.();
      onDone?.();
    });
  }
</script>

<section class="learn">
  <h3>Anlernen · {device} · Bank {bank}</h3>

  {#if activeHere}
    <p>
      {status?.index ?? 0} / {status?.total ?? 0}
      {#if status?.current}
        · aktiv: <strong>{status.current}</strong>
      {/if}
      · Kanal {status?.channel}
    </p>
    {#if status?.error}
      <p class="error" role="alert">{status.error}</p>
    {/if}
    {#if status?.paused}
      <p class="muted">Pausiert – Control erneut bedienen oder überspringen.</p>
    {/if}
    <div class="row">
      <button
        type="button"
        disabled={busy || !status?.current}
        onclick={skipControl}
      >
        Überspringen
      </button>
      <button type="button" disabled={busy} onclick={cancelSession}>
        Abbrechen
      </button>
      <button type="button" disabled={busy} onclick={finishSession}>
        Speichern
      </button>
    </div>
  {:else if status?.active}
    <p class="muted">
      Es läuft eine Sitzung für {status.device}, Bank {status.bank}. Bitte dort abschließen
      oder hier abbrechen.
    </p>
    <div class="row">
      <button type="button" disabled={busy} onclick={cancelSession}>
        Abbrechen
      </button>
    </div>
  {:else}
    <p class="muted">Startet einen geführten Durchlauf durch die noch unbelegten Controls.</p>
    {#if detecting}
      <p class="muted">Die Control-Erkennung läuft – erst abschließen oder abbrechen.</p>
    {/if}
    <button type="button" disabled={busy || detecting} onclick={startSession}>
      {control ? `Control ${control} erneut anlernen` : 'Learn starten'}
    </button>
  {/if}

  {#if error}
    <p class="error" role="alert">{error}</p>
  {/if}
</section>

<style>
  .learn {
    display: grid;
    gap: 0.5rem;
    padding: 0.75rem;
    background: var(--surface);
    border: 1px solid var(--accent-dim);
    border-radius: var(--radius);
  }

  h3 {
    margin: 0;
    font-size: 0.9rem;
    font-weight: 500;
  }

  p {
    margin: 0;
    font-size: 0.8rem;
  }

  .row {
    display: flex;
    gap: 0.5rem;
  }

  .error {
    color: var(--danger);
  }

  .muted {
    color: var(--text-muted);
  }
</style>

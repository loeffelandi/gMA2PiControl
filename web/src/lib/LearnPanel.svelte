<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import type { ApiClient, DeviceLearnStatus } from './api';

  interface Props {
    api: ApiClient;
    device: string;
    bank: number;
    control?: string | null;
    onFinished?: () => void;
    onStatus?: (status: DeviceLearnStatus | null) => void;
  }

  let {
    api,
    device,
    bank,
    control = null,
    onFinished,
    onStatus,
  }: Props = $props();
  let status = $state<DeviceLearnStatus | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  async function refresh(): Promise<void> {
    try {
      status = await api.deviceLearnStatus();
      onStatus?.(status);
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Status nicht verfügbar';
      onStatus?.(null);
    }
  }

  onMount(() => {
    void refresh();
    timer = setInterval(() => void refresh(), 500);
  });

  onDestroy(() => {
    if (timer !== null) clearInterval(timer);
    onStatus?.(null);
    if (activeHere) {
      void api.cancelDeviceLearn().catch(() => {});
    }
  });

  async function run(action: () => Promise<unknown>): Promise<void> {
    busy = true;
    error = null;
    try {
      await action();
      await refresh();
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Aktion fehlgeschlagen';
    } finally {
      busy = false;
    }
  }

  const activeHere = $derived(
    status?.active === true && status.device === device && status.bank === bank,
  );
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
      <button type="button" disabled={busy} onclick={() => run(() => api.skipDeviceLearn())}>
        Überspringen
      </button>
      <button type="button" disabled={busy} onclick={() => run(() => api.cancelDeviceLearn())}>
        Abbrechen
      </button>
      <button
        type="button"
        disabled={busy}
        onclick={() =>
          run(async () => {
            await api.finishDeviceLearn();
            onFinished?.();
          })}
      >
        Speichern
      </button>
    </div>
  {:else if status?.active}
    <p class="muted">
      Es läuft eine Sitzung für {status.device}, Bank {status.bank}. Bitte dort abschließen
      oder abbrechen.
    </p>
  {:else}
    <p class="muted">Startet einen geführten Durchlauf durch die noch unbelegten Controls.</p>
    <button
      type="button"
      disabled={busy}
      onclick={() =>
        run(() =>
          control
            ? api.startDeviceLearn(device, bank, control)
            : api.startDeviceLearn(device, bank),
        )}
    >
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

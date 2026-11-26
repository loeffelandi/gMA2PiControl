<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import type { ApiClient, DeviceLearnStatus } from './api';
  import type { StatusStore } from './status';

  interface Props {
    api: ApiClient;
    device: string;
    bank: number;
    control?: string | null;
    store?: StatusStore;
    onFinished?: () => void;
    onDone?: () => void;
    onStatus?: (status: DeviceLearnStatus | null) => void;
  }

  let {
    api,
    device,
    bank,
    control = null,
    store,
    onFinished,
    onDone,
    onStatus,
  }: Props = $props();

  let status = $state<DeviceLearnStatus | null>(null);
  let error = $state<string | null>(null);
  let busy = $state(false);
  let startedSession = $state(false);
  let timer: ReturnType<typeof setInterval> | null = null;
  let inFlight = false;
  let actionEpoch = 0;
  let destroyed = false;

  const activeHere = $derived(
    status?.active === true && status.device === device && status.bank === bank,
  );
  const ownsOpenSession = $derived(startedSession || activeHere);

  function applyStatus(next: DeviceLearnStatus | null): void {
    status = next;
    onStatus?.(next);
  }

  async function refresh(force = false): Promise<void> {
    if (destroyed) return;
    if (!force && (busy || inFlight)) return;
    inFlight = true;
    const epoch = actionEpoch;
    try {
      const next = await api.deviceLearnStatus();
      if (destroyed || epoch !== actionEpoch || (!force && busy)) return;
      applyStatus(next);
    } catch (cause) {
      if (destroyed || epoch !== actionEpoch || (!force && busy)) return;
      error = cause instanceof Error ? cause.message : 'Status nicht verfügbar';
      onStatus?.(null);
    } finally {
      inFlight = false;
    }
  }

  let lastTarget: { device: string; bank: number } | null = null;

  function syncTarget(targetDevice: string, targetBank: number) {
    return (): void => {
      if (
        lastTarget !== null &&
        (lastTarget.device !== targetDevice || lastTarget.bank !== targetBank)
      ) {
        error = null;
        void refresh();
      }
      lastTarget = { device: targetDevice, bank: targetBank };
    };
  }

  onMount(() => {
    void refresh();
    timer = setInterval(() => void refresh(), 500);
    if (!store) return;
    let previous = store.state.deviceLearn;
    if (previous) {
      applyStatus(previous);
    }
    return store.subscribe(() => {
      const next = store.state.deviceLearn;
      if (!next || next === previous) return;
      previous = next;
      if (!busy && !destroyed) {
        actionEpoch += 1;
        if (!next.active) {
          startedSession = false;
        }
        applyStatus(next);
      }
    });
  });

  onDestroy(() => {
    destroyed = true;
    if (timer !== null) clearInterval(timer);
    onStatus?.(null);
    if (ownsOpenSession) {
      startedSession = false;
      void api.cancelDeviceLearn().catch(() => {});
    }
  });

  async function run(
    action: () => Promise<void>,
    options: { refreshAfter?: boolean } = { refreshAfter: true },
  ): Promise<void> {
    actionEpoch += 1;
    busy = true;
    error = null;
    try {
      await action();
      if (options.refreshAfter) {
        await refresh(true);
      }
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Aktion fehlgeschlagen';
    } finally {
      busy = false;
    }
  }

  function startSession(): Promise<void> {
    return run(async () => {
      const next = control
        ? await api.startDeviceLearn(device, bank, control)
        : await api.startDeviceLearn(device, bank);
      startedSession = true;
      if (next && typeof next.active === 'boolean') {
        applyStatus(next);
      }
    });
  }

  function skipControl(): Promise<void> {
    return run(async () => {
      const next = await api.skipDeviceLearn();
      if (next && typeof next.active === 'boolean') {
        applyStatus(next);
      }
    });
  }

  function cancelSession(): Promise<void> {
    return run(
      async () => {
        await api.cancelDeviceLearn();
        startedSession = false;
        applyStatus({ active: false });
        onDone?.();
      },
      { refreshAfter: false },
    );
  }

  function finishSession(): Promise<void> {
    return run(
      async () => {
        await api.finishDeviceLearn();
        startedSession = false;
        applyStatus({ active: false });
        onFinished?.();
        onDone?.();
      },
      { refreshAfter: false },
    );
  }
</script>

<section class="learn" {@attach syncTarget(device, bank)}>
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
    <button type="button" disabled={busy} onclick={startSession}>
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

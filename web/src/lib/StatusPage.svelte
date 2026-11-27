<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import type {
    ActivityDevice,
    ActivityEntry,
    DeviceEntry,
    MidiRemoteSessionState,
    MidiRemoteSessionStatus,
    MidiRemoteSyncStatus,
  } from './api';
  import {
    emptyStatusState,
    LOG_LIMIT,
    type StatusState,
    type StatusStore,
  } from './status';

  let {
    store,
    devicesLoader,
    retriggerMidiSync,
  }: {
    store: StatusStore;
    devicesLoader?: () => Promise<DeviceEntry[]>;
    retriggerMidiSync?: () => Promise<unknown>;
  } = $props();

  let snapshot = $state<StatusState>(emptyStatusState());
  let devices = $state<DeviceEntry[]>([]);
  let detectedDevices = $derived(
    devices.filter((device) => {
      const presence = snapshot.status?.presence?.[device.name];
      return presence ? presence.seen : device.detected !== null;
    }),
  );
  let devicesError = $state<string | null>(null);
  let pulses = $state<Record<string, boolean>>({});
  let power = $derived(snapshot.status?.power ?? null);

  let previousCounts: Record<string, number> = Object.create(null);
  let pulseTimers: Record<string, ReturnType<typeof setTimeout>> =
    Object.create(null);
  let seenActivityDevices: Record<string, true> = Object.create(null);
  let lostSeqByDevice: Record<string, number> = Object.create(null);

  function maxLostSeq(entries: ActivityEntry[]): number {
    let max = -1;
    for (const entry of entries) {
      if (entry.kind === 'device-lost' && entry.seq > max) {
        max = entry.seq;
      }
    }
    return max;
  }

  function lostDeviceEntries(
    entries: ActivityEntry[],
    afterSeq: number,
  ): { name: string; seq: number }[] {
    const out: { name: string; seq: number }[] = [];
    for (const entry of entries) {
      if (entry.kind === 'device-lost' && entry.seq > afterSeq) {
        const colon = entry.summary.indexOf(':');
        const name = (
          colon >= 0 ? entry.summary.slice(0, colon) : entry.summary
        ).trim();
        if (name) out.push({ name, seq: entry.seq });
      }
    }
    return out;
  }

  function collectActivityDevices(state: StatusState): string[] {
    const seen: Record<string, true> = Object.create(null);
    for (const name of Object.keys(state.activity.devices)) {
      if (!(name in lostSeqByDevice)) {
        seen[name] = true;
      }
    }
    for (const entry of state.activity.entries) {
      if (
        entry.device &&
        entry.device !== 'system' &&
        entry.device !== 'ma2' &&
        entry.kind !== 'device-lost'
      ) {
        const lostSeq = lostSeqByDevice[entry.device];
        if (lostSeq === undefined || entry.seq > lostSeq) {
          delete lostSeqByDevice[entry.device];
          seen[entry.device] = true;
        }
      }
    }
    for (const [name, info] of Object.entries(state.status?.presence ?? {})) {
      if (info?.connected && name in lostSeqByDevice) {
        delete lostSeqByDevice[name];
        seen[name] = true;
      }
    }
    return Object.keys(seen);
  }

  let lastConfigGeneration: number | null = null;
  let lastDeviceLostSeq = -1;
  let initialDevicesLoaded = false;
  let pendingUnseenCheck = false;
  let loadingDevices = false;
  let reloadQueued = false;
  let destroyed = false;

  const timeFormat = new Intl.DateTimeFormat('de-DE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  const emptyCounts: ActivityDevice = {
    rx: 0,
    tx: 0,
    last_rx: null,
    last_tx: null,
  };

  function refreshDevices(): void {
    if (!devicesLoader || destroyed) return;
    if (loadingDevices) {
      reloadQueued = true;
      return;
    }
    loadingDevices = true;
    devicesLoader()
      .then((list) => {
        if (destroyed) return;
        devices = list;
        devicesError = null;
        if (!initialDevicesLoaded) {
          initialDevicesLoaded = true;
          if (pendingUnseenCheck) {
            pendingUnseenCheck = false;
            for (const name of Object.keys(seenActivityDevices)) {
              if (!list.some((d) => d.name === name && d.detected !== null)) {
                reloadQueued = true;
                break;
              }
            }
          }
        }
      })
      .catch((error: unknown) => {
        if (!destroyed) {
          devicesError =
            error instanceof Error ? error.message : 'Geräte nicht lesbar';
          initialDevicesLoaded = true;
        }
      })
      .finally(() => {
        loadingDevices = false;
        if (reloadQueued && !destroyed) {
          reloadQueued = false;
          refreshDevices();
        }
      });
  }

  function updatePulses(activityDevices: Record<string, ActivityDevice>): void {
    for (const [name, counts] of Object.entries(activityDevices)) {
      for (const direction of ['rx', 'tx'] as const) {
        const key = `${name}:${direction}`;
        const value = counts[direction];
        const before = previousCounts[key];
        if (before !== undefined && value > before) {
          pulses[key] = true;
          const running = pulseTimers[key];
          if (running !== undefined) clearTimeout(running);
          pulseTimers[key] = setTimeout(() => {
            pulses[key] = false;
          }, 400);
        }
        previousCounts[key] = value;
      }
    }
  }

  function handleStoreUpdate(next: StatusState, initial = false): void {
    snapshot = { ...next };
    if (initial) {
      for (const [name, counts] of Object.entries(next.activity.devices)) {
        previousCounts[`${name}:rx`] = counts.rx;
        previousCounts[`${name}:tx`] = counts.tx;
      }
      lastConfigGeneration = next.configGeneration;
      lastDeviceLostSeq = maxLostSeq(next.activity.entries);
      for (const item of lostDeviceEntries(next.activity.entries, -1)) {
        lostSeqByDevice[item.name] = Math.max(
          lostSeqByDevice[item.name] ?? -1,
          item.seq,
        );
      }
      for (const name of collectActivityDevices(next)) {
        seenActivityDevices[name] = true;
      }
      return;
    }

    updatePulses(next.activity.devices);

    let shouldReload = false;

    if (next.configGeneration !== lastConfigGeneration) {
      const changedToNumber = next.configGeneration !== null;
      lastConfigGeneration = next.configGeneration;
      if (changedToNumber) shouldReload = true;
    }

    const currentMaxLost = maxLostSeq(next.activity.entries);
    if (currentMaxLost > lastDeviceLostSeq) {
      for (const item of lostDeviceEntries(next.activity.entries, lastDeviceLostSeq)) {
        lostSeqByDevice[item.name] = Math.max(
          lostSeqByDevice[item.name] ?? -1,
          item.seq,
        );
        delete seenActivityDevices[item.name];
      }
      lastDeviceLostSeq = currentMaxLost;
      shouldReload = true;
    } else if (next.status === null && next.activity.entries.length === 0) {
      lastDeviceLostSeq = -1;
      lostSeqByDevice = Object.create(null);
      seenActivityDevices = Object.create(null);
      previousCounts = Object.create(null);
    }

    for (const name of collectActivityDevices(next)) {
      if (!seenActivityDevices[name]) {
        seenActivityDevices[name] = true;
        if (initialDevicesLoaded) {
          if (!devices.some((d) => d.name === name && d.detected !== null)) {
            shouldReload = true;
          }
        } else {
          pendingUnseenCheck = true;
        }
      }
    }

    if (shouldReload) {
      refreshDevices();
    }
  }

  onMount(() => {
    handleStoreUpdate(store.state, true);
    refreshDevices();
    return store.subscribe(() => {
      handleStoreUpdate(store.state, false);
    });
  });

  let stickToBottom = true;

  function trackLogScroll(node: HTMLOListElement): () => void {
    stickToBottom = true;
    function onScroll(): void {
      stickToBottom =
        node.scrollHeight - node.scrollTop - node.clientHeight < 32;
    }
    node.addEventListener('scroll', onScroll);
    return () => {
      node.removeEventListener('scroll', onScroll);
    };
  }

  function scrollLogOnCount(count: number) {
    return (node: HTMLOListElement): void => {
      if (count > 0 && stickToBottom) {
        node.scrollTop = node.scrollHeight;
      }
    };
  }

  onDestroy(() => {
    destroyed = true;
    for (const timer of Object.values(pulseTimers)) clearTimeout(timer);
  });

  const connectionLabel = $derived(
    snapshot.connection === 'open'
      ? 'verbunden'
      : snapshot.connection === 'connecting'
        ? 'verbinde'
        : 'getrennt',
  );

  const encoderModeLabel = $derived(
    snapshot.status === null
      ? 'Unbekannt'
      : snapshot.status.screen_mode
        ? 'Screen (grün)'
        : 'Attribut (rot)',
  );

  const midiSessionStateLabels: Record<MidiRemoteSessionState, string> = {
    connected: 'verbunden',
    connecting: 'verbinde',
    disconnected: 'getrennt',
    'dry-run': 'Dry-Run',
  };

  function midiSessionLabel(session: MidiRemoteSessionStatus): string {
    let label = midiSessionStateLabels[session.state] ?? session.state;
    if (session.state === 'connected' && typeof session.latency_ms === 'number') {
      label += ` · ${session.latency_ms.toFixed(1)} ms`;
    }
    if (session.state === 'disconnected' && session.detail) {
      label += ` (${session.detail})`;
    }
    return label;
  }

  function midiSyncLabel(sync: MidiRemoteSyncStatus): string {
    if (sync.mode === 'off') return 'aus (alle Ziele aktiv)';
    const parts = [`${sync.synced}/${sync.targets} abgeglichen`];
    if (sync.mode === 'check') parts.push('nur prüfen');
    if (sync.running) {
      parts.push('läuft');
    } else if (sync.at !== null) {
      parts.push(`zuletzt ${timeFormat.format(new Date(sync.at * 1000))}`);
    }
    if (sync.created || sync.changed || sync.removed || sync.failed) {
      parts.push(`+${sync.created} ~${sync.changed} −${sync.removed}`);
      if (sync.failed > 0) parts.push(`${sync.failed} fehlerhaft`);
    }
    return parts.join(' · ');
  }

  const midiRemote = $derived.by(() => {
    const info = snapshot.status?.midi_remote;
    return info?.enabled ? info : null;
  });

  const canRetriggerMidi = $derived(
    retriggerMidiSync != null &&
      midiRemote != null &&
      midiRemote.sync.mode !== 'off' &&
      midiRemote.session.state !== 'dry-run',
  );

  let retriggering = $state(false);
  let retriggerError = $state<string | null>(null);

  async function retrigger(): Promise<void> {
    if (!retriggerMidiSync || retriggering) return;
    retriggering = true;
    retriggerError = null;
    try {
      await retriggerMidiSync();
    } catch (error) {
      retriggerError =
        error instanceof Error ? error.message : 'Abgleich fehlgeschlagen';
    } finally {
      retriggering = false;
    }
  }

  function countsFor(name: string): ActivityDevice {
    return snapshot.activity.devices[name] ?? emptyCounts;
  }

  function formatTime(ts: number): string {
    const date = new Date(ts * 1000);
    return `${timeFormat.format(date)}.${String(date.getMilliseconds()).padStart(3, '0')}`;
  }
</script>

<section class="status-page">
  <h1>Status</h1>

  {#if snapshot.reconnecting || snapshot.connection !== 'open'}
    <p class="banner" role="status">
      {#if snapshot.reconnecting}
        Verbindung unterbrochen – die Oberfläche verbindet sich automatisch neu.
      {:else if snapshot.connection === 'connecting'}
        Verbinde mit dem Daemon …
      {:else}
        Keine Live-Verbindung zum Daemon.
      {/if}
    </p>
  {/if}

  {#if power?.state === 'shutting_down'}
    <p class="banner warn" role="status">Der Pi fährt herunter.</p>
  {:else if power?.state === 'holding'}
    <p class="banner warn" role="status">
      Ausschalten: noch {power.confirm_remaining ?? 0}× Please drücken, MA + Off gehalten.
    </p>
  {/if}

  <dl class="grid">
    <div>
      <dt>Live-Verbindung</dt>
      <dd data-testid="connection">{connectionLabel}</dd>
    </div>
    <div>
      <dt>onPC</dt>
      <dd data-testid="ma2-state">
        {snapshot.status?.connected ? 'verbunden' : 'getrennt'}
        {#if snapshot.status?.session != null}
          (Session {snapshot.status.session})
        {/if}
      </dd>
    </div>
    <div>
      <dt>Generation</dt>
      <dd>{snapshot.status?.generation ?? '–'}</dd>
    </div>
    <div>
      <dt>Rate</dt>
      <dd>{snapshot.status ? `${snapshot.status.rate.toFixed(1)} Frames/s` : '–'}</dd>
    </div>
    <div>
      <dt>Warteschlange</dt>
      <dd>{snapshot.status?.queue_depth ?? '–'}</dd>
    </div>
    <div>
      <dt>Frames gesamt</dt>
      <dd>{snapshot.status?.frames_sent ?? '–'}</dd>
    </div>
    <div>
      <dt>Encoder-Modus</dt>
      <dd>
        <span
          class={[
            'led',
            {
              green: snapshot.status?.screen_mode === true,
              red: snapshot.status?.screen_mode === false,
            },
          ]}
          aria-hidden="true"
        ></span>
        {encoderModeLabel}
      </dd>
    </div>
    <div>
      <dt>Reconnects</dt>
      <dd>{snapshot.status?.reconnects ?? '–'}</dd>
    </div>
    {#if midiRemote}
      <div>
        <dt>MIDI-Remote</dt>
        <dd data-testid="midi-remote-session">
          {midiSessionLabel(midiRemote.session)}
        </dd>
      </div>
      <div class="midi-sync-cell">
        <dt>Remote-Abgleich</dt>
        <dd data-testid="midi-remote-sync">{midiSyncLabel(midiRemote.sync)}</dd>
        {#if canRetriggerMidi}
          <button
            type="button"
            data-testid="midi-remote-retrigger"
            disabled={retriggering || midiRemote.sync.running}
            onclick={retrigger}
          >
            {retriggering || midiRemote.sync.running
              ? 'Abgleich läuft …'
              : 'Remotes ausrollen'}
          </button>
        {/if}
      </div>
    {/if}
  </dl>

  {#if snapshot.status?.last_error}
    <p class="error">Letzter Fehler: {snapshot.status.last_error}</p>
  {/if}
  {#if midiRemote?.sync.error}
    <p class="error" data-testid="midi-remote-error">
      MIDI-Remote-Abgleich: {midiRemote.sync.error}
    </p>
  {:else if midiRemote && midiRemote.sync.failed > 0 && midiRemote.sync.mode === 'auto'}
    <p class="error" data-testid="midi-remote-incomplete">
      MIDI-Remote-Abgleich unvollständig: {midiRemote.sync.failed} von {midiRemote.sync.targets} fehlen{midiRemote.sync.running
        ? ' – Abgleich läuft'
        : ' – „Remotes ausrollen“ wiederholt den Abgleich'}
    </p>
  {/if}
  {#if retriggerError}
    <p class="error" data-testid="midi-remote-retrigger-error">{retriggerError}</p>
  {/if}

  <div class="monitor">
    <div class="monitor-head">
      <span class="monitor-title">Geräte</span>
      <span class="monitor-legend">
        <i class="activity-led rx" aria-hidden="true"></i> RX vom Gerät
        <i class="activity-led tx" aria-hidden="true"></i> TX zum Gerät
      </span>
    </div>

    {#if devicesError}
      <p class="monitor-empty error">{devicesError}</p>
    {:else if detectedDevices.length}
      {#each detectedDevices as device (device.name)}
        {@const counts = countsFor(device.name)}
        {@const presence = snapshot.status?.presence?.[device.name]}
        {@const connected = presence ? presence.connected : device.detected !== null}
        <div class="device-row">
          <span class="activity-leds" aria-hidden="true">
            {#key counts.rx}
              <i
                class={[
                  'activity-led rx',
                  { pulse: pulses[`${device.name}:rx`] },
                ]}
              ></i>
            {/key}
            {#key counts.tx}
              <i
                class={[
                  'activity-led tx',
                  { pulse: pulses[`${device.name}:tx`] },
                ]}
              ></i>
            {/key}
          </span>
          <span class="device-id">{device.name}</span>
          <span class="device-meta">
            {device.backend} · {device.vendor_product} · {device.profile}
            <span class="device-counts">{counts.rx} rx / {counts.tx} tx</span>
          </span>
          <span
            class={['device-state', { ok: connected, lost: !connected }]}
          >
            {connected ? 'verbunden' : 'verbindung verloren'}
          </span>
        </div>
      {/each}
    {:else}
      <p class="monitor-empty muted">Keine Geräte verbunden.</p>
    {/if}
  </div>

  <section class="terminal">
    <header>
      <span>Log</span>
      <span class="terminal-meta">RX/TX · letzte {LOG_LIMIT}</span>
    </header>
    {#if snapshot.activity.entries.length}
      <ol
        class="log"
        {@attach trackLogScroll}
        {@attach scrollLogOnCount(snapshot.activity.entries.at(-1)?.seq ?? 0)}
      >
        {#each snapshot.activity.entries as entry (entry.seq)}
          <li
            class={{
              rx: entry.direction === 'rx',
              tx: entry.direction === 'tx',
            }}
          >
            <time datetime={new Date(entry.ts * 1000).toISOString()}>
              {formatTime(entry.ts)}
            </time>
            <span class="log-dir">{entry.direction}</span>
            <span class="log-device">{entry.device}</span>
            <span class="log-summary">{entry.summary}</span>
          </li>
        {/each}
      </ol>
    {:else}
      <p class="log-empty">Noch keine Aktivität.</p>
    {/if}
  </section>

  {#if snapshot.learn}
    <p class="learn">
      Learn: {snapshot.learn.kind} {snapshot.learn.status}
      {#if snapshot.learn.control}
        · {snapshot.learn.control}
      {/if}
      {#if snapshot.learn.raw}
        · roh {snapshot.learn.raw}
      {/if}
    </p>
  {/if}
</section>

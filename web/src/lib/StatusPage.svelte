<script lang="ts">
  import { onDestroy } from 'svelte';

  import type { ActivityDevice, DeviceEntry } from './api';
  import { LOG_LIMIT, type StatusState, type StatusStore } from './status';

  let {
    store,
    devicesLoader,
  }: {
    store: StatusStore;
    devicesLoader?: () => Promise<DeviceEntry[]>;
  } = $props();

  let snapshot = $state<StatusState>({
    connection: 'closed',
    reconnecting: false,
    status: null,
    learn: null,
    network: null,
    activity: { devices: {}, entries: [] },
    lastError: null,
  });
  let devices = $state<DeviceEntry[]>([]);
  let detectedDevices = $derived(
    devices.filter((device) => {
      const presence = snapshot.status?.presence?.[device.name];
      return presence ? presence.seen : device.detected !== null;
    }),
  );
  let devicesError = $state<string | null>(null);
  let pulses = $state<Record<string, boolean>>({});
  let logEl = $state<HTMLOListElement | null>(null);
  let stickToBottom = $state(true);

  const previousCounts = new Map<string, number>();
  const pulseTimers = new Map<string, ReturnType<typeof setTimeout>>();

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

  $effect(() => {
    snapshot = { ...store.state };
    return store.subscribe(() => {
      snapshot = { ...store.state };
    });
  });

  $effect(() => {
    if (!devicesLoader) return;
    let cancelled = false;
    devicesLoader()
      .then((list) => {
        if (!cancelled) devices = list;
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          devicesError = error instanceof Error ? error.message : 'Geräte nicht lesbar';
        }
      });
    return () => {
      cancelled = true;
    };
  });

  // Pulse an LED for a short moment whenever its counter grows.
  $effect(() => {
    for (const [name, counts] of Object.entries(snapshot.activity.devices)) {
      for (const direction of ['rx', 'tx'] as const) {
        const key = `${name}:${direction}`;
        const value = counts[direction];
        const before = previousCounts.get(key);
        if (before !== undefined && value > before) {
          pulses[key] = true;
          const running = pulseTimers.get(key);
          if (running) clearTimeout(running);
          pulseTimers.set(
            key,
            setTimeout(() => {
              pulses[key] = false;
            }, 400),
          );
        }
        previousCounts.set(key, value);
      }
    }
  });

  // Keep the newest log line in view unless the user scrolled up.
  $effect(() => {
    const count = snapshot.activity.entries.length;
    if (logEl && count > 0 && stickToBottom) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  });

  function onLogScroll(): void {
    if (!logEl) return;
    stickToBottom =
      logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 32;
  }

  onDestroy(() => {
    for (const timer of pulseTimers.values()) clearTimeout(timer);
  });

  const connectionLabel = $derived(
    snapshot.connection === 'open'
      ? 'verbunden'
      : snapshot.connection === 'connecting'
        ? 'verbinde'
        : 'getrennt',
  );

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
          class="led"
          class:green={snapshot.status?.screen_mode === true}
          class:red={snapshot.status?.screen_mode === false}
          aria-hidden="true"
        ></span>
        {snapshot.status?.screen_mode ? 'Screen (grün)' : 'Attribut (rot)'}
      </dd>
    </div>
    <div>
      <dt>Reconnects</dt>
      <dd>{snapshot.status?.reconnects ?? '–'}</dd>
    </div>
  </dl>

  {#if snapshot.status?.last_error}
    <p class="error">Letzter Fehler: {snapshot.status.last_error}</p>
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
                class="activity-led rx"
                class:pulse={pulses[`${device.name}:rx`]}
              ></i>
            {/key}
            {#key counts.tx}
              <i
                class="activity-led tx"
                class:pulse={pulses[`${device.name}:tx`]}
              ></i>
            {/key}
          </span>
          <span class="device-id">{device.name}</span>
          <span class="device-meta">
            {device.backend} · {device.vendor_product} · {device.profile}
            <span class="device-counts">{counts.rx} rx / {counts.tx} tx</span>
          </span>
          <span
            class="device-state"
            class:ok={connected}
            class:lost={!connected}
          >
            {connected ? 'erkannt' : 'verbindung verloren'}
          </span>
        </div>
      {/each}
    {:else}
      <p class="monitor-empty muted">Keine Geräte erkannt.</p>
    {/if}
  </div>

  <section class="terminal">
    <header>
      <span>Log</span>
      <span class="terminal-meta">RX/TX · letzte {LOG_LIMIT}</span>
    </header>
    {#if snapshot.activity.entries.length}
      <ol class="log" bind:this={logEl} onscroll={onLogScroll}>
        {#each snapshot.activity.entries as entry (entry.seq)}
          <li class:rx={entry.direction === 'rx'} class:tx={entry.direction === 'tx'}>
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

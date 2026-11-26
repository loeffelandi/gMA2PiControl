<script lang="ts">
  import type { DeviceEntry } from './api';
  import type { StatusState, StatusStore } from './status';

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
    lastError: null,
  });
  let devices = $state<DeviceEntry[]>([]);
  let devicesError = $state<string | null>(null);

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

  const connectionLabel = $derived(
    snapshot.connection === 'open'
      ? 'verbunden'
      : snapshot.connection === 'connecting'
        ? 'verbinde'
        : 'getrennt',
  );
</script>

<section class="status-page">
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

  <h2>Letzte Frames</h2>
  {#if snapshot.status?.last_frame_types?.length}
    <ul class="frames">
      {#each snapshot.status.last_frame_types as frame}
        <li>{frame}</li>
      {/each}
    </ul>
  {:else}
    <p class="muted">Noch keine Frames gesendet.</p>
  {/if}

  <h2>Geräte</h2>
  {#if devicesError}
    <p class="error">{devicesError}</p>
  {:else if devices.length}
    <ul class="devices">
      {#each devices as device (device.name)}
        <li>
          <strong>{device.name}</strong>
          <span class="muted">
            {device.backend} · {device.vendor_product} · {device.profile}
          </span>
          <span class:recognised={device.detected !== null}>
            {device.detected ? 'erkannt' : 'nicht erkannt'}
          </span>
        </li>
      {/each}
    </ul>
  {:else}
    <p class="muted">Keine Geräte gemeldet.</p>
  {/if}

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

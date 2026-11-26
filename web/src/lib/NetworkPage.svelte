<script lang="ts">
  import { onDestroy, onMount } from 'svelte';

  import {
    ApiError,
    type ApiClient,
    type NetworkCandidate,
    type NetworkLastResult,
    type NetworkMode,
    type NetworkPending,
    type NetworkStatus,
    type RecoveryStatus,
  } from './api';
  import type { StatusStore } from './status';

  let { api, store }: { api: ApiClient; store?: StatusStore } = $props();

  let loading = $state(true);
  let busy = $state(false);
  let initialized = $state(false);
  let error = $state<string | null>(null);
  let message = $state<{ ok: boolean; text: string } | null>(null);
  let fieldErrors = $state<Record<string, string>>({});
  let warnings = $state<string[]>([]);
  let status = $state<NetworkStatus | null>(null);
  let pending = $state<NetworkPending | null>(null);
  let lastResult = $state<NetworkLastResult | null>(null);
  let mode = $state<NetworkMode>('dhcp');
  let address = $state('');
  let subnetMask = $state('255.255.255.0');
  let gateway = $state('');
  let dns = $state('');
  let dialogOpen = $state(false);
  let targetUrl = $state<string | null>(null);
  let now = $state(Date.now());
  let recovery = $state<RecoveryStatus | null>(null);
  let recoveryEnabled = $state(false);
  let recoverySsid = $state('ma2pi-recovery');
  let recoveryPassword = $state('');
  let recoveryAuto = $state(true);
  let recoveryInitialized = $state(false);
  let recoveryMessage = $state<{ ok: boolean; text: string } | null>(null);
  let recoveryFieldError = $state<string | null>(null);

  let ticker: ReturnType<typeof setInterval> | null = null;
  let poller: ReturnType<typeof setInterval> | null = null;
  let destroyed = false;

  function stopPendingTimers(): void {
    if (ticker !== null) {
      clearInterval(ticker);
      ticker = null;
    }
    if (poller !== null) {
      clearInterval(poller);
      poller = null;
    }
  }

  function setPending(nextPending: NetworkPending | null): void {
    now = Date.now();
    pending = nextPending;
    if (nextPending !== null && !destroyed) {
      if (ticker === null) {
        ticker = setInterval(() => {
          now = Date.now();
        }, 1000);
      }
      if (poller === null) {
        poller = setInterval(() => {
          void load(false);
        }, 5000);
      }
    } else {
      stopPendingTimers();
    }
  }

  function modalDialog(el: HTMLDialogElement): () => void {
    if (typeof el.showModal === 'function') {
      if (!el.open) {
        try {
          el.showModal();
        } catch {
          el.setAttribute('open', '');
        }
      }
    } else {
      el.setAttribute('open', '');
    }
    return () => {
      if (el.hasAttribute('open')) {
        if (typeof el.close === 'function') {
          try {
            el.close();
          } catch {
            el.removeAttribute('open');
          }
        } else {
          el.removeAttribute('open');
        }
      }
    };
  }

  function errorText(value: unknown): string {
    if (value instanceof ApiError) return value.detail || value.message;
    if (value instanceof Error) return value.message;
    return 'Unbekannter Fehler';
  }

  function fieldErrorsFrom(value: unknown): Record<string, string> {
    if (value instanceof ApiError && value.field) {
      return { [value.field]: value.detail || value.message };
    }
    return {};
  }

  function parseDns(value: string): string[] {
    return value
      .replaceAll(',', ' ')
      .split(/\s+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function candidate(): NetworkCandidate {
    if (mode === 'dhcp') return { mode };
    return {
      mode,
      address: address.trim(),
      subnet_mask: subnetMask.trim(),
      ...(gateway.trim() ? { gateway: gateway.trim() } : {}),
      dns: parseDns(dns),
    };
  }

  function applyForm(next: NetworkStatus): void {
    if (initialized) return;
    initialized = true;
    mode = next.mode === 'static' ? 'static' : 'dhcp';
    address = next.current.address ?? '';
    subnetMask = next.current.subnet_mask ?? '255.255.255.0';
    gateway = next.current.gateway ?? '';
    dns = next.current.dns.join(', ');
  }

  async function load(initial = false): Promise<void> {
    const hadPending = pending !== null;
    try {
      const next = await api.network();
      status = next;
      setPending(next.pending);
      lastResult = next.last_result;
      if (initial || (hadPending && next.pending === null)) {
        initialized = false;
        applyForm(next);
      }
      error = null;
    } catch (value) {
      error = errorText(value);
    } finally {
      loading = false;
    }
  }

  async function loadRecovery(): Promise<void> {
    try {
      const next = await api.recovery();
      recovery = next;
      if (!recoveryInitialized) {
        recoveryEnabled = next.enabled;
        recoverySsid = next.ssid;
        recoveryPassword = next.password;
        recoveryAuto = next.auto;
        recoveryInitialized = true;
      }
    } catch (value) {
      recoveryMessage = { ok: false, text: errorText(value) };
    }
  }

  async function saveRecovery(): Promise<void> {
    busy = true;
    recoveryMessage = null;
    recoveryFieldError = null;
    try {
      const next = await api.saveRecovery({
        enabled: recoveryEnabled,
        ssid: recoverySsid.trim(),
        password: recoveryPassword,
        auto: recoveryAuto,
      });
      recovery = next;
      recoveryMessage = {
        ok: true,
        text: next.active
          ? `Rettungs-WLAN aktiv: ${next.ssid}`
          : 'Rettungs-WLAN ist aus.',
      };
    } catch (value) {
      recoveryFieldError =
        value instanceof ApiError && value.field ? value.field : null;
      recoveryMessage = { ok: false, text: errorText(value) };
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    if (store?.state.network) {
      setPending(store.state.network.pending);
      lastResult = store.state.network.last_result;
    }
    void load(true);
    void loadRecovery();

    if (!store) return;
    let previous = store.state.network;
    return store.subscribe(() => {
      const event = store.state.network;
      if (!event || event === previous) return;
      previous = event;
      setPending(event.pending);
      lastResult = event.last_result;
      if (event.pending === null) void load(false);
    });
  });

  onDestroy(() => {
    destroyed = true;
    stopPendingTimers();
  });

  function closeDialog(): void {
    if (busy) return;
    dialogOpen = false;
  }

  async function check(): Promise<boolean> {
    busy = true;
    error = null;
    fieldErrors = {};
    warnings = [];
    try {
      const result = await api.validateNetwork(candidate());
      warnings = result.warnings;
      targetUrl = result.target_url;
      return true;
    } catch (value) {
      fieldErrors = fieldErrorsFrom(value);
      error = Object.keys(fieldErrors).length ? null : errorText(value);
      return false;
    } finally {
      busy = false;
    }
  }

  async function preview(): Promise<void> {
    if (await check()) {
      message = { ok: true, text: 'Die Eingaben sind gültig.' };
    } else {
      message = null;
    }
  }

  async function openDialog(): Promise<void> {
    message = null;
    if (await check()) dialogOpen = true;
  }

  async function applyChange(): Promise<void> {
    dialogOpen = false;
    busy = true;
    error = null;
    fieldErrors = {};
    try {
      const result = await api.applyNetwork(candidate());
      setPending(result.pending);
      targetUrl = result.target_url;
      if (status) status = { ...status, pending: result.pending };
      message = null;
    } catch (value) {
      fieldErrors = fieldErrorsFrom(value);
      error = Object.keys(fieldErrors).length ? null : errorText(value);
    } finally {
      busy = false;
    }
  }

  async function confirm(): Promise<void> {
    busy = true;
    error = null;
    try {
      const next = await api.confirmNetwork();
      status = next;
      setPending(next.pending);
      lastResult = next.last_result;
      message = { ok: true, text: 'Netzwerkkonfiguration gespeichert.' };
      initialized = false;
      applyForm(next);
    } catch (value) {
      error = errorText(value);
    } finally {
      busy = false;
    }
  }

  async function rollback(): Promise<void> {
    busy = true;
    error = null;
    try {
      const next = await api.rollbackNetwork();
      status = next;
      setPending(next.pending);
      lastResult = next.last_result;
      message = null;
      initialized = false;
      applyForm(next);
    } catch (value) {
      error = errorText(value);
    } finally {
      busy = false;
    }
  }

  const remaining = $derived.by(() => {
    if (!pending?.deadline) return null;
    const seconds = Math.max(
      0,
      Math.ceil((new Date(pending.deadline).getTime() - now) / 1000),
    );
    return seconds;
  });

  const remainingLabel = $derived.by(() => {
    if (remaining === null) return null;
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  });

  const canEdit = $derived(
    Boolean(status?.available && status?.can_manage && status?.interface),
  );

  const canRollback = $derived(
    pending?.phase === 'awaiting_confirmation' || pending?.phase === 'failed',
  );

  const phaseLabel = $derived(
    pending?.phase === 'activating'
      ? 'Aktivierung läuft …'
      : pending?.phase === 'awaiting_confirmation'
        ? 'Warte auf Bestätigung'
        : pending?.phase === 'rolling_back'
          ? 'Rollback läuft …'
          : (pending?.phase ?? ''),
  );
</script>

<section class="page network-page">
  <h1>Netzwerk</h1>

  {#if loading}
    <p class="muted">Lade Netzwerkstatus …</p>
  {:else}
    {#if error}
      <p class="message error" role="alert">{error}</p>
    {/if}

    {#if status}
      {#if !status.available || !status.can_manage || !status.interface}
        <p class="message error" role="status">
          {status.error ?? 'Die Netzwerkverwaltung ist auf diesem System nicht verfügbar.'}
        </p>
      {/if}

      {#if status.self_connection}
        <p class="banner warn" role="alert">
          Diese Änderung betrifft die Adresse, über die du gerade verbunden bist.
          Nach dem Anwenden musst du die neue Adresse öffnen und die PIN erneut eingeben.
        </p>
      {/if}

      <dl class="grid">
        <div>
          <dt>Schnittstelle</dt>
          <dd>{status.interface?.name ?? '–'}</dd>
        </div>
        <div>
          <dt>Zustand</dt>
          <dd>{status.interface?.state ?? '–'}</dd>
        </div>
        <div>
          <dt>Modus</dt>
          <dd>{status.mode === 'static' ? 'Statisch' : status.mode === 'dhcp' ? 'DHCP' : status.mode}</dd>
        </div>
        <div>
          <dt>IPv4-Adresse</dt>
          <dd>{status.current.address ?? '–'}</dd>
        </div>
        <div>
          <dt>Subnetzmaske</dt>
          <dd>{status.current.subnet_mask ?? '–'}</dd>
        </div>
        <div>
          <dt>Gateway</dt>
          <dd>{status.current.gateway ?? '–'}</dd>
        </div>
        <div>
          <dt>DNS</dt>
          <dd>{status.current.dns.length ? status.current.dns.join(', ') : '–'}</dd>
        </div>
      </dl>

      {#if lastResult && !pending && !message}
        <p class={['message', { error: lastResult.status === 'failed' }]}>
          {#if lastResult.status === 'confirmed'}
            Netzwerkkonfiguration gespeichert.
          {:else if lastResult.status === 'rolled_back'}
            Änderung zurückgerollt{lastResult.detail ? `: ${lastResult.detail}` : '.'}
          {:else if lastResult.status === 'fallback'}
            Notfall-Adresse 192.168.178.254/24 ist aktiv{lastResult.detail ? `: ${lastResult.detail}` : '.'}
          {:else}
            Netzwerkänderung fehlgeschlagen{lastResult.detail ? `: ${lastResult.detail}` : '.'}
          {/if}
        </p>
      {/if}

      {#if pending}
        <section class="network-pending">
          <h2>Offene Änderung: {phaseLabel}</h2>
          <p>
            Kandidat: {pending.mode === 'static' ? 'Statisch' : 'DHCP'}
            {#if pending.address}
              · {pending.address}
            {/if}
            {#if pending.subnet_mask}
              · {pending.subnet_mask}
            {/if}
          </p>
          {#if pending.target_url}
            <p>
              Ziel: <a href={pending.target_url}>{pending.target_url}</a>
            </p>
          {:else}
            <p class="muted">Die neue Adresse wird nach dem DHCP-Bezug bekannt.</p>
          {/if}
          {#if remainingLabel && pending.phase === 'awaiting_confirmation'}
            <p>
              Verbleibend: <strong>{remainingLabel}</strong>. Ohne Bestätigung wird
              automatisch zurückgerollt.
            </p>
          {/if}
          {#if pending.error}
            <p class="error">{pending.error}</p>
          {/if}
          <div class="actions">
            <button
              type="button"
              onclick={confirm}
              disabled={busy || pending.phase !== 'awaiting_confirmation'}
            >
              Ich bin verbunden – bestätigen
            </button>
            <button
              type="button"
              onclick={rollback}
              disabled={busy || !canRollback}
            >
              Zurückrollen
            </button>
          </div>
          <p class="hint">
            Öffne die Ziel-Adresse in einem neuen Tab und melde dich dort erneut mit
            der PIN an. Erst diese neue Sitzung kann die Änderung bestätigen.
          </p>
        </section>
      {:else if canEdit}
        <form class="form network-form" onsubmit={(event) => event.preventDefault()}>
          <fieldset class="network-mode">
            <legend>Modus</legend>
            <label>
              <input type="radio" bind:group={mode} value="dhcp" />
              DHCP
            </label>
            <label>
              <input type="radio" bind:group={mode} value="static" />
              Statisch
            </label>
          </fieldset>

          <label for="network-address">IPv4-Adresse</label>
          <input
            id="network-address"
            bind:value={address}
            disabled={mode === 'dhcp'}
            autocomplete="off"
            aria-invalid={Boolean(fieldErrors.address)}
          />
          {#if fieldErrors.address}
            <p class="field-error">{fieldErrors.address}</p>
          {/if}

          <label for="network-mask">Subnetzmaske</label>
          <input
            id="network-mask"
            bind:value={subnetMask}
            disabled={mode === 'dhcp'}
            autocomplete="off"
            placeholder="255.255.255.0"
            aria-invalid={Boolean(fieldErrors.subnet_mask)}
          />
          {#if fieldErrors.subnet_mask}
            <p class="field-error">{fieldErrors.subnet_mask}</p>
          {:else}
            <p class="hint">Punktnotation, z. B. 255.255.255.0.</p>
          {/if}

          <label for="network-gateway">Gateway</label>
          <input
            id="network-gateway"
            bind:value={gateway}
            disabled={mode === 'dhcp'}
            autocomplete="off"
            aria-invalid={Boolean(fieldErrors.gateway)}
          />
          {#if fieldErrors.gateway}
            <p class="field-error">{fieldErrors.gateway}</p>
          {/if}

          <label for="network-dns">DNS</label>
          <input
            id="network-dns"
            bind:value={dns}
            disabled={mode === 'dhcp'}
            autocomplete="off"
            placeholder="192.168.10.1, 1.1.1.1"
            aria-invalid={Boolean(fieldErrors.dns)}
          />
          {#if fieldErrors.dns}
            <p class="field-error">{fieldErrors.dns}</p>
          {:else}
            <p class="hint">Kommagetrennt, höchstens drei IPv4-Adressen.</p>
          {/if}

          <div class="actions">
            <button type="button" onclick={preview} disabled={busy}>Vorschau</button>
            <button type="button" onclick={openDialog} disabled={busy}>Anwenden …</button>
          </div>
        </form>
      {/if}

      {#if warnings.length}
        <ul class="network-warnings">
          {#each warnings as warning (warning)}
            <li>{warning}</li>
          {/each}
        </ul>
      {/if}

      {#if message}
        <p class={['message', { error: !message.ok }]} role={message.ok ? 'status' : 'alert'}>
          {message.text}
        </p>
      {/if}
    {/if}
  {/if}

  {#if recovery}
    <section class="network-pending">
      <h2>Rettungs-WLAN</h2>
      <p class="muted">
        Der Pi spannt bei Bedarf einen eigenen Hotspot auf. Er ist unter
        <strong>{recovery.url}</strong> erreichbar; die Oberfläche bleibt durch
        die PIN geschützt.
      </p>
      {#if !recovery.available}
        <p class="error">
          {recovery.error ?? 'Keine WLAN-Schnittstelle verfügbar.'}
        </p>
      {:else}
        {#if recovery.active}
          <p class="message" role="status">
            Aktiv: <strong>{recovery.ssid}</strong>
            {#if recovery.address} · {recovery.address}{/if}
          </p>
        {/if}
        {#if recovery.auto_triggered}
          <p class="hint">Automatisch wegen fehlender LAN-Verbindung aktiviert.</p>
        {/if}
        <form class="form network-form" onsubmit={(event) => event.preventDefault()}>
          <label for="recovery-enabled">Aktiv</label>
          <input
            id="recovery-enabled"
            type="checkbox"
            bind:checked={recoveryEnabled}
            aria-invalid={recoveryFieldError === 'enabled'}
          />

          <label for="recovery-ssid">SSID</label>
          <input
            id="recovery-ssid"
            bind:value={recoverySsid}
            autocomplete="off"
            aria-invalid={recoveryFieldError === 'ssid'}
          />

          <label for="recovery-password">WLAN-Passwort</label>
          <input
            id="recovery-password"
            bind:value={recoveryPassword}
            autocomplete="new-password"
            aria-invalid={recoveryFieldError === 'password'}
          />
          <p class="hint">8 bis 63 Zeichen; das Standardpasswort sollte geändert werden.</p>

          <label for="recovery-auto">Automatik</label>
          <input
            id="recovery-auto"
            type="checkbox"
            bind:checked={recoveryAuto}
            aria-invalid={recoveryFieldError === 'auto'}
          />
          <p class="hint">
            Nach 60 Sekunden ohne nutzbares LAN automatisch einschalten und nach
            stabiler LAN-Rückkehr wieder ausschalten.
          </p>

          <div class="actions">
            <button type="button" onclick={saveRecovery} disabled={busy}>
              Rettungs-WLAN speichern
            </button>
          </div>
        </form>
        <p class="hint">
          Beim Aktivieren wird die bestehende WLAN-Verbindung auf <code>wlan0</code>
          getrennt. Das ist für den Rettungszugang beabsichtigt.
        </p>
        {#if recoveryMessage}
          <p
            class={['message', { error: !recoveryMessage.ok }]}
            role={recoveryMessage.ok ? 'status' : 'alert'}
          >
            {recoveryMessage.text}
          </p>
        {/if}
      {/if}
    </section>
  {/if}

  {#if dialogOpen}
    <dialog
      {@attach modalDialog}
      class="network-dialog"
      aria-labelledby="network-dialog-title"
      oncancel={(event) => {
        event.preventDefault();
        closeDialog();
      }}
      onkeydown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          closeDialog();
        }
      }}
    >
      <h2 id="network-dialog-title">Netzwerkkonfiguration anwenden?</h2>
      <p>
        Die neue Konfiguration wird sofort aktiviert; ein Neustart ist nicht
        nötig. Die Verbindung kann dabei getrennt werden.
      </p>
      {#if targetUrl}
        <p>
          Ziel: <a href={targetUrl}>{targetUrl}</a>
        </p>
      {:else}
        <p class="muted">Die neue Adresse wird nach dem DHCP-Bezug bekannt.</p>
      {/if}
      <p>
        Öffne danach die Ziel-Adresse, melde dich erneut mit der PIN an und
        bestätige die Änderung. Ohne Bestätigung wird nach 180 Sekunden
        automatisch die vorherige Konfiguration wiederhergestellt.
      </p>
      <div class="actions">
        <button type="button" onclick={applyChange} disabled={busy}>Jetzt anwenden</button>
        <button type="button" onclick={closeDialog} disabled={busy}>Abbrechen</button>
      </div>
    </dialog>
  {/if}
</section>

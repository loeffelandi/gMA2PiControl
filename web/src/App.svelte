<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiClient, ApiError, type AuthStatus } from './lib/api';
  import { BRAND_PREFIX, BRAND_SUFFIX } from './lib/brand';
  import AdvancedPage from './lib/AdvancedPage.svelte';
  import BackupsPage from './lib/BackupsPage.svelte';
  import DevicesPage from './lib/DevicesPage.svelte';
  import Ma2Page from './lib/Ma2Page.svelte';
  import MappingPage from './lib/MappingPage.svelte';
  import NetworkPage from './lib/NetworkPage.svelte';
  import PinGate from './lib/PinGate.svelte';
  import StatusPage from './lib/StatusPage.svelte';
  import { StatusStore } from './lib/status';

  type Page =
    | 'status'
    | 'ma2'
    | 'network'
    | 'devices'
    | 'mapping'
    | 'advanced'
    | 'backups';

  const pages: { id: Page; label: string }[] = [
    { id: 'status', label: 'Status' },
    { id: 'ma2', label: 'MA2' },
    { id: 'network', label: 'Netzwerk' },
    { id: 'devices', label: 'Geräte' },
    { id: 'mapping', label: 'Mapping' },
    { id: 'advanced', label: 'Erweitert' },
    { id: 'backups', label: 'Backups' },
  ];

  const statusStore = new StatusStore();

  let page = $state<Page>('status');
  let versionError = $state<string | null>(null);
  let auth = $state<AuthStatus | null>(null);
  let authError = $state<string | null>(null);
  let authLoading = $state(true);
  let liveStarted = false;
  let handlingUnauthorized = false;

  function formatError(error: unknown, fallback: string): string {
    if (error instanceof ApiError) return error.detail || error.message;
    if (error instanceof Error) return error.message;
    return fallback;
  }

  function startLive(): void {
    if (liveStarted) return;
    liveStarted = true;
    statusStore.connect();
    api
      .checkVersion()
      .then(() => {
        versionError = null;
      })
      .catch((error: unknown) => {
        versionError = formatError(error, 'Versionsprüfung fehlgeschlagen');
      });
  }

  function stopLive(clear = false): void {
    liveStarted = false;
    if (clear) {
      statusStore.reset();
    } else {
      statusStore.disconnect();
    }
  }

  function applyAuth(next: AuthStatus): void {
    auth = next;
    authError = null;
    if (!next.pin_enabled || next.authenticated) {
      startLive();
    } else {
      stopLive(true);
    }
  }

  async function refreshAuth(
    options: { initial?: boolean; fallback?: AuthStatus } = {},
  ): Promise<void> {
    if (options.initial) {
      authLoading = true;
    }
    authError = null;
    try {
      const status = await api.authStatus();
      applyAuth({
        pin_enabled: Boolean(status.pin_enabled),
        pin_set: Boolean(status.pin_set ?? status.pin_enabled),
        authenticated: Boolean(status.authenticated),
      });
    } catch (error: unknown) {
      if (options.fallback) {
        applyAuth(options.fallback);
      } else if (auth === null) {
        authError = formatError(error, 'Authentifizierung fehlgeschlagen');
      } else {
        versionError = formatError(error, 'Authentifizierung fehlgeschlagen');
      }
    } finally {
      if (options.initial) {
        authLoading = false;
      }
    }
  }

  function handleUnauthorized(): void {
    if (handlingUnauthorized) return;
    handlingUnauthorized = true;
    stopLive(true);
    versionError = null;
    void refreshAuth({
      fallback: { pin_enabled: true, pin_set: true, authenticated: false },
    }).finally(() => {
      handlingUnauthorized = false;
    });
  }

  const api = new ApiClient({ onUnauthorized: handleUnauthorized });

  function unlocked(): void {
    applyAuth({ pin_enabled: true, pin_set: true, authenticated: true });
  }

  async function logout(): Promise<void> {
    const wasPinEnabled = Boolean(auth?.pin_enabled);
    handlingUnauthorized = true;
    try {
      await api.logout();
    } catch {
      // Ignore network or 401 errors while logging out.
    } finally {
      stopLive(true);
      versionError = null;
      page = 'status';
      try {
        await refreshAuth({
          fallback: wasPinEnabled
            ? { pin_enabled: true, pin_set: true, authenticated: false }
            : { pin_enabled: false, pin_set: false, authenticated: true },
        });
      } finally {
        handlingUnauthorized = false;
      }
    }
  }

  onMount(() => {
    void refreshAuth({ initial: true });
    return () => {
      api.onUnauthorized = null;
      stopLive();
    };
  });
</script>

{#if authLoading}
  <main class="page">
    <p class="muted">Lade Oberfläche …</p>
  </main>
{:else if auth === null}
  <main class="gate">
    <section class="gate-card" role="alert">
      <h1>Verbindung zum Dienst fehlgeschlagen</h1>
      {#if authError}
        <p class="message error">{authError}</p>
      {/if}
      <button type="button" onclick={() => void refreshAuth({ initial: true })}>
        Erneut versuchen
      </button>
    </section>
  </main>
{:else if auth.pin_enabled && !auth.authenticated}
  <PinGate {api} onUnlocked={unlocked} />
{:else}
  <header class="topbar">
    <div class="brand">
      <img src="/favicon.svg" alt="" width="26" height="26" />
      <span class="brand-name"><span class="brand-accent">{BRAND_PREFIX}</span>{BRAND_SUFFIX}</span>
    </div>
    <nav>
      {#each pages as entry (entry.id)}
        <button
          type="button"
          class={{ active: page === entry.id }}
          onclick={() => (page = entry.id)}
        >
          {entry.label}
        </button>
      {/each}
    </nav>
    {#if auth.pin_enabled}
      <button type="button" class="logout" onclick={logout}>Abmelden</button>
    {/if}
  </header>

  {#if !auth.pin_enabled || !auth.pin_set}
    <p class="banner warn" role="status">
      Keine PIN gesetzt – Oberfläche und API sind im LAN ungeschützt.
      <button type="button" onclick={() => (page = 'advanced')}>PIN setzen</button>
    </p>
  {/if}

  {#if versionError}
    <p class="banner" role="alert">{versionError}</p>
  {/if}

  <main>
    {#if page === 'status'}
      <StatusPage store={statusStore} devicesLoader={() => api.devices()} />
    {:else if page === 'ma2'}
      <Ma2Page {api} />
    {:else if page === 'network'}
      <NetworkPage {api} store={statusStore} />
    {:else if page === 'mapping'}
      <MappingPage {api} learnStore={statusStore} />
    {:else if page === 'devices'}
      <DevicesPage {api} />
    {:else if page === 'advanced'}
      <AdvancedPage {api} onAuthChange={() => void refreshAuth()} />
    {:else if page === 'backups'}
      <BackupsPage {api} onAuthChange={() => void refreshAuth()} />
    {/if}
  </main>
{/if}

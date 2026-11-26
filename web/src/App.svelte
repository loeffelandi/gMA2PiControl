<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiClient, type AuthStatus } from './lib/api';
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

  const api = new ApiClient();
  const statusStore = new StatusStore();

  let page = $state<Page>('status');
  let versionError = $state<string | null>(null);
  let auth = $state<AuthStatus | null>(null);
  let authLoading = $state(true);
  let liveStarted = false;

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
        versionError =
          error instanceof Error ? error.message : 'Versionsprüfung fehlgeschlagen';
      });
  }

  function unlocked(): void {
    auth = { pin_enabled: true, pin_set: true, authenticated: true };
    startLive();
  }

  async function logout(): Promise<void> {
    try {
      await api.logout();
    } finally {
      statusStore.disconnect();
      liveStarted = false;
      versionError = null;
      page = 'status';
      auth = { pin_enabled: true, pin_set: true, authenticated: false };
    }
  }

  onMount(() => {
    api
      .authStatus()
      .then((status) => {
        auth = status;
        if (!status.pin_enabled || status.authenticated) startLive();
      })
      .catch((error: unknown) => {
        versionError =
          error instanceof Error ? error.message : 'Authentifizierung fehlgeschlagen';
      })
      .finally(() => {
        authLoading = false;
      });
    return () => statusStore.disconnect();
  });
</script>

{#if authLoading}
  <main class="page">
    <p class="muted">Lade Oberfläche …</p>
  </main>
{:else if auth && auth.pin_enabled && !auth.authenticated}
  <PinGate {api} onUnlocked={unlocked} />
{:else}
  <header class="topbar">
    <strong>ma2pi</strong>
    <nav>
      {#each pages as entry (entry.id)}
        <button
          type="button"
          class:active={page === entry.id}
          onclick={() => (page = entry.id)}
        >
          {entry.label}
        </button>
      {/each}
    </nav>
    {#if auth?.pin_enabled}
      <button type="button" class="logout" onclick={logout}>Abmelden</button>
    {/if}
  </header>

  {#if auth && (!auth.pin_enabled || !auth.pin_set)}
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
      <AdvancedPage {api} />
    {:else if page === 'backups'}
      <BackupsPage {api} />
    {:else}
      <section class="page">
        <h1>{pages.find((entry) => entry.id === page)?.label}</h1>
        <p class="muted">Diese Seite wird in den folgenden Schritten ausgebaut.</p>
      </section>
    {/if}
  </main>
{/if}

<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiClient } from './lib/api';
  import BackupsPage from './lib/BackupsPage.svelte';
  import Ma2Page from './lib/Ma2Page.svelte';
  import MappingPage from './lib/MappingPage.svelte';
  import StatusPage from './lib/StatusPage.svelte';
  import { StatusStore } from './lib/status';

  type Page = 'status' | 'ma2' | 'devices' | 'mapping' | 'advanced' | 'backups';

  const pages: { id: Page; label: string }[] = [
    { id: 'status', label: 'Status' },
    { id: 'ma2', label: 'MA2' },
    { id: 'devices', label: 'Geräte' },
    { id: 'mapping', label: 'Mapping' },
    { id: 'advanced', label: 'Erweitert' },
    { id: 'backups', label: 'Backups' },
  ];

  const api = new ApiClient();
  const statusStore = new StatusStore();

  let page = $state<Page>('status');
  let versionError = $state<string | null>(null);

  onMount(() => {
    statusStore.connect();
    api
      .checkVersion()
      .then(() => {
        versionError = null;
      })
      .catch((error: unknown) => {
        versionError = error instanceof Error ? error.message : 'Versionsprüfung fehlgeschlagen';
      });
    return () => statusStore.disconnect();
  });
</script>

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
</header>

{#if versionError}
  <p class="banner" role="alert">{versionError}</p>
{/if}

<main>
  {#if page === 'status'}
    <StatusPage store={statusStore} devicesLoader={() => api.devices()} />
  {:else if page === 'ma2'}
    <Ma2Page {api} />
  {:else if page === 'mapping'}
    <MappingPage {api} learnStore={statusStore} />
  {:else if page === 'backups' || page === 'advanced'}
    <BackupsPage {api} />
  {:else}
    <section class="page">
      <h1>{pages.find((entry) => entry.id === page)?.label}</h1>
      <p class="muted">Diese Seite wird in den folgenden Schritten ausgebaut.</p>
    </section>
  {/if}
</main>

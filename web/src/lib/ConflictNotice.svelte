<script lang="ts">
  import type { ConfigStore } from './configStore.svelte';

  let { store, onDiscard }: { store: ConfigStore; onDiscard?: () => void } = $props();

  let busy = $state(false);

  async function resolve(choice: 'reload' | 'discard'): Promise<void> {
    busy = true;
    try {
      await store.resolveConflict(choice);
      if (choice === 'discard') onDiscard?.();
    } finally {
      busy = false;
    }
  }
</script>

{#if store.conflict}
  <div class="conflict" role="alert" data-testid="config-conflict">
    <p>
      Die Konfiguration wurde inzwischen an anderer Stelle geändert. Nichts wurde
      überschrieben.
    </p>
    <div class="actions">
      <button type="button" disabled={busy} onclick={() => resolve('reload')}>
        Neu laden
      </button>
      <button type="button" disabled={busy} onclick={() => resolve('discard')}>
        Verwerfen
      </button>
    </div>
  </div>
{/if}

<style>
  .conflict {
    display: grid;
    gap: 0.4rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--warning);
    border-radius: var(--radius);
    font-size: 0.8rem;
  }

  p {
    margin: 0;
  }

  .actions {
    display: flex;
    gap: 0.5rem;
  }
</style>

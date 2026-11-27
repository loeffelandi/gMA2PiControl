<script lang="ts">
  interface Props {
    /** Origin label of the effective assignment, e.g. "geerbt mit Bank-Offset (Offset +5)". */
    source?: string | null;
    /** Explanation of a priority conflict, `null` when nothing is shadowed. */
    conflict?: string | null;
    /** Hide the visible explanation and keep it as tooltip only. */
    compact?: boolean;
  }

  let { source = null, conflict = null, compact = false }: Props = $props();
</script>

{#if source}
  <span class="badge source" data-testid="source-badge">{source}</span>
{/if}
{#if conflict}
  <span
    class="badge conflict"
    data-testid="conflict-badge"
    role="img"
    title={conflict}
    aria-label={`Vorrangkonflikt: ${conflict}`}
  >
    Vorrang
  </span>
  {#if !compact}
    <span class="explain" data-testid="conflict-explanation">{conflict}</span>
  {/if}
{/if}

<style>
  .badge {
    display: inline-block;
    padding: 0.05rem 0.35rem;
    border: 1px solid var(--border-strong);
    border-radius: 0.6rem;
    font-size: 0.65rem;
    line-height: 1.3;
    white-space: nowrap;
  }

  .source {
    color: var(--text-muted);
  }

  .conflict {
    border-color: var(--warning);
    color: var(--warning);
  }

  .explain {
    font-size: 0.7rem;
    color: var(--warning);
  }
</style>

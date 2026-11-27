<script lang="ts">
  import type { ConfigStore } from './configStore.svelte';

  interface Props {
    store: ConfigStore;
    /** Which tab shows the bar; the note session is only linked from the mapping tab. */
    tab: 'mapping' | 'devices';
    /** Open the assignment dialog for the control the detection captured. */
    onAssign?: (control: string) => void;
    /** Switch to the devices tab, where the note session can be operated. */
    onOpenDevices?: () => void;
  }

  let { store, tab, onAssign, onOpenDevices }: Props = $props();

  const learn = $derived(store.learn);
  const session = $derived(store.deviceLearn);
  const detected = $derived(store.detectedControl);
  const ended = $derived(learn?.status === 'timeout' || learn?.status === 'cancelled');

  async function cancel(): Promise<void> {
    await store.cancelLearn();
  }
</script>

{#if learn?.status === 'active'}
  <p class="learn-bar" role="status" data-testid="learn-active">
    Control-Erkennung läuft{learn.device ? ` (${learn.device})` : ''} – bitte
    {learn.kind === 'key' ? 'eine Taste drücken' : 'einen Encoder drehen'}.
    <button type="button" onclick={cancel}>Abbrechen</button>
  </p>
{:else if learn?.status === 'timeout'}
  <p class="learn-bar muted" role="status" data-testid="learn-ended">
    Learn abgelaufen – keine Eingabe erkannt.
  </p>
{/if}

{#if detected && !ended}
  <p class="learn-bar" role="status" data-testid="learn-detected">
    Erkannt: <strong>{detected.control}</strong>
    {#if onAssign}
      <button type="button" onclick={() => onAssign(detected.control)}>Zuweisen</button>
    {/if}
    <button type="button" onclick={() => store.clearDetectedControl()}>Schließen</button>
  </p>
{/if}

{#if session?.active && tab === 'mapping'}
  <p class="learn-bar" role="status" data-testid="note-learn-active">
    Noten-Anlernen läuft für {session.device}, Bank {session.bank}
    {#if session.current}
      · aktiv: <strong>{session.current}</strong>
    {/if}
    {#if onOpenDevices}
      <button type="button" onclick={onOpenDevices}>Zum Geräte-Tab</button>
    {/if}
  </p>
{/if}

{#if store.learnError}
  <p class="learn-bar error" role="alert">{store.learnError}</p>
{/if}

<style>
  .learn-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.6rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid #d4a72c;
    border-radius: var(--radius);
    background: rgba(255, 209, 102, 0.12);
    font-size: 0.85rem;
  }

  .muted {
    color: var(--text-muted);
    border-color: var(--border);
    background: transparent;
  }

  .error {
    color: var(--danger);
    border-color: var(--danger);
    background: transparent;
  }
</style>

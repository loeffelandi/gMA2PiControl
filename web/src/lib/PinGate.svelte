<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient } from './api';

  let {
    api,
    onUnlocked,
  }: {
    api: ApiClient;
    onUnlocked: () => void;
  } = $props();

  let pin = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);
  let input = $state<HTMLInputElement>();

  onMount(() => {
    input?.focus();
  });

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (!pin) return;
    busy = true;
    error = null;
    try {
      await api.login(pin);
      pin = '';
      onUnlocked();
    } catch (failure) {
      error =
        failure instanceof ApiError
          ? failure.detail || failure.message
          : failure instanceof Error
            ? failure.message
            : 'PIN falsch';
      pin = '';
    } finally {
      busy = false;
    }
  }
</script>

<main class="gate">
  <form class="gate-card" onsubmit={submit}>
    <h1>ma2pi</h1>
    <p class="muted">Bitte PIN eingeben, um die Oberfläche zu entsperren.</p>

    <label for="pin">PIN</label>
    <input
      id="pin"
      type="password"
      inputmode="numeric"
      autocomplete="current-password"
      maxlength="12"
      bind:value={pin}
      bind:this={input}
    />

    {#if error}
      <p class="message error" role="alert">{error}</p>
    {/if}

    <button type="submit" disabled={busy || !pin}>
      {busy ? 'Prüfe …' : 'Entsperren'}
    </button>
  </form>
</main>

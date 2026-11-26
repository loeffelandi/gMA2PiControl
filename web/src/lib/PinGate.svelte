<script lang="ts">
  import { ApiError, type ApiClient } from './api';
  import { PRODUCT_NAME } from './brand';

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

  function focusOnMount(node: HTMLInputElement): void {
    node.focus();
  }

  function formatLoginError(failure: unknown): string {
    if (failure instanceof ApiError) {
      if (failure.code === 'pin_locked') {
        if (failure.detail) return failure.detail;
        if (failure.retryAfter !== undefined) {
          return `Zu viele Fehlversuche – bitte ${failure.retryAfter} s warten`;
        }
        return 'Zu viele Fehlversuche – bitte warten';
      }
      return failure.detail || failure.message;
    }
    if (failure instanceof Error) return failure.message;
    return 'PIN falsch';
  }

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
      error = formatLoginError(failure);
      pin = '';
    } finally {
      busy = false;
    }
  }
</script>

<main class="gate">
  <form class="gate-card" onsubmit={submit}>
    <h1>
      <img src="/favicon.svg" alt="" width="32" height="32" />
      {PRODUCT_NAME}
    </h1>
    <p class="muted">Bitte PIN eingeben, um die Oberfläche zu entsperren.</p>

    <label for="pin">PIN</label>
    <input
      id="pin"
      type="password"
      inputmode="numeric"
      autocomplete="current-password"
      maxlength="12"
      bind:value={pin}
      {@attach focusOnMount}
    />

    {#if error}
      <p class="message error" role="alert">{error}</p>
    {/if}

    <button type="submit" disabled={busy || !pin}>
      {busy ? 'Prüfe …' : 'Entsperren'}
    </button>
  </form>
</main>

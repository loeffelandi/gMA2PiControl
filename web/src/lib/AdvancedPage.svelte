<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient } from './api';

  let { api }: { api: ApiClient } = $props();

  let loading = $state(true);
  let busy = $state(false);
  let message = $state<{ ok: boolean; text: string } | null>(null);

  let rate = $state(25);
  let burst = $state(10);
  let level = $state('INFO');
  let pinEnabled = $state(true);
  let pin = $state('');
  let pinSet = $state(true);

  function errorText(error: unknown): string {
    if (error instanceof ApiError) return error.detail || error.message;
    if (error instanceof Error) return error.message;
    return 'Unbekannter Fehler';
  }

  onMount(async () => {
    try {
      const config = await api.config();
      const rateLimit = (config.rate_limit ?? {}) as Record<string, unknown>;
      const logging = (config.logging ?? {}) as Record<string, unknown>;
      const web = (config.web ?? {}) as Record<string, unknown>;
      rate = Number(rateLimit.messages_per_second ?? 25);
      burst = Number(rateLimit.burst ?? 10);
      level = String(logging.level ?? 'INFO');
      pinEnabled = Boolean(web.pin_enabled ?? true);
      pinSet = Boolean(web.pin_set ?? true);
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      loading = false;
    }
  });

  async function saveSettings(): Promise<void> {
    busy = true;
    message = null;
    try {
      await api.updateConfig({
        rate_limit: {
          messages_per_second: Number(rate),
          burst: Number(burst),
        },
        logging: { level },
        web: {
          pin_enabled: pinEnabled,
          ...(pin ? { pin } : {}),
        },
      });
      if (pin) {
        pinSet = true;
        pin = '';
      }
      message = { ok: true, text: 'Erweiterte Einstellungen gespeichert.' };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }
</script>

<section class="page">
  <h1>Erweitert</h1>

  {#if loading}
    <p class="muted">Lade Einstellungen …</p>
  {:else}
    <h2>LAN-Port</h2>
    <p class="hint">
      Bind-Adresse und Port stehen in <code>/var/lib/ma2pi/config.toml</code>
      unter <code>[web]</code>. Änderungen daran werden erst nach einem
      Dienstneustart wirksam.
    </p>

    <h2>PIN-Sperre</h2>
    <form class="form" onsubmit={(event) => event.preventDefault()}>
      <label for="pin-enabled">PIN aktiv</label>
      <input id="pin-enabled" type="checkbox" bind:checked={pinEnabled} />

      <label for="pin">Neue PIN</label>
      <input
        id="pin"
        type="password"
        inputmode="numeric"
        maxlength="12"
        placeholder={pinSet ? '•••••• (unverändert)' : '4–12 Ziffern'}
        bind:value={pin}
      />
      <p class="hint">
        Die PIN schützt Oberfläche und API. Sie wird nur geschrieben und nie
        zurückgegeben. Ohne PIN ist die Oberfläche im LAN offen; die Oberfläche
        warnt oben, solange keine PIN gesetzt ist.
      </p>

      <h2>Rate &amp; Logging</h2>
      <label for="rate">Frames pro Sekunde</label>
      <input id="rate" type="number" min="1" bind:value={rate} />

      <label for="burst">Burst</label>
      <input id="burst" type="number" min="1" bind:value={burst} />

      <label for="level">Log-Level</label>
      <select id="level" bind:value={level}>
        <option value="DEBUG">DEBUG</option>
        <option value="INFO">INFO</option>
        <option value="WARNING">WARNING</option>
        <option value="ERROR">ERROR</option>
      </select>

      <div class="actions">
        <button type="button" onclick={saveSettings} disabled={busy}>Einstellungen speichern</button>
      </div>
    </form>

    {#if message}
      <p class:error={!message.ok} class="message" role={message.ok ? 'status' : 'alert'}>
        {message.text}
      </p>
    {/if}
  {/if}
</section>

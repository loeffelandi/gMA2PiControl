<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient } from './api';

  let {
    api,
    onAuthChange,
  }: {
    api: ApiClient;
    onAuthChange?: () => void;
  } = $props();

  let loading = $state(true);
  let busy = $state(false);
  let message = $state<{ ok: boolean; text: string } | null>(null);

  let rate = $state(25);
  let burst = $state(10);
  let level = $state('INFO');
  let pinEnabled = $state(false);
  let pin = $state('');
  let pinSet = $state(false);

  let powerEnabled = $state(true);
  let powerCombo = $state(true);
  let holdControls = $state<string[]>(['ma', 'off']);
  let confirmControl = $state('please_big');
  let confirmPresses = $state(2);
  let confirming = $state(false);
  let powerBusy = $state(false);
  let shuttingDown = $state(false);
  let powerError = $state<string | null>(null);

  const CONTROL_LABELS: Record<string, string> = {
    ma: 'MA',
    off: 'Off',
    please_big: 'Please',
  };

  function controlLabel(control: string): string {
    return CONTROL_LABELS[control] ?? control;
  }

  let comboHint = $derived(
    !powerEnabled
      ? 'Herunterfahren ist in [power] abgeschaltet.'
      : powerCombo
        ? `Am Cherry: ${holdControls.map(controlLabel).join(' + ')} gedrückt halten und dabei ` +
          `${confirmPresses}× ${controlLabel(confirmControl)} drücken. ` +
          'Die onPC zeigt jeden Schritt im System Monitor.'
        : 'Die Cherry-Tastenkombination ist in [power] abgeschaltet.',
  );

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
      const power = (config.power ?? {}) as Record<string, unknown>;
      rate = Number(rateLimit.messages_per_second ?? 25);
      burst = Number(rateLimit.burst ?? 10);
      level = String(logging.level ?? 'INFO');
      pinEnabled = Boolean(web.pin_enabled ?? false);
      pinSet = Boolean(web.pin_set ?? false);
      powerEnabled = Boolean(power.enabled ?? true);
      powerCombo = Boolean(power.combo ?? true);
      if (Array.isArray(power.hold_controls)) {
        holdControls = power.hold_controls.map(String);
      }
      confirmControl = String(power.confirm_control ?? 'please_big');
      confirmPresses = Number(power.confirm_presses ?? 2);
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
      onAuthChange?.();
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }

  async function shutdown(): Promise<void> {
    powerBusy = true;
    powerError = null;
    try {
      await api.shutdown();
      shuttingDown = true;
      confirming = false;
    } catch (error) {
      powerError = errorText(error);
    } finally {
      powerBusy = false;
    }
  }
</script>

<section class="page">
  <h1>Erweitert</h1>

  {#if loading}
    <p class="muted">Lade Einstellungen …</p>
  {:else}
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
      <input id="rate" type="number" min="5" max="40" bind:value={rate} />

      <label for="burst">Burst</label>
      <input id="burst" type="number" min="1" bind:value={burst} />

      <label for="level">Log-Level</label>
      <select id="level" bind:value={level}>
        <option value="DEBUG">DEBUG</option>
        <option value="INFO">INFO</option>
        <option value="WARNING">WARNING</option>
        <option value="ERROR">ERROR</option>
        <option value="CRITICAL">CRITICAL</option>
      </select>

      <div class="actions">
        <button type="button" onclick={saveSettings} disabled={busy}>Einstellungen speichern</button>
      </div>
    </form>

    {#if message}
      <p class={['message', { error: !message.ok }]} role={message.ok ? 'status' : 'alert'}>
        {message.text}
      </p>
    {/if}

    <h2>Raspberry Pi</h2>
    <div class="power">
      {#if shuttingDown}
        <p class="message" role="status">
          Der Pi fährt herunter. Den Strom erst trennen, wenn die grüne LED am Pi
          aus ist (etwa 20 Sekunden).
        </p>
      {:else if confirming}
        <p>
          Pi wirklich herunterfahren? Er startet erst wieder, wenn der Strom
          getrennt und neu verbunden wird.
        </p>
        <div class="power-actions">
          <button type="button" class="danger" onclick={shutdown} disabled={powerBusy}>
            Ja, herunterfahren
          </button>
          <button type="button" onclick={() => (confirming = false)} disabled={powerBusy}>
            Abbrechen
          </button>
        </div>
      {:else}
        <div class="power-actions">
          <button
            type="button"
            class="danger"
            onclick={() => (confirming = true)}
            disabled={!powerEnabled}
          >
            Pi herunterfahren
          </button>
        </div>
      {/if}
      {#if powerError}
        <p class="message error" role="alert">{powerError}</p>
      {/if}
      <p class="muted">{comboHint}</p>
    </div>
  {/if}
</section>

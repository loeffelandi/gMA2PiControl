<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient } from './api';

  let { api }: { api: ApiClient } = $props();

  let host = $state('');
  let port = $state(80);
  let path = $state('/?ma=1');
  let username = $state('');
  let password = $state('');
  let passwordSet = $state(false);
  let loading = $state(true);
  let busy = $state(false);
  let message = $state<{ ok: boolean; text: string } | null>(null);

  function errorText(error: unknown): string {
    if (error instanceof ApiError) return error.detail || error.message;
    if (error instanceof Error) return error.message;
    return 'Unbekannter Fehler';
  }

  function credentials(): Record<string, unknown> {
    return {
      host,
      port: Number(port),
      path,
      username,
      ...(password ? { password } : {}),
    };
  }

  onMount(async () => {
    try {
      const config = await api.config();
      const ma2 = (config.ma2 ?? {}) as Record<string, unknown>;
      host = String(ma2.host ?? '');
      port = Number(ma2.port ?? 80);
      path = String(ma2.path ?? '/?ma=1');
      username = String(ma2.username ?? '');
      passwordSet = Boolean(ma2.password_set);
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      loading = false;
    }
  });

  async function test(): Promise<void> {
    busy = true;
    message = null;
    try {
      const result = await api.testConnection(credentials());
      message = {
        ok: true,
        text: `Verbindung erfolgreich: ${String(result.username)} (Session ${String(result.session)})`,
      };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }

  async function save(): Promise<void> {
    busy = true;
    message = null;
    try {
      await api.updateConfig({ ma2: credentials() });
      password = '';
      passwordSet = true;
      message = { ok: true, text: 'Zugangsdaten gespeichert.' };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }
</script>

<section class="page">
  <h1>MA2-Zugangsdaten</h1>

  {#if loading}
    <p class="muted">Lade Konfiguration …</p>
  {:else}
    <form class="form" onsubmit={(event) => event.preventDefault()}>
      <label for="ma2-host">Host</label>
      <input id="ma2-host" bind:value={host} autocomplete="off" />

      <label for="ma2-port">Port</label>
      <input id="ma2-port" bind:value={port} type="number" min="1" max="65535" />

      <label for="ma2-path">Pfad</label>
      <input id="ma2-path" bind:value={path} autocomplete="off" />

      <label for="ma2-user">Benutzer</label>
      <input id="ma2-user" bind:value={username} autocomplete="username" />

      <label for="ma2-password">Passwort</label>
      <input
        id="ma2-password"
        bind:value={password}
        type="password"
        autocomplete="new-password"
        placeholder={passwordSet ? '•••••• (unverändert)' : 'Passwort'}
      />
      <p class="hint">
        Das Passwort wird nur geschrieben und nie zurückgegeben.
        {passwordSet ? 'Aktuell ist ein Passwort gesetzt.' : 'Noch kein Passwort gesetzt.'}
      </p>

      <div class="actions">
        <button type="button" onclick={test} disabled={busy}>Testen</button>
        <button type="button" onclick={save} disabled={busy}>Speichern</button>
      </div>
    </form>

    {#if message}
      <p class:error={!message.ok} class="message" role={message.ok ? 'status' : 'alert'}>
        {message.text}
      </p>
    {/if}
  {/if}
</section>

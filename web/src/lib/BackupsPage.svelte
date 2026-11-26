<script lang="ts">
  import { onMount } from 'svelte';

  import { ApiError, type ApiClient, type BackupEntry } from './api';

  let { api }: { api: ApiClient } = $props();

  let backups = $state<BackupEntry[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let message = $state<{ ok: boolean; text: string } | null>(null);
  let confirmId = $state<string | null>(null);

  let rate = $state(25);
  let burst = $state(10);
  let level = $state('INFO');

  function errorText(error: unknown): string {
    if (error instanceof ApiError) return error.detail || error.message;
    if (error instanceof Error) return error.message;
    return 'Unbekannter Fehler';
  }

  async function reload(): Promise<void> {
    backups = await api.backups();
  }

  onMount(async () => {
    try {
      const [, config] = await Promise.all([reload(), api.config()]);
      const rateLimit = (config.rate_limit ?? {}) as Record<string, unknown>;
      const logging = (config.logging ?? {}) as Record<string, unknown>;
      rate = Number(rateLimit.messages_per_second ?? 25);
      burst = Number(rateLimit.burst ?? 10);
      level = String(logging.level ?? 'INFO');
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      loading = false;
    }
  });

  async function createBackup(): Promise<void> {
    busy = true;
    message = null;
    try {
      const entry = await api.createBackup();
      await reload();
      message = { ok: true, text: `Backup ${entry.id} angelegt.` };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }

  async function restore(): Promise<void> {
    if (!confirmId) return;
    const id = confirmId;
    busy = true;
    message = null;
    try {
      await api.restoreBackup(id);
      confirmId = null;
      message = { ok: true, text: `Backup ${id} wiederhergestellt.` };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }

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
      });
      message = { ok: true, text: 'Erweiterte Einstellungen gespeichert.' };
    } catch (error) {
      message = { ok: false, text: errorText(error) };
    } finally {
      busy = false;
    }
  }
</script>

<section class="page table-page">
  <h1>Backups &amp; Erweitert</h1>

  {#if loading}
    <p class="muted">Lade Backups …</p>
  {:else}
    <h2>Konfigurations-Backups</h2>
    <button type="button" onclick={createBackup} disabled={busy}>Backup anlegen</button>

    {#if backups.length}
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Zeitpunkt</th>
            <th>Größe</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each backups as backup (backup.id)}
            <tr>
              <td>
                {backup.id}
                {#if backup.last_good}<span class="muted"> (last-good)</span>{/if}
              </td>
              <td>{backup.modified}</td>
              <td>{backup.size} B</td>
              <td>
                <button type="button" onclick={() => (confirmId = backup.id)} disabled={busy}>
                  Wiederherstellen
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {:else}
      <p class="muted">Noch keine Backups vorhanden.</p>
    {/if}

    {#if confirmId}
      <div class="confirm" data-testid="restore-confirm">
        <p>Backup <strong>{confirmId}</strong> wirklich wiederherstellen?</p>
        <div class="actions">
          <button type="button" onclick={restore} disabled={busy}>Ja, wiederherstellen</button>
          <button type="button" onclick={() => (confirmId = null)} disabled={busy}>Abbrechen</button>
        </div>
      </div>
    {/if}

    <h2>Rate &amp; Logging</h2>
    <form class="form" onsubmit={(event) => event.preventDefault()}>
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

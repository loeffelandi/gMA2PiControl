<script lang="ts">
  import { SaveError, type ConfigStore } from './configStore.svelte';

  interface Props {
    store: ConfigStore;
    /** Show the values without inputs, e.g. in the mapping tab. */
    readonly?: boolean;
  }

  let { store, readonly = false }: Props = $props();

  interface Draft {
    device: string | null;
    bank: number | null;
    bankSize?: number | '';
    channel?: number | '';
    maPage?: number | '';
  }

  let draft = $state.raw<Draft>({ device: null, bank: null });
  let saving = $state(false);
  let message = $state<string | null>(null);

  const device = $derived(store.device);
  const bank = $derived(store.bank);
  const activeBank = $derived(store.banks.find((entry) => entry.number === bank));
  const storedPage = $derived(
    device ? (store.config?.mapping?.device_banks?.[device.name]?.[String(bank)]?.ma_page ?? '') : '',
  );

  // The bank size belongs to the device, channel and MA page to the bank: a draft
  // survives switching banks only for the bank size.
  const bankSize = $derived(
    draft.device === device?.name && draft.bankSize !== undefined
      ? draft.bankSize
      : (device?.bank_size ?? 1),
  );
  const channel = $derived(
    draft.device === device?.name && draft.bank === bank && draft.channel !== undefined
      ? draft.channel
      : (activeBank?.channel ?? bank),
  );
  const maPage = $derived(
    draft.device === device?.name && draft.bank === bank && draft.maPage !== undefined
      ? draft.maPage
      : storedPage,
  );

  function edit(change: Partial<Draft>): void {
    const sameBank = draft.device === (device?.name ?? null) && draft.bank === bank;
    const sameDevice = draft.device === (device?.name ?? null);
    draft = {
      device: device?.name ?? null,
      bank,
      bankSize: sameDevice ? draft.bankSize : undefined,
      channel: sameBank ? draft.channel : undefined,
      maPage: sameBank ? draft.maPage : undefined,
      ...change,
    };
  }

  function parse(value: number | '' | null | undefined): number | null {
    return value === '' || value === null || value === undefined ? null : Number(value);
  }

  async function save(): Promise<void> {
    if (!device || saving) return;
    saving = true;
    message = null;
    try {
      await store.saveBankSettings({
        bank,
        bankSize: Number(bankSize),
        channel: Number(channel),
        maPage: parse(maPage),
      });
      draft = { device: null, bank: null };
    } catch (cause) {
      // The store already holds the message; keep the draft for correction.
      if (!(cause instanceof SaveError)) {
        message = cause instanceof Error ? cause.message : 'Speichern fehlgeschlagen';
      }
    } finally {
      saving = false;
    }
  }
</script>

{#if device && store.banks.length}
  {#if readonly}
    <dl class="settings readonly" data-testid="bank-settings-readonly">
      <div>
        <dt>Bankgröße</dt>
        <dd>{bankSize}</dd>
      </div>
      <div>
        <dt>Kanal</dt>
        <dd>{channel}</dd>
      </div>
      <div>
        <dt>MA-Page</dt>
        <dd>{maPage === '' ? '—' : maPage}</dd>
      </div>
    </dl>
  {:else}
    <div class="settings">
      <label>
        Bankgröße
        <input
          type="number"
          min="1"
          value={bankSize}
          oninput={(event) => edit({ bankSize: event.currentTarget.valueAsNumber })}
        />
      </label>
      <label>
        Kanal
        <input
          type="number"
          min="1"
          max="16"
          value={channel}
          oninput={(event) => edit({ channel: event.currentTarget.valueAsNumber })}
        />
      </label>
      <label>
        MA-Page
        <input
          type="number"
          min="1"
          placeholder="—"
          value={maPage}
          oninput={(event) =>
            edit({
              maPage: event.currentTarget.value === '' ? '' : event.currentTarget.valueAsNumber,
            })}
        />
      </label>
      <button type="button" disabled={saving} onclick={save}>Einstellungen speichern</button>
    </div>
    {#if message}
      <p class="error" role="alert">{message}</p>
    {/if}
  {/if}
{/if}

<style>
  .settings {
    display: flex;
    align-items: end;
    gap: 0.6rem;
    margin-top: 0.9rem;
  }

  .settings label,
  .settings div {
    display: grid;
    gap: 0.2rem;
    font-size: 0.75rem;
  }

  dl,
  dt,
  dd {
    margin: 0;
  }

  dt {
    color: var(--text-muted);
  }

  .readonly {
    align-items: start;
  }

  .error {
    margin: 0.4rem 0 0;
    font-size: 0.75rem;
    color: var(--danger);
  }

  input {
    padding: 0.3rem;
    background: var(--surface-inset);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    color: inherit;
  }
</style>

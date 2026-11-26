<script lang="ts">
  import { ApiError } from './api';

  type ActionKind =
    | 'hardkey'
    | 'command'
    | 'executor'
    | 'encoder'
    | 'screen_mode'
    | 'screen'
    | 'encoder_press';

  type AssignScope = 'bank' | 'global';

  interface InitialValues {
    action?: ActionKind;
    hardkey?: string;
    command?: string;
    page?: string;
    executor?: number;
    targetKind?: 'button' | 'fader';
    button?: number;
    accelerated?: boolean;
    slot?: number;
    attribute?: string;
    screen?: number;
  }

  interface FormValues {
    action: ActionKind;
    hardkey: string;
    command: string;
    page: string;
    executor: number;
    targetKind: 'button' | 'fader';
    button: number;
    accelerated: boolean;
    slot: number;
    attribute: string;
    encoderMode: 'slot' | 'attribute';
    encoderScreen: number;
    screenNumber: number;
    scope: AssignScope;
    step: number;
  }

  interface Props {
    control: string;
    bank: number;
    kind: string;
    count: number;
    initial?: InitialValues | null;
    inherited?: boolean;
    hasAssignment?: boolean;
    onSave: (values: {
      action: ActionKind;
      hardkey: string;
      command: string;
      page: string;
      executor: number;
      targetKind: 'button' | 'fader';
      button: number;
      accelerated: boolean;
      start: number;
      step: number;
      slot: number;
      attribute: string;
      screen: number;
      scope: AssignScope;
    }) => Promise<void>;
    onClear?: () => Promise<void>;
    onClose: () => void;
  }

  let {
    control,
    bank,
    kind,
    count,
    initial = null,
    inherited = false,
    hasAssignment = false,
    onSave,
    onClear,
    onClose,
  }: Props = $props();

  function defaultAction(controlKind: string): ActionKind {
    if (controlKind === 'relative-encoder') return 'encoder';
    return 'executor';
  }

  function defaultTargetKind(controlKind: string): 'button' | 'fader' {
    if (
      controlKind === 'fader' ||
      controlKind === 'poti' ||
      controlKind === 'encoder'
    ) {
      return 'fader';
    }
    return 'button';
  }

  const base = $derived<FormValues & { _control: string; _bank: number }>({
    _control: control,
    _bank: bank,
    action: initial?.action ?? defaultAction(kind),
    hardkey: initial?.hardkey ?? 'GOTO',
    command: initial?.command ?? '',
    page: initial?.page ?? 'current',
    executor: initial?.executor ?? 1,
    targetKind: initial?.targetKind ?? defaultTargetKind(kind),
    button: initial?.button ?? 1,
    accelerated: initial?.accelerated ?? false,
    slot: initial?.slot ?? 1,
    attribute: initial?.attribute ?? '',
    encoderMode: initial?.attribute ? 'attribute' : 'slot',
    encoderScreen: initial?.action === 'screen' ? 0 : (initial?.screen ?? 0),
    screenNumber: initial?.action === 'screen' ? (initial?.screen ?? 1) : 1,
    scope: inherited ? 'global' : 'bank',
    step: 1,
  });

  let edits = $state.raw<{ forBase: object | null; values: Partial<FormValues> }>({
    forBase: null,
    values: {},
  });
  let saving = $state(false);
  let error = $state<string | null>(null);

  function field<K extends keyof FormValues>(name: K): FormValues[K] {
    const currentBase = base;
    if (edits.forBase === currentBase && name in edits.values) {
      return edits.values[name] as FormValues[K];
    }
    return currentBase[name];
  }

  function setField<K extends keyof FormValues>(name: K, value: FormValues[K]): void {
    const currentBase = base;
    const prev = edits.forBase === currentBase ? edits.values : {};
    edits = { forBase: currentBase, values: { ...prev, [name]: value } };
  }

  function openModal(node: HTMLDialogElement) {
    if (typeof node.showModal === 'function') {
      if (!node.open) {
        node.showModal();
      }
    } else {
      node.setAttribute('open', '');
    }
  }

  const action = $derived(field('action'));
  const targetKind = $derived(field('targetKind'));
  const executor = $derived(field('executor'));
  const step = $derived(field('step'));
  const slot = $derived(field('slot'));
  const encoderMode = $derived(field('encoderMode'));

  const multi = $derived(count > 1);
  const showAcceleration = $derived(
    action === 'executor' && targetKind === 'fader' && kind === 'encoder',
  );
  const preview = $derived(
    multi
      ? Array.from({ length: count }, (_, index) => executor + index * step).join(', ')
      : String(executor),
  );

  function errorMessage(cause: unknown, fallback: string): string {
    if (cause instanceof ApiError) return cause.detail || fallback;
    if (cause instanceof Error) return cause.message || fallback;
    return fallback;
  }

  function handleCancel(event: Event): void {
    event.preventDefault();
    if (!saving) {
      onClose();
    }
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && !saving) {
      event.preventDefault();
      onClose();
    }
  }

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (multi && action === 'encoder') return;
    saving = true;
    error = null;
    try {
      const currentScreen =
        action === 'screen'
          ? Number(field('screenNumber'))
          : encoderMode === 'slot' && slot >= 1 && slot <= 4 && bank === 1
            ? Number(field('encoderScreen'))
            : 0;
      await onSave({
        action,
        hardkey: field('hardkey'),
        command: field('command'),
        page: field('page'),
        executor,
        targetKind,
        button: field('button'),
        accelerated: field('accelerated'),
        start: executor,
        step,
        slot,
        attribute:
          action === 'encoder' && encoderMode === 'attribute'
            ? field('attribute')
            : '',
        screen: currentScreen,
        scope: inherited && action === 'executor' && bank >= 2 ? field('scope') : 'bank',
      });
    } catch (cause) {
      error = errorMessage(cause, 'Speichern fehlgeschlagen');
    } finally {
      saving = false;
    }
  }

  async function clear(): Promise<void> {
    if (!onClear) return;
    saving = true;
    error = null;
    try {
      await onClear();
    } catch (cause) {
      error = errorMessage(cause, 'Löschen fehlgeschlagen');
    } finally {
      saving = false;
    }
  }
</script>

<dialog
  class="assign-dialog"
  {@attach openModal}
  oncancel={handleCancel}
  onkeydown={handleKeydown}
>
  <form class="assign" onsubmit={submit}>
    <h3>{control} · Bank {bank}{multi ? ` · ${count} Controls` : ''}</h3>

    <label>
      Aktion
      <select bind:value={() => field('action'), (v) => setField('action', v)}>
        <option value="hardkey">Hardkey</option>
        <option value="command">Command</option>
        <option value="executor">Executor</option>
        {#if kind === 'relative-encoder'}
          <option value="encoder">Attribut-Encoder</option>
        {/if}
        <option value="screen_mode">Screen-Modus umschalten</option>
        <option value="screen">Screen wählen</option>
        <option value="encoder_press">Encoder-Klick</option>
      </select>
    </label>

    {#if action === 'encoder'}
      <label>
        Ziel
        <select
          bind:value={() => field('encoderMode'), (v) => setField('encoderMode', v)}
        >
          <option value="slot">Attribut-Slot</option>
          <option value="attribute">Attributname</option>
        </select>
      </label>
      <div class="row">
        {#if encoderMode === 'slot'}
          <label>
            Slot
            <input
              type="number"
              min="1"
              max="8"
              bind:value={() => field('slot'), (v) => setField('slot', v)}
            />
          </label>
          {#if slot >= 1 && slot <= 4 && bank === 1}
            <label>
              Screen-Encoder <span class="muted">(MA/Bank)</span>
              <select
                bind:value={() => field('encoderScreen'), (v) => setField('encoderScreen', v)}
              >
                <option value={0}>— keiner —</option>
                <option value={5}>Screen-Encoder 5</option>
                <option value={6}>Screen-Encoder 6</option>
                <option value={7}>Screen-Encoder 7</option>
                <option value={8}>Screen-Encoder 8</option>
                <option value={9}>Screen-Encoder 9</option>
                <option value={10}>Screen-Encoder 10</option>
              </select>
            </label>
          {/if}
        {:else}
          <label>
            Attributname
            <input
              bind:value={() => field('attribute'), (v) => setField('attribute', v)}
              placeholder="z. B. Dimmer"
            />
          </label>
        {/if}
      </div>
      <p class="muted">
        Ohne MA/Bank wirkt der Encoder auf das Attribut, mit MA oder Bank auf den
        Screen-Encoder.
      </p>
      {#if multi}
        <p class="error">Encoder-Ziele nur für ein einzelnes Control.</p>
      {/if}
    {:else if action === 'screen_mode'}
      <p class="muted">Die Taste schaltet zwischen Attribut- und Screen-Encodern um.</p>
    {:else if action === 'screen'}
      <label>
        Screen
        <input
          type="number"
          min="1"
          max="6"
          bind:value={() => field('screenNumber'), (v) => setField('screenNumber', v)}
        />
      </label>
    {:else if action === 'encoder_press'}
      <label>
        Encoder-Slot
        <input
          type="number"
          min="1"
          max="8"
          bind:value={() => field('slot'), (v) => setField('slot', v)}
        />
      </label>
    {:else if action === 'hardkey'}
      <label>
        Hardkey
        <input bind:value={() => field('hardkey'), (v) => setField('hardkey', v)} />
      </label>
    {:else if action === 'command'}
      <label>
        Command
        <input bind:value={() => field('command'), (v) => setField('command', v)} />
      </label>
    {:else}
      {#if inherited && bank >= 2}
        <p class="inherited-hint">Geerbt von Bank 1 (inkl. Bank-Offset)</p>
        <label>
          Geltungsbereich
          <select bind:value={() => field('scope'), (v) => setField('scope', v)}>
            <option value="global">Global (Bank 1 + Offset)</option>
            <option value="bank">Nur Bank {bank} (Override)</option>
          </select>
        </label>
      {/if}
      <div class="row">
        <label>
          Page
          <input bind:value={() => field('page'), (v) => setField('page', v)} />
        </label>
        <label>
          Art
          <select
            bind:value={() => field('targetKind'), (v) => setField('targetKind', v)}
          >
            <option value="button">Button</option>
            <option value="fader">Fader</option>
          </select>
        </label>
      </div>
      <div class="row">
        <label>
          Executor
          <input
            type="number"
            min="1"
            bind:value={() => field('executor'), (v) => setField('executor', v)}
          />
        </label>
        {#if targetKind === 'button'}
          <label>
            Button
            <input
              type="number"
              min="1"
              max="3"
              bind:value={() => field('button'), (v) => setField('button', v)}
            />
          </label>
        {/if}
      </div>
      {#if multi}
        <label>
          Schrittweite
          <input
            type="number"
            min="1"
            bind:value={() => field('step'), (v) => setField('step', v)}
          />
        </label>
        <p class="preview">Vorschau: {preview}</p>
      {/if}
      {#if showAcceleration}
        <label class="check">
          <input
            type="checkbox"
            bind:checked={() => field('accelerated'), (v) => setField('accelerated', v)}
          />
          Beschleunigt
        </label>
      {/if}
    {/if}

    {#if error}
      <p class="error" role="alert">{error}</p>
    {/if}

    <div class="actions">
      {#if hasAssignment && onClear}
        <button
          type="button"
          class="danger"
          disabled={saving}
          onclick={clear}
        >
          Belegung löschen
        </button>
      {/if}
      <button type="button" disabled={saving} onclick={onClose}>Abbrechen</button>
      <button type="submit" disabled={saving || (multi && action === 'encoder')}>
        {saving ? 'Speichere …' : 'Speichern'}
      </button>
    </div>
  </form>
</dialog>

<style>
  .assign-dialog {
    padding: 0;
    border: none;
    background: transparent;
    color: inherit;
    max-width: min(26rem, calc(100vw - 2rem));
    width: 100%;
  }

  .assign-dialog::backdrop {
    background: rgb(10 10 10 / 0.65);
  }

  .assign {
    display: grid;
    gap: 0.6rem;
    max-width: 26rem;
    padding: 0.8rem;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
  }

  h3 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 500;
  }

  label {
    display: grid;
    gap: 0.2rem;
    font-size: 0.8rem;
  }

  .row {
    display: flex;
    gap: 0.6rem;
  }

  .row label {
    flex: 1;
  }

  .check {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .preview,
  .inherited-hint,
  .error {
    margin: 0;
    font-size: 0.75rem;
  }

  .inherited-hint {
    color: var(--warning);
  }

  .error {
    color: var(--danger);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .actions .danger {
    margin-right: auto;
  }

  input,
  select {
    padding: 0.3rem;
    background: var(--surface-inset);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius);
    color: inherit;
  }
</style>

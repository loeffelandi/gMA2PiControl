<script lang="ts">
  interface Props {
    control: string;
    bank: number;
    kind: string;
    count: number;
    initial?: {
      action?:
        | 'hardkey'
        | 'command'
        | 'executor'
        | 'encoder'
        | 'screen_mode'
        | 'screen'
        | 'encoder_press';
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
    } | null;
    onSave: (values: {
      action:
        | 'hardkey'
        | 'command'
        | 'executor'
        | 'encoder'
        | 'screen_mode'
        | 'screen'
        | 'encoder_press';
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
    }) => Promise<void>;
    onClose: () => void;
  }

  let {
    control,
    bank,
    kind,
    count,
    initial = null,
    onSave,
    onClose,
  }: Props = $props();

  let action = $state<
    'hardkey' | 'command' | 'executor' | 'encoder' | 'screen_mode' | 'screen' | 'encoder_press'
  >(initial?.action ?? 'executor');
  let hardkey = $state(initial?.hardkey ?? 'GOTO');
  let command = $state(initial?.command ?? '');
  let page = $state(initial?.page ?? 'current');
  let executor = $state(initial?.executor ?? 1);
  let targetKind = $state<'button' | 'fader'>(initial?.targetKind ?? 'button');
  let button = $state(initial?.button ?? 1);
  let accelerated = $state(initial?.accelerated ?? false);
  let slot = $state(initial?.slot ?? 1);
  let attribute = $state(initial?.attribute ?? '');
  let encoderMode = $state<'slot' | 'attribute'>(
    initial?.attribute ? 'attribute' : 'slot',
  );
  let screen = $state(initial?.screen ?? 0);
  let step = $state(1);
  let saving = $state(false);
  let error = $state<string | null>(null);

  const multi = $derived(count > 1);
  const showAcceleration = $derived(
    action === 'executor' && targetKind === 'fader' && kind === 'encoder',
  );
  const preview = $derived(
    multi
      ? Array.from({ length: count }, (_, index) => executor + index * step).join(', ')
      : String(executor),
  );

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    saving = true;
    error = null;
    try {
      await onSave({
        action,
        hardkey,
        command,
        page,
        executor,
        targetKind,
        button,
        accelerated,
        start: executor,
        step,
        slot,
        attribute: action === 'encoder' && encoderMode === 'attribute' ? attribute : '',
        screen,
      });
    } catch (cause) {
      error = cause instanceof Error ? cause.message : 'Speichern fehlgeschlagen';
    } finally {
      saving = false;
    }
  }
</script>

<form class="assign" onsubmit={submit}>
  <h3>{control} · Bank {bank}{multi ? ` · ${count} Controls` : ''}</h3>

  <label>
    Aktion
    <select bind:value={action}>
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
      <select bind:value={encoderMode}>
        <option value="slot">Attribut-Slot</option>
        <option value="attribute">Attributname</option>
      </select>
    </label>
    <div class="row">
      {#if encoderMode === 'slot'}
        <label>Slot <input type="number" min="1" max="8" bind:value={slot} /></label>
        <label>
          Screen-Encoder <span class="muted">(MA/Bank)</span>
          <input type="number" min="5" max="10" bind:value={screen} />
        </label>
      {:else}
        <label>
          Attributname
          <input bind:value={attribute} placeholder="z. B. Dimmer" />
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
    <label>Screen <input type="number" min="1" max="6" bind:value={screen} /></label>
  {:else if action === 'encoder_press'}
    <label>Encoder-Slot <input type="number" min="1" max="8" bind:value={slot} /></label>
  {:else if action === 'hardkey'}
    <label>Hardkey <input bind:value={hardkey} /></label>
  {:else if action === 'command'}
    <label>Command <input bind:value={command} /></label>
  {:else}
    <div class="row">
      <label> Page <input bind:value={page} /></label>
      <label>
        Art
        <select bind:value={targetKind}>
          <option value="button">Button</option>
          <option value="fader">Fader</option>
        </select>
      </label>
    </div>
    <div class="row">
      <label>Executor <input type="number" min="1" bind:value={executor} /></label>
      {#if targetKind === 'button'}
        <label>Button <input type="number" min="1" max="3" bind:value={button} /></label>
      {/if}
    </div>
    {#if multi}
      <label>Schrittweite <input type="number" min="1" bind:value={step} /></label>
      <p class="preview">Vorschau: {preview}</p>
    {/if}
    {#if showAcceleration}
      <label class="check">
        <input type="checkbox" bind:checked={accelerated} />
        Beschleunigt
      </label>
    {/if}
  {/if}

  {#if error}
    <p class="error" role="alert">{error}</p>
  {/if}

  <div class="actions">
    <button type="button" onclick={onClose}>Abbrechen</button>
    <button type="submit" disabled={saving}>{saving ? 'Speichere …' : 'Speichern'}</button>
  </div>
</form>

<style>
  .assign {
    display: grid;
    gap: 0.6rem;
    max-width: 26rem;
    padding: 0.8rem;
    background: #1f242b;
    border: 1px solid #39424e;
    border-radius: 0.5rem;
  }

  h3 {
    margin: 0;
    font-size: 0.95rem;
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
  .error {
    margin: 0;
    font-size: 0.75rem;
  }

  .error {
    color: #ff9b8f;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  input,
  select {
    padding: 0.3rem;
    background: #12161b;
    border: 1px solid #39424e;
    border-radius: 0.25rem;
    color: inherit;
  }
</style>

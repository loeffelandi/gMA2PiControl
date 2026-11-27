<script lang="ts">
  import { untrack } from 'svelte';

  import {
    AssignmentError,
    bankOffset,
    keyAction,
    rawGlobalExecutor,
    screenEncoderFor,
    type Assignment,
    type PlaybackTransport,
    type Scope,
  } from './assignment';
  import ConflictNotice from './ConflictNotice.svelte';
  import type { ConfigStore } from './configStore.svelte';
  import { SaveError, sourceText as formatSource } from './configStore.svelte';
  import type { ControlInfo } from './deviceControls';

  type ActionKind =
    | 'hardkey'
    | 'command'
    | 'screen_mode'
    | 'screen'
    | 'encoder_press'
    | 'executor'
    | 'encoder'
    | 'modifier';

  type ScopeChoice = 'global' | 'bank';

  interface FormValues {
    action: ActionKind;
    hardkey: string;
    command: string;
    screenNumber: number;
    pressSlot: number;
    page: string;
    executor: number;
    targetKind: 'button' | 'fader';
    button: number;
    accelerated: boolean;
    transport: PlaybackTransport | '';
    encoderMode: 'slot' | 'attribute';
    slot: number;
    attribute: string;
    encoderScreen: number;
    modifierMode: 'hardkey' | 'local';
    modifierHardkey: string;
    step: number;
    scope: ScopeChoice;
  }

  interface Props {
    store: ConfigStore;
    /** One control, or several in click order for a stepped multi assignment. */
    controls: ControlInfo[];
    onClose: () => void;
    /** Called after a successful save or removal, before `onClose`. */
    onDone?: () => void;
  }

  let { store, controls, onClose, onDone }: Props = $props();

  const primary = $derived(controls[0]);
  const multi = $derived(controls.length > 1);

  function defaultAction(control: ControlInfo): ActionKind {
    return control.kind === 'relative-encoder' ? 'encoder' : 'executor';
  }

  function defaultTargetKind(control: ControlInfo): 'button' | 'fader' {
    return control.kind === 'fader' || control.kind === 'poti' || control.kind === 'encoder'
      ? 'fader'
      : 'button';
  }

  function initialForm(): FormValues {
    const control = controls[0];
    const resolved = store.resolve(control);
    const assignment = resolved.assignment;
    const scopeNow = store.editScope(control);
    const form: FormValues = {
      action: defaultAction(control),
      hardkey: 'GOTO',
      command: '',
      screenNumber: 1,
      pressSlot: 1,
      page: 'current',
      executor: 1,
      targetKind: defaultTargetKind(control),
      button: 1,
      accelerated: false,
      transport: '',
      encoderMode: 'slot',
      slot: 1,
      attribute: '',
      encoderScreen: 0,
      modifierMode: 'hardkey',
      modifierHardkey: '',
      step: 1,
      scope: scopeNow.kind === 'bank' ? 'bank' : 'global',
    };
    switch (assignment.kind) {
      case 'key': {
        const action = keyAction(assignment);
        form.action = action;
        if (action === 'hardkey') form.hardkey = assignment.hardkey ?? 'GOTO';
        if (action === 'command') form.command = assignment.command ?? '';
        if (action === 'screen') form.screenNumber = Number(assignment.screen ?? 1);
        if (action === 'encoder_press') form.pressSlot = Number(assignment.encoderPress ?? 1);
        break;
      }
      case 'playback':
        form.action = 'executor';
        form.page = String(assignment.page);
        form.executor = assignment.executor;
        form.targetKind = assignment.target;
        form.button = assignment.button ?? 1;
        form.accelerated = assignment.accelerated === true;
        form.transport = assignment.transport ?? '';
        break;
      case 'encoder':
        form.action = 'encoder';
        form.encoderMode = assignment.attribute ? 'attribute' : 'slot';
        form.slot = Number(assignment.slot ?? 1);
        form.attribute = assignment.attribute ?? '';
        form.encoderScreen = Number(assignment.screenEncoder ?? 0);
        break;
      case 'modifier':
        form.action = 'modifier';
        form.modifierMode = assignment.local ? 'local' : 'hardkey';
        form.modifierHardkey = assignment.hardkey ?? '';
        break;
      default:
        break;
    }
    return form;
  }

  let form = $state<FormValues>(untrack(() => initialForm()));

  let saving = $state(false);
  let error = $state<string | null>(null);
  let errorField = $state<string | null>(null);

  const device = $derived(store.device);
  const bank = $derived(store.bank);
  const resolved = $derived(store.resolve(primary));
  const hasPlayback = $derived(form.action === 'executor');
  const isModifier = $derived(form.action === 'modifier');
  // A modifier has no bank layer, so it is always written globally.
  const scopeChoice = $derived<ScopeChoice>(isModifier ? 'global' : form.scope);
  const scope = $derived<Scope>(
    scopeChoice === 'bank' && device
      ? { kind: 'bank', device: device.name, bank }
      : { kind: 'global' },
  );
  const offset = $derived(
    device ? bankOffset(store.config, device.name, bank, device.bank_size ?? 1) : 0,
  );
  const globalOffset = $derived(scopeChoice === 'global' ? offset : 0);
  const transport = $derived<PlaybackTransport | ''>(
    form.targetKind === 'fader' && form.transport === 'midi' ? '' : form.transport,
  );
  const defaultTransport = $derived(
    form.targetKind === 'button' && store.midiRemoteEnabled ? 'MIDI' : 'Web',
  );
  const showAcceleration = $derived(
    hasPlayback && form.targetKind === 'fader' && primary.kind === 'encoder',
  );
  const showScreenEncoder = $derived(
    form.action === 'encoder' &&
      form.encoderMode === 'slot' &&
      form.slot >= 1 &&
      form.slot <= 4 &&
      scopeChoice === 'global',
  );
  const preview = $derived(
    multi
      ? controls.map((_, index) => Number(form.executor) + index * Number(form.step)).join(', ')
      : String(form.executor),
  );
  const rawExecutor = $derived.by(() => {
    try {
      return rawGlobalExecutor(Number(form.executor), globalOffset);
    } catch {
      return null;
    }
  });
  const sourceLine = $derived(
    resolved.assignment.kind === 'none'
      ? 'Noch nicht belegt'
      : formatSource(resolved),
  );
  const inheritedOffset = $derived(resolved.source === 'inherited-offset');
  const layerWillBeReplaced = $derived(
    scopeChoice === 'global' &&
      !isModifier &&
      controls.some((control) => store.removable(control, viewBankScope)),
  );
  const viewBankScope = $derived<Scope>(
    device ? { kind: 'bank', device: device.name, bank } : { kind: 'global' },
  );
  const removable = $derived(controls.some((control) => store.removable(control, scope)));
  const actions = $derived.by<{ value: ActionKind; label: string }[]>(() => {
    const out: { value: ActionKind; label: string }[] = [];
    const valueControl =
      primary.kind === 'fader' || primary.kind === 'poti' || primary.kind === 'encoder';
    if (!valueControl) {
      out.push(
        { value: 'hardkey', label: 'Hardkey' },
        { value: 'command', label: 'Command' },
      );
    }
    out.push({ value: 'executor', label: 'Executor' });
    if (primary.kind === 'relative-encoder') {
      out.push({ value: 'encoder', label: 'Attribut-Encoder' });
    }
    if (!valueControl) {
      out.push(
        { value: 'screen_mode', label: 'Screen-Modus umschalten' },
        { value: 'screen', label: 'Screen wählen' },
        { value: 'encoder_press', label: 'Encoder-Klick' },
        { value: 'modifier', label: 'Modifier' },
      );
    }
    return out;
  });

  function setSlot(next: number): void {
    form.slot = next;
    const mapped =
      next >= 1 && next <= 4 ? Number(screenEncoderFor(store.config, next) ?? 0) : 0;
    form.encoderScreen = Number.isInteger(mapped) ? mapped : 0;
  }

  function openModal(node: HTMLDialogElement) {
    if (typeof node.showModal === 'function') {
      if (!node.open) node.showModal();
    } else {
      node.setAttribute('open', '');
    }
  }

  /** Map a config path or model field to the input it belongs to. */
  function inputFor(field: string): string | null {
    if (field.includes('screen_encoders')) return 'encoderScreen';
    const last = field.split('.').pop() ?? field;
    switch (last) {
      case 'executor':
      case 'page':
      case 'button':
      case 'transport':
      case 'hardkey':
      case 'command':
      case 'attribute':
      case 'encoder_press':
        return last === 'hardkey' && form.action === 'modifier' ? 'modifierHardkey' : last;
      case 'screen':
        return form.action === 'encoder' ? 'encoderScreen' : 'screen';
      case 'slot':
        return 'slot';
      default:
        return null;
    }
  }

  function showError(cause: unknown, fallback: string): void {
    if (cause instanceof SaveError && cause.stale) {
      // The conflict notice explains it and offers reload or discard.
      error = null;
      errorField = null;
    } else if (cause instanceof SaveError || cause instanceof AssignmentError) {
      error = cause.message || fallback;
      errorField = cause.field ? inputFor(cause.field) : null;
    } else if (cause instanceof Error) {
      error = cause.message || fallback;
      errorField = null;
    } else {
      error = fallback;
      errorField = null;
    }
  }

  function buildAssignment(index: number): Assignment {
    switch (form.action) {
      case 'hardkey':
        return { kind: 'key', hardkey: form.hardkey.trim() };
      case 'command':
        return { kind: 'key', command: form.command.trim() };
      case 'screen_mode':
        return { kind: 'key', screenMode: true };
      case 'screen':
        return { kind: 'key', screen: Number(form.screenNumber) };
      case 'encoder_press':
        return { kind: 'key', encoderPress: Number(form.pressSlot) };
      case 'modifier':
        return form.modifierMode === 'local'
          ? { kind: 'modifier', local: true }
          : { kind: 'modifier', hardkey: form.modifierHardkey.trim() };
      case 'encoder': {
        const attribute = form.attribute.trim();
        return form.encoderMode === 'attribute'
          ? { kind: 'encoder', attribute }
          : {
              kind: 'encoder',
              slot: Number(form.slot),
              screenEncoder: showScreenEncoder ? Number(form.encoderScreen) : null,
            };
      }
      default: {
        const trimmedPage = form.page.trim();
        const pageNumber = Number(trimmedPage);
        const effective = Number(form.executor) + index * Number(form.step);
        const executor = scopeChoice === 'global' ? rawGlobalExecutor(effective, globalOffset) : effective;
        return {
          kind: 'playback',
          page: trimmedPage === 'current' ? 'current' : pageNumber,
          executor,
          target: form.targetKind,
          button: Number(form.button),
          accelerated: form.accelerated,
          transport: transport === '' ? null : transport,
        };
      }
    }
  }

  async function submit(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (multi && form.action === 'encoder') return;
    error = null;
    errorField = null;
    if (multi && hasPlayback && (!Number.isInteger(Number(form.step)) || Number(form.step) < 1)) {
      error = 'Schrittweite muss eine ganze Zahl ab 1 sein.';
      errorField = 'step';
      return;
    }
    saving = true;
    try {
      await store.assign(controls, scope, (_control, index) => buildAssignment(index));
      onDone?.();
      onClose();
    } catch (cause) {
      showError(cause, 'Speichern fehlgeschlagen');
    } finally {
      saving = false;
    }
  }

  async function remove(): Promise<void> {
    saving = true;
    error = null;
    errorField = null;
    try {
      await store.remove(controls, scope);
      onDone?.();
      onClose();
    } catch (cause) {
      showError(cause, 'Entfernen fehlgeschlagen');
    } finally {
      saving = false;
    }
  }

  function handleCancel(event: Event): void {
    event.preventDefault();
    if (!saving) onClose();
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && !saving) {
      event.preventDefault();
      onClose();
    }
  }
</script>

{#snippet fieldMessage(name: string)}
  {#if error && errorField === name}
    <p class="error field-error" role="alert" data-field={name}>{error}</p>
  {/if}
{/snippet}

<dialog
  class="assign-dialog"
  {@attach openModal}
  oncancel={handleCancel}
  onkeydown={handleKeydown}
>
  <form class="assign" onsubmit={submit}>
    <h3>
      {multi ? `${controls.length} Controls` : primary.id} · Bank {bank}
    </h3>

    {#if resolved.assignment.kind !== 'none'}
      <p class="source" data-testid="assignment-source">Aktuell: {sourceLine}</p>
    {/if}

    <label>
      Aktion
      <select bind:value={form.action}>
        {#each actions as entry (entry.value)}
          <option value={entry.value}>{entry.label}</option>
        {/each}
      </select>
    </label>

    {#if device}
      <label>
        Geltungsbereich
        <select bind:value={form.scope} disabled={isModifier}>
          <option value="global">Global (alle Bänke)</option>
          <option value="bank">Nur Bank {bank} (Override)</option>
        </select>
      </label>
      {#if isModifier}
        <p class="hint">Modifier gelten immer global.</p>
      {:else if scopeChoice === 'global' && resolved.source !== 'explicit-layer' && resolved.assignment.kind !== 'none'}
        <p class="inherited-hint">
          Die Änderung gilt für alle Bänke ohne eigenen Eintrag; „Nur Bank {bank}“ legt einen
          bewussten Override an.
        </p>
      {:else if scopeChoice === 'bank' && hasPlayback && inheritedOffset}
        <p class="inherited-hint">
          Ein expliziter Bank-Eintrag folgt nicht mehr dem Bank-Offset.
        </p>
      {/if}
      {#if layerWillBeReplaced}
        <p class="inherited-hint">Der vorhandene Eintrag von Bank {bank} wird ersetzt.</p>
      {/if}
    {/if}

    {#if form.action === 'encoder'}
      <label>
        Ziel
        <select bind:value={form.encoderMode}>
          <option value="slot">Attribut-Slot</option>
          <option value="attribute">Attributname</option>
        </select>
      </label>
      <div class="row">
        {#if form.encoderMode === 'slot'}
          <label>
            Slot
            <input
              type="number"
              min="1"
              max="8"
              value={form.slot}
              oninput={(event) => setSlot(Number(event.currentTarget.value))}
            />
          </label>
          {#if showScreenEncoder}
            <label>
              Screen-Encoder <span class="muted">(MA/Bank)</span>
              <select bind:value={form.encoderScreen}>
                <option value={0}>— keiner —</option>
                {#each [5, 6, 7, 8, 9, 10] as number (number)}
                  <option value={number}>Screen-Encoder {number}</option>
                {/each}
              </select>
            </label>
          {/if}
        {:else}
          <label>
            Attributname
            <input bind:value={form.attribute} placeholder="z. B. Dimmer" />
          </label>
        {/if}
      </div>
      {@render fieldMessage('slot')}
      {@render fieldMessage('attribute')}
      {@render fieldMessage('encoderScreen')}
      <p class="muted">
        Ohne MA/Bank wirkt der Encoder auf das Attribut, mit MA oder Bank auf den
        Screen-Encoder.
      </p>
      {#if multi}
        <p class="error">Encoder-Ziele nur für ein einzelnes Control.</p>
      {/if}
    {:else if form.action === 'screen_mode'}
      <p class="muted">Die Taste schaltet zwischen Attribut- und Screen-Encodern um.</p>
    {:else if form.action === 'screen'}
      <label>
        Screen
        <input type="number" min="1" max="6" bind:value={form.screenNumber} />
      </label>
      {@render fieldMessage('screen')}
    {:else if form.action === 'encoder_press'}
      <label>
        Encoder-Slot
        <input type="number" min="1" max="8" bind:value={form.pressSlot} />
      </label>
      {@render fieldMessage('encoder_press')}
    {:else if form.action === 'hardkey'}
      <label>
        Hardkey
        <input bind:value={form.hardkey} />
      </label>
      {@render fieldMessage('hardkey')}
    {:else if form.action === 'command'}
      <label>
        Command
        <input bind:value={form.command} />
      </label>
      {@render fieldMessage('command')}
    {:else if form.action === 'modifier'}
      <label>
        Modifier-Art
        <select bind:value={form.modifierMode}>
          <option value="hardkey">Hardkey</option>
          <option value="local">Lokal (nur Web-Remote)</option>
        </select>
      </label>
      {#if form.modifierMode === 'hardkey'}
        <label>
          Hardkey
          <input bind:value={form.modifierHardkey} />
        </label>
        {@render fieldMessage('modifierHardkey')}
      {/if}
    {:else}
      <div class="row">
        <label>
          Page
          <input bind:value={form.page} />
        </label>
        <label>
          Art
          <select bind:value={form.targetKind}>
            <option value="button">Button</option>
            <option value="fader">Fader</option>
          </select>
        </label>
      </div>
      {@render fieldMessage('page')}
      <div class="row">
        <label>
          Executor
          <input type="number" min="1" bind:value={form.executor} />
        </label>
        {#if form.targetKind === 'button'}
          <label>
            Button
            <input type="number" min="1" max="3" bind:value={form.button} />
          </label>
        {/if}
      </div>
      {@render fieldMessage('executor')}
      {@render fieldMessage('button')}
      {#if scopeChoice === 'global' && globalOffset > 0}
        <p class="hint" data-testid="raw-executor">
          Global gespeichert als Executor {rawExecutor ?? '?'} (Bank-Offset {globalOffset}).
        </p>
      {/if}
      <label>
        Transport
        <select
          bind:value={
            () => transport,
            (value) => (form.transport = value)
          }
        >
          <option value="">Standard ({defaultTransport})</option>
          {#if form.targetKind === 'button'}
            <option value="midi" disabled={!store.midiRemoteEnabled}>
              {store.midiRemoteEnabled ? 'MIDI-Remote' : 'MIDI-Remote (nicht aktiviert)'}
            </option>
          {/if}
          <option value="web">Web Remote</option>
        </select>
      </label>
      {@render fieldMessage('transport')}
      {#if multi}
        <label>
          Schrittweite
          <input type="number" min="1" bind:value={form.step} />
        </label>
        {@render fieldMessage('step')}
        <p class="preview">Vorschau: {preview}</p>
      {/if}
      {#if showAcceleration}
        <label class="check">
          <input type="checkbox" bind:checked={form.accelerated} />
          Beschleunigt
        </label>
      {/if}
    {/if}

    {#if error && errorField === null}
      <p class="error" role="alert">{error}</p>
    {/if}

    <!-- "Verwerfen" drops the draft, i.e. closes the dialog. -->
    <ConflictNotice {store} onDiscard={onClose} />

    <div class="actions">
      {#if removable}
        <button type="button" class="danger" disabled={saving} onclick={remove}>
          Belegung entfernen
        </button>
      {/if}
      <button type="button" disabled={saving} onclick={onClose}>Abbrechen</button>
      <button type="submit" disabled={saving || (multi && form.action === 'encoder')}>
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
  .hint,
  .source,
  .error {
    margin: 0;
    font-size: 0.75rem;
  }

  .source,
  .hint {
    color: var(--text-muted);
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

/**
 * Shared assignment model of the mapping and device tabs.
 *
 * Pure and framework free: the resolver mirrors the runtime resolution of
 * `ma2pi/playback_targets.py`, `ma2pi/playback.py` and `ma2pi/mapping.py`, and
 * the patch builders produce the RFC 7386 merge patches `PUT /api/config`
 * expects.  Both tabs use these functions, so the same action on the same
 * control and scope yields exactly the same configuration.
 *
 * The resolver reports the *configured* target.  Executor topology (wide
 * executors, `resolve-combined-executors`) is a runtime concern and is not
 * modelled here.
 */

export type AnyConfig = Record<string, any>;
export type Patch = Record<string, any>;

export type Scope =
  | { kind: 'global' }
  | { kind: 'bank'; device: string; bank: number };

export type AssignmentSource =
  | 'explicit-layer'
  | 'explicit-global'
  | 'inherited-global'
  | 'inherited-offset'
  | 'default';

export type PlaybackTransport = 'midi' | 'web';
export type KeyAction = 'hardkey' | 'command' | 'screen_mode' | 'screen' | 'encoder_press';

export interface KeyAssignment {
  kind: 'key';
  hardkey?: string | null;
  command?: string | null;
  screenMode?: boolean;
  screen?: number | null;
  encoderPress?: number | null;
}

export interface PlaybackAssignment {
  kind: 'playback';
  page: number | 'current';
  executor: number;
  target: 'button' | 'fader';
  button?: number;
  accelerated?: boolean;
  transport?: PlaybackTransport | null;
}

export interface EncoderAssignment {
  kind: 'encoder';
  slot?: number | null;
  attribute?: string | null;
  screenEncoder?: number | null;
}

export interface ModifierAssignment {
  kind: 'modifier';
  hardkey?: string | null;
  local?: boolean;
}

export type Assignment =
  | { kind: 'none' }
  | KeyAssignment
  | PlaybackAssignment
  | EncoderAssignment
  | ModifierAssignment;

/** The control an assignment applies to, with the device facts the resolver needs. */
export interface ControlRef {
  device: string;
  control: string;
  /** Inventory kind (`button`, `fader`, `poti`, `encoder`, `relative-encoder`). */
  kind?: string;
  /** Encoder id of a relative encoder, `null` for every other control. */
  encoderId?: number | null;
  /** Executor offset between two banks (`DeviceEntry.bank_size`). */
  bankSize: number;
}

export type ConflictParticipant = 'layer-key' | 'playback' | 'modifier' | 'key';

export interface Conflict {
  winner: ConflictParticipant;
  shadowed: ConflictParticipant[];
}

export interface Resolved<T extends Assignment> {
  assignment: T;
  source: AssignmentSource;
}

export interface ResolvedPlayback extends Resolved<PlaybackAssignment> {
  /** Bank offset already added to `assignment.executor` (0 when none applies). */
  offset: number;
}

export interface ResolvedAssignment {
  assignment: Assignment;
  source: AssignmentSource;
  offset: number;
  layers: {
    key: Resolved<KeyAssignment> | null;
    playback: ResolvedPlayback | null;
    encoder: Resolved<EncoderAssignment> | null;
    modifier: Resolved<ModifierAssignment> | null;
  };
  conflict: Conflict | null;
}

export class AssignmentError extends Error {
  readonly field: string;

  constructor(field: string, message: string) {
    super(message);
    this.name = 'AssignmentError';
    this.field = field;
  }
}

const VALUE_KINDS = new Set(['fader', 'poti', 'encoder', 'relative-encoder']);

// ---------------------------------------------------------------------------
// Config accessors

function mappingOf(config: AnyConfig | null | undefined): AnyConfig {
  return (config?.mapping ?? {}) as AnyConfig;
}

export function deviceBankSettings(config: AnyConfig | null | undefined, device: string): AnyConfig | null {
  return (mappingOf(config).device_banks?.[device] as AnyConfig | undefined) ?? null;
}

export function layerOf(
  config: AnyConfig | null | undefined,
  device: string,
  bank: number,
): AnyConfig | null {
  const settings = deviceBankSettings(config, device);
  if (!settings) return null;
  return (
    settings[String(bank)] ??
    settings[bank] ??
    settings.banks?.[String(bank)] ??
    settings.banks?.[bank] ??
    null
  );
}

function normalizeEncoder(entry: unknown, fallbackId?: number): AnyConfig | null {
  if (!entry || typeof entry !== 'object') return null;
  const raw = entry as AnyConfig;
  const id = raw.id !== undefined ? Number(raw.id) : fallbackId;
  if (id === undefined || !Number.isInteger(id)) return null;
  if (raw.attribute !== undefined && raw.attribute !== null && raw.attribute !== '') {
    return { id, attribute: String(raw.attribute) };
  }
  if (raw.slot !== undefined && raw.slot !== null) {
    return { id, slot: Number(raw.slot) };
  }
  return null;
}

function normalizeEncoderList(raw: unknown): AnyConfig[] {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw
      .map((entry) => normalizeEncoder(entry))
      .filter((entry): entry is AnyConfig => entry !== null);
  }
  if (typeof raw === 'object') {
    return Object.entries(raw as Record<string, unknown>)
      .map(([key, entry]) => normalizeEncoder(entry, Number(key)))
      .filter((entry): entry is AnyConfig => entry !== null);
  }
  return [];
}

export function globalEncoders(config: AnyConfig | null | undefined): AnyConfig[] {
  return normalizeEncoderList(mappingOf(config).encoders);
}

export function layerEncoders(
  config: AnyConfig | null | undefined,
  device: string,
  bank: number,
): AnyConfig[] {
  return normalizeEncoderList(layerOf(config, device, bank)?.encoders);
}

export function screenEncoderFor(
  config: AnyConfig | null | undefined,
  slot: number,
): number | null {
  const screens = (mappingOf(config).screen_encoders ?? {}) as AnyConfig;
  const value = screens[String(slot)] ?? screens[slot];
  return value === undefined || value === null ? null : Number(value);
}

/**
 * Encoder id of a relative encoder, from the inventory first, then the profile
 * and finally the free `encoder.N` naming.
 */
export function encoderIdForControl(
  control: string,
  inventory: { id: string; kind: string; encoder_id?: number }[] = [],
  profileControls: AnyConfig[] = [],
): number | null {
  const valid = (value: unknown): value is number =>
    typeof value === 'number' && Number.isInteger(value) && value >= 1;
  const inv = inventory.find((item) => item.id === control);
  if (inv?.kind === 'relative-encoder' && valid(inv.encoder_id)) return inv.encoder_id;
  const prof = profileControls.find((item) => item?.id === control);
  if (prof?.kind === 'relative-encoder' && valid(prof.encoder_id)) return prof.encoder_id;
  if (control.startsWith('encoder.')) {
    const parsed = Number(control.slice('encoder.'.length));
    if (Number.isInteger(parsed) && parsed >= 1) return parsed;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Bank offset

/** Executor offset of ``bank``, mirroring `playback_targets.resolve_target`. */
export function bankOffset(
  config: AnyConfig | null | undefined,
  device: string,
  bank: number,
  bankSize: number,
): number {
  if (bank <= 1) return 0;
  if (!deviceBankSettings(config, device)) return 0;
  const maPage = layerOf(config, device, bank)?.ma_page;
  if (maPage !== undefined && maPage !== null) return 0;
  return (bank - 1) * bankSize;
}

/**
 * Executor value to store in the global layer for an effective executor shown in
 * a bank with ``offset``.  Throws when the global value would drop below 1.
 */
export function rawGlobalExecutor(effective: number, offset: number): number {
  const raw = effective - offset;
  if (!Number.isInteger(raw) || raw < 1) {
    throw new AssignmentError(
      'executor',
      `Für globale Speicherung muss Executor mindestens ${offset + 1} sein.`,
    );
  }
  return raw;
}

/** Effective transport as the daemon derives it (`config.effective_transport`). */
export function effectiveTransport(
  kind: string,
  transport: PlaybackTransport | null | undefined,
  midiRemoteEnabled: boolean,
): PlaybackTransport {
  if (transport) return transport;
  if (kind === 'button' && midiRemoteEnabled) return 'midi';
  return 'web';
}

// ---------------------------------------------------------------------------
// Raw <-> model conversion

export function keyFromRaw(raw: AnyConfig): KeyAssignment {
  if (raw.screen_mode) return { kind: 'key', screenMode: true };
  if (raw.screen !== undefined && raw.screen !== null) {
    return { kind: 'key', screen: Number(raw.screen) };
  }
  if (raw.encoder_press !== undefined && raw.encoder_press !== null) {
    return { kind: 'key', encoderPress: Number(raw.encoder_press) };
  }
  if (raw.command) return { kind: 'key', command: String(raw.command) };
  return { kind: 'key', hardkey: raw.hardkey ? String(raw.hardkey) : null };
}

export function keyAction(key: KeyAssignment): KeyAction {
  if (key.screenMode) return 'screen_mode';
  if (key.screen !== undefined && key.screen !== null) return 'screen';
  if (key.encoderPress !== undefined && key.encoderPress !== null) return 'encoder_press';
  if (key.command !== undefined && key.command !== null) return 'command';
  return 'hardkey';
}

function keyEntry(key: KeyAssignment): AnyConfig {
  const entry: AnyConfig = {
    hardkey: null,
    command: null,
    screen_mode: null,
    encoder_press: null,
    screen: null,
  };
  switch (keyAction(key)) {
    case 'screen_mode':
      entry.screen_mode = true;
      break;
    case 'screen':
      entry.screen = Number(key.screen);
      break;
    case 'encoder_press':
      entry.encoder_press = Number(key.encoderPress);
      break;
    case 'command':
      entry.command = key.command;
      break;
    default:
      entry.hardkey = key.hardkey;
  }
  return entry;
}

function transportOf(value: unknown): PlaybackTransport | null {
  return value === 'midi' || value === 'web' ? value : null;
}

// ---------------------------------------------------------------------------
// Resolver

function resolveKey(
  config: AnyConfig,
  scope: Scope,
  ref: ControlRef,
): Resolved<KeyAssignment> | null {
  const mapping = mappingOf(config);
  if (scope.kind === 'bank') {
    const layerKey = layerOf(config, scope.device, scope.bank)?.keys?.[ref.control];
    if (layerKey) {
      return { assignment: keyFromRaw(layerKey), source: 'explicit-layer' };
    }
  }
  const globalKey = mapping.keys?.[ref.control];
  if (!globalKey || Object.keys(globalKey).length === 0) return null;
  return {
    assignment: keyFromRaw(globalKey),
    source: scope.kind === 'global' ? 'explicit-global' : 'inherited-global',
  };
}

function resolvePlayback(
  config: AnyConfig,
  scope: Scope,
  ref: ControlRef,
): ResolvedPlayback | null {
  const mapping = mappingOf(config);
  const base = (mapping.playbacks?.[ref.control] as AnyConfig | undefined) ?? null;
  const override =
    scope.kind === 'bank'
      ? ((layerOf(config, scope.device, scope.bank)?.playbacks?.[ref.control] as
          | AnyConfig
          | undefined) ?? null)
      : null;
  if (!base && !override) return null;

  const pick = (name: string): any =>
    override && override[name] !== undefined && override[name] !== null
      ? override[name]
      : base
        ? base[name]
        : undefined;

  const page = pick('page');
  const executor = pick('executor');
  if (page === undefined || page === null || executor === undefined || executor === null) {
    return null;
  }
  const overridesExecutor =
    override !== null && override.executor !== undefined && override.executor !== null;
  const offset =
    scope.kind === 'bank' && !overridesExecutor
      ? bankOffset(config, scope.device, scope.bank, ref.bankSize)
      : 0;
  const target = pick('kind') === 'fader' ? 'fader' : 'button';
  const assignment: PlaybackAssignment = {
    kind: 'playback',
    page: page === 'current' ? 'current' : Number(page),
    executor: Number(executor) + offset,
    target,
    button: Number(pick('button') ?? 1),
    accelerated: pick('accelerated') === true,
    transport: transportOf(pick('transport')),
  };
  let source: AssignmentSource;
  if (scope.kind === 'global') source = 'explicit-global';
  else if (overridesExecutor) source = 'explicit-layer';
  else if (offset !== 0) source = 'inherited-offset';
  else source = 'inherited-global';
  return { assignment, source, offset };
}

function resolveEncoder(
  config: AnyConfig,
  scope: Scope,
  ref: ControlRef,
): Resolved<EncoderAssignment> | null {
  const id = ref.encoderId;
  if (id === null || id === undefined) return null;
  const toAssignment = (entry: AnyConfig): EncoderAssignment => ({
    kind: 'encoder',
    slot: entry.slot ?? null,
    attribute: entry.attribute ?? null,
    screenEncoder: entry.slot != null ? screenEncoderFor(config, Number(entry.slot)) : null,
  });
  if (scope.kind === 'bank') {
    const hit = layerEncoders(config, scope.device, scope.bank).find((entry) => entry.id === id);
    if (hit) return { assignment: toAssignment(hit), source: 'explicit-layer' };
  }
  const hit = globalEncoders(config).find((entry) => entry.id === id);
  if (!hit) return null;
  return {
    assignment: toAssignment(hit),
    source: scope.kind === 'global' ? 'explicit-global' : 'inherited-global',
  };
}

function resolveModifier(
  config: AnyConfig,
  scope: Scope,
  ref: ControlRef,
): Resolved<ModifierAssignment> | null {
  const raw = mappingOf(config).modifiers?.[ref.control] as AnyConfig | undefined;
  if (!raw) return null;
  const assignment: ModifierAssignment = raw.local
    ? { kind: 'modifier', local: true }
    : { kind: 'modifier', hardkey: raw.hardkey ? String(raw.hardkey) : null };
  return {
    assignment,
    source: scope.kind === 'global' ? 'explicit-global' : 'inherited-global',
  };
}

/**
 * Resolve every layer of a control and pick the one the daemon acts on.
 *
 * Key events: an explicit layer key skips the playback router and goes to the
 * engine, where a modifier beats any key; otherwise a playback target beats the
 * global key and the modifier.  Value events (faders, encoders) know no layer
 * key, so no conflict is reported for them.
 */
export function resolveAssignment(
  config: AnyConfig | null | undefined,
  scope: Scope,
  ref: ControlRef,
): ResolvedAssignment {
  const safe = config ?? {};
  const key = resolveKey(safe, scope, ref);
  const playback = resolvePlayback(safe, scope, ref);
  const encoder = resolveEncoder(safe, scope, ref);
  const modifier = resolveModifier(safe, scope, ref);
  const layers = { key, playback, encoder, modifier };
  const valueControl = ref.kind !== undefined && VALUE_KINDS.has(ref.kind);

  let winner: ConflictParticipant | null = null;
  const shadowed: ConflictParticipant[] = [];
  if (valueControl) {
    // Value events: playback target first, then the encoder mapping.
  } else {
    const layerKey = key?.source === 'explicit-layer';
    if (layerKey) {
      if (modifier) {
        winner = 'modifier';
        shadowed.push('layer-key');
      } else {
        winner = 'layer-key';
      }
      if (playback) shadowed.push('playback');
    } else if (playback) {
      winner = 'playback';
      if (modifier) shadowed.push('modifier');
      if (key) shadowed.push('key');
    } else if (modifier) {
      winner = 'modifier';
      if (key) shadowed.push('key');
    } else if (key) {
      winner = 'key';
    }
  }
  const conflict = winner !== null && shadowed.length > 0 ? { winner, shadowed } : null;

  let picked: { assignment: Assignment; source: AssignmentSource; offset: number } | null = null;
  const pickPlayback = () =>
    playback ? { assignment: playback.assignment, source: playback.source, offset: playback.offset } : null;
  const pickKey = () => (key ? { ...key, offset: 0 } : null);
  const pickModifier = () => (modifier ? { ...modifier, offset: 0 } : null);
  const pickEncoder = () => (encoder ? { ...encoder, offset: 0 } : null);
  if (valueControl) {
    picked = pickPlayback() ?? pickEncoder() ?? pickKey() ?? pickModifier();
  } else if (winner === 'layer-key' || winner === 'key') {
    picked = pickKey();
  } else if (winner === 'playback') {
    picked = pickPlayback();
  } else if (winner === 'modifier') {
    picked = pickModifier();
  }
  picked ??= pickEncoder();
  return {
    assignment: picked?.assignment ?? { kind: 'none' },
    source: picked?.source ?? 'default',
    offset: picked?.offset ?? 0,
    layers,
    conflict,
  };
}

/** True when ``scope`` itself holds an explicit entry for the control. */
export function hasEntryIn(
  config: AnyConfig | null | undefined,
  scope: Scope,
  ref: ControlRef,
): boolean {
  const mapping = mappingOf(config);
  if (scope.kind === 'bank') {
    const layer = layerOf(config, scope.device, scope.bank);
    if (!layer) return false;
    if (ref.encoderId !== null && ref.encoderId !== undefined) {
      return layerEncoders(config, scope.device, scope.bank).some(
        (entry) => entry.id === ref.encoderId,
      );
    }
    return layer.keys?.[ref.control] !== undefined || layer.playbacks?.[ref.control] !== undefined;
  }
  if (ref.encoderId !== null && ref.encoderId !== undefined) {
    return globalEncoders(config).some((entry) => entry.id === ref.encoderId);
  }
  return (
    mapping.keys?.[ref.control] !== undefined ||
    mapping.playbacks?.[ref.control] !== undefined ||
    mapping.modifiers?.[ref.control] !== undefined
  );
}

/**
 * Scope a tab should edit by default for a bank view.  Bank 1 follows the
 * existing layer entry and otherwise the global layer; every other bank edits
 * its own layer.
 */
export function defaultScope(
  config: AnyConfig | null | undefined,
  device: string,
  bank: number,
  ref: ControlRef,
): Scope {
  const bankScope: Scope = { kind: 'bank', device, bank };
  if (bank >= 2) return bankScope;
  return hasEntryIn(config, bankScope, ref) ? bankScope : { kind: 'global' };
}

// ---------------------------------------------------------------------------
// Validation

export function validateAssignment(assignment: Assignment): AssignmentError | null {
  switch (assignment.kind) {
    case 'key': {
      const action = keyAction(assignment);
      if (action === 'hardkey' && !String(assignment.hardkey ?? '').trim()) {
        return new AssignmentError('hardkey', 'Bitte einen Hardkey angeben.');
      }
      if (action === 'command' && !String(assignment.command ?? '').trim()) {
        return new AssignmentError('command', 'Bitte ein Command angeben.');
      }
      if (action === 'screen') {
        const screen = Number(assignment.screen);
        if (!Number.isInteger(screen) || screen < 1) {
          return new AssignmentError('screen', 'Screen muss eine Zahl ab 1 sein.');
        }
      }
      if (action === 'encoder_press') {
        const slot = Number(assignment.encoderPress);
        if (!Number.isInteger(slot) || slot < 1 || slot > 4) {
          return new AssignmentError('encoder_press', 'Encoder-Slot muss zwischen 1 und 4 liegen.');
        }
      }
      return null;
    }
    case 'playback': {
      const page = assignment.page;
      if (page !== 'current' && (!Number.isInteger(page) || page < 1)) {
        return new AssignmentError('page', 'Page muss eine Zahl ab 1 oder "current" sein.');
      }
      if (!Number.isInteger(assignment.executor) || assignment.executor < 1) {
        return new AssignmentError('executor', 'Executor muss eine Zahl ab 1 sein.');
      }
      if (assignment.target === 'button') {
        const button = Number(assignment.button ?? 1);
        if (![1, 2, 3].includes(button)) {
          return new AssignmentError('button', 'Button muss 1, 2 oder 3 sein.');
        }
      }
      return null;
    }
    case 'encoder': {
      const attribute = String(assignment.attribute ?? '').trim();
      if (attribute) return null;
      const slot = Number(assignment.slot);
      if (!Number.isInteger(slot) || slot < 1) {
        return new AssignmentError('slot', 'Bitte Attributname oder Slot angeben.');
      }
      if (assignment.screenEncoder !== null && assignment.screenEncoder !== undefined) {
        const screen = Number(assignment.screenEncoder);
        if (screen !== 0 && (!Number.isInteger(screen) || screen < 5 || screen > 10)) {
          return new AssignmentError('screen', 'Screen-Encoder muss zwischen 5 und 10 liegen.');
        }
      }
      return null;
    }
    case 'modifier': {
      if (!assignment.local && !String(assignment.hardkey ?? '').trim()) {
        return new AssignmentError('hardkey', 'Bitte für den Modifier einen Hardkey angeben.');
      }
      return null;
    }
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Patch builders

function areaFor(patch: Patch, scope: Scope): AnyConfig {
  patch.mapping ??= {};
  if (scope.kind === 'global') return patch.mapping;
  return (((patch.mapping.device_banks ??= {})[scope.device] ??= {})[String(scope.bank)] ??= {});
}

/** Deep merge of merge patches: objects merge, arrays and scalars replace. */
export function mergePatches(...patches: Patch[]): Patch {
  const merge = (target: AnyConfig, source: AnyConfig): AnyConfig => {
    for (const [key, value] of Object.entries(source)) {
      const current = target[key];
      if (
        value !== null &&
        typeof value === 'object' &&
        !Array.isArray(value) &&
        current !== null &&
        typeof current === 'object' &&
        !Array.isArray(current)
      ) {
        merge(current, value);
      } else if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
        target[key] = merge({}, value);
      } else {
        target[key] = value;
      }
    }
    return target;
  };
  const out: Patch = {};
  for (const patch of patches) merge(out, patch);
  return out;
}

function sortedById(list: AnyConfig[]): AnyConfig[] {
  return [...list].sort((a, b) => a.id - b.id);
}

export interface AssignOptions {
  /**
   * A bank whose explicit entry for the control is replaced when the write goes
   * to the global layer.  The tabs pass the bank in view so the edit does not
   * stay hidden behind an override of that bank.
   */
  replaceOverrideIn?: { device: string; bank: number } | null;
}

function dropLayerEntries(
  config: AnyConfig,
  patch: Patch,
  ref: ControlRef,
  target: { device: string; bank: number },
): void {
  const bankScope: Scope = { kind: 'bank', device: target.device, bank: target.bank };
  const layer = layerOf(config, target.device, target.bank);
  if (!layer) return;
  const area = areaFor(patch, bankScope);
  if (ref.encoderId !== null && ref.encoderId !== undefined) {
    const list = layerEncoders(config, target.device, target.bank);
    if (list.some((entry) => entry.id === ref.encoderId)) {
      area.encoders = list.filter((entry) => entry.id !== ref.encoderId);
    }
    return;
  }
  if (layer.keys?.[ref.control] !== undefined) (area.keys ??= {})[ref.control] = null;
  if (layer.playbacks?.[ref.control] !== undefined) (area.playbacks ??= {})[ref.control] = null;
}

function playbackEntry(
  config: AnyConfig,
  scope: Scope,
  ref: ControlRef,
  playback: PlaybackAssignment,
): AnyConfig {
  const fader = playback.target === 'fader';
  let transport: PlaybackTransport | null = null;
  if (fader) {
    // A bank fader would inherit a global "midi", which faders reject.
    const inheritsMidi =
      scope.kind === 'bank' && mappingOf(config).playbacks?.[ref.control]?.transport === 'midi';
    transport = playback.transport === 'web' || inheritsMidi ? 'web' : null;
  } else {
    transport = playback.transport ?? null;
  }
  return {
    page: playback.page === 'current' ? 'current' : Number(playback.page),
    executor: Number(playback.executor),
    kind: playback.target,
    button: fader ? null : Number(playback.button ?? 1),
    accelerated:
      ref.kind === 'encoder' && fader ? Boolean(playback.accelerated) : null,
    transport,
  };
}

/**
 * Patch for assigning ``assignment`` to ``ref`` in ``scope``.
 *
 * Unused fields are written as explicit `null`, so switching the action never
 * leaves contradictory fields behind.  Encoder lists are replaced as a whole
 * because merge patches replace arrays.
 *
 * Throws `AssignmentError` for invalid values.
 */
export function buildAssignPatch(
  config: AnyConfig | null | undefined,
  scope: Scope,
  ref: ControlRef,
  assignment: Assignment,
  options: AssignOptions = {},
): Patch {
  const safe = config ?? {};
  if (assignment.kind === 'none') return buildDeletePatch(safe, scope, ref);
  const invalid = validateAssignment(assignment);
  if (invalid) throw invalid;

  const patch: Patch = {};
  const mapping = mappingOf(safe);

  if (assignment.kind === 'modifier') {
    patch.mapping = {
      modifiers: {
        [ref.control]: assignment.local
          ? { local: true, hardkey: null }
          : { hardkey: String(assignment.hardkey).trim(), local: null },
      },
      keys: { [ref.control]: null },
      playbacks: { [ref.control]: null },
    };
    return patch;
  }

  if (assignment.kind === 'encoder') {
    const id = ref.encoderId;
    if (id === null || id === undefined) {
      throw new AssignmentError('control', 'Control ist kein Attribut-Encoder.');
    }
    const attribute = String(assignment.attribute ?? '').trim();
    const slot = Number(assignment.slot);
    const target: AnyConfig = attribute ? { id, attribute } : { id, slot };
    if (scope.kind === 'bank') {
      const list = layerEncoders(safe, scope.device, scope.bank);
      areaFor(patch, scope).encoders = sortedById(
        list.filter((entry) => entry.id !== id).concat(target),
      );
      return patch;
    }
    const current = globalEncoders(safe);
    const previous = current.find((entry) => entry.id === id);
    const prevSlot =
      previous?.slot !== undefined && previous?.slot !== null ? Number(previous.slot) : null;
    const next = sortedById(current.filter((entry) => entry.id !== id).concat(target));
    patch.mapping = { encoders: next };
    if (options.replaceOverrideIn) {
      dropLayerEntries(safe, patch, ref, options.replaceOverrideIn);
    }
    const screenPatch: Record<string, number | null> = {};
    if (!attribute && slot >= 1 && slot <= 4) {
      const screen = Number(assignment.screenEncoder ?? 0);
      if (screen >= 5) {
        screenPatch[String(slot)] = screen;
      } else if (screenEncoderFor(safe, slot) !== null) {
        screenPatch[String(slot)] = null;
      }
    }
    if (
      prevSlot !== null &&
      prevSlot >= 1 &&
      prevSlot <= 4 &&
      (Boolean(attribute) || prevSlot !== slot) &&
      screenEncoderFor(safe, prevSlot) !== null &&
      !next.some((entry) => entry.slot === prevSlot)
    ) {
      screenPatch[String(prevSlot)] = null;
    }
    if (Object.keys(screenPatch).length > 0) patch.mapping.screen_encoders = screenPatch;
    return patch;
  }

  // Key and playback share the clean-up of the sibling layer: a key replaces a
  // playback target in the same layer and vice versa.
  const area = areaFor(patch, scope);
  area.keys = { [ref.control]: null };
  area.playbacks = { [ref.control]: null };
  if (scope.kind === 'global') {
    if (mapping.modifiers?.[ref.control] !== undefined) {
      (patch.mapping.modifiers ??= {})[ref.control] = null;
    }
    if (options.replaceOverrideIn) {
      dropLayerEntries(safe, patch, ref, options.replaceOverrideIn);
    }
  }
  if (assignment.kind === 'key') {
    area.keys[ref.control] = keyEntry(assignment);
  } else {
    area.playbacks[ref.control] = playbackEntry(safe, scope, ref, assignment);
  }
  return patch;
}

/** Patch removing the explicit entry of ``ref`` in ``scope``. */
export function buildDeletePatch(
  config: AnyConfig | null | undefined,
  scope: Scope,
  ref: ControlRef,
): Patch {
  const safe = config ?? {};
  const patch: Patch = {};
  const isEncoder = ref.encoderId !== null && ref.encoderId !== undefined;
  const area = areaFor(patch, scope);

  if (scope.kind === 'bank') {
    if (isEncoder) {
      area.encoders = layerEncoders(safe, scope.device, scope.bank).filter(
        (entry) => entry.id !== ref.encoderId,
      );
    } else {
      area.keys = { [ref.control]: null };
      area.playbacks = { [ref.control]: null };
    }
    return patch;
  }

  if (isEncoder) {
    const current = globalEncoders(safe);
    const removed = current.find((entry) => entry.id === ref.encoderId);
    const next = current.filter((entry) => entry.id !== ref.encoderId);
    area.encoders = next;
    const slot = removed?.slot;
    if (
      slot !== undefined &&
      slot !== null &&
      slot >= 1 &&
      slot <= 4 &&
      screenEncoderFor(safe, slot) !== null &&
      !next.some((entry) => entry.slot === slot)
    ) {
      area.screen_encoders = { [String(slot)]: null };
    }
    return patch;
  }

  area.keys = { [ref.control]: null };
  area.playbacks = { [ref.control]: null };
  if (mappingOf(safe).modifiers?.[ref.control] !== undefined) {
    area.modifiers = { [ref.control]: null };
  }
  return patch;
}

export interface BankSettingsInput {
  device: string;
  profile: string;
  bank: number;
  bankSize: number;
  channel: number;
  /** `null` removes the MA page binding of the bank. */
  maPage: number | null;
}

function bankNotesRecord(notes: unknown): Record<string, string> {
  if (!notes) return {};
  if (Array.isArray(notes)) {
    const out: Record<string, string> = {};
    for (const entry of notes) {
      if (entry && typeof entry === 'object' && 'note' in entry && 'control' in entry) {
        out[String((entry as AnyConfig).note)] = String((entry as AnyConfig).control);
      }
    }
    return out;
  }
  return notes as Record<string, string>;
}

/**
 * Patch for the bank settings of a device.  Profile banks are an array and
 * therefore sent in full; only the channel of ``bank`` changes.
 */
export function buildBankSettingsPatch(
  config: AnyConfig | null | undefined,
  input: BankSettingsInput,
): Patch {
  const size = Number(input.bankSize);
  const channel = Number(input.channel);
  if (!Number.isInteger(size) || size < 1) {
    throw new AssignmentError('bank_size', 'Bankgröße muss eine ganze Zahl ab 1 sein');
  }
  if (!Number.isInteger(channel) || channel < 1 || channel > 16) {
    throw new AssignmentError('channel', 'Kanal muss zwischen 1 und 16 liegen');
  }
  if (input.maPage !== null && (!Number.isInteger(input.maPage) || input.maPage < 1)) {
    throw new AssignmentError('ma_page', 'MA-Page muss eine ganze Zahl ab 1 sein');
  }
  const banks = ((config?.profiles?.[input.profile]?.banks ?? []) as AnyConfig[]).map((entry) => ({
    number: entry.number,
    channel: entry.number === input.bank ? channel : entry.channel,
    notes: bankNotesRecord(entry.notes),
  }));
  return {
    profiles: { [input.profile]: { banks } },
    mapping: {
      device_banks: {
        [input.device]: {
          bank_size: size,
          [String(input.bank)]: { ma_page: input.maPage },
        },
      },
    },
  };
}

// ---------------------------------------------------------------------------
// Display

export const SOURCE_LABELS: Record<AssignmentSource, string> = {
  'explicit-layer': 'Bank-Eintrag',
  'explicit-global': 'global',
  'inherited-global': 'geerbt (global)',
  'inherited-offset': 'geerbt mit Bank-Offset',
  default: 'Default',
};

export function describeAssignment(assignment: Assignment): string | undefined {
  switch (assignment.kind) {
    case 'key': {
      switch (keyAction(assignment)) {
        case 'screen_mode':
          return 'Screen-Modus (Toggle)';
        case 'screen':
          return `Screen ${assignment.screen}`;
        case 'encoder_press':
          return `Enc ${assignment.encoderPress}`;
        case 'command':
          return assignment.command ?? undefined;
        default:
          return assignment.hardkey ?? undefined;
      }
    }
    case 'playback': {
      const suffix =
        assignment.target === 'fader' ? 'Fader' : `Btn ${assignment.button ?? 1}`;
      const acc = assignment.accelerated ? ' · acc' : '';
      const via = assignment.transport ? ` · ${assignment.transport}` : '';
      return `Exec ${assignment.executor} ${suffix}${acc}${via}`;
    }
    case 'encoder':
      if (assignment.slot !== undefined && assignment.slot !== null) {
        return assignment.screenEncoder
          ? `Attribut ${assignment.slot} · Screen ${assignment.screenEncoder} (MA/Bank)`
          : `Attribut ${assignment.slot}`;
      }
      return assignment.attribute ? `Attribut ${assignment.attribute}` : undefined;
    case 'modifier':
      return assignment.local ? 'Modifier (lokal)' : `Modifier ${assignment.hardkey}`;
    default:
      return undefined;
  }
}

/** Short explanation of a priority conflict for the badge tooltip. */
export function describeConflict(conflict: Conflict): string {
  const subject: Record<ConflictParticipant, string> = {
    'layer-key': 'Bank-Taste',
    playback: 'Playback-Ziel',
    modifier: 'Modifier',
    key: 'Globale Taste',
  };
  const dative: Record<ConflictParticipant, string> = {
    'layer-key': 'der Bank-Taste',
    playback: 'dem Playback-Ziel',
    modifier: 'dem Modifier',
    key: 'der globalen Taste',
  };
  const shadowed = conflict.shadowed.map((entry) => dative[entry]).join(' und ');
  return `${subject[conflict.winner]} hat Vorrang vor ${shadowed}.`;
}

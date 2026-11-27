/**
 * Shared configuration state of the mapping and device tabs.
 *
 * One store holds the configuration, the device list, the generation the
 * configuration was read at, the selected device and bank and the save state.
 * Both tabs read and write exclusively through it, so a change saved in one tab
 * is visible in the other without reloading, and a stale draft is detected
 * before it overwrites a newer configuration.
 */

import {
  ApiError,
  type ApiClient,
  type DeviceEntry,
  type DeviceLearnStatus,
  type DevicePresence,
  type LearnResult,
} from './api';
import {
  AssignmentError,
  buildAssignPatch,
  buildBankSettingsPatch,
  buildDeletePatch,
  defaultScope,
  describeAssignment,
  describeConflict,
  hasEntryIn,
  keyFromRaw,
  mergePatches,
  resolveAssignment,
  SOURCE_LABELS,
  type AnyConfig,
  type Assignment,
  type AssignOptions,
  type BankSettingsInput,
  type Patch,
  type ResolvedAssignment,
  type Scope,
} from './assignment';
import { controlRef, controlsOf, type ControlInfo } from './deviceControls';
import type { StatusStore } from './status';

/** A rejected write.  `field` is the config path the daemon reported, if any. */
export class SaveError extends Error {
  readonly field: string | null;
  readonly stale: boolean;

  constructor(message: string, options: { field?: string | null; stale?: boolean } = {}) {
    super(message);
    this.name = 'SaveError';
    this.field = options.field ?? null;
    this.stale = options.stale ?? false;
  }
}

export interface FieldError {
  field: string;
  message: string;
}

type ConflictChoice = 'reload' | 'discard';

/** Origin label with the bank offset, e.g. "geerbt mit Bank-Offset (Offset +5)". */
export function sourceText(resolved: ResolvedAssignment): string {
  return `${SOURCE_LABELS[resolved.source]}${resolved.offset ? ` (Offset +${resolved.offset})` : ''}`;
}

function errorText(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) return cause.detail || fallback;
  if (cause instanceof Error) return cause.message || fallback;
  return fallback;
}

export class ConfigStore {
  config = $state.raw<AnyConfig | null>(null);
  devices = $state.raw<DeviceEntry[]>([]);
  presence = $state.raw<Record<string, DevicePresence>>({});
  generation = $state<number | null>(null);
  loading = $state(false);
  loaded = $state(false);
  saving = $state(false);
  error = $state<string | null>(null);
  fieldError = $state<FieldError | null>(null);
  /** True after a write was rejected because the configuration moved on. */
  conflict = $state(false);
  /** Bumps when the user discards a draft after a conflict; tabs close dialogs. */
  discardEpoch = $state(0);
  selectedDevice = $state<string | null>(null);
  bank = $state(1);
  /** Control detection session (`/api/learn`), fed by `learn` events. */
  learn = $state.raw<LearnResult | null>(null);
  /** Note learning session (`/api/device-learn`), fed by `device_learn` events. */
  deviceLearn = $state.raw<DeviceLearnStatus | null>(null);
  learnError = $state<string | null>(null);
  /** Control the last detection captured, until a tab takes it over. */
  detectedControl = $state<{ control: string; device: string | null } | null>(null);

  private readonly api: ApiClient;
  private unsubscribe: (() => void) | null = null;
  private seenLearn: LearnResult | null = null;
  private seenDeviceLearn: DeviceLearnStatus | null = null;
  private deviceLearnRevision = 0;

  constructor(api: ApiClient, status?: StatusStore) {
    this.api = api;
    if (status) this.attach(status);
  }

  /** Follow device presence and external configuration changes of the daemon. */
  attach(status: StatusStore): void {
    this.detach();
    const apply = (): void => {
      this.presence = status.state.status?.presence ?? {};
      this.adoptLearn(status.state.learn, status.state.deviceLearn);
      this.ensureSelection();
      const external = status.state.configGeneration;
      if (
        external !== null &&
        this.generation !== null &&
        external !== this.generation &&
        !this.saving &&
        !this.loading &&
        this.loaded
      ) {
        void this.reload();
      }
    };
    apply();
    this.unsubscribe = status.subscribe(apply);
  }

  /** Take over learn states that arrived as events (identity change only). */
  private adoptLearn(learn: LearnResult | null, deviceLearn: DeviceLearnStatus | null): void {
    if (learn !== this.seenLearn) {
      this.seenLearn = learn;
      this.setLearn(learn);
    }
    if (deviceLearn !== this.seenDeviceLearn) {
      this.seenDeviceLearn = deviceLearn;
      if (deviceLearn) this.setDeviceLearn(deviceLearn);
    }
  }

  private setDeviceLearn(next: DeviceLearnStatus): void {
    this.deviceLearnRevision += 1;
    this.deviceLearn = next;
  }

  private setLearn(learn: LearnResult | null): void {
    this.learn = learn;
    if (learn?.status === 'captured' && learn.control) {
      this.detectedControl = { control: learn.control, device: learn.device ?? null };
    }
  }

  detach(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
  }

  /** Devices both tabs offer: the ones the daemon currently sees. */
  get visibleDevices(): DeviceEntry[] {
    return this.devices.filter((device) => {
      const state = this.presence[device.name];
      return state ? state.seen : device.detected !== null;
    });
  }

  get device(): DeviceEntry | null {
    return this.visibleDevices.find((entry) => entry.name === this.selectedDevice) ?? null;
  }

  /** Banks of the selected device, never empty. */
  get banks(): { number: number; channel: number }[] {
    const banks = this.device?.controls.banks ?? [];
    return banks.length ? banks : [{ number: 1, channel: 1 }];
  }

  async load(): Promise<void> {
    if (this.loading) return;
    this.loading = true;
    this.error = null;
    try {
      await this.fetchAll();
      this.loaded = true;
    } catch (cause) {
      this.error = errorText(cause, 'Laden fehlgeschlagen');
    } finally {
      this.loading = false;
    }
  }

  /** Re-read configuration and devices without a loading state. */
  async reload(): Promise<void> {
    try {
      await this.fetchAll();
      this.error = null;
    } catch (cause) {
      this.error = errorText(cause, 'Laden fehlgeschlagen');
    }
  }

  private async fetchAll(): Promise<void> {
    const [snapshot, devices] = await Promise.all([
      this.api.configSnapshot(),
      this.api.devices(),
    ]);
    this.config = snapshot.config as AnyConfig;
    this.generation = snapshot.generation;
    this.devices = devices;
    this.ensureSelection();
  }

  async refreshDevices(): Promise<void> {
    try {
      this.devices = await this.api.devices();
      this.ensureSelection();
    } catch (cause) {
      this.error = errorText(cause, 'Laden fehlgeschlagen');
    }
  }

  /** Keep device and bank valid for the devices currently visible. */
  ensureSelection(): void {
    const visible = this.visibleDevices;
    if (!visible.some((entry) => entry.name === this.selectedDevice)) {
      this.selectedDevice = visible[0]?.name ?? null;
    }
    const banks = this.device?.controls.banks ?? [];
    if (banks.length && !banks.some((entry) => entry.number === this.bank)) {
      this.bank = banks[0].number;
    }
  }

  selectDevice(name: string): void {
    if (this.selectedDevice === name) return;
    this.selectedDevice = name;
    this.ensureSelection();
  }

  selectBank(bank: number): void {
    this.bank = bank;
  }

  /**
   * Write a merge patch.  Sends the generation the configuration was read at;
   * on success the new configuration replaces the shared state.  Throws
   * `SaveError`; a stale write additionally sets `conflict`.
   */
  async save(patch: Patch): Promise<void> {
    this.saving = true;
    this.error = null;
    this.fieldError = null;
    this.conflict = false;
    try {
      const result = await this.api.updateConfig(patch, { generation: this.generation });
      const next = (result as { config?: AnyConfig } | undefined)?.config;
      const generation = (result as { generation?: unknown } | undefined)?.generation;
      if (next && typeof next === 'object') {
        this.config = next;
        if (typeof generation === 'number') this.generation = generation;
        await this.refreshDevices();
      } else {
        await this.fetchAll();
      }
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 412) {
        this.conflict = true;
        this.error = cause.detail || 'Die Konfiguration wurde inzwischen geändert.';
        throw new SaveError(this.error, { stale: true });
      }
      const message = errorText(cause, 'Speichern fehlgeschlagen');
      const field = cause instanceof ApiError ? (cause.field ?? null) : null;
      this.error = message;
      if (field) this.fieldError = { field, message };
      throw new SaveError(message, { field });
    } finally {
      this.saving = false;
    }
  }

  /** `reload` keeps open edits and retries on the fresh generation, `discard` drops them. */
  async resolveConflict(choice: ConflictChoice): Promise<void> {
    await this.reload();
    this.conflict = false;
    this.error = null;
    this.fieldError = null;
    if (choice === 'discard') this.discardEpoch += 1;
  }

  clearError(): void {
    this.error = null;
    this.fieldError = null;
  }

  /** Drop everything, e.g. after logging out. */
  reset(): void {
    this.config = null;
    this.devices = [];
    this.generation = null;
    this.loaded = false;
    this.selectedDevice = null;
    this.bank = 1;
    this.conflict = false;
    this.error = null;
    this.fieldError = null;
    this.learn = null;
    this.deviceLearn = null;
    this.detectedControl = null;
    this.seenLearn = null;
    this.seenDeviceLearn = null;
  }

  // -------------------------------------------------------------------------
  // Assignment model

  /** Controls of the selected device in the selected bank, one list for both tabs. */
  get controls(): ControlInfo[] {
    return controlsOf(this.device, this.bank);
  }

  get midiRemoteEnabled(): boolean {
    return this.config?.midi_remote?.enabled === true;
  }

  get profile(): AnyConfig | null {
    const device = this.device;
    return device && this.config ? (this.config.profiles?.[device.profile] ?? null) : null;
  }

  /** Scope in which the viewed bank is read: the bank with inheritance from global. */
  get viewScope(): Scope {
    return this.device
      ? { kind: 'bank', device: this.device.name, bank: this.bank }
      : { kind: 'global' };
  }

  /** Effective assignment of a control in the viewed bank with source and conflicts. */
  resolve(control: ControlInfo, scope: Scope = this.viewScope): ResolvedAssignment {
    const device = this.device;
    if (!device) return resolveAssignment(this.config, scope, { device: '', control: control.id, bankSize: 1 });
    return resolveAssignment(this.config, scope, controlRef(device, control));
  }

  /** Scope a new edit starts in: where the effective entry lives, or the model default. */
  editScope(control: ControlInfo): Scope {
    const device = this.device;
    if (!device) return { kind: 'global' };
    const resolved = this.resolve(control);
    const sources = Object.values(resolved.layers)
      .filter((layer) => layer !== null)
      .map((layer) => layer!.source);
    if (resolved.assignment.kind === 'none') {
      return defaultScope(this.config, device.name, this.bank, controlRef(device, control));
    }
    if (resolved.assignment.kind === 'modifier') return { kind: 'global' };
    if (sources.includes('explicit-layer') && resolved.source === 'explicit-layer') {
      return { kind: 'bank', device: device.name, bank: this.bank };
    }
    return { kind: 'global' };
  }

  /** Text shown for the effective assignment of a control, `undefined` when free. */
  labelFor(control: ControlInfo): string | undefined {
    const resolved = this.resolve(control);
    const text = describeAssignment(resolved.assignment);
    if (text) return text;
    const note = (this.device?.controls.notes ?? []).find((entry) => entry.control === control.id)?.note;
    const led = this.config?.led;
    if (note !== undefined && led && (note === led.nipple_note || note === led.note)) return 'LED';
    return undefined;
  }

  /**
   * Global entries whose control no visible device offers, e.g. of a device that
   * is not connected.  They stay reachable so they can still be removed.
   */
  get orphans(): { control: string; text: string }[] {
    const known = new Set(
      this.visibleDevices.flatMap((entry) => controlsOf(entry, 1).map((item) => item.id)),
    );
    const mapping = this.config?.mapping ?? {};
    const out = new Map<string, string>();
    const note = (control: string, text: string): void => {
      if (known.has(control)) return;
      out.set(control, out.has(control) ? `${out.get(control)} · ${text}` : text);
    };
    for (const [control, raw] of Object.entries<AnyConfig>(mapping.keys ?? {})) {
      note(control, describeAssignment(keyFromRaw(raw)) ?? 'Taste');
    }
    for (const [control, raw] of Object.entries<AnyConfig>(mapping.playbacks ?? {})) {
      note(control, `Playback ${raw.page ?? '?'}/${raw.executor ?? '?'}`);
    }
    for (const control of Object.keys(mapping.modifiers ?? {})) note(control, 'Modifier');
    return [...out.entries()].map(([control, text]) => ({ control, text }));
  }

  async removeOrphan(control: string): Promise<void> {
    await this.write(() =>
      buildDeletePatch(this.config, { kind: 'global' }, { device: '', control, bankSize: 1 }),
    );
  }

  /** Source and conflict text both tabs show next to an assignment. */
  markerFor(control: ControlInfo): { source: string | null; conflict: string | null } {
    const resolved = this.resolve(control);
    return {
      source: resolved.assignment.kind === 'none' ? null : sourceText(resolved),
      conflict: resolved.conflict ? describeConflict(resolved.conflict) : null,
    };
  }

  /** Does ``scope`` hold an entry the user can remove for ``control``? */
  removable(control: ControlInfo, scope: Scope): boolean {
    const device = this.device;
    if (!device) return false;
    const ref = controlRef(device, control);
    return hasEntryIn(this.config, scope, ref);
  }

  private async write(build: () => Patch): Promise<void> {
    let patch: Patch;
    try {
      patch = build();
    } catch (cause) {
      if (cause instanceof AssignmentError) {
        this.fieldError = { field: cause.field, message: cause.message };
        this.error = cause.message;
        throw new SaveError(cause.message, { field: cause.field });
      }
      throw cause;
    }
    await this.save(patch);
  }

  /**
   * Assign to one or more controls with the shared serializer.  `build` yields the
   * assignment per control and its index, so a multi assignment can step executors.
   */
  async assign(
    controls: ControlInfo[],
    scope: Scope,
    build: (control: ControlInfo, index: number) => Assignment,
    options: AssignOptions = {},
  ): Promise<void> {
    const device = this.device;
    if (!device) return;
    await this.write(() => {
      const replaceOverrideIn =
        options.replaceOverrideIn ?? { device: device.name, bank: this.bank };
      const patches = controls.map((control, index) =>
        buildAssignPatch(this.config, scope, controlRef(device, control), build(control, index), {
          replaceOverrideIn,
        }),
      );
      return mergePatches(...patches);
    });
  }

  /** Remove the explicit entry of the controls in ``scope``. */
  async remove(controls: ControlInfo[], scope: Scope): Promise<void> {
    const device = this.device;
    if (!device) return;
    await this.write(() =>
      mergePatches(
        ...controls.map((control) =>
          buildDeletePatch(this.config, scope, controlRef(device, control)),
        ),
      ),
    );
  }

  async saveBankSettings(input: Omit<BankSettingsInput, 'device' | 'profile'>): Promise<void> {
    const device = this.device;
    if (!device) return;
    await this.write(() =>
      buildBankSettingsPatch(this.config, { ...input, device: device.name, profile: device.profile }),
    );
  }

  // -------------------------------------------------------------------------
  // Learn sessions

  get anyLearnActive(): boolean {
    return this.learn?.status === 'active' || this.deviceLearn?.active === true;
  }

  private async learnCall<T>(action: () => Promise<T>): Promise<T | null> {
    this.learnError = null;
    try {
      return await action();
    } catch (cause) {
      this.learnError = errorText(cause, 'Lernen fehlgeschlagen');
      return null;
    }
  }

  /** Start control detection; only one session runs at a time across both tabs. */
  async startLearn(kind: 'key' | 'encoder', device?: string): Promise<void> {
    if (this.anyLearnActive) {
      this.learnError = 'Es läuft bereits eine Lern-Sitzung.';
      return;
    }
    this.detectedControl = null;
    const started = await this.learnCall(() => this.api.startLearn(kind, device));
    if (started) this.setLearn(started);
  }

  async cancelLearn(): Promise<void> {
    const result = await this.learnCall(() => this.api.cancelLearn());
    if (!result) return;
    if (result.learn) this.setLearn(result.learn);
    else if (this.learn) this.setLearn({ ...this.learn, status: 'cancelled' });
  }

  clearDetectedControl(): void {
    this.detectedControl = null;
  }

  async startDeviceLearn(device: string, bank: number, control?: string): Promise<void> {
    if (this.anyLearnActive) {
      this.learnError = 'Es läuft bereits eine Lern-Sitzung.';
      return;
    }
    const next = await this.learnCall(() =>
      control ? this.api.startDeviceLearn(device, bank, control) : this.api.startDeviceLearn(device, bank),
    );
    if (next && typeof next.active === 'boolean') this.setDeviceLearn(next);
  }

  async skipDeviceLearn(): Promise<void> {
    const next = await this.learnCall(() => this.api.skipDeviceLearn());
    if (next && typeof next.active === 'boolean') this.setDeviceLearn(next);
  }

  async cancelDeviceLearn(): Promise<void> {
    const done = await this.learnCall(() => this.api.cancelDeviceLearn());
    if (done) this.setDeviceLearn({ active: false, cancelled: true });
  }

  async finishDeviceLearn(): Promise<void> {
    const done = await this.learnCall(() => this.api.finishDeviceLearn());
    if (done) {
      this.setDeviceLearn({ active: false, saved: true });
      await this.reload();
    }
  }

  /** One-off read after (re)connecting; events keep the state current afterwards. */
  async syncLearn(): Promise<void> {
    if (typeof this.api.deviceLearnStatus !== 'function') return;
    const revision = this.deviceLearnRevision;
    try {
      const status = await this.api.deviceLearnStatus();
      // An event that arrived while the read was in flight is newer than the snapshot.
      if (revision === this.deviceLearnRevision && status && typeof status.active === 'boolean') {
        this.setDeviceLearn(status);
      }
    } catch {
      // Events deliver the state; a missing snapshot is not an error.
    }
  }
}

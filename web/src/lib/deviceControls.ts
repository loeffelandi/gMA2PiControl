/**
 * The control list both tabs show for a device.
 *
 * One source for the mapping and the device tab: inventory, notes, absolute
 * values, encoders and the notes of every bank.  A control that only the
 * inventory or only one bank knows is therefore selectable in both tabs.
 */

import type { DeviceBank, DeviceEntry } from './api';
import { encoderIdForControl, type ControlRef } from './assignment';

export type ControlKind = 'button' | 'fader' | 'poti' | 'encoder' | 'relative-encoder';

export interface ControlInfo {
  id: string;
  kind: ControlKind;
  label: string | null;
  /** Encoder id of a relative encoder, `null` for every other control. */
  encoderId: number | null;
  /** Note bound to the control in the viewed bank, `null` when unbound. */
  note: number | null;
  /** True when the viewed bank binds a note to this control. */
  bound: boolean;
}

interface RawControls {
  keys?: { control: string }[];
  notes?: { control: string; note?: number }[];
  encoders?: { id?: number; control?: string }[];
  midi_encoders?: { id?: number; control?: string }[];
  values?: { control: string; kind: string }[];
  inventory?: { id: string; kind: string; label?: string | null; encoder_id?: number }[];
  banks?: DeviceBank[];
}

/** Notes of a bank as `note -> control`, accepting the list and the map form. */
export function bankNotes(bank: { notes?: unknown } | undefined | null): Record<string, string> {
  const notes = bank?.notes;
  if (!notes) return {};
  if (Array.isArray(notes)) {
    const out: Record<string, string> = {};
    for (const entry of notes) {
      if (entry && typeof entry === 'object' && 'note' in entry && 'control' in entry) {
        out[String((entry as { note: unknown }).note)] = String(
          (entry as { control: unknown }).control,
        );
      }
    }
    return out;
  }
  return notes as Record<string, string>;
}

function asKind(kind: string | undefined, fallback: ControlKind): ControlKind {
  switch (kind) {
    case 'button':
    case 'fader':
    case 'poti':
    case 'encoder':
    case 'relative-encoder':
      return kind;
    default:
      return fallback;
  }
}

export function controlsOf(device: DeviceEntry | null | undefined, bank = 1): ControlInfo[] {
  if (!device) return [];
  const controls = device.controls as unknown as RawControls;
  const banks = controls.banks ?? [];
  const activeBank = banks.find((entry) => entry.number === bank);
  const noteOf = new Map<string, number>();
  for (const [note, control] of Object.entries(bankNotes(activeBank))) {
    if (!noteOf.has(control)) noteOf.set(control, Number(note));
  }
  const known = new Map<string, ControlInfo>();
  const add = (id: string, kind: ControlKind, label: string | null, encoderHint?: number): void => {
    if (!id || known.has(id)) return;
    const encoderId =
      kind === 'relative-encoder'
        ? encoderIdForControl(id, controls.inventory ?? [], []) ??
          (Number.isInteger(encoderHint) && (encoderHint as number) >= 1 ? (encoderHint as number) : null)
        : null;
    known.set(id, {
      id,
      kind,
      label,
      encoderId,
      note: noteOf.get(id) ?? null,
      bound: noteOf.has(id),
    });
  };

  for (const item of controls.inventory ?? []) {
    add(item.id, asKind(item.kind, 'button'), item.label ?? null, item.encoder_id);
  }
  for (const entry of controls.values ?? []) {
    add(entry.control, asKind(entry.kind, 'fader'), null);
  }
  for (const entry of controls.keys ?? []) add(entry.control, 'button', null);
  for (const entry of controls.notes ?? []) add(entry.control, 'button', null);
  for (const entry of [...(controls.encoders ?? []), ...(controls.midi_encoders ?? [])]) {
    const id = entry.control ?? (entry.id !== undefined ? `encoder.${entry.id}` : '');
    add(id, 'relative-encoder', null, entry.id);
  }
  for (const entry of banks) {
    for (const control of Object.values(bankNotes(entry))) add(control, 'button', null);
  }
  return [...known.values()];
}

export function controlRef(device: DeviceEntry, control: ControlInfo): ControlRef {
  return {
    device: device.name,
    control: control.id,
    kind: control.kind,
    encoderId: control.encoderId,
    bankSize: device.bank_size ?? 1,
  };
}

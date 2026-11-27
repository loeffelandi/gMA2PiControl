import { describe, expect, it } from 'vitest';

import goldenRaw from '../../../tests/fixtures/assignment_golden.json?raw';

import {
  AssignmentError,
  bankOffset,
  buildAssignPatch,
  buildBankSettingsPatch,
  buildDeletePatch,
  defaultScope,
  describeConflict,
  effectiveTransport,
  encoderIdForControl,
  mergePatches,
  rawGlobalExecutor,
  resolveAssignment,
  type AnyConfig,
  type Assignment,
  type ControlRef,
  type Scope,
} from './assignment';

const DEVICE = 'midicraft-enc';

/** RFC 7386 merge patch, as the daemon applies `PUT /api/config`. */
function applyPatch(target: AnyConfig, patch: AnyConfig): AnyConfig {
  const out: AnyConfig = structuredClone(target);
  const merge = (dst: AnyConfig, src: AnyConfig): void => {
    for (const [key, value] of Object.entries(src)) {
      if (value === null) {
        delete dst[key];
      } else if (typeof value === 'object' && !Array.isArray(value)) {
        if (typeof dst[key] !== 'object' || dst[key] === null || Array.isArray(dst[key])) {
          dst[key] = {};
        }
        merge(dst[key], value);
      } else {
        dst[key] = value;
      }
    }
  };
  merge(out, patch);
  return out;
}

function ref(control: string, kind = 'button', extra: Partial<ControlRef> = {}): ControlRef {
  return { device: DEVICE, control, kind, bankSize: 5, ...extra };
}

const global: Scope = { kind: 'global' };
const bank = (number: number): Scope => ({ kind: 'bank', device: DEVICE, bank: number });

describe('golden fixtures shared with the daemon', () => {
  const fixture = JSON.parse(goldenRaw) as {
    device: string;
    bank_size: number;
    cases: {
      name: string;
      midi_remote_enabled?: boolean;
      mapping: AnyConfig;
      queries: {
        bank: number;
        control: string;
        playback?: AnyConfig | null;
        key?: AnyConfig;
      }[];
    }[];
  };

  function kindOf(control: string): string {
    if (control.includes('fader')) return 'fader';
    if (control.includes('encoder')) return 'encoder';
    return 'button';
  }

  for (const entry of fixture.cases) {
    it(entry.name, () => {
      const config = { mapping: entry.mapping, midi_remote: { enabled: entry.midi_remote_enabled === true } };
      for (const query of entry.queries) {
        const resolved = resolveAssignment(
          config,
          { kind: 'bank', device: fixture.device, bank: query.bank },
          { device: fixture.device, control: query.control, kind: kindOf(query.control), bankSize: fixture.bank_size },
        );
        if ('playback' in query) {
          const playback = resolved.layers.playback;
          if (query.playback === null || query.playback === undefined) {
            expect(playback).toBeNull();
          } else {
            expect(playback).not.toBeNull();
            const expected = query.playback;
            const got = playback!.assignment;
            expect(got.page).toBe(expected.page);
            expect(got.executor).toBe(expected.executor);
            expect(got.target).toBe(expected.kind);
            expect(Boolean(got.accelerated)).toBe(expected.accelerated);
            expect(effectiveTransport(expected.kind, got.transport, entry.midi_remote_enabled === true)).toBe(
              expected.transport,
            );
            if (expected.kind === 'button') expect(got.button).toBe(expected.button);
          }
        }
        if (query.key) {
          const key = resolved.layers.key?.assignment;
          expect(key).toBeDefined();
          const flat: AnyConfig = {};
          if (key!.hardkey) flat.hardkey = key!.hardkey;
          if (key!.command) flat.command = key!.command;
          if (key!.screen != null) flat.screen = key!.screen;
          if (key!.encoderPress != null) flat.encoder_press = key!.encoderPress;
          expect(flat).toEqual(query.key);
        }
      }
    });
  }
});

describe('resolver sources', () => {
  const config: AnyConfig = {
    mapping: {
      keys: { mc_click_2: { hardkey: 'GOTO' } },
      playbacks: {
        mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 },
      },
      device_banks: {
        [DEVICE]: {
          bank_size: 5,
          '3': { playbacks: { mc_click_1: { executor: 20 } } },
        },
      },
    },
  };

  it('explicit-global in the global scope', () => {
    const resolved = resolveAssignment(config, global, ref('mc_click_1'));
    expect(resolved.source).toBe('explicit-global');
    expect(resolved.assignment).toMatchObject({ kind: 'playback', executor: 1 });
  });

  it('inherited-global on bank 1', () => {
    const resolved = resolveAssignment(config, bank(1), ref('mc_click_1'));
    expect(resolved.source).toBe('inherited-global');
    expect(resolved.offset).toBe(0);
  });

  it('inherited-offset on bank 2 (Executor 6 instead of an explicit entry)', () => {
    const resolved = resolveAssignment(config, bank(2), ref('mc_click_1'));
    expect(resolved.source).toBe('inherited-offset');
    expect(resolved.offset).toBe(5);
    expect(resolved.assignment).toMatchObject({ kind: 'playback', executor: 6 });
  });

  it('explicit-layer for a bank entry with its own executor', () => {
    const resolved = resolveAssignment(config, bank(3), ref('mc_click_1'));
    expect(resolved.source).toBe('explicit-layer');
    expect(resolved.assignment).toMatchObject({ executor: 20 });
    // the global entry stays untouched
    expect(resolveAssignment(config, global, ref('mc_click_1')).assignment).toMatchObject({
      executor: 1,
    });
  });

  it('default when nothing is configured', () => {
    const resolved = resolveAssignment(config, bank(2), ref('mc_row1_1'));
    expect(resolved.source).toBe('default');
    expect(resolved.assignment).toEqual({ kind: 'none' });
  });

  it('bank offset ignores banks with an MA page or without bank settings', () => {
    const withPage = {
      mapping: { device_banks: { [DEVICE]: { '2': { ma_page: 4 } } } },
    };
    expect(bankOffset(withPage, DEVICE, 2, 5)).toBe(0);
    expect(bankOffset(withPage, DEVICE, 3, 5)).toBe(10);
    expect(bankOffset({ mapping: {} }, DEVICE, 3, 5)).toBe(0);
  });
});

describe('priority conflicts', () => {
  const config: AnyConfig = {
    mapping: {
      keys: { mc_click_1: { hardkey: 'GOTO' }, mc_click_2: { hardkey: 'GOTO' } },
      playbacks: {
        mc_click_1: { page: 1, executor: 1, kind: 'button', button: 1 },
        mc_click_2: { page: 1, executor: 2, kind: 'button', button: 1 },
        mc_encoder_1: { page: 1, executor: 1, kind: 'fader' },
      },
      modifiers: { mc_click_3: { local: true } },
      device_banks: {
        [DEVICE]: { '2': { keys: { mc_click_1: { command: 'Go+' } } } },
      },
    },
  };

  it('layer key beats playback on key controls', () => {
    const resolved = resolveAssignment(config, bank(2), ref('mc_click_1'));
    expect(resolved.conflict).toEqual({ winner: 'layer-key', shadowed: ['playback'] });
    expect(resolved.assignment).toMatchObject({ kind: 'key', command: 'Go+' });
    expect(describeConflict(resolved.conflict!)).toContain('Bank-Taste');
  });

  it('playback beats the global key', () => {
    const resolved = resolveAssignment(config, bank(1), ref('mc_click_2'));
    expect(resolved.conflict).toEqual({ winner: 'playback', shadowed: ['key'] });
    expect(resolved.assignment.kind).toBe('playback');
  });

  it('reports no layer-key conflict for value controls', () => {
    const resolved = resolveAssignment(config, bank(2), ref('mc_encoder_1', 'encoder'));
    expect(resolved.conflict).toBeNull();
    expect(resolved.assignment.kind).toBe('playback');
  });

  it('a modifier beats the key in the engine', () => {
    const withKey = applyPatch(config, { mapping: { keys: { mc_click_3: { hardkey: 'GOTO' } } } });
    const resolved = resolveAssignment(withKey, global, ref('mc_click_3'));
    expect(resolved.conflict).toEqual({ winner: 'modifier', shadowed: ['key'] });
  });
});

describe('patch builders: keys and playbacks', () => {
  const base: AnyConfig = {
    mapping: {
      keys: { mc_click_1: { hardkey: 'GOTO' } },
      playbacks: {
        mc_click_2: { page: 1, executor: 3, kind: 'button', button: 2, transport: 'midi' },
      },
      modifiers: {},
    },
  };

  it('Hardkey -> Command nulls every unused field', () => {
    const patch = buildAssignPatch(base, global, ref('mc_click_1'), {
      kind: 'key',
      command: 'Go+',
    });
    expect(patch.mapping.keys.mc_click_1).toEqual({
      hardkey: null,
      command: 'Go+',
      screen_mode: null,
      encoder_press: null,
      screen: null,
    });
    const next = applyPatch(base, patch);
    expect(next.mapping.keys.mc_click_1).toEqual({ command: 'Go+' });
  });

  it('Command -> Screen -> Screen mode', () => {
    const withCommand = applyPatch(
      base,
      buildAssignPatch(base, global, ref('mc_click_1'), { kind: 'key', command: 'Go+' }),
    );
    const toScreen = applyPatch(
      withCommand,
      buildAssignPatch(withCommand, global, ref('mc_click_1'), { kind: 'key', screen: 4 }),
    );
    expect(toScreen.mapping.keys.mc_click_1).toEqual({ screen: 4 });
    const toMode = applyPatch(
      toScreen,
      buildAssignPatch(toScreen, global, ref('mc_click_1'), { kind: 'key', screenMode: true }),
    );
    expect(toMode.mapping.keys.mc_click_1).toEqual({ screen_mode: true });
  });

  it('a key removes the playback target of the same layer', () => {
    const patch = buildAssignPatch(base, global, ref('mc_click_2'), {
      kind: 'key',
      hardkey: 'STORE',
    });
    expect(applyPatch(base, patch).mapping.playbacks.mc_click_2).toBeUndefined();
  });

  it('Button -> Fader drops button and midi transport', () => {
    const fader: Assignment = {
      kind: 'playback',
      page: 1,
      executor: 3,
      target: 'fader',
      button: 2,
      transport: 'midi',
    };
    const patch = buildAssignPatch(base, global, ref('mc_click_2'), fader);
    expect(patch.mapping.playbacks.mc_click_2).toEqual({
      page: 1,
      executor: 3,
      kind: 'fader',
      button: null,
      accelerated: null,
      transport: null,
    });
    expect(applyPatch(base, patch).mapping.playbacks.mc_click_2).toEqual({
      page: 1,
      executor: 3,
      kind: 'fader',
    });
  });

  it('writes the transport of a button target and clears the key', () => {
    const patch = buildAssignPatch(base, global, ref('mc_click_1'), {
      kind: 'playback',
      page: 'current',
      executor: 4,
      target: 'button',
      button: 1,
      transport: 'midi',
    });
    const next = applyPatch(base, patch);
    expect(next.mapping.keys.mc_click_1).toBeUndefined();
    expect(next.mapping.playbacks.mc_click_1).toEqual({
      page: 'current',
      executor: 4,
      kind: 'button',
      button: 1,
      transport: 'midi',
    });
  });

  it('writes accelerated only for absolute encoders with a fader target', () => {
    const fader: Assignment = {
      kind: 'playback',
      page: 1,
      executor: 1,
      target: 'fader',
      accelerated: true,
    };
    expect(
      buildAssignPatch(base, global, ref('mc_encoder_1', 'encoder'), fader).mapping.playbacks
        .mc_encoder_1.accelerated,
    ).toBe(true);
    expect(
      buildAssignPatch(base, global, ref('mc_fader_1', 'fader'), fader).mapping.playbacks.mc_fader_1
        .accelerated,
    ).toBeNull();
  });

  it('a bank fader does not inherit a global midi transport', () => {
    const patch = buildAssignPatch(base, bank(2), ref('mc_click_2'), {
      kind: 'playback',
      page: 1,
      executor: 9,
      target: 'fader',
    });
    expect(patch.mapping.device_banks[DEVICE]['2'].playbacks.mc_click_2.transport).toBe('web');
  });

  it('bank scope writes only the layer and keeps the global entry', () => {
    const patch = buildAssignPatch(base, bank(2), ref('mc_click_2'), {
      kind: 'playback',
      page: 1,
      executor: 9,
      target: 'button',
      button: 1,
    });
    expect(patch.mapping.keys).toBeUndefined();
    const next = applyPatch(base, patch);
    expect(next.mapping.playbacks.mc_click_2.executor).toBe(3);
    expect(next.mapping.device_banks[DEVICE]['2'].playbacks.mc_click_2.executor).toBe(9);
  });

  it('a global write clears the explicit entry of the bank in view', () => {
    const config = applyPatch(base, {
      mapping: {
        device_banks: {
          [DEVICE]: { '2': { playbacks: { mc_click_2: { executor: 9 } } } },
        },
      },
    });
    const patch = buildAssignPatch(
      config,
      global,
      ref('mc_click_2'),
      { kind: 'playback', page: 1, executor: 5, target: 'button', button: 1 },
      { replaceOverrideIn: { device: DEVICE, bank: 2 } },
    );
    const next = applyPatch(config, patch);
    expect(next.mapping.device_banks[DEVICE]['2'].playbacks).toEqual({});
    // the global raw value 5 is shifted by the offset of bank 2 again
    expect(resolveAssignment(next, bank(2), ref('mc_click_2')).assignment).toMatchObject({
      executor: 10,
    });
  });

  it('converts an effective executor to the raw global value', () => {
    expect(rawGlobalExecutor(10, 5)).toBe(5);
    expect(() => rawGlobalExecutor(3, 5)).toThrow(/mindestens 6/);
  });

  it('a global key removes a modifier of the control', () => {
    const config = applyPatch(base, { mapping: { modifiers: { mc_click_1: { local: true } } } });
    const patch = buildAssignPatch(config, global, ref('mc_click_1'), {
      kind: 'key',
      hardkey: 'GOTO',
    });
    expect(applyPatch(config, patch).mapping.modifiers.mc_click_1).toBeUndefined();
  });

  it('delete removes key and playback in the scope', () => {
    const globalPatch = buildDeletePatch(base, global, ref('mc_click_2'));
    expect(applyPatch(base, globalPatch).mapping.playbacks.mc_click_2).toBeUndefined();
    const bankPatch = buildDeletePatch(base, bank(2), ref('mc_click_2'));
    expect(bankPatch.mapping.device_banks[DEVICE]['2']).toEqual({
      keys: { mc_click_2: null },
      playbacks: { mc_click_2: null },
    });
  });

  it('removing a bank override makes the inherited target visible again', () => {
    const config = applyPatch(base, {
      mapping: {
        device_banks: {
          [DEVICE]: { bank_size: 5, '2': { playbacks: { mc_click_2: { executor: 9 } } } },
        },
      },
    });
    expect(resolveAssignment(config, bank(2), ref('mc_click_2')).source).toBe('explicit-layer');
    const after = applyPatch(config, buildDeletePatch(config, bank(2), ref('mc_click_2')));
    const resolved = resolveAssignment(after, bank(2), ref('mc_click_2'));
    expect(resolved.source).toBe('inherited-offset');
    expect(resolved.assignment).toMatchObject({ executor: 8 });
  });

  it('removing a global entry keeps the overrides of other banks', () => {
    const config = applyPatch(base, {
      mapping: {
        device_banks: {
          [DEVICE]: { '3': { playbacks: { mc_click_2: { page: 1, executor: 9, kind: 'button' } } } },
        },
      },
    });
    const after = applyPatch(config, buildDeletePatch(config, global, ref('mc_click_2')));
    expect(resolveAssignment(after, bank(2), ref('mc_click_2')).assignment.kind).toBe('none');
    expect(resolveAssignment(after, bank(3), ref('mc_click_2')).assignment).toMatchObject({
      executor: 9,
    });
  });

  it('modifier replaces key and playback and keeps exactly one variant', () => {
    const local = buildAssignPatch(base, global, ref('mc_click_1'), { kind: 'modifier', local: true });
    expect(local.mapping.modifiers.mc_click_1).toEqual({ local: true, hardkey: null });
    const hardkey = buildAssignPatch(base, global, ref('mc_click_1'), {
      kind: 'modifier',
      hardkey: ' SHIFT ',
    });
    expect(hardkey.mapping.modifiers.mc_click_1).toEqual({ hardkey: 'SHIFT', local: null });
    expect(applyPatch(base, hardkey).mapping.keys.mc_click_1).toBeUndefined();
  });

  it('rejects invalid values with a field', () => {
    const attempt = (assignment: Assignment, field: string) => {
      try {
        buildAssignPatch(base, global, ref('mc_click_1'), assignment);
      } catch (error) {
        expect(error).toBeInstanceOf(AssignmentError);
        expect((error as AssignmentError).field).toBe(field);
        return;
      }
      throw new Error('expected an error');
    };
    attempt({ kind: 'key', hardkey: '' }, 'hardkey');
    attempt({ kind: 'playback', page: 0, executor: 1, target: 'button' }, 'page');
    attempt({ kind: 'playback', page: 1, executor: 0, target: 'button' }, 'executor');
    attempt({ kind: 'playback', page: 1, executor: 1, target: 'button', button: 4 }, 'button');
    attempt({ kind: 'modifier', hardkey: ' ' }, 'hardkey');
  });
});

describe('patch builders: encoders and screen encoders', () => {
  const enc = (id: number) => ref(`encoder.${id}`, 'relative-encoder', { encoderId: id });
  const base: AnyConfig = {
    mapping: {
      encoders: [
        { id: 1, slot: 1 },
        { id: 2, slot: 2 },
      ],
      screen_encoders: { '1': 8, '2': 7 },
    },
  };

  it('sends the complete encoder list sorted by id', () => {
    const patch = buildAssignPatch(base, global, enc(3), {
      kind: 'encoder',
      slot: 3,
      screenEncoder: 6,
    });
    expect(patch.mapping.encoders).toEqual([
      { id: 1, slot: 1 },
      { id: 2, slot: 2 },
      { id: 3, slot: 3 },
    ]);
    expect(patch.mapping.screen_encoders).toEqual({ '3': 6 });
  });

  it('switching to an attribute clears the old screen encoder', () => {
    const patch = buildAssignPatch(base, global, enc(1), {
      kind: 'encoder',
      attribute: 'Dimmer',
    });
    expect(patch.mapping.encoders).toEqual([
      { id: 1, attribute: 'Dimmer' },
      { id: 2, slot: 2 },
    ]);
    expect(patch.mapping.screen_encoders).toEqual({ '1': null });
    expect(applyPatch(base, patch).mapping.screen_encoders).toEqual({ '2': 7 });
  });

  it('switching to another slot moves the screen encoder entry', () => {
    const patch = buildAssignPatch(base, global, enc(1), {
      kind: 'encoder',
      slot: 3,
      screenEncoder: 9,
    });
    expect(patch.mapping.screen_encoders).toEqual({ '3': 9, '1': null });
  });

  it('"keiner" removes the screen encoder of the slot', () => {
    const patch = buildAssignPatch(base, global, enc(1), {
      kind: 'encoder',
      slot: 1,
      screenEncoder: 0,
    });
    expect(patch.mapping.screen_encoders).toEqual({ '1': null });
  });

  it('delete removes the entry and the orphaned screen encoder', () => {
    const patch = buildDeletePatch(base, global, enc(2));
    expect(patch.mapping.encoders).toEqual([{ id: 1, slot: 1 }]);
    expect(patch.mapping.screen_encoders).toEqual({ '2': null });
  });

  it('bank scope replaces only the layer list', () => {
    const config = applyPatch(base, {
      mapping: { device_banks: { [DEVICE]: { '2': { encoders: [{ id: 2, attribute: 'Pan' }] } } } },
    });
    const patch = buildAssignPatch(config, bank(2), enc(1), { kind: 'encoder', attribute: 'Tilt' });
    expect(patch.mapping.device_banks[DEVICE]['2'].encoders).toEqual([
      { id: 1, attribute: 'Tilt' },
      { id: 2, attribute: 'Pan' },
    ]);
    expect(patch.mapping.encoders).toBeUndefined();
    expect(patch.mapping.screen_encoders).toBeUndefined();
  });

  it('a global encoder write can replace the layer override of the bank in view', () => {
    const config = applyPatch(base, {
      mapping: { device_banks: { [DEVICE]: { '1': { encoders: [{ id: 1, attribute: 'Pan' }] } } } },
    });
    const patch = buildAssignPatch(
      config,
      global,
      enc(1),
      { kind: 'encoder', slot: 1, screenEncoder: 8 },
      { replaceOverrideIn: { device: DEVICE, bank: 1 } },
    );
    expect(patch.mapping.device_banks[DEVICE]['1'].encoders).toEqual([]);
  });

  it('resolves encoder layers and inherits the global entry', () => {
    const config = applyPatch(base, {
      mapping: { device_banks: { [DEVICE]: { '2': { encoders: [{ id: 1, attribute: 'Pan' }] } } } },
    });
    expect(resolveAssignment(config, bank(2), enc(1)).assignment).toMatchObject({
      kind: 'encoder',
      attribute: 'Pan',
    });
    const inherited = resolveAssignment(config, bank(3), enc(1));
    expect(inherited.source).toBe('inherited-global');
    expect(inherited.assignment).toMatchObject({ slot: 1, screenEncoder: 8 });
  });

  it('finds encoder ids from inventory, profile and naming', () => {
    expect(
      encoderIdForControl('mc_rot_1', [{ id: 'mc_rot_1', kind: 'relative-encoder', encoder_id: 4 }]),
    ).toBe(4);
    expect(encoderIdForControl('x', [], [{ id: 'x', kind: 'relative-encoder', encoder_id: 2 }])).toBe(2);
    expect(encoderIdForControl('encoder.7')).toBe(7);
    expect(encoderIdForControl('mc_click_1')).toBeNull();
  });
});

describe('bank 1 and bank settings', () => {
  const config: AnyConfig = {
    mapping: {
      keys: { mc_click_1: { hardkey: 'GOTO' } },
      device_banks: {
        [DEVICE]: { bank_size: 5, '1': { keys: { mc_click_2: { command: 'Go+' } } } },
      },
    },
    profiles: {
      [DEVICE]: {
        banks: [
          { number: 1, channel: 1, notes: { '60': 'mc_click_1' } },
          { number: 2, channel: 2, notes: [{ note: 61, control: 'mc_click_2' }] },
        ],
      },
    },
  };

  it('bank 1 with a layer entry edits the layer, without one the global layer', () => {
    expect(defaultScope(config, DEVICE, 1, ref('mc_click_2'))).toEqual(bank(1));
    expect(defaultScope(config, DEVICE, 1, ref('mc_click_1'))).toEqual(global);
    expect(defaultScope(config, DEVICE, 2, ref('mc_click_1'))).toEqual(bank(2));
  });

  it('bank 1 layer wins in the resolver and is marked explicit', () => {
    const resolved = resolveAssignment(config, bank(1), ref('mc_click_2'));
    expect(resolved.source).toBe('explicit-layer');
  });

  it('bank 1 layer edits keep the global entry', () => {
    const patch = buildAssignPatch(config, bank(1), ref('mc_click_2'), {
      kind: 'key',
      hardkey: 'STORE',
    });
    const next = applyPatch(config, patch);
    expect(next.mapping.device_banks[DEVICE]['1'].keys.mc_click_2).toEqual({ hardkey: 'STORE' });
    expect(next.mapping.keys.mc_click_1).toEqual({ hardkey: 'GOTO' });
  });

  it('bank settings patch keeps notes of all banks and changes one channel and MA page', () => {
    const patch = buildBankSettingsPatch(config, {
      device: DEVICE,
      profile: DEVICE,
      bank: 2,
      bankSize: 10,
      channel: 5,
      maPage: 3,
    });
    expect(patch.profiles[DEVICE].banks).toEqual([
      { number: 1, channel: 1, notes: { '60': 'mc_click_1' } },
      { number: 2, channel: 5, notes: { '61': 'mc_click_2' } },
    ]);
    expect(patch.mapping.device_banks[DEVICE]).toEqual({ bank_size: 10, '2': { ma_page: 3 } });
  });

  it('bank settings are validated with a field', () => {
    const attempt = (input: Partial<Parameters<typeof buildBankSettingsPatch>[1]>, field: string) => {
      try {
        buildBankSettingsPatch(config, {
          device: DEVICE,
          profile: DEVICE,
          bank: 1,
          bankSize: 5,
          channel: 1,
          maPage: null,
          ...input,
        });
      } catch (error) {
        expect((error as AssignmentError).field).toBe(field);
        return;
      }
      throw new Error('expected an error');
    };
    attempt({ bankSize: 0 }, 'bank_size');
    attempt({ channel: 17 }, 'channel');
    attempt({ maPage: 0 }, 'ma_page');
  });

  it('merges patches of several controls', () => {
    const merged = mergePatches(
      buildAssignPatch(config, global, ref('mc_click_1'), { kind: 'key', hardkey: 'A' }),
      buildAssignPatch(config, global, ref('mc_click_3'), { kind: 'key', hardkey: 'B' }),
    );
    expect(Object.keys(merged.mapping.keys).sort()).toEqual(['mc_click_1', 'mc_click_3']);
  });
});

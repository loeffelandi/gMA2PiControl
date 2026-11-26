import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import AssignDialog from './AssignDialog.svelte';

describe('AssignDialog', () => {
  it('previews the distributed executor numbers in click order', async () => {
    render(AssignDialog, {
      props: {
        control: 'mc_fader_1',
        bank: 2,
        kind: 'fader',
        count: 5,
        initial: { action: 'executor', executor: 1, targetKind: 'fader' },
        onSave: vi.fn(),
        onClose: vi.fn(),
      },
    });
    expect(screen.getByText('Vorschau: 1, 2, 3, 4, 5')).toBeTruthy();
  });

  it('offers acceleration only for an absolute encoder fader target', async () => {
    const { rerender } = render(AssignDialog, {
      props: {
        control: 'mc_encoder_1',
        bank: 1,
        kind: 'encoder',
        count: 1,
        initial: { action: 'executor', targetKind: 'fader' },
        onSave: vi.fn(),
        onClose: vi.fn(),
      },
    });
    expect(screen.getByText('Beschleunigt')).toBeTruthy();

    await rerender({
      control: 'mc_fader_1',
      bank: 1,
      kind: 'fader',
      count: 1,
      initial: { action: 'executor', targetKind: 'fader' },
      onSave: vi.fn(),
      onClose: vi.fn(),
    });
    expect(screen.queryByText('Beschleunigt')).toBeNull();
  });

  it('submits hardkey assignments', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'mc_click_1',
        bank: 1,
        kind: 'button',
        count: 1,
        initial: { action: 'hardkey', hardkey: 'GO' },
        onSave,
        onClose: vi.fn(),
      },
    });
    await fireEvent.click(screen.getByText('Speichern'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'hardkey', hardkey: 'GO' }),
    );
  });
});

describe('AssignDialog special mappings', () => {
  it('edits a screen-mode mapping without overwriting it', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'asl_bank',
        bank: 1,
        kind: 'button',
        count: 1,
        initial: { action: 'screen_mode' },
        onSave,
        onClose: vi.fn(),
      },
    });
    await fireEvent.click(screen.getByText('Speichern'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'screen_mode' }),
    );
  });

  it('edits a screen selection', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'screen2',
        bank: 1,
        kind: 'button',
        count: 1,
        initial: { action: 'screen', screen: 2 },
        onSave,
        onClose: vi.fn(),
      },
    });
    const input = screen.getByLabelText('Screen') as HTMLInputElement;
    await fireEvent.input(input, { target: { value: '4' } });
    await fireEvent.click(screen.getByText('Speichern'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'screen', screen: 4 }),
    );
  });
});

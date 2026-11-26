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

  it('defaults fader controls to targetKind = fader when initial is null', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'mc_fader_1',
        bank: 1,
        kind: 'fader',
        count: 1,
        initial: null,
        onSave,
        onClose: vi.fn(),
      },
    });
    expect((screen.getByLabelText('Art') as HTMLSelectElement).value).toBe('fader');
    expect(screen.queryByLabelText('Button')).toBeNull();

    await fireEvent.click(screen.getByText('Speichern'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'executor', targetKind: 'fader' }),
    );
  });

  it('defaults relative-encoder to encoder action and saves screen = 0 without HTML5 validation block', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'encoder.1',
        bank: 1,
        kind: 'relative-encoder',
        count: 1,
        initial: null,
        onSave,
        onClose: vi.fn(),
      },
    });
    expect((screen.getByLabelText('Aktion') as HTMLSelectElement).value).toBe('encoder');
    const screenSelect = screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement;
    expect(screenSelect.value).toBe('0');

    await fireEvent.click(screen.getByText('Speichern'));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ action: 'encoder', slot: 1, screen: 0 }),
    );
  });

  it('disables submit when multiple controls are selected with action = encoder', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'encoder.1',
        bank: 1,
        kind: 'relative-encoder',
        count: 2,
        initial: null,
        onSave,
        onClose: vi.fn(),
      },
    });
    expect(screen.getByText('Encoder-Ziele nur für ein einzelnes Control.')).toBeTruthy();
    const submitButton = screen.getByRole('button', { name: 'Speichern' }) as HTMLButtonElement;
    expect(submitButton.disabled).toBe(true);
  });

  it('renders inside a native dialog, closes on Escape, and triggers Belegung löschen', async () => {
    const onClose = vi.fn();
    const onClear = vi.fn().mockResolvedValue(undefined);
    const { container } = render(AssignDialog, {
      props: {
        control: 'mc_click_1',
        bank: 1,
        kind: 'button',
        count: 1,
        initial: { action: 'hardkey', hardkey: 'GO' },
        hasAssignment: true,
        onSave: vi.fn(),
        onClear,
        onClose,
      },
    });
    const dialog = container.querySelector('dialog');
    expect(dialog).toBeTruthy();
    expect(dialog?.hasAttribute('open')).toBe(true);

    await fireEvent.click(screen.getByText('Belegung löschen'));
    expect(onClear).toHaveBeenCalledTimes(1);

    await fireEvent.keyDown(dialog!, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
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

  it('rejects empty attribute name and refreshes Screen-Encoder when slot changes', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(AssignDialog, {
      props: {
        control: 'encoder.1',
        bank: 1,
        kind: 'relative-encoder',
        count: 1,
        initial: { action: 'encoder', slot: 1, screen: 8 },
        screenEncoders: { '1': 8, '2': 6 },
        onSave,
        onClose: vi.fn(),
      },
    });

    // Changing slot 1 -> 2 updates Screen-Encoder 8 -> 6
    await fireEvent.input(screen.getByLabelText('Slot'), { target: { value: '2' } });
    expect((screen.getByLabelText(/Screen-Encoder/) as HTMLSelectElement).value).toBe('6');

    // Switching to Attributname with empty attribute is rejected
    await fireEvent.change(screen.getByLabelText('Ziel'), { target: { value: 'attribute' } });
    await fireEvent.click(screen.getByText('Speichern'));
    expect(screen.getByRole('alert').textContent).toContain('Attributnamen');
    expect(onSave).not.toHaveBeenCalled();
  });
});

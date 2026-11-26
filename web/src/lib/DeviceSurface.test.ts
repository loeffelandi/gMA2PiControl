import { fireEvent, render, screen } from '@testing-library/svelte';
import { describe, expect, it, vi } from 'vitest';

import DeviceSurface from './DeviceSurface.svelte';
import type { DeviceLayout } from './api';

const layout: DeviceLayout = {
  profile: 'cherry-g86',
  columns: 4,
  rows: [
    {
      cells: [
        { label: 'Pause', control: 'pause_big', col_span: 2, row_span: 2, color: 'green', row: 1, col: 1 },
        { label: 'Frei', control: null, col_span: 1, row_span: 1, color: null, row: 1, col: 3 },
        { label: 'Fix', control: 'fix', col_span: 1, row_span: 1, color: 'red', row: 1, col: 4 },
      ],
    },
  ],
};

describe('DeviceSurface', () => {
  it('renders spans, colours and assignment labels', () => {
    render(DeviceSurface, {
      props: {
        layout,
        assignments: { pause_big: 'Exec 1 Fader', fix: 'GO' },
      },
    });

    const pause = screen.getByText('Pause').closest('button')!;
    expect(pause.getAttribute('style')).toContain('grid-column: 1 / span 2');
    expect(pause.getAttribute('style')).toContain('grid-row: 1 / span 2');
    expect(pause.getAttribute('style')).toContain('rgb(126, 203, 138)');
    expect(screen.getByText('Exec 1 Fader')).toBeTruthy();
    expect(screen.getByText('GO')).toBeTruthy();
  });

  it('toggles only cells that reference a control', async () => {
    const onToggle = vi.fn();
    render(DeviceSurface, { props: { layout, onToggle } });

    await fireEvent.click(screen.getByText('Fix'));
    expect(onToggle).toHaveBeenCalledWith('fix');

    await fireEvent.click(screen.getByText('Frei'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('marks selected controls', () => {
    render(DeviceSurface, { props: { layout, selected: ['fix'] } });
    expect(screen.getByText('Fix').closest('button')!.classList.contains('selected')).toBe(true);
  });

  it('highlights the active learn control and locks editing', async () => {
    const onToggle = vi.fn();
    render(DeviceSurface, {
      props: {
        layout,
        activeControl: 'fix',
        activeKind: 'button',
        interactive: false,
        onToggle,
      },
    });

    const fix = screen.getByText('Fix').closest('button')!;
    expect(fix.classList.contains('active')).toBe(true);
    expect(screen.getByText('● Drücken')).toBeTruthy();

    await fireEvent.click(screen.getByText('Fix'));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('uses light text on black keycaps and respects reduced motion + selector escaping', () => {
    const specialLayout: DeviceLayout = {
      profile: 'custom',
      columns: 2,
      rows: [
        {
          cells: [
            {
              label: 'Black Key',
              control: 'ctrl"quote\\1',
              col_span: 1,
              row_span: 1,
              color: 'black',
              row: 1,
              col: 1,
            },
            {
              label: 'White Key',
              control: 'encoder.1',
              col_span: 1,
              row_span: 1,
              color: 'white',
              row: 1,
              col: 2,
            },
          ],
        },
      ],
    };

    const scrollSpy = vi.fn();
    HTMLElement.prototype.scrollIntoView = scrollSpy;
    const matchMediaOrig = window.matchMedia;
    window.matchMedia = vi.fn().mockReturnValue({ matches: true });

    try {
      render(DeviceSurface, {
        props: {
          layout: specialLayout,
          activeControl: 'ctrl"quote\\1',
        },
      });

      const blackBtn = screen.getByText('Black Key').closest('button')!;
      const whiteBtn = screen.getByText('White Key').closest('button')!;
      expect(blackBtn.getAttribute('style')).toContain('color: var(--text)');
      expect(whiteBtn.getAttribute('style')).toContain('color: var(--on-accent)');
      expect(scrollSpy).toHaveBeenCalledWith({
        block: 'nearest',
        inline: 'nearest',
        behavior: 'auto',
      });
    } finally {
      window.matchMedia = matchMediaOrig;
    }
  });
});


describe('DeviceSurface confirmed assignments', () => {
  it('shows a checkmark when the assignment equals the printed label', () => {
    render(DeviceSurface, {
      props: { layout, assignments: { fix: 'FIX' } },
    });
    expect(screen.getByText('✓')).toBeTruthy();
  });

  it('shows a checkmark for a modifier whose hardkey matches the label', () => {
    const maLayout: DeviceLayout = {
      ...layout,
      columns: 1,
      rows: [
        {
          cells: [
            { label: 'MA', control: 'ma', col_span: 1, row_span: 1, color: 'white', row: 1, col: 1 },
          ],
        },
      ],
    };
    render(DeviceSurface, {
      props: { layout: maLayout, assignments: { ma: 'Modifier MA' } },
    });
    expect(screen.getByText('✓')).toBeTruthy();
  });

  it('keeps the text for a modifier with a different hardkey', () => {
    const maLayout: DeviceLayout = {
      ...layout,
      columns: 1,
      rows: [
        {
          cells: [
            { label: 'MA', control: 'ma', col_span: 1, row_span: 1, color: 'white', row: 1, col: 1 },
          ],
        },
      ],
    };
    render(DeviceSurface, {
      props: { layout: maLayout, assignments: { ma: 'Modifier FINE' } },
    });
    expect(screen.getByText('Modifier FINE')).toBeTruthy();
  });
});

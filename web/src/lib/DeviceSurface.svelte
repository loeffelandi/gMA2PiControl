<script lang="ts">
  import type { DeviceLayout, LayoutCell } from './api';

  interface Props {
    layout: DeviceLayout;
    assignments?: Record<string, string>;
    selected?: string[];
    activeControl?: string | null;
    activeKind?: string | null;
    interactive?: boolean;
    onToggle?: (control: string) => void;
  }

  let {
    layout,
    assignments = {},
    selected = [],
    activeControl = null,
    activeKind = null,
    interactive = true,
    onToggle,
  }: Props = $props();

  function hintFor(kind: string | null): string {
    if (kind === 'encoder' || kind === 'relative-encoder' || kind === 'poti') {
      return '↻ Drehen';
    }
    if (kind === 'fader') return '↕ Bewegen';
    return '● Drücken';
  }

  function escapeControl(value: string): string {
    return typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
      ? CSS.escape(value)
      : value.replace(/["\\]/g, '\\$&');
  }

  function scrollActive(target: string | null) {
    return (node: HTMLElement): void => {
      if (!target) return;
      const escaped = escapeControl(target);
      const element = node.querySelector<HTMLElement>(
        `[data-control="${escaped}"]`,
      );
      const reduced =
        typeof window !== 'undefined' &&
        Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches);
      element?.scrollIntoView?.({
        block: 'nearest',
        inline: 'nearest',
        behavior: reduced ? 'auto' : 'smooth',
      });
    };
  }

  const palette: Record<string, string> = {
    // Reale Keycap-Farben aus config.toml; bewusst außerhalb der UI-Tokens.
    green: '#7ecb8a',
    blue: '#8fc4e8',
    red: '#e79a8f',
    yellow: '#e8d27e',
    grey: '#c9c9c9',
    black: '#3b3b3b',
    white: '#f4f4f4',
  };

  function styleFor(cell: LayoutCell): string {
    const parts: string[] = [];
    if (cell.row !== null && cell.col !== null) {
      parts.push(`grid-row: ${cell.row} / span ${cell.row_span}`);
      parts.push(`grid-column: ${cell.col} / span ${cell.col_span}`);
    } else {
      parts.push(`grid-row: span ${cell.row_span}`);
      parts.push(`grid-column: span ${cell.col_span}`);
    }
    if (cell.color && palette[cell.color]) {
      parts.push(`background: ${palette[cell.color]}`);
      parts.push(
        cell.color === 'black' ? 'color: var(--text)' : 'color: var(--on-accent)',
      );
    }
    return parts.join('; ');
  }

  function normalize(text: string): string {
    return text.toLowerCase().replace(/[\s_+]/g, '');
  }

  function isConfirmed(value: string, label: string): boolean {
    if (normalize(value) === normalize(label)) return true;
    const prefix = 'Modifier ';
    return (
      value.startsWith(prefix) &&
      normalize(value.slice(prefix.length)) === normalize(label)
    );
  }

  function showAssignment(cell: LayoutCell): string | null {
    if (cell.control === null) return null;
    const value = assignments[cell.control] ?? 'frei';
    if (value !== 'frei' && isConfirmed(value, cell.label)) {
      return '✓';
    }
    return value;
  }

  const keyedCells = $derived.by(() => {
    const counts: Record<string, number> = Object.create(null);
    return layout.rows.flatMap((row, rowIdx) =>
      row.cells.map((cell, colIdx) => {
        const base =
          cell.control ??
          `${cell.row ?? rowIdx + 1}:${cell.col ?? colIdx + 1}:${cell.label}`;
        const n = (counts[base] ?? 0) + 1;
        counts[base] = n;
        return { key: n === 1 ? base : `${base}#${n}`, cell };
      }),
    );
  });
</script>

<div
  class="surface"
  data-testid="device-surface"
  {@attach scrollActive(activeControl)}
  style={`grid-template-columns: repeat(${layout.columns}, minmax(3.6rem, 1fr));`}
>
  {#each keyedCells as { key, cell } (key)}
    {@const assignment = showAssignment(cell)}
    <button
      type="button"
      class={[
        'cell',
        {
          selected: cell.control !== null && selected.includes(cell.control),
          active: cell.control !== null && cell.control === activeControl,
          static: cell.control === null,
        },
      ]}
      disabled={cell.control === null}
      data-control={cell.control ?? undefined}
      style={styleFor(cell)}
      onclick={() => {
        if (interactive && cell.control !== null) onToggle?.(cell.control);
      }}
    >
      <span class="label">{cell.label}</span>
      {#if assignment !== null}
        <span class="assignment">{assignment}</span>
      {/if}
      {#if cell.control !== null && cell.control === activeControl}
        <span class="active-hint">{hintFor(activeKind)}</span>
      {/if}
    </button>
  {/each}
</div>

<style>
  .surface {
    display: grid;
    width: 100%;
    grid-auto-rows: minmax(3.3rem, auto);
    gap: 0.3rem;
    padding: 0.6rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow-x: auto;
  }

  .cell {
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 3.3rem;
    min-width: 0;
    padding: 0.4rem 0.45rem;
    border: 1px solid var(--bg);
    border-radius: var(--radius);
    background: var(--surface-raised);
    color: var(--text);
    font-size: 0.85rem;
    text-align: left;
    overflow-wrap: normal;
    word-break: normal;
  }

  .cell.static {
    background: var(--surface-raised);
    color: var(--text-muted);
    cursor: default;
  }

  .cell.selected {
    outline: 2px solid var(--accent-hover);
    outline-offset: -1px;
  }

  .cell.active {
    z-index: 2;
    outline: 3px solid #ffd166;
    outline-offset: -2px;
    box-shadow:
      0 0 0 3px rgba(255, 209, 102, 0.35),
      0 0 14px rgba(255, 209, 102, 0.6);
    animation: learn-pulse 1.4s ease-in-out infinite;
  }

  .active-hint {
    position: absolute;
    top: 0.15rem;
    right: 0.2rem;
    padding: 0.05rem 0.25rem;
    border-radius: 0.2rem;
    background: rgba(0, 0, 0, 0.72);
    color: #ffe08a;
    font-size: 0.55rem;
    font-weight: 600;
    line-height: 1.25;
    letter-spacing: 0.02em;
    white-space: nowrap;
  }

  @keyframes learn-pulse {
    0%,
    100% {
      box-shadow:
        0 0 0 3px rgba(255, 209, 102, 0.35),
        0 0 14px rgba(255, 209, 102, 0.6);
    }
    50% {
      box-shadow:
        0 0 0 6px rgba(255, 209, 102, 0.2),
        0 0 26px rgba(255, 209, 102, 0.85);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .cell.active {
      animation: none;
    }
  }

  .label {
    font-weight: 500;
    line-height: 1.15;
    overflow-wrap: normal;
    word-break: normal;
  }

  .assignment {
    margin-top: 0.2rem;
    font-size: 0.66rem;
    line-height: 1.15;
    opacity: 0.8;
    overflow-wrap: normal;
    word-break: normal;
  }
</style>

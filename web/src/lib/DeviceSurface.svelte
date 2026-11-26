<script lang="ts">
  import type { DeviceLayout, LayoutCell } from './api';

  interface Props {
    layout: DeviceLayout;
    assignments?: Record<string, string>;
    selected?: string[];
    onToggle?: (control: string) => void;
  }

  let { layout, assignments = {}, selected = [], onToggle }: Props = $props();

  const palette: Record<string, string> = {
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
    }
    return parts.join('; ');
  }

  function normalize(text: string): string {
    return text.toLowerCase().replace(/[\s_+]/g, '');
  }

  function showAssignment(cell: LayoutCell): string | null {
    if (cell.control === null) return null;
    const value = assignments[cell.control] ?? 'frei';
    if (value !== 'frei' && normalize(value) === normalize(cell.label)) {
      return '✓';
    }
    return value;
  }

  const cells = $derived(
    layout.rows.flatMap((row) => row.cells),
  );
</script>

<div
  class="surface"
  data-testid="device-surface"
  style={`grid-template-columns: repeat(${layout.columns}, minmax(3.6rem, 1fr));`}
>
  {#each cells as cell}
    {@const assignment = showAssignment(cell)}
    <button
      type="button"
      class="cell"
      class:selected={cell.control !== null && selected.includes(cell.control)}
      class:static={cell.control === null}
      disabled={cell.control === null}
      style={styleFor(cell)}
      onclick={() => cell.control !== null && onToggle?.(cell.control)}
    >
      <span class="label">{cell.label}</span>
      {#if assignment !== null}
        <span class="assignment">{assignment}</span>
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
    background: #1f242b;
    border-radius: 0.5rem;
    overflow-x: auto;
  }

  .cell {
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    min-height: 3.3rem;
    min-width: 0;
    padding: 0.4rem 0.45rem;
    border: 1px solid #0c0f12;
    border-radius: 0.25rem;
    color: #111;
    font-size: 0.85rem;
    text-align: left;
    overflow-wrap: normal;
    word-break: normal;
  }

  .cell.static {
    background: #2c333d;
    color: #98a4b3;
    cursor: default;
  }

  .cell.selected {
    outline: 2px solid #ffb347;
    outline-offset: -1px;
  }

  .label {
    font-weight: 700;
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

/**
 * Shared chart configuration.
 *
 * Colours are referenced as CSS custom properties (`var(--viz-1)`) rather than
 * resolved hex strings. SVG `fill` and `stroke` accept them, which means a
 * theme switch repaints every chart with no React state, no re-render and no
 * risk of the light palette leaking into dark mode.
 *
 * The categorical order is fixed and never cycled: colour follows the entity,
 * so a filter that removes a series must not repaint the survivors.
 */

/** Fixed categorical order. Slot 7+ folds into "Other" rather than inventing a hue. */
export const VIZ_SERIES = [
  'var(--viz-1)',
  'var(--viz-2)',
  'var(--viz-3)',
  'var(--viz-4)',
  'var(--viz-5)',
  'var(--viz-6)',
] as const;

/** Status colours are reserved — never reused as "series 5". */
export const SEVERITY_COLORS = {
  critical: 'var(--critical)',
  high: 'var(--high)',
  medium: 'var(--medium)',
  low: 'var(--low)',
} as const;

export const CHART_GRID = 'var(--viz-grid)';
export const CHART_AXIS = 'var(--viz-axis)';

/** Axis tick styling, applied identically everywhere. */
export const AXIS_TICK = {
  fill: 'var(--fg-subtle)',
  fontSize: 11,
} as const;

/** Recessive grid: present enough to read a value against, never competing. */
export const GRID_PROPS = {
  stroke: CHART_GRID,
  strokeDasharray: '0',
  vertical: false,
} as const;

/** Rounded data-ends on the free end of a horizontal bar, square at the baseline. */
export const BAR_RADIUS: [number, number, number, number] = [0, 4, 4, 0];

/** Same, for a vertical bar. */
export const COLUMN_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

export const CHART_MARGIN = { top: 8, right: 16, bottom: 0, left: 0 } as const;

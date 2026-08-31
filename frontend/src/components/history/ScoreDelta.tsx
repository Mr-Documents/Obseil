import { ArrowRight, Minus, TrendingDown, TrendingUp } from 'lucide-react';

import type { ComparisonDirection } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatDelta, formatNumber } from '@/utils/format';

/**
 * A change, shown with its meaning rather than just its sign.
 *
 * "Neutral" metrics — row count, column count — get a plain arrow and neutral
 * ink. Colouring "more rows" green would tell the reader something untrue.
 */
const TONE: Record<ComparisonDirection, string> = {
  improved: 'text-success',
  regressed: 'text-danger',
  unchanged: 'text-fg-subtle',
  changed: 'text-fg-muted',
};

const ICON = {
  improved: TrendingUp,
  regressed: TrendingDown,
  unchanged: Minus,
  changed: ArrowRight,
} as const;

export function ScoreDelta({
  delta,
  direction,
  digits = 0,
  unit,
  className,
}: {
  delta: number | null;
  direction: ComparisonDirection;
  digits?: number;
  unit?: string | null;
  className?: string;
}) {
  const Icon = ICON[direction];
  const label =
    delta === null ? '—' : direction === 'unchanged' ? 'no change' : formatDelta(delta, digits);

  return (
    <span
      className={cn(
        'tabular inline-flex items-center gap-1 font-medium',
        TONE[direction],
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden="true" />
      {label}
      {unit && delta !== null && direction !== 'unchanged' && (
        // "%" binds to the number; a word unit like "pts" takes a space.
        <span className={cn('font-normal opacity-80', unit === '%' && '-ml-1')}>{unit}</span>
      )}
    </span>
  );
}

/** "78 → 87" — the two values that produced the delta. */
export function BeforeAfter({
  baseline,
  current,
  digits = 0,
}: {
  baseline: number | null;
  current: number | null;
  digits?: number;
}) {
  return (
    <span className="tabular inline-flex items-center gap-1.5 text-fg-muted">
      <span>{formatNumber(baseline, digits)}</span>
      <ArrowRight className="size-3 text-fg-subtle" aria-hidden="true" />
      <span className="font-medium text-fg">{formatNumber(current, digits)}</span>
    </span>
  );
}

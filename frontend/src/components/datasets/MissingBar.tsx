import { cn } from '@/utils/cn';
import { formatPercent } from '@/utils/format';

/**
 * A one-line completeness meter for a column.
 *
 * The colour follows the same severity bands the quality engine uses, so a bar
 * that looks alarming in the explorer corresponds to a finding that is actually
 * severe - the visual and the data never disagree.
 */
export function MissingBar({ percentage, className }: { percentage: number; className?: string }) {
  const tone =
    percentage >= 50
      ? 'bg-critical'
      : percentage >= 30
        ? 'bg-high'
        : percentage >= 10
          ? 'bg-medium'
          : percentage > 0
            ? 'bg-low'
            : 'bg-success';

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div
        className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-surface-muted"
        role="img"
        aria-label={`${formatPercent(percentage)} missing`}
      >
        <div
          className={cn('h-full rounded-full', tone)}
          style={{ width: `${Math.min(Math.max(percentage, percentage > 0 ? 3 : 0), 100)}%` }}
        />
      </div>
      <span className="tabular text-[13px] text-fg-muted">{formatPercent(percentage)}</span>
    </div>
  );
}

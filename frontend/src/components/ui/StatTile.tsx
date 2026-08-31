import { type LucideIcon } from 'lucide-react';
import { type ReactNode } from 'react';

import { cn } from '@/utils/cn';

interface StatTileProps {
  label: string;
  value: ReactNode;
  /** Secondary line: a share, a comparison, a unit. */
  detail?: ReactNode;
  icon?: LucideIcon;
  tone?: 'neutral' | 'critical' | 'high' | 'medium' | 'low' | 'success';
  className?: string;
}

const TONES = {
  neutral: 'text-fg',
  critical: 'text-critical',
  high: 'text-high',
  medium: 'text-medium',
  low: 'text-low',
  success: 'text-success',
} as const;

/**
 * A single headline figure. Deliberately plain: the number is the content, and
 * anything competing with it — a chart, a gradient, a badge — makes a dense
 * row of tiles harder to scan, not easier.
 */
export function StatTile({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'neutral',
  className,
}: StatTileProps) {
  return (
    <div className={cn('rounded-card border border-border-default bg-surface p-4', className)}>
      <div className="flex items-center gap-1.5">
        {Icon && <Icon className="size-3.5 text-fg-subtle" aria-hidden="true" />}
        <p className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">{label}</p>
      </div>
      <p className={cn('tabular mt-2 text-2xl font-semibold tracking-[-0.02em]', TONES[tone])}>
        {value}
      </p>
      {detail && <p className="mt-1 text-[13px] text-fg-muted">{detail}</p>}
    </div>
  );
}

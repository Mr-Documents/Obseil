import { type ReactNode } from 'react';

import { cn } from '@/utils/cn';

export type BadgeTone =
  'neutral' | 'accent' | 'critical' | 'high' | 'medium' | 'low' | 'success' | 'warning';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-surface-muted text-fg-muted border-border-default',
  accent: 'bg-accent-soft text-accent border-transparent',
  critical: 'bg-critical-soft text-critical border-transparent',
  high: 'bg-high-soft text-high border-transparent',
  medium: 'bg-medium-soft text-medium border-transparent',
  low: 'bg-low-soft text-low border-transparent',
  success: 'bg-success-soft text-success border-transparent',
  warning: 'bg-warning-soft text-warning border-transparent',
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  /** Adds a small filled dot — useful for severity and status pills. */
  dot?: boolean;
  className?: string;
  size?: 'sm' | 'md';
}

export function Badge({
  children,
  tone = 'neutral',
  dot = false,
  size = 'sm',
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border font-medium whitespace-nowrap',
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
        TONES[tone],
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  );
}

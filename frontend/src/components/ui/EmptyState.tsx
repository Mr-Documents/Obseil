import { type LucideIcon } from 'lucide-react';
import { type ReactNode } from 'react';

import { cn } from '@/utils/cn';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  /** One sentence explaining what the user can do next - never just "No data". */
  description?: string;
  action?: ReactNode;
  className?: string;
  size?: 'sm' | 'md';
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  size = 'md',
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        size === 'md' ? 'px-6 py-14' : 'px-4 py-9',
        className,
      )}
    >
      {Icon && (
        <div
          className={cn(
            'mb-4 flex items-center justify-center rounded-xl border border-border-default bg-surface-muted text-fg-subtle',
            size === 'md' ? 'size-11' : 'size-9',
          )}
        >
          <Icon className={size === 'md' ? 'size-5' : 'size-4'} aria-hidden="true" />
        </div>
      )}
      <p className={cn('font-medium text-fg', size === 'md' ? 'text-[15px]' : 'text-sm')}>
        {title}
      </p>
      {description && (
        <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-fg-muted">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

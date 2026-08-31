import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import { type ReactNode } from 'react';

import { cn } from '@/utils/cn';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<AlertTone, { wrapper: string; icon: typeof Info }> = {
  info: { wrapper: 'border-border-default bg-surface-muted text-fg', icon: Info },
  success: { wrapper: 'border-transparent bg-success-soft text-success', icon: CheckCircle2 },
  warning: { wrapper: 'border-transparent bg-warning-soft text-warning', icon: AlertTriangle },
  danger: { wrapper: 'border-transparent bg-danger-soft text-danger', icon: XCircle },
};

interface AlertProps {
  tone?: AlertTone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
}

/**
 * Inline message block. Error alerts use `role="alert"` so screen readers
 * announce a failed submission without the user having to hunt for it.
 */
export function Alert({ tone = 'info', title, children, className, action }: AlertProps) {
  const { wrapper, icon: Icon } = TONES[tone];
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      className={cn('flex gap-3 rounded-lg border px-4 py-3 text-[13px]', wrapper, className)}
    >
      <Icon className="mt-px size-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && (
          <div className={cn('leading-relaxed', title && 'mt-1 opacity-90')}>{children}</div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

import { type HTMLAttributes, type ReactNode } from 'react';

import { cn } from '@/utils/cn';

/**
 * The surface primitive: a hairline border on a raised background. Elevation
 * comes from the border rather than a shadow, which keeps dense dashboards
 * calm. `interactive` adds hover affordance for cards that are links.
 */
export function Card({
  className,
  interactive = false,
  ...props
}: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        'rounded-card border border-border-default bg-surface',
        interactive &&
          'transition-colors duration-150 hover:border-border-strong hover:bg-surface-hover',
        className,
      )}
      {...props}
    />
  );
}

interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Right-aligned controls: filters, menus, "view all" links. */
  action?: ReactNode;
  className?: string;
}

export function CardHeader({ title, description, action, className }: CardHeaderProps) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-start justify-between gap-3 border-b border-border-default px-5 py-4',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-sm font-semibold tracking-[-0.01em] text-fg">{title}</h2>
        {description && (
          <p className="mt-1 text-[13px] leading-relaxed text-fg-muted">{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('p-5', className)} {...props} />;
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-3 border-t border-border-default px-5 py-3',
        className,
      )}
      {...props}
    />
  );
}

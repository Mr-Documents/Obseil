import { type ReactNode } from 'react';

import { cn } from '@/utils/cn';

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Primary actions, right-aligned on wide screens and stacked on mobile. */
  actions?: ReactNode;
  /** Breadcrumbs or a back link, rendered above the title. */
  eyebrow?: ReactNode;
  /** Tabs or filters, rendered flush with the bottom border. */
  children?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  children,
  className,
}: PageHeaderProps) {
  return (
    <div className={cn('border-b border-border-default bg-surface', className)}>
      <div className="mx-auto max-w-7xl px-5 pt-6 sm:px-8">
        {eyebrow && <div className="mb-3">{eyebrow}</div>}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-[-0.02em] text-fg sm:text-2xl">
              {title}
            </h1>
            {description && (
              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-fg-muted">
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
        </div>
        <div className={cn(children ? 'mt-5' : 'pb-6')}>{children}</div>
      </div>
    </div>
  );
}

/** Standard content well: consistent max width and gutters on every page. */
export function PageContent({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('mx-auto max-w-7xl px-5 py-6 sm:px-8 sm:py-8', className)}>{children}</div>
  );
}

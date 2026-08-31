import { type HTMLAttributes, type ReactNode, type ThHTMLAttributes } from 'react';

import { cn } from '@/utils/cn';

/**
 * Table primitives.
 *
 * `TableScroller` is the important one: wide data tables scroll *inside their
 * own container* rather than pushing the page sideways. Nothing in Obseil is
 * allowed to cause horizontal page scroll, which is the single most common way
 * a data dashboard breaks on a phone.
 */
export function TableScroller({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('w-full overflow-x-auto overscroll-x-contain', className)}>{children}</div>
  );
}

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return <table className={cn('w-full border-collapse text-sm', className)} {...props} />;
}

export function THead({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={cn('border-b border-border-default bg-surface-muted', className)}
      {...props}
    />
  );
}

export function TBody({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn('divide-y divide-border-default', className)} {...props} />;
}

export function TR({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn('transition-colors hover:bg-surface-hover', className)} {...props} />;
}

interface THProps extends ThHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
}

export function TH({ className, numeric, ...props }: THProps) {
  return (
    <th
      scope="col"
      className={cn(
        'whitespace-nowrap px-4 py-2.5 text-left text-[12px] font-medium uppercase tracking-wide text-fg-subtle',
        numeric && 'text-right',
        className,
      )}
      {...props}
    />
  );
}

export function TD({
  className,
  numeric,
  ...props
}: HTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      className={cn('px-4 py-2.5 text-[13px] text-fg', numeric && 'tabular text-right', className)}
      {...props}
    />
  );
}

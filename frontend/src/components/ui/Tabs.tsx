import { NavLink } from 'react-router-dom';

import { cn } from '@/utils/cn';

export interface TabDefinition {
  to: string;
  label: string;
  /** Rendered as a small count pill beside the label. */
  count?: number | null;
  end?: boolean;
}

/**
 * Route-driven tabs.
 *
 * Tabs are links, not buttons: each view gets its own URL, so it can be
 * bookmarked, shared and reached with the browser's back button. On narrow
 * screens the strip scrolls horizontally inside itself rather than wrapping.
 */
export function Tabs({ items, className }: { items: TabDefinition[]; className?: string }) {
  return (
    <div className={cn('-mb-px overflow-x-auto', className)}>
      <nav className="flex min-w-max gap-1" aria-label="Dataset views">
        {items.map(({ to, label, count, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors',
                isActive
                  ? 'border-accent text-fg'
                  : 'border-transparent text-fg-muted hover:text-fg',
              )
            }
          >
            {label}
            {count !== undefined && count !== null && (
              <span className="tabular rounded-full bg-surface-muted px-1.5 py-0.5 text-[11px] text-fg-subtle">
                {count}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

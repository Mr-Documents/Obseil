import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';

import { cn } from '@/utils/cn';

export interface TabDefinition {
  to: string;
  label: string;
  /** Rendered as a small count pill beside the label. */
  count?: number | null;
  end?: boolean;
}

/** How much of the strip a fade covers. Wide enough to read as "there is more". */
const FADE = 'pointer-events-none absolute inset-y-0 w-8 transition-opacity duration-150';

/**
 * Route-driven tabs.
 *
 * Tabs are links, not buttons: each view gets its own URL, so it can be
 * bookmarked, shared and reached with the browser's back button. On narrow
 * screens the strip scrolls horizontally inside itself rather than wrapping.
 *
 * Horizontal scrolling on its own is a trap: at a phone width the last tab sits
 * entirely off-screen with nothing to suggest it exists. Two things fix that —
 * a fade on whichever edge still has content behind it, and scrolling the
 * active tab into view so a deep link never opens on a strip that looks like it
 * is showing a different page.
 */
export function Tabs({ items, className }: { items: TabDefinition[]; className?: string }) {
  const scroller = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: false, end: false });
  const { pathname } = useLocation();

  const measure = useCallback(() => {
    const element = scroller.current;
    if (!element) return;
    const remaining = element.scrollWidth - element.clientWidth - element.scrollLeft;
    setEdges({ start: element.scrollLeft > 1, end: remaining > 1 });
  }, []);

  // Before paint, so the strip never flashes with the wrong tab in view.
  useLayoutEffect(() => {
    scroller.current
      ?.querySelector('[aria-current="page"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    measure();
  }, [measure, pathname, items.length]);

  useEffect(() => {
    const element = scroller.current;
    if (!element || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [measure]);

  return (
    <div className={cn('relative -mb-px', className)}>
      <div ref={scroller} onScroll={measure} className="overflow-x-auto">
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

      {/* Decorative: the tabs themselves remain reachable by keyboard and by
          screen reader regardless of what is currently scrolled into view. */}
      <div
        aria-hidden
        className={cn(
          FADE,
          'left-0 bg-gradient-to-r from-surface to-transparent',
          edges.start ? 'opacity-100' : 'opacity-0',
        )}
      />
      <div
        aria-hidden
        className={cn(
          FADE,
          'right-0 bg-gradient-to-l from-surface to-transparent',
          edges.end ? 'opacity-100' : 'opacity-0',
        )}
      />
    </div>
  );
}

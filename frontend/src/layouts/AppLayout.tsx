import { FolderKanban, LogOut, Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';

import { Logo } from '@/components/brand/Logo';
import { Button } from '@/components/ui/Button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { useAuth } from '@/hooks/authContext';
import { cn } from '@/utils/cn';

const NAV_ITEMS = [{ to: '/projects', label: 'Projects', icon: FolderKanban }];

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="space-y-0.5" aria-label="Main">
      {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-accent-soft text-accent'
                : 'text-fg-muted hover:bg-surface-hover hover:text-fg',
            )
          }
        >
          <Icon className="size-4 shrink-0" aria-hidden="true" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function AccountPanel({ compact = false }: { compact?: boolean }) {
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <div className={cn('border-t border-border-default pt-3', compact ? 'px-0' : 'px-0')}>
      <div className="flex items-center gap-2.5 px-2.5 py-1.5">
        <span
          aria-hidden="true"
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent"
        >
          {initials(user.full_name)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-fg">{user.full_name}</p>
          <p className="truncate text-xs text-fg-subtle">{user.email}</p>
        </div>
      </div>
      <div className="mt-2 flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          leadingIcon={<LogOut className="size-4" />}
          onClick={() => void logout()}
          className="flex-1 justify-start"
        >
          Sign out
        </Button>
        <ThemeToggle />
      </div>
    </div>
  );
}

/**
 * Authenticated shell.
 *
 * Desktop gets a persistent sidebar; below `lg` the same navigation becomes a
 * slide-over drawer opened from a compact top bar. The two are built from the
 * same `NavItems` component so they can never drift apart.
 */
export function AppLayout() {
  const [isDrawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Navigating always closes the drawer, including via browser back/forward.
  useEffect(() => setDrawerOpen(false), [location.pathname]);

  // Escape closes the drawer, and the page behind it must not scroll.
  useEffect(() => {
    if (!isDrawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = '';
    };
  }, [isDrawerOpen]);

  return (
    <div className="min-h-dvh bg-canvas">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col border-r border-border-default bg-surface px-3 py-4 lg:flex">
        <Link to="/projects" className="mb-6 rounded-lg px-2.5" aria-label="Obseil home">
          <Logo />
        </Link>
        <div className="flex-1 overflow-y-auto">
          <NavItems />
        </div>
        <AccountPanel />
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border-default bg-surface/95 px-4 backdrop-blur lg:hidden">
        <Link to="/projects" className="rounded-lg" aria-label="Obseil home">
          <Logo size="sm" />
        </Link>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setDrawerOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={isDrawerOpen}
        >
          <Menu className="size-5" aria-hidden="true" />
        </Button>
      </header>

      {/* Mobile drawer */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation menu"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 h-full w-full cursor-default bg-black/40 animate-fade-in"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
            className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] animate-slide-up flex-col border-l border-border-default bg-surface px-3 py-4"
          >
            <div className="mb-6 flex items-center justify-between px-2.5">
              <Logo size="sm" />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close navigation menu"
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <NavItems onNavigate={() => setDrawerOpen(false)} />
            </div>
            <AccountPanel compact />
          </div>
        </div>
      )}

      <main id="main" className="lg:pl-60">
        <Outlet />
      </main>
    </div>
  );
}

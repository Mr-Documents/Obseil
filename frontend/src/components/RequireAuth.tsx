import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { Logo } from '@/components/brand/Logo';
import { Spinner } from '@/components/ui/Spinner';
import { useAuth } from '@/hooks/authContext';

/** Where the user was heading before they were asked to sign in. */
interface LocationState {
  from?: string;
}

/**
 * Route guard for the authenticated area.
 *
 * While the stored token is being verified it renders a calm splash rather
 * than bouncing the user to the login screen and back — a redirect flash on
 * every reload is the most common way SPA auth feels broken.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-canvas">
        <Logo size="lg" />
        <Spinner className="size-5 text-fg-subtle" label="Restoring your session" />
      </div>
    );
  }

  if (status === 'anonymous') {
    // `state.from` lets the login page return the user where they were headed.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <>{children}</>;
}

/**
 * Inverse guard: keeps a signed-in user off the login and register screens.
 *
 * It honours the same `state.from` that `RequireAuth` sets. This guard runs
 * the moment the session becomes authenticated — before the login page's own
 * `navigate` can — so without reading `from` here it would race the deep-link
 * redirect and always win, dumping the user on the projects list instead of
 * the page they originally asked for.
 */
export function RedirectIfAuthenticated({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-canvas">
        <Spinner className="size-5 text-fg-subtle" label="Loading" />
      </div>
    );
  }

  if (status === 'authenticated') {
    const destination = (location.state as LocationState | null)?.from ?? '/projects';
    return <Navigate to={destination} replace />;
  }

  return <>{children}</>;
}

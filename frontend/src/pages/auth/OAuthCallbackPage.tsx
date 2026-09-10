import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { Alert } from '@/components/ui/Alert';
import { buttonStyles } from '@/components/ui/buttonStyles';
import { Spinner } from '@/components/ui/Spinner';
import { useAuth } from '@/hooks/authContext';

/**
 * Where the API sends the browser back after a provider sign-in.
 *
 * It arrives with either a single-use `code` to exchange, or an `error` to
 * explain. Nothing else: no tokens are ever in this URL, which is the reason
 * the handoff code exists at all.
 */
export function OAuthCallbackPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { completeOAuth } = useAuth();
  const [error, setError] = useState<string | null>(params.get('error'));

  // React 18's StrictMode mounts effects twice in development. The code is
  // single-use, so a second exchange would fail and show a spurious error.
  const attempted = useRef(false);

  useEffect(() => {
    const code = params.get('code');
    if (!code || attempted.current) return;
    attempted.current = true;

    completeOAuth(code)
      .then(() => navigate('/projects', { replace: true }))
      .catch((cause: unknown) => {
        setError(
          cause instanceof Error
            ? cause.message
            : 'That sign-in link has expired. Please try again.',
        );
      });
  }, [completeOAuth, navigate, params]);

  if (error) {
    return (
      <div className="mx-auto w-full max-w-sm space-y-4">
        <Alert tone="danger" title="Could not sign you in">
          {error}
        </Alert>
        <Link to="/login" className={buttonStyles({ variant: 'secondary', className: 'w-full' })}>
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <div
      className="mx-auto flex w-full max-w-sm flex-col items-center gap-3 py-8"
      role="status"
      aria-live="polite"
    >
      <Spinner />
      <p className="text-sm text-fg-muted">Finishing sign-in...</p>
    </div>
  );
}

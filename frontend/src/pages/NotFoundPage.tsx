import { MoveLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Logo } from '@/components/brand/Logo';
import { buttonStyles } from '@/components/ui/buttonStyles';

export function NotFoundPage() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-6 bg-canvas px-6 text-center">
      <Logo size="lg" />
      <div>
        <p className="font-mono text-sm text-fg-subtle">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.02em] text-fg">
          We couldn&rsquo;t find that page
        </h1>
        <p className="mt-2 max-w-md text-sm leading-relaxed text-fg-muted">
          The page may have been moved, or the link may be out of date.
        </p>
      </div>
      <Link to="/" className={buttonStyles({ variant: 'secondary' })}>
        <MoveLeft className="size-4" aria-hidden="true" />
        Back to Obseil
      </Link>
    </div>
  );
}

import { type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Logo } from '@/components/brand/Logo';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

interface AuthLayoutProps {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

/**
 * Single-column layout for sign-in and registration.
 *
 * Deliberately not a split-screen hero: on a phone the marketing half is dead
 * weight above the fold, and the form is the only thing anyone came here for.
 */
export function AuthLayout({ title, subtitle, children, footer }: AuthLayoutProps) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="flex items-center justify-between px-5 py-5 sm:px-8">
        <Link to="/" className="rounded-lg" aria-label="Obseil home">
          <Logo />
        </Link>
        <ThemeToggle />
      </header>

      <main className="flex flex-1 items-center justify-center px-5 py-8 sm:px-8">
        <div className="w-full max-w-[26rem]">
          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-fg">{title}</h1>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">{subtitle}</p>
          <div className="mt-7">{children}</div>
          <div className="mt-6 text-center text-[13px] text-fg-muted">{footer}</div>
        </div>
      </main>

      <footer className="px-5 py-6 text-center text-xs text-fg-subtle sm:px-8">
        Obseil - uncover what&rsquo;s hidden in your data.
      </footer>
    </div>
  );
}

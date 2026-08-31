import { ArrowRight, Fingerprint, GitCompareArrows, ScanSearch, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Logo } from '@/components/brand/Logo';
import { buttonStyles } from '@/components/ui/buttonStyles';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

const CAPABILITIES = [
  {
    icon: ScanSearch,
    title: 'Automatic profiling',
    body: 'Schema, inferred types, distributions and per-column statistics the moment a file lands.',
  },
  {
    icon: ShieldCheck,
    title: 'Deterministic quality checks',
    body: 'Missingness, duplicates, invalid values, constant columns and statistical outliers - with the method shown.',
  },
  {
    icon: Fingerprint,
    title: 'ML anomaly detection',
    body: 'An Isolation Forest surfaces rows that are unusual across several columns at once, where no single value looks wrong.',
  },
  {
    icon: GitCompareArrows,
    title: 'Scores you can argue with',
    body: 'One 0-100 number, every penalty itemised, and a diff against the previous run.',
  },
];

/**
 * Public landing page. Deliberately restrained: one claim, one action, and a
 * short honest description of what the product actually does.
 */
export function LandingPage() {
  return (
    <div className="min-h-dvh bg-canvas">
      <a href="#main" className="skip-link">
        Skip to content
      </a>

      <header className="border-b border-border-default">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
          <Logo />
          <nav className="flex items-center gap-1.5">
            <ThemeToggle />
            <Link
              to="/login"
              className={buttonStyles({
                variant: 'ghost',
                size: 'sm',
                className: 'hidden sm:inline-flex',
              })}
            >
              Sign in
            </Link>
            <Link to="/register" className={buttonStyles({ variant: 'primary', size: 'sm' })}>
              Get started
            </Link>
          </nav>
        </div>
      </header>

      <main id="main">
        <section className="mx-auto max-w-6xl px-5 pb-20 pt-16 sm:px-8 sm:pt-24">
          <p className="text-[13px] font-medium uppercase tracking-wide text-accent">
            Data quality intelligence
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-[1.08] tracking-[-0.03em] text-fg sm:text-5xl lg:text-6xl">
            Uncover what&rsquo;s hidden in your data.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-relaxed text-fg-muted sm:text-lg">
            Obseil profiles a dataset, runs a suite of quality detectors and an unsupervised anomaly
            model, then answers the only question that matters before you build on it:{' '}
            <span className="text-fg">can I trust this?</span>
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/register" className={buttonStyles({ variant: 'primary', size: 'lg' })}>
              Analyse a dataset
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
            <Link to="/login" className={buttonStyles({ variant: 'secondary', size: 'lg' })}>
              Sign in
            </Link>
          </div>
        </section>

        <section className="border-t border-border-default bg-surface">
          <div className="mx-auto grid max-w-6xl px-5 sm:px-8 md:grid-cols-2 lg:grid-cols-4 lg:px-0">
            {CAPABILITIES.map(({ icon: Icon, title, body }) => (
              <div
                key={title}
                className="py-7 lg:border-r lg:border-border-default lg:px-7 lg:last:border-r-0"
              >
                <Icon className="size-5 text-accent" aria-hidden="true" />
                <h2 className="mt-4 text-sm font-semibold tracking-[-0.01em] text-fg">{title}</h2>
                <p className="mt-2 text-[13px] leading-relaxed text-fg-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-border-default">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-5 py-8 text-[13px] text-fg-subtle sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <span>Obseil - open-source data quality intelligence.</span>
          <a
            href="https://github.com/Obseil"
            className="transition-colors hover:text-fg"
            target="_blank"
            rel="noreferrer noopener"
          >
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}

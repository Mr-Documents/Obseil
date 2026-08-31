import { cn } from '@/utils/cn';

/**
 * Indeterminate progress indicator. Decorative by default — the surrounding
 * control is expected to carry `aria-busy`, so screen readers are not spammed
 * with a redundant "loading" announcement.
 */
export function Spinner({ className, label }: { className?: string; label?: string }) {
  return (
    <span
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn('inline-block', className)}
    >
      <svg viewBox="0 0 24 24" fill="none" className="size-full animate-spin">
        <circle cx="12" cy="12" r="9.5" stroke="currentColor" strokeWidth="2.5" opacity="0.2" />
        <path
          d="M21.5 12a9.5 9.5 0 0 0-9.5-9.5"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

import { cn } from '@/utils/cn';

/**
 * The Obseil mark: a lens ring with a solid pupil and two alignment ticks.
 * It reads as "looking closely at something", scales down to a 16px favicon,
 * and is drawn with `currentColor` so it inherits the surrounding text colour.
 */
export function ObseilMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className={cn('size-7 shrink-0', className)}
    >
      <rect width="32" height="32" rx="8" className="fill-accent" />
      <circle cx="16" cy="16" r="8.5" stroke="white" strokeWidth="2" strokeOpacity="0.55" />
      <circle cx="16" cy="16" r="3.25" fill="white" />
      <path
        d="M16 3.5V7"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeOpacity="0.9"
      />
      <path
        d="M16 25V28.5"
        stroke="white"
        strokeWidth="2"
        strokeLinecap="round"
        strokeOpacity="0.9"
      />
    </svg>
  );
}

interface LogoProps {
  className?: string;
  /** Show the tagline beneath the wordmark. Used on the marketing and auth screens. */
  withTagline?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

const WORDMARK_SIZE = {
  sm: 'text-base',
  md: 'text-lg',
  lg: 'text-2xl',
} as const;

const MARK_SIZE = {
  sm: 'size-6',
  md: 'size-7',
  lg: 'size-9',
} as const;

export function Logo({ className, withTagline = false, size = 'md' }: LogoProps) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <ObseilMark className={MARK_SIZE[size]} />
      <div className="min-w-0">
        <span
          className={cn(
            'block font-semibold tracking-[-0.02em] text-fg leading-none',
            WORDMARK_SIZE[size],
          )}
        >
          Obseil
        </span>
        {withTagline && (
          <span className="mt-1 block text-xs text-fg-subtle leading-none">
            Uncover what&rsquo;s hidden in your data.
          </span>
        )}
      </div>
    </div>
  );
}

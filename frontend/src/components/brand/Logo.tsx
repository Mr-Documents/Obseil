import { cn } from '@/utils/cn';

/**
 * The Obseil mark: a Q built from a lens ring, with a rising bar chart inside
 * and a sparkle for the part a rule cannot see.
 *
 * It is a **badge**, not a glyph - the deep navy tile is part of the brand and
 * is kept in both themes, the way an app icon is. What adapts is the edge: the
 * ring below is drawn from theme tokens so the rounded corners read crisply on
 * a light surface and do not float on a dark one.
 *
 * Ids inside an inline SVG are global to the document, so the gradients are
 * namespaced. Two marks on one page would otherwise fight over them.
 *
 * Kept in step with `public/obseil-mark.svg`, which the browser needs as a file
 * for the favicon. Change both together.
 */
export function ObseilMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      // 22% is `rx="14"` over a 64 viewBox, so the CSS corner the ring follows
      // lands exactly on the tile's own corner at every size. An `em` radius
      // would drift with whatever font-size the mark happens to sit in.
      className={cn('size-7 shrink-0 rounded-[22%] ring-1 ring-border-default/70', className)}
    >
      <defs>
        <linearGradient
          id="obseil-ring"
          x1="10"
          y1="52"
          x2="54"
          y2="12"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#7C5CF0" />
          <stop offset="0.45" stopColor="#4C7DF0" />
          <stop offset="1" stopColor="#3ECF8E" />
        </linearGradient>
        <linearGradient
          id="obseil-bars"
          x1="22"
          y1="42"
          x2="42"
          y2="22"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#35C7A5" />
          <stop offset="1" stopColor="#4ADE9B" />
        </linearGradient>
        <linearGradient
          id="obseil-spark"
          x1="46"
          y1="20"
          x2="56"
          y2="10"
          gradientUnits="userSpaceOnUse"
        >
          <stop offset="0" stopColor="#6AA8F5" />
          <stop offset="1" stopColor="#4ADE9B" />
        </linearGradient>
      </defs>

      <rect width="64" height="64" rx="14" fill="#1C2035" />

      <circle cx="29" cy="30" r="15.5" stroke="url(#obseil-ring)" strokeWidth="6" />
      <path
        d="M37.5 41.5 L46 50"
        stroke="url(#obseil-ring)"
        strokeWidth="6"
        strokeLinecap="round"
      />

      <g fill="url(#obseil-bars)">
        <rect x="21.5" y="31" width="4.5" height="8" rx="1.2" />
        <rect x="28" y="27" width="4.5" height="12" rx="1.2" />
        <rect x="34.5" y="22.5" width="4.5" height="16.5" rx="1.2" />
      </g>

      <path
        d="M51 12 C51 15 52.5 16.5 55.5 16.5 C52.5 16.5 51 18 51 21 C51 18 49.5 16.5 46.5 16.5 C49.5 16.5 51 15 51 12 Z"
        fill="url(#obseil-spark)"
      />
      <path
        d="M52 46 C52 48 53 49 55 49 C53 49 52 50 52 52 C52 50 51 49 49 49 C51 49 52 48 52 46 Z"
        fill="#8B93A3"
        fillOpacity="0.75"
      />
      <path
        d="M57.5 54 C57.5 55.3 58.2 56 59.5 56 C58.2 56 57.5 56.7 57.5 58 C57.5 56.7 56.8 56 55.5 56 C56.8 56 57.5 55.3 57.5 54 Z"
        fill="#8B93A3"
        fillOpacity="0.55"
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

import { cn } from '@/utils/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'link';
export type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

const BASE =
  'inline-flex items-center justify-center font-medium whitespace-nowrap select-none ' +
  'transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover active:bg-accent-active shadow-xs',
  secondary:
    'bg-surface text-fg border border-border-default hover:bg-surface-hover ' +
    'active:bg-surface-muted shadow-xs',
  ghost: 'text-fg-muted hover:bg-surface-hover hover:text-fg active:bg-surface-muted',
  danger: 'bg-danger text-white hover:opacity-90 active:opacity-80 shadow-xs',
  link: 'text-accent underline-offset-4 hover:underline gap-1.5',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-md',
  md: 'h-9 px-3.5 text-sm gap-2 rounded-lg',
  lg: 'h-11 px-5 text-[15px] gap-2 rounded-lg',
  icon: 'size-9 rounded-lg',
};

export interface ButtonStyleOptions {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  className?: string;
}

/**
 * Button styling as a plain class string.
 *
 * Router `<Link>`s that should *look* like buttons use this instead of being
 * nested inside a `<button>` — nesting an anchor in a button is invalid HTML
 * and breaks keyboard activation.
 */
export function buttonStyles({
  variant = 'secondary',
  size = 'md',
  fullWidth = false,
  className,
}: ButtonStyleOptions = {}): string {
  return cn(
    BASE,
    VARIANTS[variant],
    variant === 'link' ? 'h-auto p-0' : SIZES[size],
    fullWidth && 'w-full',
    className,
  );
}

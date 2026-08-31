import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

import { buttonStyles, type ButtonSize, type ButtonVariant } from './buttonStyles';
import { Spinner } from './Spinner';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  /** Rendered before the label; replaced by the spinner while loading. */
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
  fullWidth?: boolean;
}

/**
 * The single button primitive. Every clickable action in Obseil uses it so
 * that focus rings, disabled styling and loading behaviour are identical
 * everywhere. A loading button is also disabled - it cannot be double-submitted.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    isLoading = false,
    leadingIcon,
    trailingIcon,
    fullWidth = false,
    className,
    children,
    disabled,
    type = 'button',
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      className={buttonStyles({ variant, size, fullWidth, className })}
      {...props}
    >
      {isLoading ? (
        <Spinner className="size-4" />
      ) : (
        leadingIcon && <span className="shrink-0">{leadingIcon}</span>
      )}
      {children}
      {!isLoading && trailingIcon && <span className="shrink-0">{trailingIcon}</span>}
    </button>
  );
});

import { forwardRef, type InputHTMLAttributes, type ReactNode, useId } from 'react';

import { cn } from '@/utils/cn';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  /** Explanatory text shown under the field when there is no error. */
  hint?: string;
  error?: string;
  leadingIcon?: ReactNode;
  trailingSlot?: ReactNode;
  containerClassName?: string;
}

/**
 * Accessible text field: the label is always a real `<label>`, hints and errors
 * are wired through `aria-describedby`, and an invalid field sets
 * `aria-invalid` so assistive technology announces the failure.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    hint,
    error,
    leadingIcon,
    trailingSlot,
    className,
    containerClassName,
    id,
    required,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [error ? errorId : null, hint && !error ? hintId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cn('w-full', containerClassName)}>
      {label && (
        <label htmlFor={inputId} className="mb-1.5 block text-[13px] font-medium text-fg">
          {label}
          {required && (
            <span className="ml-0.5 text-danger" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      <div className="relative">
        {leadingIcon && (
          <span
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle"
            aria-hidden="true"
          >
            {leadingIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          className={cn(
            'h-10 w-full rounded-lg border bg-surface px-3 text-sm text-fg',
            'placeholder:text-fg-subtle',
            'transition-colors duration-150',
            'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-fg-subtle',
            leadingIcon && 'pl-9',
            trailingSlot && 'pr-10',
            error
              ? 'border-danger focus-visible:outline-danger'
              : 'border-border-default hover:border-border-strong',
            className,
          )}
          {...props}
        />
        {trailingSlot && (
          <span className="absolute right-1.5 top-1/2 -translate-y-1/2">{trailingSlot}</span>
        )}
      </div>
      {error ? (
        <p id={errorId} role="alert" className="mt-1.5 text-[13px] text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={hintId} className="mt-1.5 text-[13px] text-fg-subtle">
            {hint}
          </p>
        )
      )}
    </div>
  );
});

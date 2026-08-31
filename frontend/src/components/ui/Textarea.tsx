import { forwardRef, type TextareaHTMLAttributes, useId } from 'react';

import { cn } from '@/utils/cn';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
  containerClassName?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className, containerClassName, id, required, rows = 3, ...props },
  ref,
) {
  const generatedId = useId();
  const fieldId = id ?? generatedId;
  const hintId = `${fieldId}-hint`;
  const errorId = `${fieldId}-error`;
  const describedBy = [error ? errorId : null, hint && !error ? hintId : null]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cn('w-full', containerClassName)}>
      {label && (
        <label htmlFor={fieldId} className="mb-1.5 block text-[13px] font-medium text-fg">
          {label}
          {required && (
            <span className="ml-0.5 text-danger" aria-hidden="true">
              *
            </span>
          )}
        </label>
      )}
      <textarea
        ref={ref}
        id={fieldId}
        rows={rows}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        className={cn(
          'w-full resize-y rounded-lg border bg-surface px-3 py-2 text-sm text-fg',
          'placeholder:text-fg-subtle transition-colors duration-150',
          'disabled:cursor-not-allowed disabled:bg-surface-muted',
          error
            ? 'border-danger focus-visible:outline-danger'
            : 'border-border-default hover:border-border-strong',
          className,
        )}
        {...props}
      />
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

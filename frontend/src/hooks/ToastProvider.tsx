import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { cn } from '@/utils/cn';

import { type Toast, type ToastTone, ToastContext } from './toastContext';

const AUTO_DISMISS_MS: Record<ToastTone, number> = {
  success: 4000,
  info: 5000,
  // Errors stay until dismissed - they usually require the user to do something.
  error: 9000,
};

const TONE_STYLES: Record<ToastTone, { ring: string; icon: typeof Info; iconColor: string }> = {
  success: { ring: 'border-border-default', icon: CheckCircle2, iconColor: 'text-success' },
  error: { ring: 'border-danger/40', icon: XCircle, iconColor: 'text-danger' },
  info: { ring: 'border-border-default', icon: Info, iconColor: 'text-accent' },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const notify = useCallback(
    (toast: Omit<Toast, 'id'>) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setToasts((current) => [...current.slice(-3), { ...toast, id }]);
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), AUTO_DISMISS_MS[toast.tone]),
      );
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const value = useMemo(() => ({ toasts, notify, dismiss }), [toasts, notify, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {/* Announced politely so a screen reader hears the outcome of an action. */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:inset-x-auto sm:right-0 sm:items-end"
      >
        {toasts.map((toast) => {
          const { ring, icon: Icon, iconColor } = TONE_STYLES[toast.tone];
          return (
            <div
              key={toast.id}
              role={toast.tone === 'error' ? 'alert' : 'status'}
              className={cn(
                'pointer-events-auto flex w-full max-w-sm animate-slide-up items-start gap-3',
                'rounded-lg border bg-surface p-3.5 shadow-lg',
                ring,
              )}
            >
              <Icon className={cn('mt-px size-4 shrink-0', iconColor)} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-medium text-fg">{toast.title}</p>
                {toast.description && (
                  <p className="mt-0.5 text-[13px] leading-relaxed text-fg-muted">
                    {toast.description}
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss notification"
                className="-m-1 rounded p-1 text-fg-subtle transition-colors hover:text-fg"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

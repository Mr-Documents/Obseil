import { useMutation } from '@tanstack/react-query';
import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { useToast } from '@/hooks/toastContext';
import { ApiError } from '@/services/apiClient';
import { type ReportFormat, reportsApi } from '@/services/reportsApi';
import { cn } from '@/utils/cn';

const OPTIONS: { format: ReportFormat; label: string; hint: string; icon: typeof FileText }[] = [
  {
    format: 'pdf',
    label: 'Full report (PDF)',
    hint: 'Score, statistics, findings and recommendations - shareable as-is.',
    icon: FileText,
  },
  {
    format: 'csv',
    label: 'Findings (CSV)',
    hint: 'One row per finding, including the impact and the recommendation.',
    icon: FileSpreadsheet,
  },
];

/**
 * Export menu.
 *
 * A plain dropdown rather than a dialog: exporting is a one-click action, and
 * a modal for it would put a confirmation step in front of something that
 * cannot go wrong.
 */
export function ExportMenu({
  analysisId,
  disabled = false,
}: {
  analysisId: string | null;
  disabled?: boolean;
}) {
  const [isOpen, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { notify } = useToast();

  const download = useMutation({
    mutationFn: (format: ReportFormat) => reportsApi.download(analysisId as string, format),
    onSuccess: (filename) => {
      notify({ tone: 'success', title: 'Report downloaded.', description: filename });
      setOpen(false);
    },
    onError: (cause) =>
      notify({
        tone: 'error',
        title: 'Could not generate the report',
        description: cause instanceof ApiError ? cause.message : 'Please try again.',
      }),
  });

  // Close on Escape or a click outside - the two things a user expects of any
  // menu, and the two most commonly forgotten.
  useEffect(() => {
    if (!isOpen) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false);
    }
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }

    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('mousedown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('mousedown', onPointerDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative">
      <Button
        variant="secondary"
        leadingIcon={<Download className="size-4" />}
        disabled={disabled || analysisId === null}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        onClick={() => setOpen((open) => !open)}
      >
        Export
      </Button>

      {isOpen && (
        <div
          role="menu"
          aria-label="Export format"
          className="absolute right-0 z-40 mt-2 w-72 animate-slide-up overflow-hidden rounded-lg border border-border-default bg-surface shadow-lg"
        >
          {OPTIONS.map(({ format, label, hint, icon: Icon }) => {
            const isBusy = download.isPending && download.variables === format;
            return (
              <button
                key={format}
                type="button"
                role="menuitem"
                disabled={download.isPending}
                onClick={() => download.mutate(format)}
                className={cn(
                  'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors',
                  'hover:bg-surface-hover disabled:opacity-60',
                  'border-b border-border-default last:border-b-0',
                )}
              >
                {isBusy ? (
                  <Spinner className="mt-0.5 size-4 text-accent" />
                ) : (
                  <Icon className="mt-0.5 size-4 shrink-0 text-fg-subtle" aria-hidden="true" />
                )}
                <span className="min-w-0">
                  <span className="block text-[13px] font-medium text-fg">
                    {isBusy ? 'Generating…' : label}
                  </span>
                  <span className="mt-0.5 block text-[12px] leading-relaxed text-fg-subtle">
                    {hint}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

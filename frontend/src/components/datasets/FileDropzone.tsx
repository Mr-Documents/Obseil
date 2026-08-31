import { FileSpreadsheet, Upload, X } from 'lucide-react';
import { type DragEvent, useCallback, useId, useRef, useState } from 'react';

import { Button } from '@/components/ui/Button';
import { cn } from '@/utils/cn';
import { formatBytes } from '@/utils/format';

import { ACCEPT_ATTRIBUTE, validateFile } from './fileValidation';

interface FileDropzoneProps {
  onSelect: (file: File | null) => void;
  file: File | null;
  maxBytes: number;
  disabled?: boolean;
}

/**
 * Drag-and-drop or click-to-browse file picker.
 *
 * Both paths are validated: a dropped file bypasses the input's `accept`
 * filter entirely, so relying on that attribute alone would let an unsupported
 * file through to the server.
 */
export function FileDropzone({ onSelect, file, maxBytes, disabled = false }: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const errorId = `${inputId}-error`;

  const accept = useCallback(
    (candidate: File | undefined) => {
      if (!candidate) return;
      const problem = validateFile(candidate, maxBytes);
      setError(problem);
      onSelect(problem ? null : candidate);
    },
    [maxBytes, onSelect],
  );

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;
    accept(event.dataTransfer.files[0]);
  }

  if (file) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-border-default bg-surface-muted p-4">
        <FileSpreadsheet className="size-5 shrink-0 text-accent" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-fg">{file.name}</p>
          <p className="mt-0.5 text-[13px] text-fg-subtle">{formatBytes(file.size)}</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          disabled={disabled}
          aria-label={`Remove ${file.name}`}
          onClick={() => {
            onSelect(null);
            setError(null);
            if (inputRef.current) inputRef.current.value = '';
          }}
        >
          <X className="size-4" aria-hidden="true" />
        </Button>
      </div>
    );
  }

  return (
    <div>
      {/* The visible drop target; the label below is the accessible control. */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cn(
          'rounded-lg border border-dashed transition-colors duration-150',
          isDragging
            ? 'border-accent bg-accent-soft'
            : 'border-border-strong bg-surface-muted hover:border-accent/60',
          disabled && 'pointer-events-none opacity-60',
        )}
      >
        <label
          htmlFor={inputId}
          className="flex cursor-pointer flex-col items-center gap-2 px-6 py-10 text-center"
        >
          <Upload
            className={cn('size-6', isDragging ? 'text-accent' : 'text-fg-subtle')}
            aria-hidden="true"
          />
          <span className="text-sm font-medium text-fg">
            Drop a file here, or <span className="text-accent">browse</span>
          </span>
          <span className="text-[13px] text-fg-subtle">
            CSV or Excel, up to {formatBytes(maxBytes)}
          </span>
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          className="sr-only"
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          aria-describedby={error ? errorId : undefined}
          aria-invalid={error ? true : undefined}
          onChange={(event) => accept(event.target.files?.[0])}
        />
      </div>
      {error && (
        <p id={errorId} role="alert" className="mt-2 text-[13px] text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

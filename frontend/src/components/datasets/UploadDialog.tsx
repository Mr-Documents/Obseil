import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { useToast } from '@/hooks/toastContext';
import { ApiError } from '@/services/apiClient';
import { datasetKeys, datasetsApi } from '@/services/datasetsApi';
import { projectKeys } from '@/services/projectsApi';
import type { Dataset } from '@/types/api';

import { FileDropzone } from './FileDropzone';

/** Mirrors OBSEIL_MAX_UPLOAD_BYTES. The server is still the authority. */
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

type Phase = 'idle' | 'uploading' | 'analysing';

interface UploadDialogProps {
  projectId: string;
  open: boolean;
  onClose: () => void;
  onUploaded?: (dataset: Dataset) => void;
}

export function UploadDialog({ projectId, open, onClose, onUploaded }: UploadDialogProps) {
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setFile(null);
    setName('');
    setProgress(0);
    setPhase('idle');
    setError(null);
  }

  const mutation = useMutation({
    mutationFn: (selected: File) =>
      datasetsApi.upload(projectId, selected, {
        name: name.trim() || undefined,
        onProgress: (percent) => {
          setProgress(percent);
          // 100% means "bytes delivered", not "done": the server is now
          // profiling. Saying so is more honest than a bar stuck at full.
          if (percent >= 100) setPhase('analysing');
        },
      }),
    onMutate: () => {
      setError(null);
      setProgress(0);
      setPhase('uploading');
    },
    onSuccess: (dataset) => {
      void queryClient.invalidateQueries({ queryKey: datasetKeys.listForProject(projectId) });
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      notify({
        tone: 'success',
        title: `“${dataset.name}” analysed.`,
        description: `${dataset.row_count?.toLocaleString() ?? '—'} rows, ${dataset.column_count ?? '—'} columns.`,
      });
      onUploaded?.(dataset);
      reset();
      onClose();
    },
    onError: (cause) => {
      setPhase('idle');
      setProgress(0);
      setError(
        cause instanceof ApiError
          ? cause.message
          : 'The upload could not be completed. Please try again.',
      );
    },
  });

  const isBusy = mutation.isPending;

  function handleClose() {
    if (isBusy) return; // Never drop an in-flight upload silently.
    reset();
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Upload a dataset"
      description="Obseil profiles the file, runs its quality checks, and scores it."
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={isBusy}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!file}
            isLoading={isBusy}
            onClick={() => file && mutation.mutate(file)}
          >
            {phase === 'analysing'
              ? 'Analysing'
              : phase === 'uploading'
                ? 'Uploading'
                : 'Upload and analyse'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && <Alert tone="danger">{error}</Alert>}

        <FileDropzone
          file={file}
          onSelect={setFile}
          maxBytes={MAX_UPLOAD_BYTES}
          disabled={isBusy}
        />

        <Input
          label="Display name"
          placeholder={file?.name ?? 'March transactions'}
          value={name}
          onChange={(event) => setName(event.target.value)}
          hint="Optional. Defaults to the filename."
          disabled={isBusy}
          maxLength={160}
        />

        {isBusy && (
          <div>
            <div className="mb-1.5 flex items-center justify-between text-[13px]">
              <span className="text-fg-muted">
                {phase === 'analysing' ? 'Profiling and running quality checks…' : 'Uploading…'}
              </span>
              <span className="tabular text-fg-subtle">{progress}%</span>
            </div>
            <div
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Upload progress"
              className="h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
            >
              <div
                className={
                  phase === 'analysing'
                    ? 'h-full w-full animate-shimmer bg-accent'
                    : 'h-full bg-accent transition-[width] duration-200'
                }
                style={phase === 'analysing' ? undefined : { width: `${progress}%` }}
              />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, RefreshCw, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link, Outlet, useNavigate, useParams } from 'react-router-dom';

import { DatasetStatusBadge } from '@/components/datasets/DatasetStatusBadge';
import { ExportMenu } from '@/components/reports/ExportMenu';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { PageContent, PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { Tabs } from '@/components/ui/Tabs';
import { useToast } from '@/hooks/toastContext';
import { ApiError } from '@/services/apiClient';
import { datasetKeys, datasetsApi } from '@/services/datasetsApi';
import { findingKeys, findingsApi } from '@/services/findingsApi';
import { anomalyKeys, scoreApi, scoreKeys } from '@/services/scoreApi';
import { projectKeys } from '@/services/projectsApi';
import { formatBytes, formatDateTime, formatNumber } from '@/utils/format';

/**
 * Shell for every dataset view. Owns the dataset query and the destructive
 * actions; the tabs below render into the outlet and each fetch only what it
 * needs.
 */
export function DatasetLayout() {
  const { datasetId = '' } = useParams<{ datasetId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [isDeleteOpen, setDeleteOpen] = useState(false);

  const {
    data: dataset,
    isPending,
    isError,
    error,
  } = useQuery({
    queryKey: datasetKeys.detail(datasetId),
    queryFn: () => datasetsApi.get(datasetId),
    enabled: Boolean(datasetId),
  });

  // The tab badge shows how many findings are still open, not how many exist:
  // a triaged queue should visibly empty out.
  const summary = useQuery({
    queryKey: findingKeys.summary(datasetId),
    queryFn: () => findingsApi.summary(datasetId),
    enabled: dataset?.status === 'ready',
  });

  const score = useQuery({
    queryKey: scoreKeys.detail(datasetId),
    queryFn: () => scoreApi.get(datasetId),
    enabled: dataset?.status === 'ready',
  });

  const reanalyse = useMutation({
    mutationFn: () => datasetsApi.analyze(datasetId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: datasetKeys.all });
      void queryClient.invalidateQueries({ queryKey: findingKeys.all });
      void queryClient.invalidateQueries({ queryKey: anomalyKeys.all });
      void queryClient.invalidateQueries({ queryKey: scoreKeys.all });
      notify({ tone: 'success', title: 'Analysis re-run.' });
    },
    onError: (cause) =>
      notify({
        tone: 'error',
        title: 'Could not re-run the analysis',
        description: cause instanceof ApiError ? cause.message : 'Please try again.',
      }),
  });

  const remove = useMutation({
    mutationFn: () => datasetsApi.remove(datasetId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: datasetKeys.all });
      void queryClient.invalidateQueries({ queryKey: projectKeys.all });
      notify({ tone: 'success', title: 'Dataset deleted.' });
      navigate(dataset ? `/projects/${dataset.project_id}` : '/projects', { replace: true });
    },
  });

  if (isPending) {
    return (
      <>
        <PageHeader title={<Skeleton className="h-7 w-64" />} />
        <PageContent>
          <Skeleton className="h-64 w-full" />
        </PageContent>
      </>
    );
  }

  if (isError || !dataset) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <PageContent>
        <Alert tone="danger" title={notFound ? 'Dataset not found' : 'Could not load this dataset'}>
          {notFound
            ? 'It may have been deleted, or you may not have access to it.'
            : error instanceof ApiError
              ? error.message
              : 'Please try again in a moment.'}
          <div className="mt-3">
            <Link
              to="/projects"
              className="font-medium text-accent underline-offset-4 hover:underline"
            >
              Back to projects
            </Link>
          </div>
        </Alert>
      </PageContent>
    );
  }

  const base = `/datasets/${dataset.id}`;

  return (
    <>
      <PageHeader
        eyebrow={
          <Link
            to={`/projects/${dataset.project_id}`}
            className="inline-flex items-center gap-1 text-[13px] text-fg-muted transition-colors hover:text-fg"
          >
            <ChevronLeft className="size-3.5" aria-hidden="true" />
            Back to project
          </Link>
        }
        title={
          <span className="flex flex-wrap items-center gap-3">
            <span className="truncate">{dataset.name}</span>
            <DatasetStatusBadge status={dataset.status} />
            {score.data && (
              <span className="tabular text-base font-medium text-fg-muted">
                {formatNumber(score.data.score, 1)}
                <span className="text-fg-subtle"> / 100</span>
              </span>
            )}
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
            <span>{formatNumber(dataset.row_count)} rows</span>
            <span aria-hidden="true">·</span>
            <span>{formatNumber(dataset.column_count)} columns</span>
            <span aria-hidden="true">·</span>
            <span>{formatBytes(dataset.size_bytes)}</span>
            <span aria-hidden="true">·</span>
            <span>Uploaded {formatDateTime(dataset.created_at)}</span>
          </span>
        }
        actions={
          <>
            <ExportMenu
              analysisId={dataset.latest_analysis?.id ?? null}
              disabled={dataset.status !== 'ready'}
            />
            <Button
              variant="secondary"
              leadingIcon={<RefreshCw className="size-4" />}
              isLoading={reanalyse.isPending}
              onClick={() => reanalyse.mutate()}
            >
              Re-analyse
            </Button>
            <Button
              variant="ghost"
              leadingIcon={<Trash2 className="size-4" />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </>
        }
      >
        <Tabs
          items={[
            { to: base, label: 'Overview', end: true },
            {
              to: `${base}/findings`,
              label: 'Findings',
              count: summary.data?.open_count ?? null,
            },
            {
              to: `${base}/anomalies`,
              label: 'Anomalies',
              count: dataset.latest_analysis?.anomaly_count ?? null,
            },
            { to: `${base}/columns`, label: 'Columns', count: dataset.column_count },
            { to: `${base}/rows`, label: 'Rows' },
            { to: `${base}/history`, label: 'History' },
          ]}
        />
      </PageHeader>

      <PageContent>
        {dataset.status === 'failed' && dataset.error_message && (
          <Alert tone="danger" title="This dataset could not be analysed" className="mb-6">
            {dataset.error_message}
          </Alert>
        )}
        <Outlet context={dataset} />
      </PageContent>

      <Modal
        open={isDeleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Delete this dataset?"
        description="The file and every analysis and finding derived from it are removed. This cannot be undone."
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="danger" isLoading={remove.isPending} onClick={() => remove.mutate()}>
              Delete dataset
            </Button>
          </>
        }
      >
        <p className="text-[13px] text-fg-muted">
          <span className="font-medium text-fg">{dataset.name}</span> —{' '}
          {formatBytes(dataset.size_bytes)}
        </p>
      </Modal>
    </>
  );
}

import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, History } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ScoreTrendChart } from '@/components/charts/ScoreTrendChart';
import { ComparisonPanel } from '@/components/history/ComparisonPanel';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageContent, PageHeader } from '@/components/ui/PageHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { historyApi, historyKeys } from '@/services/historyApi';
import { projectKeys, projectsApi } from '@/services/projectsApi';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';

function scoreTone(score: number | null): string {
  if (score === null) return 'text-fg-subtle';
  if (score >= 95) return 'text-success';
  if (score >= 80) return 'text-low';
  if (score >= 60) return 'text-medium';
  if (score >= 40) return 'text-high';
  return 'text-critical';
}

export function ProjectHistoryPage() {
  const { projectId = '' } = useParams<{ projectId: string }>();
  const [comparing, setComparing] = useState<string | null>(null);

  const project = useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => projectsApi.get(projectId),
    enabled: Boolean(projectId),
  });

  const history = useQuery({
    queryKey: historyKeys.project(projectId),
    queryFn: () => historyApi.forProject(projectId, { limit: 100 }),
    enabled: Boolean(projectId),
  });

  const trend = useQuery({
    queryKey: historyKeys.trend(projectId),
    queryFn: () => historyApi.trend(projectId),
    enabled: Boolean(projectId),
  });

  const comparison = useQuery({
    queryKey: historyKeys.compare(comparing ?? ''),
    queryFn: () => historyApi.compare(comparing as string),
    enabled: comparing !== null,
  });

  const runs = history.data?.items ?? [];
  const noBaseline =
    comparison.error instanceof ApiError && comparison.error.code === 'no_baseline';

  return (
    <>
      <PageHeader
        eyebrow={
          <Link
            to={`/projects/${projectId}`}
            className="inline-flex items-center gap-1 text-[13px] text-fg-muted transition-colors hover:text-fg"
          >
            <ChevronLeft className="size-3.5" aria-hidden="true" />
            {project.data?.name ?? 'Back to project'}
          </Link>
        }
        title="Analysis history"
        description="Every completed analysis in this project, and how quality has moved."
      />

      <PageContent className="space-y-6">
        {history.isError && (
          <Alert tone="danger" title="Could not load the history">
            {history.error instanceof ApiError
              ? history.error.message
              : 'Please try again in a moment.'}
          </Alert>
        )}

        {history.isPending ? (
          <Skeleton className="h-72 w-full" />
        ) : runs.length === 0 ? (
          <Card>
            <EmptyState
              icon={History}
              title="No analyses yet"
              description="Upload a dataset to this project and its analysis will appear here."
              action={
                <Link to={`/projects/${projectId}`}>
                  <Button variant="primary">Go to the project</Button>
                </Link>
              }
            />
          </Card>
        ) : (
          <>
            <Card>
              <CardHeader
                title="Quality over time"
                description="Each point is one completed analysis. Bands mark the grade boundaries."
              />
              <div className="p-5">
                {trend.isPending ? (
                  <Skeleton className="h-52 w-full" />
                ) : (
                  <ScoreTrendChart points={trend.data ?? []} />
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Analyses" description="Newest first." />
              <TableScroller>
                <Table>
                  <THead>
                    <TR>
                      <TH numeric>Version</TH>
                      <TH>Dataset</TH>
                      <TH numeric>Score</TH>
                      <TH numeric>Findings</TH>
                      <TH numeric>Anomalies</TH>
                      <TH numeric>Rows</TH>
                      <TH>Analysed</TH>
                      <TH aria-label="Actions" />
                    </TR>
                  </THead>
                  <TBody>
                    {runs.map((run) => (
                      <TR key={run.id}>
                        <TD numeric className="text-fg-subtle">
                          v{run.version}
                        </TD>
                        <TD>
                          <Link
                            to={`/datasets/${run.dataset_id}`}
                            className="font-medium text-fg underline-offset-4 hover:text-accent hover:underline"
                          >
                            {run.dataset_name}
                          </Link>
                        </TD>
                        <TD numeric className={cn('font-medium', scoreTone(run.quality_score))}>
                          {run.quality_score === null ? '-' : formatNumber(run.quality_score, 1)}
                        </TD>
                        <TD numeric>{formatNumber(run.finding_count)}</TD>
                        <TD numeric>{formatNumber(run.anomaly_count)}</TD>
                        <TD numeric>{formatNumber(run.row_count)}</TD>
                        <TD className="whitespace-nowrap text-fg-muted">
                          {formatDateTime(run.completed_at ?? run.created_at)}
                        </TD>
                        <TD>
                          <Button
                            size="sm"
                            variant={comparing === run.id ? 'secondary' : 'ghost'}
                            onClick={() => setComparing(comparing === run.id ? null : run.id)}
                          >
                            {comparing === run.id ? 'Hide' : 'Compare'}
                          </Button>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableScroller>
            </Card>

            {comparing !== null && (
              <>
                {comparison.isPending && <Skeleton className="h-64 w-full" />}
                {noBaseline && (
                  <Alert tone="info" title="Nothing to compare against yet">
                    This is the first completed analysis in the project. Analyse another dataset and
                    Obseil will show you what changed.
                  </Alert>
                )}
                {comparison.isError && !noBaseline && (
                  <Alert tone="danger" title="Could not build the comparison">
                    {comparison.error instanceof ApiError
                      ? comparison.error.message
                      : 'Please try again in a moment.'}
                  </Alert>
                )}
                {comparison.data && <ComparisonPanel comparison={comparison.data} />}
              </>
            )}
          </>
        )}
      </PageContent>
    </>
  );
}

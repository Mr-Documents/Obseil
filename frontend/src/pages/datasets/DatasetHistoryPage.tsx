import { useQuery } from '@tanstack/react-query';
import { History } from 'lucide-react';
import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import { ComparisonPanel } from '@/components/history/ComparisonPanel';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { historyApi, historyKeys } from '@/services/historyApi';
import type { Dataset } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatDateTime, formatDuration, formatNumber } from '@/utils/format';

function scoreTone(score: number | null): string {
  if (score === null) return 'text-fg-subtle';
  if (score >= 95) return 'text-success';
  if (score >= 80) return 'text-low';
  if (score >= 60) return 'text-medium';
  if (score >= 40) return 'text-high';
  return 'text-critical';
}

export function DatasetHistoryPage() {
  const dataset = useOutletContext<Dataset>();
  const [comparing, setComparing] = useState<string | null>(null);

  const history = useQuery({
    queryKey: historyKeys.dataset(dataset.id),
    queryFn: () => historyApi.forDataset(dataset.id, { limit: 100 }),
  });

  const comparison = useQuery({
    queryKey: historyKeys.compare(comparing ?? ''),
    queryFn: () => historyApi.compare(comparing as string),
    enabled: comparing !== null,
  });

  if (history.isPending) return <Skeleton className="h-64 w-full" />;

  if (history.isError) {
    return (
      <Alert tone="danger" title="Could not load the history">
        {history.error instanceof ApiError
          ? history.error.message
          : 'Please try again in a moment.'}
      </Alert>
    );
  }

  const runs = history.data.items;

  if (runs.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={History}
          title="No analyses yet"
          description="Run an analysis and it will appear here, so you can compare it with later runs."
        />
      </Card>
    );
  }

  const noBaseline =
    comparison.error instanceof ApiError && comparison.error.code === 'no_baseline';

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Analysis history"
          description="Every run for this dataset, including failures. Compare any run with the one before it."
        />
        <TableScroller>
          <Table>
            <THead>
              <TR>
                <TH>Run</TH>
                <TH>Status</TH>
                <TH numeric>Score</TH>
                <TH numeric>Findings</TH>
                <TH numeric>Anomalies</TH>
                <TH numeric>Duration</TH>
                <TH>When</TH>
                <TH aria-label="Actions" />
              </TR>
            </THead>
            <TBody>
              {runs.map((run, index) => (
                <TR key={run.id}>
                  <TD className="tabular text-fg-subtle">#{runs.length - index}</TD>
                  <TD>
                    {run.status === 'completed' ? (
                      <Badge tone="success">Completed</Badge>
                    ) : run.status === 'failed' ? (
                      <Badge tone="critical">Failed</Badge>
                    ) : (
                      <Badge tone="neutral">Running</Badge>
                    )}
                  </TD>
                  <TD numeric className={cn('font-medium', scoreTone(run.quality_score))}>
                    {run.quality_score === null ? '—' : formatNumber(run.quality_score, 1)}
                  </TD>
                  <TD numeric>{formatNumber(run.finding_count)}</TD>
                  <TD numeric>{formatNumber(run.anomaly_count)}</TD>
                  <TD numeric className="text-fg-muted">
                    {formatDuration(run.duration_ms)}
                  </TD>
                  <TD className="whitespace-nowrap text-fg-muted">
                    {formatDateTime(run.completed_at ?? run.created_at)}
                  </TD>
                  <TD>
                    {run.status === 'completed' && (
                      <Button
                        size="sm"
                        variant={comparing === run.id ? 'secondary' : 'ghost'}
                        onClick={() => setComparing(comparing === run.id ? null : run.id)}
                      >
                        {comparing === run.id ? 'Hide' : 'Compare'}
                      </Button>
                    )}
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
    </div>
  );
}

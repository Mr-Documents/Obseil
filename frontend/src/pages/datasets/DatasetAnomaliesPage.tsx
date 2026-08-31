import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Info, ShieldCheck, SquareDashed } from 'lucide-react';
import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatTile } from '@/components/ui/StatTile';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { anomaliesApi, anomalyKeys } from '@/services/scoreApi';
import type { Dataset } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber, formatPercent, formatStatistic } from '@/utils/format';

const PAGE_SIZE = 25;

/** How unusual a row is, relative to the rest of this dataset only. */
function ScoreBar({ score }: { score: number }) {
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-surface-muted">
        <div className="h-full rounded-full bg-viz-4" style={{ width: `${Math.max(score, 4)}%` }} />
      </div>
      <span className="tabular w-10 text-right text-[13px] text-fg">{formatNumber(score, 0)}</span>
    </div>
  );
}

export function DatasetAnomaliesPage() {
  const dataset = useOutletContext<Dataset>();
  const [offset, setOffset] = useState(0);
  const enabled = dataset.status === 'ready';

  const overview = useQuery({
    queryKey: anomalyKeys.overview(dataset.id),
    queryFn: () => anomaliesApi.overview(dataset.id),
    enabled,
  });

  const { data, isPending, isFetching, isError, error } = useQuery({
    queryKey: anomalyKeys.list(dataset.id, offset, PAGE_SIZE),
    queryFn: () => anomaliesApi.list(dataset.id, { offset, limit: PAGE_SIZE }),
    enabled,
    placeholderData: keepPreviousData,
  });

  if (!enabled) {
    return (
      <Card>
        <EmptyState
          icon={SquareDashed}
          title="No analysis yet"
          description="Run an analysis to let the model look for unusual rows."
        />
      </Card>
    );
  }

  if (isError) {
    return (
      <Alert tone="danger" title="Could not load the anomalies">
        {error instanceof ApiError ? error.message : 'Please try again in a moment.'}
      </Alert>
    );
  }

  if (overview.data && !overview.data.ran) {
    return (
      <Card>
        <CardHeader title="Anomaly detection was not run" />
        <CardBody className="space-y-3">
          <Alert tone="info" title="Why it was skipped">
            {overview.data.skipped_reason}
          </Alert>
          <p className="text-[13px] leading-relaxed text-fg-muted">
            Skipping is a deliberate outcome, not a failure. Multivariate anomaly detection needs at
            least two usable numeric columns and enough rows for &ldquo;unusual&rdquo; to mean
            anything; below that, a model would only rediscover what the interquartile-range check
            already reports.
          </p>
        </CardBody>
      </Card>
    );
  }

  const features = overview.data?.features ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          label="Rows flagged"
          value={formatNumber(overview.data?.anomaly_count ?? 0)}
          detail={`${formatPercent(overview.data?.anomaly_rate ?? 0)} of ${formatNumber(
            overview.data?.rows_scored ?? 0,
          )} scored`}
        />
        <StatTile label="Features used" value={formatNumber(features.length)} />
        <StatTile
          label="Algorithm"
          value={<span className="text-base">Isolation Forest</span>}
          detail="Unsupervised, no labels required"
        />
      </div>

      <Alert tone="info" title="How to read these rows">
        {overview.data?.method_note}
      </Alert>

      {features.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[13px] text-fg-muted">
          <Info className="size-3.5" aria-hidden="true" />
          <span>Trained on</span>
          {features.map((feature) => (
            <Badge key={feature} tone="neutral">
              {feature}
            </Badge>
          ))}
        </div>
      )}

      <Card>
        {isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }, (_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : total === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No unusual rows found"
            description="The model scored every row and none stood out from the rest. Combined with the quality checks, that is a good sign for this dataset."
          />
        ) : (
          <>
            <TableScroller>
              <Table>
                <THead>
                  <TR>
                    <TH numeric>Row</TH>
                    <TH numeric>Unusualness</TH>
                    <TH>What stood out</TH>
                    {features.map((feature) => (
                      <TH key={feature} numeric className="font-mono normal-case tracking-normal">
                        {feature}
                      </TH>
                    ))}
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((anomaly) => {
                    const standout = new Set(
                      (anomaly.top_contributors ?? []).map((entry) => entry.feature),
                    );
                    return (
                      <TR key={anomaly.id}>
                        <TD numeric className="text-fg-subtle">
                          {formatNumber(anomaly.row_index + 1)}
                        </TD>
                        <TD numeric>
                          <ScoreBar score={anomaly.anomaly_score} />
                        </TD>
                        <TD>
                          <div className="flex flex-wrap gap-1">
                            {(anomaly.top_contributors ?? []).map((entry) => (
                              <Badge key={entry.feature} tone="accent">
                                {entry.feature}
                              </Badge>
                            ))}
                          </div>
                        </TD>
                        {features.map((feature) => (
                          <TD
                            key={feature}
                            numeric
                            className={cn(
                              'font-mono text-[12px]',
                              standout.has(feature) && 'font-semibold text-fg',
                            )}
                          >
                            {formatStatistic(anomaly.feature_values?.[feature] ?? null)}
                          </TD>
                        ))}
                      </TR>
                    );
                  })}
                </TBody>
              </Table>
            </TableScroller>

            <CardBody className="flex flex-wrap items-center justify-between gap-3 border-t border-border-default px-4 py-3">
              <p className="tabular text-[13px] text-fg-muted" aria-live="polite">
                {formatNumber(offset + 1)}–{formatNumber(offset + data.items.length)} of{' '}
                {formatNumber(total)}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset === 0 || isFetching}
                  leadingIcon={<ChevronLeft className="size-4" />}
                  onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset + data.items.length >= total || isFetching}
                  trailingIcon={<ChevronRight className="size-4" />}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </CardBody>
          </>
        )}
      </Card>
    </div>
  );
}

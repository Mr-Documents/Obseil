import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Copy, Fingerprint, Rows3, SquareDashed, TriangleAlert } from 'lucide-react';
import { Link, useOutletContext } from 'react-router-dom';

import { AnomalyScoreChart } from '@/components/charts/AnomalyScoreChart';
import { ColumnTypeChart } from '@/components/charts/ColumnTypeChart';
import { MissingValuesChart } from '@/components/charts/MissingValuesChart';
import { SeverityBreakdownChart } from '@/components/charts/SeverityBreakdownChart';
import { QualityScoreCard } from '@/components/score/QualityScoreCard';
import { Alert } from '@/components/ui/Alert';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatTile } from '@/components/ui/StatTile';
import { ApiError } from '@/services/apiClient';
import { datasetKeys, datasetsApi } from '@/services/datasetsApi';
import { findingKeys, findingsApi, findingTypeLabel } from '@/services/findingsApi';
import { anomaliesApi, anomalyKeys, scoreApi, scoreKeys } from '@/services/scoreApi';
import type { Dataset } from '@/types/api';
import { formatBytes, formatNumber, formatPercent } from '@/utils/format';

/** How many anomalies to fetch purely to shape the distribution chart. */
const ANOMALY_SAMPLE = 200;

function SectionLink({ to, children }: { to: string; children: string }) {
  return (
    <Link
      to={to}
      className="text-[13px] font-medium text-accent underline-offset-4 hover:underline"
    >
      {children}
    </Link>
  );
}

export function DatasetOverviewPage() {
  const dataset = useOutletContext<Dataset>();
  const ready = dataset.status === 'ready';

  const statistics = useQuery({
    queryKey: datasetKeys.statistics(dataset.id),
    queryFn: () => datasetsApi.statistics(dataset.id),
    enabled: ready,
  });
  const summary = useQuery({
    queryKey: findingKeys.summary(dataset.id),
    queryFn: () => findingsApi.summary(dataset.id),
    enabled: ready,
  });
  const score = useQuery({
    queryKey: scoreKeys.detail(dataset.id),
    queryFn: () => scoreApi.get(dataset.id),
    enabled: ready,
  });
  const anomalies = useQuery({
    queryKey: anomalyKeys.list(dataset.id, 0, ANOMALY_SAMPLE),
    queryFn: () => anomaliesApi.list(dataset.id, { limit: ANOMALY_SAMPLE }),
    enabled: ready,
  });

  if (!ready) {
    return (
      <Card>
        <EmptyState
          icon={SquareDashed}
          title="No analysis yet"
          description="Run an analysis to profile this dataset, check its quality and score it."
        />
      </Card>
    );
  }

  if (statistics.isPending || score.isPending) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-56 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-[104px]" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (statistics.isError || !statistics.data) {
    return (
      <Alert tone="danger" title="Could not load this analysis">
        {statistics.error instanceof ApiError
          ? statistics.error.message
          : 'Please try again in a moment.'}
      </Alert>
    );
  }

  const stats = statistics.data;
  const severity = summary.data?.by_severity ?? {};
  const base = `/datasets/${dataset.id}`;

  return (
    <div className="space-y-6">
      {score.data && <QualityScoreCard score={score.data} />}

      {stats.notes.length > 0 && (
        <Alert tone="info" title="How this file was read">
          <ul className="mt-1 list-disc space-y-1 pl-4">
            {stats.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </Alert>
      )}

      {/* The figures the product promises, in one scannable row. */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Critical"
          value={formatNumber(severity.critical ?? 0)}
          tone={(severity.critical ?? 0) > 0 ? 'critical' : 'neutral'}
          icon={TriangleAlert}
        />
        <StatTile
          label="High"
          value={formatNumber(severity.high ?? 0)}
          tone={(severity.high ?? 0) > 0 ? 'high' : 'neutral'}
        />
        <StatTile
          label="Medium"
          value={formatNumber(severity.medium ?? 0)}
          tone={(severity.medium ?? 0) > 0 ? 'medium' : 'neutral'}
        />
        <StatTile
          label="Low"
          value={formatNumber(severity.low ?? 0)}
          tone={(severity.low ?? 0) > 0 ? 'low' : 'neutral'}
        />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="Anomalies"
          value={formatNumber(dataset.latest_analysis?.anomaly_count ?? 0)}
          icon={Fingerprint}
          detail={formatPercent(dataset.latest_analysis?.anomaly_rate ?? 0)}
        />
        <StatTile
          label="Missing values"
          value={formatPercent(stats.missing_percentage)}
          icon={SquareDashed}
          tone={
            stats.missing_percentage > 10
              ? 'high'
              : stats.missing_percentage > 0
                ? 'medium'
                : 'success'
          }
          detail={`${formatNumber(stats.missing_cells)} of ${formatNumber(stats.total_cells)} cells`}
        />
        <StatTile
          label="Duplicate rows"
          value={formatNumber(stats.duplicate_row_count)}
          icon={Copy}
          tone={
            stats.duplicate_row_percentage > 1
              ? 'high'
              : stats.duplicate_row_count > 0
                ? 'medium'
                : 'success'
          }
          detail={formatPercent(stats.duplicate_row_percentage)}
        />
        <StatTile
          label="Shape"
          value={
            <span className="text-2xl">
              {formatNumber(stats.row_count)}
              <span className="text-base font-normal text-fg-subtle">
                {' '}
                &times; {stats.column_count}
              </span>
            </span>
          }
          icon={Rows3}
          detail={
            stats.sampled && stats.source_rows
              ? `Sampled from ${formatNumber(stats.source_rows)} rows`
              : formatBytes(stats.memory_bytes)
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Issues by severity"
            description="What the deterministic checks found, and how serious it is."
            action={<SectionLink to={`${base}/findings`}>All findings</SectionLink>}
          />
          <CardBody>
            {summary.isPending ? (
              <Skeleton className="h-40 w-full" />
            ) : (
              <SeverityBreakdownChart counts={severity} />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Where values are missing"
            description="Columns with gaps, worst first, banded by the same rules the checks use."
            action={<SectionLink to={`${base}/columns`}>All columns</SectionLink>}
          />
          <CardBody>
            <MissingValuesChart columns={stats.columns} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Column types"
            description="What Obseil inferred each column to contain, which drives every later check."
            action={<SectionLink to={`${base}/columns`}>Explore</SectionLink>}
          />
          <CardBody>
            <ColumnTypeChart columns={stats.columns} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Anomaly distribution"
            description="How far the rows the model flagged sit from the rest."
            action={<SectionLink to={`${base}/anomalies`}>Inspect rows</SectionLink>}
          />
          <CardBody>
            {anomalies.isPending ? (
              <Skeleton className="h-44 w-full" />
            ) : dataset.latest_analysis?.ml_skipped_reason ? (
              <EmptyState
                size="sm"
                title="Anomaly detection was not run"
                description={dataset.latest_analysis.ml_skipped_reason}
              />
            ) : (
              <AnomalyScoreChart anomalies={anomalies.data?.items ?? []} />
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Most common issues"
          description="The finding types that account for most of what was found."
          action={<SectionLink to={`${base}/findings`}>All findings</SectionLink>}
        />
        {summary.data && summary.data.total > 0 ? (
          <CardBody>
            <ul className="space-y-2">
              {Object.entries(summary.data.by_type)
                .slice(0, 6)
                .map(([type, count]) => (
                  <li key={type} className="flex items-baseline justify-between gap-4 text-[13px]">
                    <span className="text-fg">{findingTypeLabel(type)}</span>
                    <span className="tabular text-fg-muted">{formatNumber(count)}</span>
                  </li>
                ))}
            </ul>
          </CardBody>
        ) : (
          <EmptyState
            size="sm"
            icon={CheckCircle2}
            title="No issues found"
            description="Every quality check passed on this dataset."
          />
        )}
      </Card>

      <Card>
        <CardHeader title="Dataset details" />
        <CardBody>
          <dl className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { label: 'Rows', value: formatNumber(stats.row_count) },
              { label: 'Columns', value: formatNumber(stats.column_count) },
              { label: 'Total cells', value: formatNumber(stats.total_cells) },
              { label: 'In-memory size', value: formatBytes(stats.memory_bytes) },
              { label: 'File on disk', value: formatBytes(dataset.size_bytes) },
              { label: 'Format', value: dataset.file_format.toUpperCase() },
              {
                label: 'Complete columns',
                value: `${formatNumber(
                  stats.columns.filter((column) => column.missing_count === 0).length,
                )} of ${formatNumber(stats.column_count)}`,
              },
              { label: 'Checksum', value: dataset.checksum_sha256.slice(0, 12) },
            ].map(({ label, value }) => (
              <div key={label}>
                <dt className="text-[12px] text-fg-subtle">{label}</dt>
                <dd className="tabular mt-0.5 truncate text-sm text-fg" title={String(value)}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </CardBody>
      </Card>
    </div>
  );
}

import { CheckCircle2, TriangleAlert } from 'lucide-react';

import { BeforeAfter, ScoreDelta } from '@/components/history/ScoreDelta';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { findingTypeLabel } from '@/services/findingsApi';
import type { AnalysisComparison, MetricComparison } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatDateTime, formatNumber } from '@/utils/format';

/** Percentages and scores read better with a decimal; counts do not. */
function digitsFor(metric: MetricComparison): number {
  return metric.unit === '%' || metric.unit === '/100' || metric.unit === 'pts' ? 1 : 0;
}

function MetricRows({ metrics }: { metrics: MetricComparison[] }) {
  return (
    <TableScroller>
      <Table>
        <THead>
          <TR>
            <TH>Metric</TH>
            <TH numeric>Before &rarr; after</TH>
            <TH numeric>Change</TH>
          </TR>
        </THead>
        <TBody>
          {metrics.map((metric) => (
            <TR key={metric.key}>
              <TD>{metric.label}</TD>
              <TD numeric>
                <BeforeAfter
                  baseline={metric.baseline}
                  current={metric.current}
                  digits={digitsFor(metric)}
                />
              </TD>
              <TD numeric>
                <ScoreDelta
                  delta={metric.delta}
                  direction={metric.direction}
                  digits={digitsFor(metric)}
                  unit={metric.unit === '/100' ? null : metric.unit}
                />
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </TableScroller>
  );
}

export function ComparisonPanel({ comparison }: { comparison: AnalysisComparison }) {
  const improved = (comparison.score_delta ?? 0) > 0;
  const regressed = (comparison.score_delta ?? 0) < 0;

  const changedDimensions = comparison.dimensions.filter(
    (dimension) => dimension.delta !== null && Math.abs(dimension.delta) > 0.05,
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardBody className="p-6">
          <p className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
            Compared with the previous analysis
          </p>

          <div className="mt-4 flex flex-wrap items-end gap-x-6 gap-y-3">
            <div>
              <p className="text-[12px] text-fg-subtle">{formatDateTime(comparison.baseline_at)}</p>
              <p className="tabular mt-1 text-3xl font-semibold text-fg-muted">
                {formatNumber(comparison.baseline_score, 1)}
              </p>
            </div>

            <div className="pb-1.5 text-2xl text-fg-subtle" aria-hidden="true">
              &rarr;
            </div>

            <div>
              <p className="text-[12px] text-fg-subtle">{formatDateTime(comparison.current_at)}</p>
              <p
                className={cn(
                  'tabular mt-1 text-3xl font-semibold',
                  improved ? 'text-success' : regressed ? 'text-danger' : 'text-fg',
                )}
              >
                {formatNumber(comparison.current_score, 1)}
              </p>
            </div>

            <div className="pb-2">
              <ScoreDelta
                delta={comparison.score_delta}
                direction={improved ? 'improved' : regressed ? 'regressed' : 'unchanged'}
                digits={1}
                className="text-lg"
              />
            </div>
          </div>

          <p className="mt-4 text-sm leading-relaxed text-fg-muted">{comparison.headline}</p>

          {(comparison.resolved_types.length > 0 || comparison.new_types.length > 0) && (
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              {comparison.resolved_types.length > 0 && (
                <div>
                  <p className="flex items-center gap-1.5 text-[12px] font-medium uppercase tracking-wide text-success">
                    <CheckCircle2 className="size-3.5" aria-hidden="true" />
                    Resolved
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {comparison.resolved_types.map((type) => (
                      <Badge key={type} tone="success">
                        {findingTypeLabel(type)}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {comparison.new_types.length > 0 && (
                <div>
                  <p className="flex items-center gap-1.5 text-[12px] font-medium uppercase tracking-wide text-high">
                    <TriangleAlert className="size-3.5" aria-hidden="true" />
                    New
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {comparison.new_types.map((type) => (
                      <Badge key={type} tone="high">
                        {findingTypeLabel(type)}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="What changed"
          description="Each metric is judged against what an improvement means for it — shape changes are reported as neutral."
        />
        <MetricRows metrics={comparison.metrics} />
      </Card>

      {changedDimensions.length > 0 && (
        <Card>
          <CardHeader
            title="Score movement by dimension"
            description="Where the points came back, or went."
          />
          <MetricRows metrics={changedDimensions} />
        </Card>
      )}
    </div>
  );
}

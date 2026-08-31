import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { CheckCircle2, Search, SquareDashed, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import { FindingDetail } from '@/components/findings/FindingDetail';
import { CategoryBadge, SeverityBadge, StatusBadge } from '@/components/findings/SeverityBadge';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card, CardBody } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { findingKeys, findingsApi, findingTypeLabel } from '@/services/findingsApi';
import type { Dataset, Finding, FindingFilters, FindingStatus, Severity } from '@/types/api';
import { SEVERITIES } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber, formatPercent } from '@/utils/format';

const PAGE_SIZE = 25;

const STATUS_OPTIONS: { value: FindingStatus; label: string }[] = [
  { value: 'open', label: 'Open' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'ignored', label: 'Ignored' },
];

const SEVERITY_LABELS: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

function FilterChip({
  label,
  active,
  count,
  onClick,
}: {
  label: string;
  active: boolean;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors',
        active
          ? 'bg-accent-soft text-accent'
          : 'text-fg-muted hover:bg-surface-hover hover:text-fg',
      )}
    >
      {label}
      {count !== undefined && count > 0 && (
        <span className="tabular text-[11px] text-fg-subtle">{count}</span>
      )}
    </button>
  );
}

export function DatasetFindingsPage() {
  const dataset = useOutletContext<Dataset>();
  const [severities, setSeverities] = useState<Severity[]>([]);
  const [statuses, setStatuses] = useState<FindingStatus[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Finding | null>(null);

  const filters: FindingFilters = useMemo(
    () => ({
      severity: severities,
      status: statuses,
      type: types,
      search,
      limit: PAGE_SIZE,
      offset,
    }),
    [severities, statuses, types, search, offset],
  );

  const enabled = dataset.status === 'ready';

  const summary = useQuery({
    queryKey: findingKeys.summary(dataset.id),
    queryFn: () => findingsApi.summary(dataset.id),
    enabled,
  });

  const { data, isPending, isError, error } = useQuery({
    queryKey: findingKeys.list(dataset.id, filters),
    queryFn: () => findingsApi.list(dataset.id, filters),
    enabled,
    placeholderData: keepPreviousData,
  });

  function toggle<T>(value: T, current: T[], set: (next: T[]) => void) {
    setOffset(0);
    set(current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  }

  const hasFilters =
    severities.length > 0 || statuses.length > 0 || types.length > 0 || search.trim() !== '';

  function clearFilters() {
    setSeverities([]);
    setStatuses([]);
    setTypes([]);
    setSearch('');
    setOffset(0);
  }

  if (!enabled) {
    return (
      <Card>
        <EmptyState
          icon={SquareDashed}
          title="No analysis yet"
          description="Run an analysis to see what Obseil finds in this dataset."
        />
      </Card>
    );
  }

  if (isError) {
    return (
      <Alert tone="danger" title="Could not load the findings">
        {error instanceof ApiError ? error.message : 'Please try again in a moment.'}
      </Alert>
    );
  }

  const topTypes = Object.entries(summary.data?.by_type ?? {}).slice(0, 6);
  const total = data?.total ?? 0;

  return (
    <>
      <Card>
        <CardBody className="space-y-3 border-b border-border-default p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
              placeholder="Search findings"
              leadingIcon={<Search className="size-4" />}
              aria-label="Search findings"
              containerClassName="sm:max-w-xs"
            />
            <div className="-mx-1 flex gap-1 overflow-x-auto px-1 sm:ml-auto">
              {SEVERITIES.map((severity) => (
                <FilterChip
                  key={severity}
                  label={SEVERITY_LABELS[severity]}
                  count={summary.data?.by_severity[severity]}
                  active={severities.includes(severity)}
                  onClick={() => toggle(severity, severities, setSeverities)}
                />
              ))}
            </div>
          </div>

          <div className="-mx-1 flex flex-wrap gap-1 px-1">
            {STATUS_OPTIONS.map(({ value, label }) => (
              <FilterChip
                key={value}
                label={label}
                active={statuses.includes(value)}
                onClick={() => toggle(value, statuses, setStatuses)}
              />
            ))}
            {topTypes.length > 0 && (
              <span className="mx-1 self-center text-border-strong" aria-hidden="true">
                |
              </span>
            )}
            {topTypes.map(([type, count]) => (
              <FilterChip
                key={type}
                label={findingTypeLabel(type)}
                count={count}
                active={types.includes(type)}
                onClick={() => toggle(type, types, setTypes)}
              />
            ))}
            {hasFilters && (
              <Button
                size="sm"
                variant="ghost"
                leadingIcon={<X className="size-3.5" />}
                onClick={clearFilters}
              >
                Clear
              </Button>
            )}
          </div>
        </CardBody>

        {isPending ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }, (_, index) => (
              <Skeleton key={index} className="h-12 w-full" />
            ))}
          </div>
        ) : total === 0 ? (
          <EmptyState
            icon={hasFilters ? Search : CheckCircle2}
            title={hasFilters ? 'No findings match these filters' : 'No issues found'}
            description={
              hasFilters
                ? 'Try widening the filters, or clear them to see everything.'
                : 'Every quality check passed on this dataset. That is a good sign - and Obseil records which checks ran, not just that they passed.'
            }
            action={
              hasFilters ? (
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <TableScroller>
              <Table>
                <THead>
                  <TR>
                    <TH>Severity</TH>
                    <TH>Finding</TH>
                    <TH>Column</TH>
                    <TH numeric>Affected</TH>
                    <TH>Status</TH>
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((finding) => (
                    <TR key={finding.id} className="cursor-pointer">
                      <TD>
                        <SeverityBadge severity={finding.severity} />
                      </TD>
                      <TD className="max-w-md">
                        <button
                          type="button"
                          onClick={() => setSelected(finding)}
                          className="block w-full text-left"
                        >
                          <span className="font-medium text-fg underline-offset-4 hover:text-accent hover:underline">
                            {finding.title}
                          </span>
                          <span className="mt-0.5 flex items-center gap-2 text-[12px] text-fg-subtle">
                            {findingTypeLabel(finding.type)}
                            <CategoryBadge category={finding.category} />
                          </span>
                        </button>
                      </TD>
                      <TD className="font-mono text-[12px] text-fg-muted">
                        {finding.column_name ?? '-'}
                      </TD>
                      <TD numeric>
                        {finding.affected_rows === null ? (
                          '-'
                        ) : (
                          <>
                            {formatNumber(finding.affected_rows)}
                            {finding.affected_percentage !== null && (
                              <span className="ml-1 text-fg-subtle">
                                ({formatPercent(finding.affected_percentage)})
                              </span>
                            )}
                          </>
                        )}
                      </TD>
                      <TD>
                        <StatusBadge status={finding.status} />
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </TableScroller>

            <CardBody className="flex flex-wrap items-center justify-between gap-3 border-t border-border-default px-4 py-3">
              <p className="tabular text-[13px] text-fg-muted" aria-live="polite">
                {formatNumber(offset + 1)}-{formatNumber(offset + data.items.length)} of{' '}
                {formatNumber(total)}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(offset - PAGE_SIZE, 0))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset + data.items.length >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </CardBody>
          </>
        )}
      </Card>

      <FindingDetail
        finding={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
      />
    </>
  );
}

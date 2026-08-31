import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Search, SquareDashed } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import { ColumnTypeBadge } from '@/components/datasets/ColumnTypeBadge';
import { MissingBar } from '@/components/datasets/MissingBar';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Input } from '@/components/ui/Input';
import { Skeleton } from '@/components/ui/Skeleton';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { datasetKeys, datasetsApi } from '@/services/datasetsApi';
import type { ColumnProfile, ColumnType, Dataset } from '@/types/api';
import { cn } from '@/utils/cn';
import { formatNumber, formatPercent, formatStatistic, truncate } from '@/utils/format';

const TYPE_FILTERS: { value: ColumnType | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'integer', label: 'Integer' },
  { value: 'numeric', label: 'Numeric' },
  { value: 'datetime', label: 'Date/time' },
  { value: 'categorical', label: 'Category' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'text', label: 'Text' },
];

function ColumnDetail({ column }: { column: ColumnProfile }) {
  const facts: { label: string; value: string }[] = [
    { label: 'Storage type', value: column.dtype },
    { label: 'Non-missing', value: formatNumber(column.count) },
    { label: 'Distinct', value: formatNumber(column.unique_count) },
    { label: 'Distinct share', value: formatPercent(column.unique_percentage) },
  ];

  if (column.numeric) {
    facts.push(
      { label: 'Mean', value: formatStatistic(column.numeric.mean) },
      { label: 'Median', value: formatStatistic(column.numeric.median) },
      { label: 'Std. deviation', value: formatStatistic(column.numeric.std) },
      { label: 'Minimum', value: formatStatistic(column.numeric.minimum) },
      { label: 'Q1', value: formatStatistic(column.numeric.q1) },
      { label: 'Q3', value: formatStatistic(column.numeric.q3) },
      { label: 'Maximum', value: formatStatistic(column.numeric.maximum) },
      { label: 'Zeros', value: formatNumber(column.numeric.zero_count) },
      { label: 'Negatives', value: formatNumber(column.numeric.negative_count) },
    );
  }
  if (column.datetime) {
    facts.push(
      { label: 'Earliest', value: column.datetime.earliest ?? '-' },
      { label: 'Latest', value: column.datetime.latest ?? '-' },
      { label: 'Span (days)', value: formatStatistic(column.datetime.range_days) },
    );
  }
  if (column.text) {
    facts.push(
      { label: 'Shortest value', value: formatStatistic(column.text.min_length) },
      { label: 'Longest value', value: formatStatistic(column.text.max_length) },
      { label: 'Empty strings', value: formatNumber(column.text.empty_string_count) },
      { label: 'Padded values', value: formatNumber(column.text.whitespace_padded_count) },
    );
  }

  return (
    <div className="grid gap-6 bg-surface-muted px-4 py-4 lg:grid-cols-[1fr_18rem]">
      <div>
        <h3 className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
          Statistics
        </h3>
        <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
          {facts.map(({ label, value }) => (
            <div key={label} className="min-w-0">
              <dt className="text-[12px] text-fg-subtle">{label}</dt>
              <dd className="tabular truncate text-[13px] text-fg" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      </div>

      <div>
        <h3 className="text-[12px] font-medium uppercase tracking-wide text-fg-subtle">
          Most common values
        </h3>
        {column.top_values.length === 0 ? (
          <p className="mt-3 text-[13px] text-fg-subtle">No values to show.</p>
        ) : (
          <ul className="mt-3 space-y-1.5">
            {column.top_values.slice(0, 6).map((entry) => (
              <li key={entry.value} className="text-[13px]">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="truncate font-mono text-[12px] text-fg" title={entry.value}>
                    {truncate(entry.value, 28)}
                  </span>
                  <span className="tabular shrink-0 text-fg-subtle">
                    {formatPercent(entry.percentage)}
                  </span>
                </div>
                <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface">
                  <div
                    className="h-full rounded-full bg-accent/60"
                    style={{ width: `${Math.max(entry.percentage, 2)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function DatasetColumnsPage() {
  const dataset = useOutletContext<Dataset>();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<ColumnType | 'all'>('all');
  const [expanded, setExpanded] = useState<string | null>(null);

  const { data, isPending, isError, error } = useQuery({
    queryKey: datasetKeys.statistics(dataset.id),
    queryFn: () => datasetsApi.statistics(dataset.id),
    enabled: dataset.status === 'ready',
  });

  const columns = useMemo(() => {
    if (!data) return [];
    const term = search.trim().toLowerCase();
    return data.columns.filter((column) => {
      const matchesSearch = !term || column.name.toLowerCase().includes(term);
      const matchesType = typeFilter === 'all' || column.inferred_type === typeFilter;
      return matchesSearch && matchesType;
    });
  }, [data, search, typeFilter]);

  if (dataset.status !== 'ready') {
    return (
      <Card>
        <EmptyState
          icon={SquareDashed}
          title="No analysis yet"
          description="Run an analysis to see the schema and per-column statistics."
        />
      </Card>
    );
  }

  if (isPending) return <Skeleton className="h-96 w-full" />;

  if (isError || !data) {
    return (
      <Alert tone="danger" title="Could not load the columns">
        {error instanceof ApiError ? error.message : 'Please try again in a moment.'}
      </Alert>
    );
  }

  return (
    <Card>
      <CardBody className="flex flex-col gap-3 border-b border-border-default p-4 sm:flex-row sm:items-center">
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search columns"
          leadingIcon={<Search className="size-4" />}
          aria-label="Search columns"
          containerClassName="sm:max-w-xs"
        />
        <div className="-mx-1 flex gap-1 overflow-x-auto px-1 sm:ml-auto">
          {TYPE_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              onClick={() => setTypeFilter(value)}
              aria-pressed={typeFilter === value}
              className={cn(
                'whitespace-nowrap rounded-md px-2.5 py-1.5 text-[13px] font-medium transition-colors',
                typeFilter === value
                  ? 'bg-accent-soft text-accent'
                  : 'text-fg-muted hover:bg-surface-hover hover:text-fg',
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </CardBody>

      {columns.length === 0 ? (
        <EmptyState
          size="sm"
          title="No columns match"
          description="Try a different search term or clear the type filter."
        />
      ) : (
        <TableScroller>
          <Table>
            <THead>
              <TR>
                <TH className="w-8" aria-label="Expand" />
                <TH>Column</TH>
                <TH>Type</TH>
                <TH numeric>Missing</TH>
                <TH numeric>Distinct</TH>
                <TH>Notes</TH>
              </TR>
            </THead>
            <TBody>
              {columns.map((column) => {
                const isOpen = expanded === column.name;
                return [
                  <TR key={column.name}>
                    <TD className="w-8 pr-0">
                      <button
                        type="button"
                        onClick={() => setExpanded(isOpen ? null : column.name)}
                        aria-expanded={isOpen}
                        aria-label={`${isOpen ? 'Hide' : 'Show'} statistics for ${column.name}`}
                        className="rounded p-1 text-fg-subtle transition-colors hover:text-fg"
                      >
                        <ChevronRight
                          className={cn('size-4 transition-transform', isOpen && 'rotate-90')}
                          aria-hidden="true"
                        />
                      </button>
                    </TD>
                    <TD className="font-mono text-[13px] font-medium">{column.name}</TD>
                    <TD>
                      <ColumnTypeBadge type={column.inferred_type} />
                    </TD>
                    <TD numeric>
                      <div className="flex justify-end">
                        <MissingBar percentage={column.missing_percentage} />
                      </div>
                    </TD>
                    <TD numeric>{formatNumber(column.unique_count)}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1.5">
                        {column.is_constant && <Badge tone="warning">Constant</Badge>}
                        {column.is_unique && <Badge tone="neutral">Identifier</Badge>}
                        {column.is_numeric_like && <Badge tone="medium">Numbers as text</Badge>}
                      </div>
                    </TD>
                  </TR>,
                  isOpen && (
                    <tr key={`${column.name}-detail`}>
                      <td colSpan={6} className="p-0">
                        <ColumnDetail column={column} />
                      </td>
                    </tr>
                  ),
                ];
              })}
            </TBody>
          </Table>
        </TableScroller>
      )}
    </Card>
  );
}

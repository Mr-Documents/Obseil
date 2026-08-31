import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, SquareDashed } from 'lucide-react';
import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card, CardBody } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { datasetKeys, datasetsApi } from '@/services/datasetsApi';
import type { Dataset } from '@/types/api';
import { formatNumber, truncate } from '@/utils/format';

const PAGE_SIZE = 50;

/**
 * Paginated row view.
 *
 * The whole file is never fetched: the server caps the page size and this
 * requests one window at a time. `keepPreviousData` holds the current page on
 * screen while the next one loads, so paging does not flash an empty table.
 */
export function DatasetRowsPage() {
  const dataset = useOutletContext<Dataset>();
  const [offset, setOffset] = useState(0);

  const { data, isPending, isFetching, isError, error } = useQuery({
    queryKey: datasetKeys.preview(dataset.id, offset, PAGE_SIZE),
    queryFn: () => datasetsApi.preview(dataset.id, { offset, limit: PAGE_SIZE }),
    enabled: dataset.status === 'ready',
    placeholderData: keepPreviousData,
  });

  if (dataset.status !== 'ready') {
    return (
      <Card>
        <EmptyState
          icon={SquareDashed}
          title="No analysis yet"
          description="Run an analysis to browse this dataset's rows."
        />
      </Card>
    );
  }

  if (isPending) return <Skeleton className="h-96 w-full" />;

  if (isError || !data) {
    return (
      <Alert tone="danger" title="Could not load the rows">
        {error instanceof ApiError ? error.message : 'Please try again in a moment.'}
      </Alert>
    );
  }

  const start = data.rows.length === 0 ? 0 : offset + 1;
  const end = offset + data.rows.length;
  const hasPrevious = offset > 0;
  const hasNext = end < data.total_rows;

  return (
    <Card>
      <TableScroller>
        <Table>
          <THead>
            <TR>
              <TH numeric className="sticky left-0 z-10 bg-surface-muted">
                #
              </TH>
              {data.columns.map((column) => (
                <TH key={column} className="font-mono normal-case tracking-normal">
                  {column}
                </TH>
              ))}
            </TR>
          </THead>
          <TBody>
            {data.rows.map((row) => (
              <TR key={row.index}>
                <TD numeric className="sticky left-0 z-10 bg-surface text-fg-subtle">
                  {formatNumber(row.index + 1)}
                </TD>
                {data.columns.map((column) => {
                  const value = row.values[column];
                  return (
                    <TD key={column} className="max-w-[18rem]">
                      {value === null ? (
                        <span className="text-[12px] italic text-fg-subtle">null</span>
                      ) : (
                        <span className="block truncate font-mono text-[12px]" title={value}>
                          {truncate(value, 60)}
                        </span>
                      )}
                    </TD>
                  );
                })}
              </TR>
            ))}
          </TBody>
        </Table>
      </TableScroller>

      <CardBody className="flex flex-wrap items-center justify-between gap-3 border-t border-border-default px-4 py-3">
        <p className="tabular text-[13px] text-fg-muted" aria-live="polite">
          {formatNumber(start)}-{formatNumber(end)} of {formatNumber(data.total_rows)} rows
        </p>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={!hasPrevious || isFetching}
            leadingIcon={<ChevronLeft className="size-4" />}
            onClick={() => setOffset((current) => Math.max(current - PAGE_SIZE, 0))}
          >
            Previous
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={!hasNext || isFetching}
            trailingIcon={<ChevronRight className="size-4" />}
            onClick={() => setOffset((current) => current + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

import { useQuery } from '@tanstack/react-query';
import { FileUp, Upload } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { TBody, TD, TH, THead, TR, Table, TableScroller } from '@/components/ui/Table';
import { ApiError } from '@/services/apiClient';
import { datasetKeys, datasetsApi } from '@/services/datasetsApi';
import { formatBytes, formatNumber, formatRelative } from '@/utils/format';

import { DatasetStatusBadge } from './DatasetStatusBadge';

export function DatasetList({
  projectId,
  onUploadClick,
}: {
  projectId: string;
  onUploadClick: () => void;
}) {
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: datasetKeys.listForProject(projectId),
    queryFn: () => datasetsApi.listForProject(projectId, { limit: 100 }),
  });

  if (isPending) {
    return (
      <div className="space-y-2 p-5">
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-5">
        <Alert
          tone="danger"
          title="Could not load datasets"
          action={
            <Button size="sm" variant="secondary" onClick={() => void refetch()}>
              Retry
            </Button>
          }
        >
          {error instanceof ApiError ? error.message : 'Please try again in a moment.'}
        </Alert>
      </div>
    );
  }

  if (data.items.length === 0) {
    return (
      <EmptyState
        icon={FileUp}
        title="No datasets yet"
        description="Upload a CSV or Excel file and Obseil will profile it, check its quality and score it."
        action={
          <Button
            variant="primary"
            leadingIcon={<Upload className="size-4" />}
            onClick={onUploadClick}
          >
            Upload a dataset
          </Button>
        }
      />
    );
  }

  return (
    <TableScroller>
      <Table>
        <THead>
          <TR>
            <TH>Dataset</TH>
            <TH>Status</TH>
            <TH numeric>Rows</TH>
            <TH numeric>Columns</TH>
            <TH numeric>Size</TH>
            <TH>Uploaded</TH>
          </TR>
        </THead>
        <TBody>
          {data.items.map((dataset) => (
            <TR key={dataset.id}>
              <TD>
                <Link
                  to={`/datasets/${dataset.id}`}
                  className="font-medium text-fg underline-offset-4 hover:text-accent hover:underline"
                >
                  {dataset.name}
                </Link>
                <span className="ml-2 font-mono text-[11px] uppercase text-fg-subtle">
                  {dataset.file_format}
                </span>
              </TD>
              <TD>
                <DatasetStatusBadge status={dataset.status} />
              </TD>
              <TD numeric>{formatNumber(dataset.row_count)}</TD>
              <TD numeric>{formatNumber(dataset.column_count)}</TD>
              <TD numeric>{formatBytes(dataset.size_bytes)}</TD>
              <TD className="whitespace-nowrap text-fg-muted">
                {formatRelative(dataset.created_at)}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </TableScroller>
  );
}

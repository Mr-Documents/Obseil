import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { DatasetStatus } from '@/types/api';

const STATUS: Record<DatasetStatus, { label: string; tone: BadgeTone }> = {
  uploaded: { label: 'Not analysed', tone: 'neutral' },
  analyzing: { label: 'Analysing', tone: 'accent' },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'critical' },
};

export function DatasetStatusBadge({ status }: { status: DatasetStatus }) {
  const { label, tone } = STATUS[status] ?? STATUS.uploaded;
  return (
    <Badge tone={tone} dot>
      {label}
    </Badge>
  );
}

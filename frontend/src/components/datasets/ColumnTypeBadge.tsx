import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { ColumnType } from '@/types/api';

const TYPE_LABELS: Record<ColumnType, { label: string; tone: BadgeTone }> = {
  integer: { label: 'Integer', tone: 'accent' },
  numeric: { label: 'Numeric', tone: 'accent' },
  boolean: { label: 'Boolean', tone: 'neutral' },
  datetime: { label: 'Date/time', tone: 'low' },
  categorical: { label: 'Category', tone: 'neutral' },
  text: { label: 'Text', tone: 'neutral' },
  empty: { label: 'Empty', tone: 'warning' },
};

export function ColumnTypeBadge({ type }: { type: ColumnType }) {
  const { label, tone } = TYPE_LABELS[type] ?? TYPE_LABELS.text;
  return <Badge tone={tone}>{label}</Badge>;
}

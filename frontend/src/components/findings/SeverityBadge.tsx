import { Badge, type BadgeTone } from '@/components/ui/Badge';
import type { FindingStatus, Severity } from '@/types/api';

const SEVERITY_TONE: Record<Severity, BadgeTone> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
};

const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <Badge tone={SEVERITY_TONE[severity]} dot>
      {SEVERITY_LABEL[severity]}
    </Badge>
  );
}

const STATUS: Record<FindingStatus, { label: string; tone: BadgeTone }> = {
  open: { label: 'Open', tone: 'neutral' },
  reviewed: { label: 'Reviewed', tone: 'success' },
  ignored: { label: 'Ignored', tone: 'neutral' },
};

export function StatusBadge({ status }: { status: FindingStatus }) {
  const { label, tone } = STATUS[status] ?? STATUS.open;
  return <Badge tone={tone}>{label}</Badge>;
}

/**
 * Rule findings are facts; anomalies are candidates. The badge exists so a
 * reader can tell which claim is being made without reading the method.
 */
export function CategoryBadge({ category }: { category: string }) {
  if (category === 'anomaly') {
    return <Badge tone="accent">ML anomaly</Badge>;
  }
  return null;
}

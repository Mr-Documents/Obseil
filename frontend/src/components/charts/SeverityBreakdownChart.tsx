import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState } from '@/components/ui/EmptyState';
import type { Severity } from '@/types/api';
import { SEVERITIES } from '@/types/api';
import { formatNumber } from '@/utils/format';

import { AXIS_TICK, BAR_RADIUS, SEVERITY_COLORS } from './chartTheme';
import { ChartTooltip } from './ChartTooltip';

const LABELS: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

/**
 * Findings by severity.
 *
 * Horizontal bars, not a pie: the job is comparing magnitudes across four
 * ordered categories, and bar length is read far more accurately than angle.
 * The order is fixed by severity, never sorted by value, so the shape of the
 * chart is comparable between datasets at a glance.
 *
 * Severity uses the reserved status palette rather than the categorical ramp —
 * these are states, not series, and "critical" must look the same everywhere
 * in the product.
 */
export function SeverityBreakdownChart({ counts }: { counts: Record<string, number> }) {
  const data = SEVERITIES.map((severity) => ({
    severity,
    label: LABELS[severity],
    count: counts[severity] ?? 0,
  }));

  const total = data.reduce((sum, entry) => sum + entry.count, 0);
  if (total === 0) {
    return (
      <EmptyState
        size="sm"
        title="No findings to chart"
        description="Every quality check passed on this dataset."
      />
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={168}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 40, bottom: 4, left: 0 }}
          barCategoryGap={6}
        >
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={72}
            axisLine={false}
            tickLine={false}
            tick={AXIS_TICK}
          />
          <Tooltip
            cursor={{ fill: 'var(--surface-hover)' }}
            content={
              <ChartTooltip
                formatValue={(value) => `${formatNumber(value)} finding${value === 1 ? '' : 's'}`}
              />
            }
          />
          <Bar dataKey="count" name="Findings" radius={BAR_RADIUS} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell key={entry.severity} fill={SEVERITY_COLORS[entry.severity]} />
            ))}
            {/* Four categories, so every bar is directly labelled — no legend
                needed and no hover required to read a value. */}
            <LabelList
              dataKey="count"
              position="right"
              offset={8}
              fill="var(--fg-muted)"
              fontSize={12}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {/* The chart is decorative for assistive technology; this is the data. */}
      <table className="sr-only">
        <caption>Findings by severity</caption>
        <thead>
          <tr>
            <th scope="col">Severity</th>
            <th scope="col">Findings</th>
          </tr>
        </thead>
        <tbody>
          {data.map((entry) => (
            <tr key={entry.severity}>
              <th scope="row">{entry.label}</th>
              <td>{entry.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

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
import type { ColumnProfile } from '@/types/api';
import { formatNumber, formatPercent, truncate } from '@/utils/format';

import { AXIS_TICK, BAR_RADIUS, SEVERITY_COLORS } from './chartTheme';
import { ChartTooltip } from './ChartTooltip';

/** Only the worst offenders: a bar per column is unreadable past a dozen. */
const MAX_COLUMNS = 10;

/**
 * Where values are missing.
 *
 * Only columns that actually have gaps are plotted, worst first — a chart with
 * forty zero-length bars communicates nothing except that the chart exists.
 *
 * Bars are coloured by the same severity bands the quality engine uses, so a
 * bar that looks alarming corresponds to a finding that genuinely is. The
 * visual and the data never disagree.
 */
function severityFor(percentage: number) {
  if (percentage >= 80) return SEVERITY_COLORS.critical;
  if (percentage >= 40) return SEVERITY_COLORS.high;
  if (percentage >= 15) return SEVERITY_COLORS.medium;
  return SEVERITY_COLORS.low;
}

export function MissingValuesChart({ columns }: { columns: ColumnProfile[] }) {
  const data = columns
    .filter((column) => column.missing_count > 0)
    .sort((a, b) => b.missing_percentage - a.missing_percentage)
    .slice(0, MAX_COLUMNS)
    .map((column) => ({
      name: column.name,
      label: truncate(column.name, 18),
      percentage: Number(column.missing_percentage.toFixed(2)),
      count: column.missing_count,
    }));

  if (data.length === 0) {
    return (
      <EmptyState
        size="sm"
        title="No missing values"
        description="Every column is fully populated."
      />
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={Math.max(data.length * 30 + 24, 120)}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 48, bottom: 4, left: 0 }}
          barCategoryGap={6}
        >
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={128}
            axisLine={false}
            tickLine={false}
            tick={{ ...AXIS_TICK, fontFamily: 'var(--font-mono)' }}
          />
          <Tooltip
            cursor={{ fill: 'var(--surface-hover)' }}
            content={
              <ChartTooltip
                formatValue={(value) => formatPercent(value)}
                renderDetail={(entry) => {
                  const row = entry.payload as { count?: number; name?: string } | undefined;
                  return row ? `${formatNumber(row.count ?? 0)} missing values` : null;
                }}
              />
            }
          />
          <Bar dataKey="percentage" name="Missing" radius={BAR_RADIUS} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={severityFor(entry.percentage)} />
            ))}
            <LabelList
              dataKey="percentage"
              position="right"
              offset={8}
              fill="var(--fg-muted)"
              fontSize={12}
              formatter={(value: number) => formatPercent(value)}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {columns.filter((column) => column.missing_count > 0).length > MAX_COLUMNS && (
        <p className="mt-2 text-[12px] text-fg-subtle">
          Showing the {MAX_COLUMNS} columns with the most missing values.
        </p>
      )}

      <table className="sr-only">
        <caption>Missing values by column</caption>
        <thead>
          <tr>
            <th scope="col">Column</th>
            <th scope="col">Missing</th>
          </tr>
        </thead>
        <tbody>
          {data.map((entry) => (
            <tr key={entry.name}>
              <th scope="row">{entry.name}</th>
              <td>
                {entry.count} ({entry.percentage}%)
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

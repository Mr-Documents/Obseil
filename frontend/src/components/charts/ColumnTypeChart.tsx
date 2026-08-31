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

import type { ColumnProfile, ColumnType } from '@/types/api';
import { formatNumber } from '@/utils/format';

import { AXIS_TICK, BAR_RADIUS, VIZ_SERIES } from './chartTheme';
import { ChartTooltip } from './ChartTooltip';

/**
 * Fixed display order and fixed colour slot per type.
 *
 * Colour follows the entity, never its rank: "datetime" is always the same
 * colour whether it is the largest group or absent entirely, so two datasets
 * can be compared side by side.
 */
const TYPE_ORDER: { type: ColumnType; label: string; color: string }[] = [
  { type: 'integer', label: 'Integer', color: VIZ_SERIES[0] },
  { type: 'numeric', label: 'Numeric', color: VIZ_SERIES[1] },
  { type: 'datetime', label: 'Date/time', color: VIZ_SERIES[2] },
  { type: 'categorical', label: 'Category', color: VIZ_SERIES[3] },
  { type: 'text', label: 'Text', color: VIZ_SERIES[4] },
  { type: 'boolean', label: 'Boolean', color: VIZ_SERIES[5] },
  // Empty columns are a defect, not a type: they wear the status colour.
  { type: 'empty', label: 'Empty', color: 'var(--warning)' },
];

export function ColumnTypeChart({ columns }: { columns: ColumnProfile[] }) {
  const counts = new Map<ColumnType, number>();
  for (const column of columns) {
    counts.set(column.inferred_type, (counts.get(column.inferred_type) ?? 0) + 1);
  }

  const data = TYPE_ORDER.filter(({ type }) => (counts.get(type) ?? 0) > 0).map((entry) => ({
    ...entry,
    count: counts.get(entry.type) ?? 0,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={Math.max(data.length * 30 + 24, 120)}>
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
            width={80}
            axisLine={false}
            tickLine={false}
            tick={AXIS_TICK}
          />
          <Tooltip
            cursor={{ fill: 'var(--surface-hover)' }}
            content={
              <ChartTooltip
                formatValue={(value) => `${formatNumber(value)} column${value === 1 ? '' : 's'}`}
              />
            }
          />
          <Bar dataKey="count" name="Columns" radius={BAR_RADIUS} isAnimationActive={false}>
            {data.map((entry) => (
              <Cell key={entry.type} fill={entry.color} />
            ))}
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

      <table className="sr-only">
        <caption>Columns by inferred type</caption>
        <thead>
          <tr>
            <th scope="col">Type</th>
            <th scope="col">Columns</th>
          </tr>
        </thead>
        <tbody>
          {data.map((entry) => (
            <tr key={entry.type}>
              <th scope="row">{entry.label}</th>
              <td>{entry.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

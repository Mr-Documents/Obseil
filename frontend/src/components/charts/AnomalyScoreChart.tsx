import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState } from '@/components/ui/EmptyState';
import type { Anomaly } from '@/types/api';
import { formatNumber } from '@/utils/format';

import { AXIS_TICK, COLUMN_RADIUS, GRID_PROPS } from './chartTheme';
import { ChartTooltip } from './ChartTooltip';

const BUCKET_COUNT = 10;
const BUCKET_WIDTH = 100 / BUCKET_COUNT;

/**
 * How the flagged rows are spread across the unusualness scale.
 *
 * A histogram rather than a list, because the shape is the point: a long thin
 * tail means a few rows are genuinely far out, while a dense block near the
 * threshold means the model found no clear separation and the candidates
 * deserve more scepticism. That distinction is invisible in a table.
 *
 * Only flagged rows are plotted. Including the ninety-eight percent that were
 * scored and cleared would compress everything interesting into one bar.
 */
export function AnomalyScoreChart({ anomalies }: { anomalies: Anomaly[] }) {
  if (anomalies.length === 0) {
    return (
      <EmptyState
        size="sm"
        title="No unusual rows"
        description="The model scored every row and none stood out."
      />
    );
  }

  const buckets = Array.from({ length: BUCKET_COUNT }, (_, index) => ({
    lower: index * BUCKET_WIDTH,
    upper: (index + 1) * BUCKET_WIDTH,
    label: `${index * BUCKET_WIDTH}`,
    count: 0,
  }));

  for (const anomaly of anomalies) {
    const index = Math.min(Math.floor(anomaly.anomaly_score / BUCKET_WIDTH), BUCKET_COUNT - 1);
    buckets[index].count += 1;
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={buckets} margin={{ top: 8, right: 8, bottom: 4, left: -20 }}>
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={AXIS_TICK}
            interval={1}
            label={{
              value: 'Unusualness score',
              position: 'insideBottom',
              offset: -2,
              fill: 'var(--fg-subtle)',
              fontSize: 11,
            }}
          />
          <YAxis
            allowDecimals={false}
            axisLine={false}
            tickLine={false}
            tick={AXIS_TICK}
            width={44}
          />
          <Tooltip
            cursor={{ fill: 'var(--surface-hover)' }}
            content={
              <ChartTooltip
                formatValue={(value) => `${formatNumber(value)} row${value === 1 ? '' : 's'}`}
                renderDetail={(entry) => {
                  const row = entry.payload as { lower?: number; upper?: number } | undefined;
                  return row ? `Score ${row.lower}-${row.upper}` : null;
                }}
              />
            }
          />
          <Bar dataKey="count" name="Rows" radius={COLUMN_RADIUS} isAnimationActive={false}>
            {buckets.map((bucket) => (
              <Cell key={bucket.lower} fill="var(--viz-4)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="mt-3 text-[12px] leading-relaxed text-fg-subtle">
        Scores are relative to this dataset only. A long thin tail means a few rows are genuinely
        far from the rest; a dense block means the model found no clear separation.
      </p>

      <table className="sr-only">
        <caption>Flagged rows by unusualness score</caption>
        <thead>
          <tr>
            <th scope="col">Score range</th>
            <th scope="col">Rows</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket) => (
            <tr key={bucket.lower}>
              <th scope="row">
                {bucket.lower}-{bucket.upper}
              </th>
              <td>{bucket.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

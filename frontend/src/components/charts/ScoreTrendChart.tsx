import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EmptyState } from '@/components/ui/EmptyState';
import type { TrendPoint } from '@/types/api';
import { formatDate, formatNumber } from '@/utils/format';

import { AXIS_TICK, GRID_PROPS } from './chartTheme';
import { ChartTooltip } from './ChartTooltip';

/**
 * Quality score over time.
 *
 * A line, because the data is a change-over-time series and the shape of the
 * trend is the message. One series, so no legend - the card title names it.
 *
 * The grade bands are drawn as faint background regions rather than as
 * reference lines: they give the reader somewhere to place the line without
 * adding four labelled rules competing with the data.
 */
const BANDS = [
  { from: 0, to: 40, fill: 'var(--critical)' },
  { from: 40, to: 60, fill: 'var(--high)' },
  { from: 60, to: 80, fill: 'var(--medium)' },
  { from: 80, to: 95, fill: 'var(--low)' },
  { from: 95, to: 100, fill: 'var(--success)' },
];

export function ScoreTrendChart({ points }: { points: TrendPoint[] }) {
  if (points.length < 2) {
    return (
      <EmptyState
        size="sm"
        title="Not enough history yet"
        description="Upload and analyse a second dataset to see how quality is moving."
      />
    );
  }

  const data = points.map((point, index) => ({
    ...point,
    index,
    label: point.at ? formatDate(point.at) : `Run ${index + 1}`,
  }));

  return (
    <div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -16 }}>
          {BANDS.map((band) => (
            <ReferenceArea
              key={band.from}
              y1={band.from}
              y2={band.to}
              fill={band.fill}
              fillOpacity={0.06}
              stroke="none"
            />
          ))}
          <CartesianGrid {...GRID_PROPS} />
          <XAxis
            dataKey="label"
            axisLine={false}
            tickLine={false}
            tick={AXIS_TICK}
            minTickGap={24}
          />
          <YAxis
            domain={[0, 100]}
            ticks={[0, 40, 60, 80, 95, 100]}
            axisLine={false}
            tickLine={false}
            tick={AXIS_TICK}
            width={44}
          />
          <Tooltip
            content={
              <ChartTooltip
                formatValue={(value) => `${formatNumber(value, 1)} / 100`}
                renderDetail={(entry) => {
                  const row = entry.payload as TrendPoint | undefined;
                  return row
                    ? `${row.dataset_name} · ${formatNumber(row.finding_count)} findings`
                    : null;
                }}
              />
            }
          />
          <Line
            type="monotone"
            dataKey="score"
            name="Quality score"
            stroke="var(--viz-1)"
            strokeWidth={2}
            dot={{ r: 4, fill: 'var(--surface)', stroke: 'var(--viz-1)', strokeWidth: 2 }}
            activeDot={{ r: 6 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>

      <table className="sr-only">
        <caption>Quality score over time</caption>
        <thead>
          <tr>
            <th scope="col">Analysis</th>
            <th scope="col">Score</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.analysis_id}>
              <th scope="row">
                {point.label} - {point.dataset_name}
              </th>
              <td>{point.score ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

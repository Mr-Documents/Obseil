import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Anomaly, ColumnProfile } from '@/types/api';

import { AnomalyScoreChart } from './AnomalyScoreChart';
import { niceAxisMax } from './chartTheme';
import { ColumnTypeChart } from './ColumnTypeChart';
import { MissingValuesChart } from './MissingValuesChart';
import { SeverityBreakdownChart } from './SeverityBreakdownChart';

/**
 * Charts are tested through the accessible table each one renders alongside
 * the SVG. jsdom gives an SVG no layout, so asserting on rendered bars would
 * test nothing — but the table is the data, and it is what a screen-reader
 * user actually gets.
 */

function column(overrides: Partial<ColumnProfile> = {}): ColumnProfile {
  return {
    name: 'amount',
    position: 0,
    dtype: 'float64',
    inferred_type: 'numeric',
    count: 100,
    missing_count: 0,
    missing_percentage: 0,
    unique_count: 90,
    unique_percentage: 90,
    is_constant: false,
    is_unique: false,
    is_numeric_like: false,
    memory_bytes: 800,
    numeric: null,
    datetime: null,
    text: null,
    top_values: [],
    ...overrides,
  };
}

function anomaly(score: number, index: number): Anomaly {
  return {
    id: `anomaly-${index}`,
    analysis_id: 'analysis-1',
    dataset_id: 'dataset-1',
    row_index: index,
    rank: index,
    raw_score: 0.6,
    anomaly_score: score,
    feature_values: { amount: 100 },
    top_contributors: [{ feature: 'amount', value: 100, deviation_iqr: 3.2 }],
  };
}

describe('SeverityBreakdownChart', () => {
  it('exposes every severity as accessible data, including the zeros', () => {
    render(<SeverityBreakdownChart counts={{ critical: 1, high: 3, medium: 0, low: 2 }} />);

    const table = within(screen.getByRole('table', { name: /findings by severity/i }));
    expect(table.getByRole('rowheader', { name: 'Critical' })).toBeInTheDocument();
    expect(table.getByRole('rowheader', { name: 'Medium' })).toBeInTheDocument();
  });

  it('says so instead of drawing an empty chart', () => {
    render(<SeverityBreakdownChart counts={{ critical: 0, high: 0, medium: 0, low: 0 }} />);

    expect(screen.getByText(/no findings to chart/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});

describe('MissingValuesChart', () => {
  it('plots only columns that actually have gaps', () => {
    render(
      <MissingValuesChart
        columns={[
          column({ name: 'complete', missing_count: 0, missing_percentage: 0 }),
          column({ name: 'sparse', missing_count: 40, missing_percentage: 40 }),
        ]}
      />,
    );

    const table = within(screen.getByRole('table', { name: /missing values by column/i }));
    expect(table.getByRole('rowheader', { name: 'sparse' })).toBeInTheDocument();
    expect(table.queryByRole('rowheader', { name: 'complete' })).not.toBeInTheDocument();
  });

  it('orders the worst offenders first', () => {
    render(
      <MissingValuesChart
        columns={[
          column({ name: 'small', missing_count: 5, missing_percentage: 5 }),
          column({ name: 'large', missing_count: 90, missing_percentage: 90 }),
          column({ name: 'middle', missing_count: 40, missing_percentage: 40 }),
        ]}
      />,
    );

    const headers = screen.getAllByRole('rowheader').map((element) => element.textContent);
    expect(headers).toEqual(['large', 'middle', 'small']);
  });

  it('celebrates a fully populated dataset', () => {
    render(<MissingValuesChart columns={[column()]} />);
    expect(screen.getByText(/no missing values/i)).toBeInTheDocument();
  });

  it('caps the number of columns plotted and says that it did', () => {
    const columns = Array.from({ length: 15 }, (_, index) =>
      column({ name: `col${index}`, missing_count: index + 1, missing_percentage: index + 1 }),
    );

    render(<MissingValuesChart columns={columns} />);

    expect(screen.getAllByRole('rowheader')).toHaveLength(10);
    expect(screen.getByText(/showing the 10 columns/i)).toBeInTheDocument();
  });
});

describe('ColumnTypeChart', () => {
  it('counts columns by inferred type', () => {
    render(
      <ColumnTypeChart
        columns={[
          column({ name: 'a', inferred_type: 'numeric' }),
          column({ name: 'b', inferred_type: 'numeric' }),
          column({ name: 'c', inferred_type: 'categorical' }),
        ]}
      />,
    );

    const table = within(screen.getByRole('table', { name: /columns by inferred type/i }));
    const numericRow = table.getByRole('rowheader', { name: 'Numeric' }).closest('tr');
    expect(numericRow).toHaveTextContent('2');
    expect(table.getByRole('rowheader', { name: 'Category' })).toBeInTheDocument();
  });

  it('omits types that are absent rather than drawing empty bars', () => {
    render(<ColumnTypeChart columns={[column({ inferred_type: 'numeric' })]} />);

    const table = within(screen.getByRole('table'));
    expect(table.queryByRole('rowheader', { name: 'Boolean' })).not.toBeInTheDocument();
  });
});

describe('AnomalyScoreChart', () => {
  it('buckets the flagged rows across the score range', () => {
    render(<AnomalyScoreChart anomalies={[anomaly(95, 0), anomaly(92, 1), anomaly(45, 2)]} />);

    const table = within(screen.getByRole('table', { name: /flagged rows by unusualness/i }));
    expect(table.getByRole('rowheader', { name: '90–100' }).closest('tr')).toHaveTextContent('2');
    expect(table.getByRole('rowheader', { name: '40–50' }).closest('tr')).toHaveTextContent('1');
  });

  it('states that the scale is dataset-relative', () => {
    render(<AnomalyScoreChart anomalies={[anomaly(80, 0)]} />);
    expect(screen.getByText(/relative to this dataset only/i)).toBeInTheDocument();
  });

  it('says nothing stood out rather than drawing an empty histogram', () => {
    render(<AnomalyScoreChart anomalies={[]} />);
    expect(screen.getByText(/no unusual rows/i)).toBeInTheDocument();
  });
});

describe('niceAxisMax', () => {
  it('fits the axis to sub-one-percent rates rather than to a hidden 0-100', () => {
    // The case that made the bars unreadable: two columns under 1% missing.
    expect(niceAxisMax(0.89)).toBe(1);
  });

  it('never returns a bound below the value it has to contain', () => {
    for (const value of [0, 0.01, 1, 1.1, 2, 4.9, 12, 26, 51, 99.9, 100]) {
      expect(niceAxisMax(value)).toBeGreaterThanOrEqual(value);
    }
  });

  it('uses the full scale once a column is mostly empty', () => {
    expect(niceAxisMax(64)).toBe(100);
    expect(niceAxisMax(100)).toBe(100);
  });
});

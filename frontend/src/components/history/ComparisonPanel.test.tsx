import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { AnalysisComparison, MetricComparison } from '@/types/api';

import { ComparisonPanel } from './ComparisonPanel';

function metric(overrides: Partial<MetricComparison> = {}): MetricComparison {
  return {
    key: 'quality_score',
    label: 'Quality score',
    baseline: 78,
    current: 87,
    delta: 9,
    direction: 'improved',
    polarity: 'higher_is_better',
    unit: '/100',
    ...overrides,
  };
}

function comparison(overrides: Partial<AnalysisComparison> = {}): AnalysisComparison {
  return {
    baseline_id: 'analysis-1',
    current_id: 'analysis-2',
    baseline_at: '2026-03-01T10:00:00Z',
    current_at: '2026-03-08T10:00:00Z',
    baseline_score: 78,
    current_score: 87,
    score_delta: 9,
    headline: 'Quality improved by +9.0 points.',
    metrics: [
      metric(),
      metric({
        key: 'missing_percentage',
        label: 'Missing values',
        baseline: 12,
        current: 4,
        delta: -8,
        direction: 'improved',
        polarity: 'lower_is_better',
        unit: '%',
      }),
      metric({
        key: 'row_count',
        label: 'Rows',
        baseline: 500,
        current: 600,
        delta: 100,
        direction: 'changed',
        polarity: 'neutral',
        unit: null,
      }),
    ],
    dimensions: [
      metric({
        key: 'validity',
        label: 'Validity',
        baseline: 16.8,
        current: 0,
        delta: -16.8,
        direction: 'improved',
        polarity: 'lower_is_better',
        unit: 'pts',
      }),
    ],
    finding_types: [
      { type: 'negative_values', baseline_count: 2, current_count: 0, status: 'resolved' },
      { type: 'outliers', baseline_count: 0, current_count: 1, status: 'new' },
    ],
    resolved_types: ['negative_values'],
    new_types: ['outliers'],
    ...overrides,
  };
}

describe('ComparisonPanel', () => {
  it('leads with both scores and the change between them', () => {
    render(<ComparisonPanel comparison={comparison()} />);

    // Both scores also appear in the metrics table below, hence getAllByText.
    expect(screen.getAllByText('78').length).toBeGreaterThan(0);
    expect(screen.getAllByText('87').length).toBeGreaterThan(0);
    expect(screen.getAllByText('+9').length).toBeGreaterThan(0);
  });

  it('states the outcome in words as well as a number', () => {
    render(<ComparisonPanel comparison={comparison()} />);
    expect(screen.getByText(/quality improved by/i)).toBeInTheDocument();
  });

  it('names what was resolved and what is new', () => {
    render(<ComparisonPanel comparison={comparison()} />);

    expect(screen.getByText('Resolved')).toBeInTheDocument();
    expect(screen.getByText('Negative values')).toBeInTheDocument();
    expect(screen.getByText('New')).toBeInTheDocument();
    expect(screen.getByText('Outliers')).toBeInTheDocument();
  });

  it('shows before and after for every metric', () => {
    render(<ComparisonPanel comparison={comparison()} />);

    const tables = screen.getAllByRole('table');
    const metrics = within(tables[0]);
    expect(metrics.getByText('Missing values')).toBeInTheDocument();
    expect(metrics.getByText('12')).toBeInTheDocument();
    expect(metrics.getByText('4')).toBeInTheDocument();
  });

  it('does not present a neutral change as an improvement', () => {
    render(<ComparisonPanel comparison={comparison()} />);

    const rowsRow = screen.getByText('Rows').closest('tr');
    expect(rowsRow).not.toBeNull();
    // "+100" is shown, but in neutral ink rather than the success colour.
    const delta = within(rowsRow as HTMLElement).getByText('+100');
    expect(delta.className).toContain('text-fg-muted');
    expect(delta.className).not.toContain('text-success');
  });

  it('reports a regression honestly', () => {
    render(
      <ComparisonPanel
        comparison={comparison({
          baseline_score: 90,
          current_score: 71,
          score_delta: -19,
          headline: 'Quality fell by 19.0 points.',
        })}
      />,
    );

    expect(screen.getByText(/quality fell by/i)).toBeInTheDocument();
    expect(screen.getByText('−19')).toBeInTheDocument();
  });

  it('handles an unchanged score without claiming movement', () => {
    render(
      <ComparisonPanel
        comparison={comparison({
          baseline_score: 80,
          current_score: 80,
          score_delta: 0,
          headline: 'The quality score is unchanged.',
          resolved_types: [],
          new_types: [],
        })}
      />,
    );

    expect(screen.getByText(/unchanged/i)).toBeInTheDocument();
    expect(screen.queryByText('Resolved')).not.toBeInTheDocument();
  });

  it('omits the dimension table when nothing moved', () => {
    render(<ComparisonPanel comparison={comparison({ dimensions: [] })} />);
    expect(screen.queryByText(/score movement by dimension/i)).not.toBeInTheDocument();
  });
});

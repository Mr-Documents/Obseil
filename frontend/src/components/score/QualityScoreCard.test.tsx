import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { QualityScore } from '@/types/api';

import { QualityScoreCard } from './QualityScoreCard';

function score(overrides: Partial<QualityScore> = {}): QualityScore {
  return {
    analysis_id: 'analysis-1',
    dataset_id: 'dataset-1',
    analysed_at: '2026-03-08T10:00:00Z',
    score: 64,
    grade: 'needs_attention',
    grade_label: 'Needs attention',
    summary: 'Real problems that will affect analysis.',
    total_penalty: 36,
    dimensions: [
      {
        dimension: 'completeness',
        label: 'Completeness',
        penalty: 35,
        raw_penalty: 42.8,
        cap: 35,
        capped: true,
        finding_count: 4,
      },
      {
        dimension: 'uniqueness',
        label: 'Uniqueness',
        penalty: 0,
        raw_penalty: 0,
        cap: 25,
        capped: false,
        finding_count: 0,
      },
      {
        dimension: 'anomaly',
        label: 'Anomalies',
        penalty: 1,
        raw_penalty: 1,
        cap: 10,
        capped: false,
        finding_count: 1,
      },
    ],
    top_contributors: [
      {
        finding_type: 'missing_values',
        severity: 'critical',
        column: 'promo_code',
        penalty: 23.6,
        affected_percentage: 92.6,
      },
    ],
    methodology: 'Every dataset starts at 100.',
    ...overrides,
  };
}

describe('QualityScoreCard', () => {
  it('leads with the score and its grade', () => {
    render(<QualityScoreCard score={score()} />);

    expect(screen.getByText('64')).toBeInTheDocument();
    expect(screen.getByText('/ 100')).toBeInTheDocument();
    expect(screen.getAllByText('Needs attention').length).toBeGreaterThan(0);
  });

  it('describes what the grade means in words, not just colour', () => {
    render(<QualityScoreCard score={score()} />);
    expect(screen.getByText(/real problems that will affect analysis/i)).toBeInTheDocument();
  });

  it('gives the meter an accessible label rather than relying on the visual', () => {
    render(<QualityScoreCard score={score()} />);
    expect(screen.getByRole('img', { name: /quality score 64 out of 100/i })).toBeInTheDocument();
  });

  it('shows every dimension, including the clean ones', () => {
    render(<QualityScoreCard score={score()} />);

    expect(screen.getByText('Completeness')).toBeInTheDocument();
    expect(screen.getByText('Uniqueness')).toBeInTheDocument();
    expect(screen.getByText('clear')).toBeInTheDocument();
  });

  it('marks a capped dimension as capped', () => {
    render(<QualityScoreCard score={score()} />);
    expect(screen.getByText(/capped/)).toBeInTheDocument();
  });

  it('explains the derivation on demand, and it adds up', async () => {
    render(<QualityScoreCard score={score()} />);

    await userEvent.click(screen.getByRole('button', { name: /why this score/i }));

    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('Starting score')).toBeInTheDocument();
    expect(dialog.getByText('100.0')).toBeInTheDocument();
    expect(dialog.getByText('−35')).toBeInTheDocument();
    expect(dialog.getByText('Final score')).toBeInTheDocument();
    expect(dialog.getByText('64')).toBeInTheDocument();
  });

  it('names the most expensive findings', async () => {
    render(<QualityScoreCard score={score()} />);

    await userEvent.click(screen.getByRole('button', { name: /why this score/i }));

    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('Missing values')).toBeInTheDocument();
    expect(dialog.getByText('promo_code')).toBeInTheDocument();
  });

  it('renders a perfect score without breaking the meter', () => {
    render(
      <QualityScoreCard
        score={score({
          score: 100,
          grade: 'excellent',
          grade_label: 'Excellent',
          total_penalty: 0,
        })}
      />,
    );

    // "100" also appears on the meter's axis, so assert via the meter label.
    expect(screen.getByRole('img', { name: /quality score 100 out of 100/i })).toBeInTheDocument();
    expect(screen.getAllByText('Excellent').length).toBeGreaterThan(0);
  });

  it('renders a zero score without breaking the meter', () => {
    render(
      <QualityScoreCard
        score={score({ score: 0, grade: 'critical', grade_label: 'Critical', total_penalty: 120 })}
      />,
    );

    expect(screen.getByRole('img', { name: /quality score 0 out of 100/i })).toBeInTheDocument();
    expect(screen.getAllByText('Critical').length).toBeGreaterThan(0);
  });
});

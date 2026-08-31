import { describe, expect, it } from 'vitest';

import {
  formatBytes,
  formatCompact,
  formatDate,
  formatDelta,
  formatDuration,
  formatNumber,
  formatPercent,
  formatStatistic,
  truncate,
} from './format';

describe('formatNumber', () => {
  it('groups thousands', () => {
    expect(formatNumber(1234567)).toBe('1,234,567');
  });

  it('renders an em dash for missing or non-finite values', () => {
    expect(formatNumber(null)).toBe('—');
    expect(formatNumber(undefined)).toBe('—');
    expect(formatNumber(Number.NaN)).toBe('—');
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe('—');
  });
});

describe('formatCompact', () => {
  it('keeps small numbers exact', () => {
    expect(formatCompact(900)).toBe('900');
  });

  it('abbreviates large numbers', () => {
    expect(formatCompact(1234)).toBe('1.2K');
    expect(formatCompact(1_500_000)).toBe('1.5M');
  });
});

describe('formatPercent', () => {
  it('keeps precision for sub-one-percent values so they never read as zero', () => {
    expect(formatPercent(0.42)).toBe('0.42%');
  });

  it('drops decimals for large percentages', () => {
    expect(formatPercent(43.7)).toBe('44%');
  });

  it('honours an explicit precision', () => {
    expect(formatPercent(43.75, 1)).toBe('43.8%');
  });
});

describe('formatStatistic', () => {
  it('passes through strings and booleans', () => {
    expect(formatStatistic('category-a')).toBe('category-a');
    expect(formatStatistic(false)).toBe('false');
  });

  it('renders integers without decimals', () => {
    expect(formatStatistic(42)).toBe('42');
  });

  it('keeps large-but-readable integers grouped', () => {
    expect(formatStatistic(1.2e10)).toBe('12,000,000,000');
  });

  it('uses scientific notation where grouping stops being readable', () => {
    expect(formatStatistic(1.2e13)).toBe('1.20e+13');
    expect(formatStatistic(0.000004)).toBe('4.00e-6');
  });

  it('returns an em dash for null', () => {
    expect(formatStatistic(null)).toBe('—');
  });
});

describe('formatBytes', () => {
  it('scales to a readable unit', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(52428800)).toBe('50.0 MB');
  });
});

describe('formatDate', () => {
  it('formats ISO strings consistently', () => {
    expect(formatDate('2026-03-12T14:05:00Z')).toMatch(/12 Mar 2026/);
  });

  it('rejects unparseable input rather than rendering "Invalid Date"', () => {
    expect(formatDate('not-a-date')).toBe('—');
  });
});

describe('formatDuration', () => {
  it('switches units at sensible thresholds', () => {
    expect(formatDuration(340)).toBe('340 ms');
    expect(formatDuration(1200)).toBe('1.2 s');
    expect(formatDuration(125_000)).toBe('2m 5s');
  });
});

describe('formatDelta', () => {
  it('signs improvements and regressions', () => {
    expect(formatDelta(9)).toBe('+9');
    expect(formatDelta(-3)).toBe('−3');
  });

  it('describes a zero delta in words', () => {
    expect(formatDelta(0)).toBe('no change');
  });
});

describe('truncate', () => {
  it('leaves short strings alone', () => {
    expect(truncate('short', 10)).toBe('short');
  });

  it('ellipsises long strings', () => {
    expect(truncate('abcdefghij', 5)).toBe('abcd…');
  });
});

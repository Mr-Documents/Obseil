/**
 * Formatting helpers.
 *
 * Every number and date the user sees goes through this module so that
 * thousands separators, decimal places and date styles stay consistent across
 * the whole product. Locale is fixed to `en-US` for reproducible tests and
 * screenshots; switching to the browser locale later is a one-line change.
 */
import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns';

const LOCALE = 'en-US';

/** 1234567 -> "1,234,567" */
export function formatNumber(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits }).format(value);
}

/**
 * Compact notation for headline figures: 1234 -> "1.2K", 1_500_000 -> "1.5M".
 * Values below 1000 are rendered exactly, because "0.9K" reads worse than "900".
 */
export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  if (Math.abs(value) < 1000) return formatNumber(value);
  return new Intl.NumberFormat(LOCALE, { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  );
}

/**
 * Percentages arrive from the API already scaled 0-100.
 * Sub-1% values keep a decimal so "0.4%" never collapses to a misleading "0%".
 */
export function formatPercent(value: number | null | undefined, digits?: number): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const precision = digits ?? (value > 0 && value < 1 ? 2 : value < 10 ? 1 : 0);
  return `${new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: 0,
    maximumFractionDigits: precision,
  }).format(value)}%`;
}

/** Statistic values may be numbers, strings, booleans or absent. */
export function formatStatistic(value: unknown, maximumFractionDigits = 3): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '-';
    const magnitude = Math.abs(value);
    // Grouped digits stop being readable past a trillion, and a value smaller
    // than 1e-4 would round away to "0" entirely.
    if (magnitude >= 1e12 || (magnitude > 0 && magnitude < 1e-4)) {
      return value.toExponential(2);
    }
    if (Number.isInteger(value)) return formatNumber(value);
    return formatNumber(value, maximumFractionDigits);
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value);
}

/** 52428800 -> "50 MB" */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '-';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(
    Math.floor(Math.log(Math.abs(bytes)) / Math.log(1024)),
    units.length - 1,
  );
  const scaled = bytes / 1024 ** exponent;
  return `${scaled.toFixed(exponent === 0 ? 0 : scaled >= 100 ? 0 : 1)} ${units[exponent]}`;
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null;
  const date = typeof value === 'string' ? parseISO(value) : value;
  return isValid(date) ? date : null;
}

/** "12 Mar 2026" */
export function formatDate(value: string | Date | null | undefined): string {
  const date = toDate(value);
  return date ? format(date, 'd MMM yyyy') : '-';
}

/** "12 Mar 2026, 14:05" */
export function formatDateTime(value: string | Date | null | undefined): string {
  const date = toDate(value);
  return date ? format(date, 'd MMM yyyy, HH:mm') : '-';
}

/** "3 hours ago" */
export function formatRelative(value: string | Date | null | undefined): string {
  const date = toDate(value);
  return date ? `${formatDistanceToNowStrict(date)} ago` : '-';
}

/** "1.2 s" / "340 ms" - used for analysis durations. */
export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined || !Number.isFinite(milliseconds)) {
    return '-';
  }
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(1)} s`;
  const minutes = Math.floor(milliseconds / 60_000);
  const seconds = Math.round((milliseconds % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/** Signed delta for score comparisons: 9 -> "+9", -3 -> "−3" (true minus sign). */
export function formatDelta(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const rounded = Number(value.toFixed(digits));
  if (rounded === 0) return 'no change';
  const sign = rounded > 0 ? '+' : '−';
  return `${sign}${formatNumber(Math.abs(rounded), digits)}`;
}

/** Truncate long cell values without breaking the layout. */
export function truncate(value: string, maxLength = 60): string {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}…` : value;
}

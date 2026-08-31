import type {
  Finding,
  FindingFilters,
  FindingSummary,
  FindingUpdatePayload,
  Page,
} from '@/types/api';

import { api, request } from './apiClient';

/**
 * The API takes repeated query parameters for multi-valued filters
 * (`?severity=high&severity=critical`), which the shared client's flat query
 * map cannot express - so this one endpoint builds its own search string.
 */
function buildFindingQuery(filters: FindingFilters): string {
  const params = new URLSearchParams();
  for (const value of filters.severity ?? []) params.append('severity', value);
  for (const value of filters.type ?? []) params.append('type', value);
  for (const value of filters.status ?? []) params.append('status', value);
  for (const value of filters.category ?? []) params.append('category', value);
  if (filters.search?.trim()) params.set('search', filters.search.trim());
  params.set('limit', String(filters.limit ?? 50));
  params.set('offset', String(filters.offset ?? 0));
  return params.toString();
}

export const findingsApi = {
  list(datasetId: string, filters: FindingFilters = {}): Promise<Page<Finding>> {
    return request<Page<Finding>>(`/datasets/${datasetId}/findings?${buildFindingQuery(filters)}`);
  },

  summary(datasetId: string): Promise<FindingSummary> {
    return api.get<FindingSummary>(`/datasets/${datasetId}/findings/summary`);
  },

  get(findingId: string): Promise<Finding> {
    return api.get<Finding>(`/findings/${findingId}`);
  },

  update(findingId: string, payload: FindingUpdatePayload): Promise<Finding> {
    return api.patch<Finding>(`/findings/${findingId}`, payload);
  },
};

export const findingKeys = {
  all: ['findings'] as const,
  forDataset: (datasetId: string) => [...findingKeys.all, 'dataset', datasetId] as const,
  list: (datasetId: string, filters: FindingFilters) =>
    [...findingKeys.forDataset(datasetId), 'list', filters] as const,
  summary: (datasetId: string) => [...findingKeys.forDataset(datasetId), 'summary'] as const,
};

/** Display labels for the finding types the API can return. */
export const FINDING_TYPE_LABELS: Record<string, string> = {
  missing_values: 'Missing values',
  empty_column: 'Empty column',
  incomplete_rows: 'Incomplete rows',
  duplicate_rows: 'Duplicate rows',
  duplicate_identifier: 'Duplicate identifier',
  constant_column: 'Constant column',
  high_cardinality: 'High cardinality',
  outliers: 'Outliers',
  negative_values: 'Negative values',
  invalid_dates: 'Invalid dates',
  empty_strings: 'Empty strings',
  whitespace_padding: 'Whitespace padding',
  numbers_as_text: 'Numbers stored as text',
  ml_anomaly: 'ML anomaly',
};

export function findingTypeLabel(type: string): string {
  return FINDING_TYPE_LABELS[type] ?? type.replace(/_/g, ' ');
}

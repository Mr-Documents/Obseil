import type { Anomaly, AnomalyOverview, Page, QualityScore } from '@/types/api';

import { api } from './apiClient';

export const scoreApi = {
  get(datasetId: string): Promise<QualityScore> {
    return api.get<QualityScore>(`/datasets/${datasetId}/score`);
  },
};

export const anomaliesApi = {
  list(datasetId: string, params: { limit?: number; offset?: number } = {}) {
    return api.get<Page<Anomaly>>(`/datasets/${datasetId}/anomalies`, { query: params });
  },

  overview(datasetId: string): Promise<AnomalyOverview> {
    return api.get<AnomalyOverview>(`/datasets/${datasetId}/anomalies/overview`);
  },
};

export const scoreKeys = {
  all: ['score'] as const,
  detail: (datasetId: string) => [...scoreKeys.all, datasetId] as const,
};

export const anomalyKeys = {
  all: ['anomalies'] as const,
  forDataset: (datasetId: string) => [...anomalyKeys.all, datasetId] as const,
  overview: (datasetId: string) => [...anomalyKeys.forDataset(datasetId), 'overview'] as const,
  list: (datasetId: string, offset: number, limit: number) =>
    [...anomalyKeys.forDataset(datasetId), 'list', offset, limit] as const,
};

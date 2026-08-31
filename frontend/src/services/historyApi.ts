import type { AnalysisComparison, HistoryEntry, Page, TrendPoint } from '@/types/api';

import { api } from './apiClient';

export const historyApi = {
  forProject(projectId: string, params: { limit?: number; offset?: number } = {}) {
    return api.get<Page<HistoryEntry>>(`/projects/${projectId}/history`, { query: params });
  },

  forDataset(datasetId: string, params: { limit?: number; offset?: number } = {}) {
    return api.get<Page<HistoryEntry>>(`/datasets/${datasetId}/history`, { query: params });
  },

  trend(projectId: string): Promise<TrendPoint[]> {
    return api.get<TrendPoint[]>(`/projects/${projectId}/history/trend`);
  },

  /** Omit `baseline` to compare with the previous completed run in the project. */
  compare(analysisId: string, baseline?: string): Promise<AnalysisComparison> {
    return api.get<AnalysisComparison>(`/analyses/${analysisId}/compare`, {
      query: baseline ? { baseline } : undefined,
    });
  },
};

export const historyKeys = {
  all: ['history'] as const,
  project: (projectId: string) => [...historyKeys.all, 'project', projectId] as const,
  dataset: (datasetId: string) => [...historyKeys.all, 'dataset', datasetId] as const,
  trend: (projectId: string) => [...historyKeys.all, 'trend', projectId] as const,
  compare: (analysisId: string, baseline?: string) =>
    [...historyKeys.all, 'compare', analysisId, baseline ?? 'previous'] as const,
};

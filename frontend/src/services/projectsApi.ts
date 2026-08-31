import type {
  Page,
  Project,
  ProjectCreatePayload,
  ProjectSummary,
  ProjectUpdatePayload,
} from '@/types/api';

import { api } from './apiClient';

export const projectsApi = {
  list(params: { limit?: number; offset?: number } = {}): Promise<Page<ProjectSummary>> {
    return api.get<Page<ProjectSummary>>('/projects', { query: params });
  },

  get(projectId: string): Promise<Project> {
    return api.get<Project>(`/projects/${projectId}`);
  },

  create(payload: ProjectCreatePayload): Promise<Project> {
    return api.post<Project>('/projects', payload);
  },

  update(projectId: string, payload: ProjectUpdatePayload): Promise<Project> {
    return api.patch<Project>(`/projects/${projectId}`, payload);
  },

  remove(projectId: string): Promise<void> {
    return api.delete<void>(`/projects/${projectId}`);
  },
};

/** Query keys live beside the API module so they can never drift apart. */
export const projectKeys = {
  all: ['projects'] as const,
  list: (params: { limit?: number; offset?: number } = {}) =>
    [...projectKeys.all, 'list', params] as const,
  detail: (projectId: string) => [...projectKeys.all, 'detail', projectId] as const,
};

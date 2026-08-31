import type { Dataset, DatasetPreview, DatasetStatistics, Page } from '@/types/api';

import { ApiError, api, request } from './apiClient';
import { tokenStore } from './tokenStore';

export interface UploadOptions {
  name?: string;
  analyze?: boolean;
  /** 0-100, reported while the request body is being sent. */
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}

export const datasetsApi = {
  listForProject(projectId: string, params: { limit?: number; offset?: number } = {}) {
    return api.get<Page<Dataset>>(`/projects/${projectId}/datasets`, { query: params });
  },

  get(datasetId: string): Promise<Dataset> {
    return api.get<Dataset>(`/datasets/${datasetId}`);
  },

  remove(datasetId: string): Promise<void> {
    return api.delete<void>(`/datasets/${datasetId}`);
  },

  analyze(datasetId: string): Promise<unknown> {
    return api.post(`/datasets/${datasetId}/analyze`);
  },

  statistics(datasetId: string): Promise<DatasetStatistics> {
    return api.get<DatasetStatistics>(`/datasets/${datasetId}/statistics`);
  },

  preview(datasetId: string, params: { offset?: number; limit?: number } = {}) {
    return api.get<DatasetPreview>(`/datasets/${datasetId}/preview`, { query: params });
  },

  /**
   * Upload a file to a project.
   *
   * When a progress callback is supplied this uses XMLHttpRequest, for one
   * reason: `fetch` cannot report upload progress, and a multi-megabyte upload
   * with no progress bar feels broken. Without a callback it goes through the
   * shared fetch client like everything else.
   */
  upload(projectId: string, file: File, options: UploadOptions = {}): Promise<Dataset> {
    const { name, analyze = true, onProgress, signal } = options;
    const form = new FormData();
    form.append('file', file);
    if (name) form.append('name', name);
    form.append('analyze', String(analyze));

    if (!onProgress) {
      return request<Dataset>(`/projects/${projectId}/datasets`, {
        method: 'POST',
        formData: form,
        signal,
      });
    }
    return uploadWithProgress(projectId, form, onProgress, signal);
  },
};

interface ErrorEnvelope {
  error?: { code?: string; message?: string; request_id?: string };
}

/** Mirror `toApiError` for the XHR path so upload failures look identical. */
function xhrError(status: number, body: ErrorEnvelope | null): ApiError {
  const message =
    body?.error?.message ??
    (status === 0
      ? 'Could not reach the Obseil API. Check your connection and try again.'
      : 'The upload could not be completed.');
  return new ApiError(
    status,
    body?.error?.code ?? (status === 0 ? 'network_error' : 'http_error'),
    message,
    body?.error?.request_id ?? null,
  );
}

function uploadWithProgress(
  projectId: string,
  form: FormData,
  onProgress: (percent: number) => void,
  signal?: AbortSignal,
): Promise<Dataset> {
  return new Promise<Dataset>((resolve, reject) => {
    const base = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${base}/projects/${projectId}/datasets`);

    const token = tokenStore.getAccessToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);

    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    });

    xhr.addEventListener('load', () => {
      // The bytes are sent and the server is now analysing. Reporting 100% lets
      // the UI switch from "uploading" to "analysing" instead of stalling at 98%.
      onProgress(100);
      let body: ErrorEnvelope | null = null;
      try {
        body = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        body = null;
      }
      if (xhr.status >= 200 && xhr.status < 300 && body) {
        resolve(body as unknown as Dataset);
      } else {
        reject(xhrError(xhr.status, body));
      }
    });

    xhr.addEventListener('error', () => reject(xhrError(0, null)));
    xhr.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    signal?.addEventListener('abort', () => xhr.abort(), { once: true });

    xhr.send(form);
  });
}

export const datasetKeys = {
  all: ['datasets'] as const,
  listForProject: (projectId: string) => [...datasetKeys.all, 'project', projectId] as const,
  detail: (datasetId: string) => [...datasetKeys.all, 'detail', datasetId] as const,
  statistics: (datasetId: string) => [...datasetKeys.all, 'statistics', datasetId] as const,
  preview: (datasetId: string, offset: number, limit: number) =>
    [...datasetKeys.all, 'preview', datasetId, offset, limit] as const,
};

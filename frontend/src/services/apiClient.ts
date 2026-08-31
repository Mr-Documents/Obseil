/**
 * The single HTTP client.
 *
 * Responsibilities, all in one place so no component ever hand-rolls a fetch:
 *   - prefix every path with the configured API base URL
 *   - attach the bearer token
 *   - transparently refresh an expired access token once, then replay the
 *     request; concurrent 401s share a single in-flight refresh
 *   - convert every failure into an `ApiError` carrying a message that is
 *     safe and useful to show a person
 */
import type { ApiErrorBody, ApiErrorField } from '@/types/api';

import { tokenStore } from './tokenStore';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly fields: ApiErrorField[];

  constructor(
    status: number,
    code: string,
    message: string,
    requestId: string | null = null,
    fields: ApiErrorField[] = [],
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.fields = fields;
  }

  /** True when retrying is pointless — the request itself is wrong. */
  get isClientError(): boolean {
    return this.status >= 400 && this.status < 500;
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }

  /** Per-field messages for form validation failures, keyed by field name. */
  fieldErrors(): Record<string, string> {
    return Object.fromEntries(this.fields.map(({ field, message }) => [field, message]));
  }
}

const NETWORK_ERROR_MESSAGE =
  'Could not reach the Obseil API. Check your connection and try again.';

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  body?: unknown;
  /** Sent as multipart/form-data; `body` is ignored when present. */
  formData?: FormData;
  signal?: AbortSignal;
  /** Skip the Authorization header (used by login/register/refresh). */
  anonymous?: boolean;
  /** Internal: prevents an infinite refresh loop. */
  _isRetry?: boolean;
  query?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
  if (!query) return url;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value));
  }
  const search = params.toString();
  return search ? `${url}?${search}` : url;
}

async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-ID');
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body?.error) {
      return new ApiError(
        response.status,
        body.error.code,
        body.error.message,
        body.error.request_id ?? requestId,
        body.error.details?.fields ?? [],
      );
    }
  } catch {
    // Not JSON — fall through to a status-derived message.
  }
  return new ApiError(
    response.status,
    'http_error',
    response.status >= 500
      ? 'The Obseil API is having trouble right now. Please try again shortly.'
      : 'That request could not be completed.',
    requestId,
  );
}

/** Shared refresh promise so ten parallel 401s trigger exactly one refresh. */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = tokenStore.getRefreshToken();
  if (!refreshToken) return false;

  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(buildUrl('/auth/refresh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!response.ok) {
        tokenStore.clear();
        return false;
      }
      tokenStore.set(await response.json());
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, signal, anonymous, query, _isRetry } = options;

  const headers: Record<string, string> = {};
  if (!anonymous) {
    const token = tokenStore.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // Content-Type is deliberately omitted for FormData so the browser can set
  // the multipart boundary itself.
  if (!formData && body !== undefined) headers['Content-Type'] = 'application/json';

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      signal: signal ?? null,
      body: formData ?? (body === undefined ? null : JSON.stringify(body)),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'network_error', NETWORK_ERROR_MESSAGE);
  }

  if (response.status === 401 && !anonymous && !_isRetry) {
    if (await refreshAccessToken()) {
      return request<T>(path, { ...options, _isRetry: true });
    }
    tokenStore.clear();
  }

  if (!response.ok) throw await toApiError(response);

  if (response.status === 204 || response.headers.get('Content-Length') === '0') {
    return undefined as T;
  }

  const contentType = response.headers.get('Content-Type') ?? '';
  if (contentType.includes('application/json')) return (await response.json()) as T;
  return (await response.blob()) as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};

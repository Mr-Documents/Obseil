import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorResponse, jsonResponse } from '@/test/utils';

import { ApiError, api } from './apiClient';
import { tokenStore } from './tokenStore';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  tokenStore.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('attaches the bearer token to authenticated requests', async () => {
    tokenStore.set({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
      expires_in: 1800,
    });
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await api.get('/projects');

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBe('Bearer access-1');
  });

  it('omits the token for anonymous requests', async () => {
    tokenStore.set({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
      expires_in: 1800,
    });
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }));

    await api.post('/auth/login', { email: 'a@example.com' }, { anonymous: true });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.Authorization).toBeUndefined();
  });

  it('serialises query parameters and drops empty ones', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }));

    await api.get('/projects', { query: { limit: 10, offset: 0, search: undefined, q: '' } });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain('limit=10');
    expect(url).toContain('offset=0');
    expect(url).not.toContain('search');
    expect(url).not.toContain('q=');
  });

  it('turns an error envelope into an ApiError with field messages', async () => {
    fetchMock.mockResolvedValueOnce(
      errorResponse(422, 'validation_error', 'Some values are not valid.', {
        fields: [{ field: 'email', message: 'That is not a valid email address.' }],
      }),
    );

    const error = await api.post('/auth/register', {}).catch((cause: unknown) => cause);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.code).toBe('validation_error');
    expect(apiError.isClientError).toBe(true);
    expect(apiError.fieldErrors()).toEqual({ email: 'That is not a valid email address.' });
  });

  it('reports a friendly message when the network is unreachable', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    const error = (await api.get('/projects').catch((cause: unknown) => cause)) as ApiError;

    expect(error.code).toBe('network_error');
    expect(error.message).toMatch(/could not reach/i);
  });

  it('refreshes the access token once on 401 and replays the request', async () => {
    tokenStore.set({
      access_token: 'expired',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
      expires_in: 1800,
    });

    fetchMock
      .mockResolvedValueOnce(errorResponse(401, 'token_expired', 'Session expired.'))
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: 'fresh',
          refresh_token: 'refresh-2',
          token_type: 'bearer',
          expires_in: 1800,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ items: [] }));

    const result = await api.get<{ items: unknown[] }>('/projects');

    expect(result).toEqual({ items: [] });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(tokenStore.getAccessToken()).toBe('fresh');
    // The replay carries the new token, not the expired one.
    const [, retryInit] = fetchMock.mock.calls[2];
    expect(retryInit.headers.Authorization).toBe('Bearer fresh');
  });

  it('clears the session when the refresh itself fails', async () => {
    tokenStore.set({
      access_token: 'expired',
      refresh_token: 'stale',
      token_type: 'bearer',
      expires_in: 1800,
    });

    fetchMock
      .mockResolvedValueOnce(errorResponse(401, 'token_expired', 'Session expired.'))
      .mockResolvedValueOnce(errorResponse(401, 'authentication_failed', 'Invalid token.'));

    await api.get('/projects').catch(() => undefined);

    expect(tokenStore.hasSession()).toBe(false);
  });

  it('does not attempt a refresh loop on a second 401', async () => {
    tokenStore.set({
      access_token: 'expired',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
      expires_in: 1800,
    });

    fetchMock
      .mockResolvedValueOnce(errorResponse(401, 'token_expired', 'Session expired.'))
      .mockResolvedValueOnce(
        jsonResponse({
          access_token: 'fresh',
          refresh_token: 'refresh-2',
          token_type: 'bearer',
          expires_in: 1800,
        }),
      )
      .mockResolvedValueOnce(errorResponse(401, 'authentication_failed', 'Still unauthorised.'));

    await api.get('/projects').catch(() => undefined);

    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('returns undefined for 204 responses', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(api.delete('/projects/abc')).resolves.toBeUndefined();
  });
});

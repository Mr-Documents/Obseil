/**
 * Third-party sign-in.
 *
 * The browser never talks to Google or GitHub directly and never holds a
 * provider token. It leaves for the API's `start` endpoint, comes back to the
 * API's callback, and is redirected here with a **single-use code** that is
 * traded for Obseil tokens over a normal POST. Nothing sensitive is ever in a
 * URL, so nothing sensitive lands in browser history.
 */
import type { AuthResponse, OAuthProviderInfo } from '@/types/api';

import { api } from './apiClient';
import { tokenStore } from './tokenStore';

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

export const oauthKeys = {
  providers: ['oauth', 'providers'] as const,
};

export const oauthApi = {
  /** Empty when the deployment has configured no credentials. */
  providers(): Promise<OAuthProviderInfo[]> {
    return api.get<OAuthProviderInfo[]>('/auth/oauth/providers', { anonymous: true });
  },

  /**
   * Hand the browser to the provider.
   *
   * A full navigation, not fetch: the API answers with a redirect and sets an
   * httpOnly cookie that has to survive the round trip. An XHR would follow
   * the redirect itself and strand the user on this page.
   */
  start(provider: string): void {
    window.location.assign(`${BASE_URL}/auth/oauth/${provider}/start`);
  },

  async exchange(code: string): Promise<AuthResponse> {
    const result = await api.post<AuthResponse>(
      '/auth/oauth/exchange',
      { code },
      { anonymous: true },
    );
    tokenStore.set(result.tokens);
    return result;
  },
};

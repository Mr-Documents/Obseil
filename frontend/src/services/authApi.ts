import type { AuthResponse, LoginPayload, RegisterPayload, User } from '@/types/api';

import { api } from './apiClient';
import { tokenStore } from './tokenStore';

export const authApi = {
  async register(payload: RegisterPayload): Promise<AuthResponse> {
    const result = await api.post<AuthResponse>('/auth/register', payload, { anonymous: true });
    tokenStore.set(result.tokens);
    return result;
  },

  async login(payload: LoginPayload): Promise<AuthResponse> {
    const result = await api.post<AuthResponse>('/auth/login', payload, { anonymous: true });
    tokenStore.set(result.tokens);
    return result;
  },

  async logout(): Promise<void> {
    try {
      await api.post('/auth/logout');
    } catch {
      // Signing out must always succeed locally, even if the network does not.
    } finally {
      tokenStore.clear();
    }
  },

  me(): Promise<User> {
    return api.get<User>('/auth/me');
  },
};

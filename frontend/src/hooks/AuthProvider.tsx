import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';

import { authApi } from '@/services/authApi';
import { oauthApi } from '@/services/oauthApi';
import { tokenStore } from '@/services/tokenStore';
import type { LoginPayload, RegisterPayload, User } from '@/types/api';

import { type AuthStatus, AuthContext } from './authContext';

/**
 * Owns "who is signed in".
 *
 * On mount, a stored token is *verified* against `/auth/me` rather than
 * trusted: the token may be expired, revoked, or belong to a deleted account,
 * and discovering that at boot is far better than mid-workflow.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>(() =>
    tokenStore.hasSession() ? 'loading' : 'anonymous',
  );

  useEffect(() => {
    if (!tokenStore.hasSession()) {
      setStatus('anonymous');
      return;
    }

    let cancelled = false;
    authApi
      .me()
      .then((currentUser) => {
        if (cancelled) return;
        setUser(currentUser);
        setStatus('authenticated');
      })
      .catch(() => {
        if (cancelled) return;
        tokenStore.clear();
        setUser(null);
        setStatus('anonymous');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Signing out in one tab signs out every other tab.
  useEffect(
    () =>
      tokenStore.subscribe(() => {
        if (!tokenStore.hasSession()) {
          setUser(null);
          setStatus('anonymous');
        }
      }),
    [],
  );

  const login = useCallback(async (payload: LoginPayload) => {
    const { user: signedIn } = await authApi.login(payload);
    setUser(signedIn);
    setStatus('authenticated');
    return signedIn;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const { user: created } = await authApi.register(payload);
    setUser(created);
    setStatus('authenticated');
    return created;
  }, []);

  const completeOAuth = useCallback(async (code: string) => {
    // The provider half already happened in the API; all that is left is to
    // trade the one-time code for tokens and adopt the session.
    const { user: signedIn } = await oauthApi.exchange(code);
    setUser(signedIn);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
    setStatus('anonymous');
    // Never let one account's cached data be visible to the next sign-in.
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo(
    () => ({
      user,
      status,
      isAuthenticated: status === 'authenticated',
      login,
      register,
      logout,
      completeOAuth,
    }),
    [user, status, login, register, logout, completeOAuth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

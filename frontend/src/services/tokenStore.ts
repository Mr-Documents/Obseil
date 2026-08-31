/**
 * Token persistence.
 *
 * Tokens live in `localStorage` so a reload keeps the user signed in. This is
 * the usual trade-off for a token-based SPA: it is readable by any script on
 * the origin, so the mitigation is to keep access tokens short lived (30
 * minutes by default) and to ship no third-party scripts. Moving to
 * httpOnly cookies later means changing this module and the API's auth
 * dependency — nothing else.
 *
 * Every access is wrapped: `localStorage` throws in some private-browsing
 * modes, and a storage failure must degrade to "signed out", never to a crash.
 */
import type { TokenPair } from '@/types/api';

const ACCESS_KEY = 'obseil.access_token';
const REFRESH_KEY = 'obseil.refresh_token';

type Listener = () => void;
const listeners = new Set<Listener>();

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the session simply will not survive a reload.
  }
}

function notify(): void {
  for (const listener of listeners) listener();
}

export const tokenStore = {
  getAccessToken: () => read(ACCESS_KEY),
  getRefreshToken: () => read(REFRESH_KEY),
  hasSession: () => read(ACCESS_KEY) !== null,

  set(tokens: TokenPair): void {
    write(ACCESS_KEY, tokens.access_token);
    write(REFRESH_KEY, tokens.refresh_token);
    notify();
  },

  clear(): void {
    write(ACCESS_KEY, null);
    write(REFRESH_KEY, null);
    notify();
  },

  /** Subscribe to sign-in/sign-out, including from another browser tab. */
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    const onStorage = (event: StorageEvent) => {
      if (event.key === ACCESS_KEY || event.key === null) listener();
    };
    window.addEventListener('storage', onStorage);
    return () => {
      listeners.delete(listener);
      window.removeEventListener('storage', onStorage);
    };
  },
};

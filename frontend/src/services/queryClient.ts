import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './apiClient';

/**
 * Server-state defaults for the whole app.
 *
 * The important rule is the retry policy: a 4xx means the request was wrong,
 * so retrying it three times only delays the error the user needs to see. Only
 * network and 5xx failures are worth another attempt.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.isClientError) return false;
          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}

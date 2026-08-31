import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import { type ReactElement, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { AuthProvider } from '@/hooks/AuthProvider';
import { ThemeProvider } from '@/hooks/ThemeProvider';
import { ToastProvider } from '@/hooks/ToastProvider';

/**
 * Test render helpers.
 *
 * Retries are disabled so a deliberately failing request fails once and the
 * assertion runs immediately instead of after several backoffs.
 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface WrapperOptions extends Omit<RenderOptions, 'wrapper'> {
  route?: string;
  queryClient?: QueryClient;
  /** Skip AuthProvider for components that do not need a session. */
  withAuth?: boolean;
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', queryClient, withAuth = true, ...options }: WrapperOptions = {},
): RenderResult & { queryClient: QueryClient } {
  const client = queryClient ?? createTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ThemeProvider>
        <QueryClientProvider client={client}>
          <ToastProvider>
            <MemoryRouter
              initialEntries={[route]}
              future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
            >
              {withAuth ? <AuthProvider>{children}</AuthProvider> : children}
            </MemoryRouter>
          </ToastProvider>
        </QueryClientProvider>
      </ThemeProvider>
    );
  }

  return { ...render(ui, { wrapper: Wrapper, ...options }), queryClient: client };
}

/** Build a `fetch` Response for mocking the API client. */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'test-request-id' },
  });
}

export function errorResponse(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {},
): Response {
  return jsonResponse({ error: { code, message, details, request_id: 'test-request-id' } }, status);
}

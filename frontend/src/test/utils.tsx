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

/**
 * Answer the sign-in provider list, then defer to `handler`.
 *
 * Auth pages ask which OAuth providers are configured as soon as they mount.
 * Tests about the password form should not have to know or care, and asserting
 * on `mock.calls[0]` would silently start reading the wrong request the moment
 * any background call is added. Pair this with `fetchCallTo`.
 */
export function mockApiFetch(
  fetchMock: { mockImplementation: (fn: (url: string) => Promise<Response>) => unknown },
  handler: (url: string) => Response | Promise<Response>,
): void {
  fetchMock.mockImplementation(async (url: string) => {
    if (String(url).includes('/auth/oauth/providers')) return jsonResponse([]);
    return handler(String(url));
  });
}

/** The first recorded call whose URL contains `fragment`. */
export function fetchCallTo(
  fetchMock: { mock: { calls: unknown[][] } },
  fragment: string,
): [string, RequestInit] {
  const call = fetchMock.mock.calls.find(([url]) => String(url).includes(fragment));
  if (!call) {
    const seen = fetchMock.mock.calls.map(([url]) => String(url)).join(', ') || 'nothing';
    throw new Error(`No request to "${fragment}". Requests made: ${seen}`);
  }
  return call as [string, RequestInit];
}

/** Assert no request was made to `fragment`, ignoring unrelated background calls. */
export function expectNoRequestTo(
  fetchMock: { mock: { calls: unknown[][] } },
  fragment: string,
): void {
  const matched = fetchMock.mock.calls.filter(([url]) => String(url).includes(fragment));
  if (matched.length > 0) {
    throw new Error(`Expected no request to "${fragment}", but ${matched.length} was made.`);
  }
}

/** The JSON body of a recorded request, with a useful error if it is not JSON. */
export function jsonBody(init: RequestInit): unknown {
  if (typeof init.body !== 'string') {
    throw new Error(`Expected a JSON string body, got ${typeof init.body}.`);
  }
  return JSON.parse(init.body);
}

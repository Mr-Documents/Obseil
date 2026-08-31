import { QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { BrowserRouter } from 'react-router-dom';

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { AuthProvider } from '@/hooks/AuthProvider';
import { ThemeProvider } from '@/hooks/ThemeProvider';
import { ToastProvider } from '@/hooks/ToastProvider';
import { createQueryClient } from '@/services/queryClient';

import { AppRoutes } from './routes';

/**
 * Application shell. Providers are composed here, in one place, outermost
 * first: crash boundary -> theme -> server state -> toasts -> auth -> routing.
 * `AuthProvider` sits inside `QueryClientProvider` because signing out clears
 * the query cache.
 */
export function App() {
  const [queryClient] = useState(createQueryClient);

  return (
    <ErrorBoundary>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <AuthProvider>
                <AppRoutes />
              </AuthProvider>
            </BrowserRouter>
          </ToastProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

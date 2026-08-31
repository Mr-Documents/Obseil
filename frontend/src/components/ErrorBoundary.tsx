import { RotateCcw } from 'lucide-react';
import { Component, type ErrorInfo, type ReactNode } from 'react';

import { Button } from '@/components/ui/Button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Last line of defence against a white screen.
 *
 * A rendering crash shows a recoverable message instead of an empty page. The
 * stack goes to the console for developers; the user sees plain language.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled rendering error', error, info.componentStack);
  }

  private readonly handleReset = (): void => {
    this.setState({ error: null });
  };

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback;

    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-5 bg-canvas px-6 text-center">
        <div>
          <h1 className="text-xl font-semibold tracking-[-0.02em] text-fg">Something went wrong</h1>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-fg-muted">
            Obseil hit an unexpected error while rendering this page. Your data is safe — try again,
            and if it keeps happening please open an issue.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="primary"
            leadingIcon={<RotateCcw className="size-4" />}
            onClick={this.handleReset}
          >
            Try again
          </Button>
          <Button variant="secondary" onClick={() => window.location.assign('/')}>
            Go home
          </Button>
        </div>
      </div>
    );
  }
}

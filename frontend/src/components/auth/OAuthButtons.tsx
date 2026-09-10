import { useQuery } from '@tanstack/react-query';

import { Button } from '@/components/ui/Button';
import { oauthApi, oauthKeys } from '@/services/oauthApi';

import { ProviderMark } from './ProviderMark';

/**
 * "Continue with ..." for whichever providers this deployment configured.
 *
 * Renders nothing at all when none are, rather than a disabled button or an
 * explanation. Obseil is self-hosted and ships with no credentials, so for
 * most installs there is simply no third-party sign-in - and a form that never
 * mentions it is cleaner than one apologising for its absence.
 */
export function OAuthButtons({ action = 'Continue' }: { action?: string }) {
  const { data: providers } = useQuery({
    queryKey: oauthKeys.providers,
    queryFn: () => oauthApi.providers(),
    // Credentials come from the environment and cannot change while the tab
    // is open, so this never needs refetching.
    staleTime: Infinity,
    retry: false,
  });

  // `Array.isArray`, not a length check: this sits on the sign-in path, and an
  // unexpected response from an *optional* feature must never take down the
  // form that is the entire point of the page.
  if (!Array.isArray(providers) || providers.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2">
        {providers.map((provider) => (
          <Button
            key={provider.name}
            type="button"
            variant="secondary"
            className="w-full justify-center"
            leadingIcon={<ProviderMark provider={provider.name} />}
            onClick={() => oauthApi.start(provider.name)}
          >
            {action} with {provider.label}
          </Button>
        ))}
      </div>

      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-border-default" />
        <span className="text-xs text-fg-subtle">or</span>
        <span className="h-px flex-1 bg-border-default" />
      </div>
    </div>
  );
}

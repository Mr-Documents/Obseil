import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { jsonResponse, renderWithProviders } from '@/test/utils';

import { OAuthButtons } from './OAuthButtons';

const fetchMock = vi.fn();
const assign = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  assign.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  // jsdom refuses a real navigation; only the intent is under test.
  vi.stubGlobal('location', { ...window.location, assign });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const GOOGLE = { name: 'google', label: 'Google' };

describe('OAuthButtons', () => {
  it('renders a button per configured provider', async () => {
    fetchMock.mockResolvedValue(jsonResponse([GOOGLE, { name: 'github', label: 'GitHub' }]));
    renderWithProviders(<OAuthButtons />);

    expect(
      await screen.findByRole('button', { name: /continue with google/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue with github/i })).toBeInTheDocument();
  });

  it('renders nothing when the deployment configured no providers', async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));
    renderWithProviders(<OAuthButtons />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText(/^or$/i)).not.toBeInTheDocument();
  });

  it('renders nothing when the provider list cannot be loaded', async () => {
    // This sits on the sign-in page. An optional feature failing must never
    // stop somebody signing in with their password.
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    renderWithProviders(<OAuthButtons />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText(/^or$/i)).not.toBeInTheDocument();
  });

  it('survives a response that is not a list', async () => {
    // A crash here would take the whole login form down with it.
    fetchMock.mockResolvedValue(jsonResponse({ unexpected: true }));
    renderWithProviders(<OAuthButtons />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByText(/^or$/i)).not.toBeInTheDocument();
  });

  it('sends the browser to the provider on click', async () => {
    fetchMock.mockResolvedValue(jsonResponse([GOOGLE]));
    renderWithProviders(<OAuthButtons />);

    await userEvent.click(await screen.findByRole('button', { name: /continue with google/i }));

    // A full navigation, not fetch: the API replies with a redirect and sets a
    // cookie that has to survive the round trip.
    expect(assign).toHaveBeenCalledWith(expect.stringContaining('/auth/oauth/google/start'));
  });

  it('uses the wording the calling page asked for', async () => {
    fetchMock.mockResolvedValue(jsonResponse([GOOGLE]));
    renderWithProviders(<OAuthButtons action="Sign up" />);

    expect(await screen.findByRole('button', { name: /sign up with google/i })).toBeInTheDocument();
  });
});

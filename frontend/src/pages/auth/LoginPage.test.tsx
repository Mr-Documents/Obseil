import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorResponse, jsonResponse, renderWithProviders } from '@/test/utils';

import { LoginPage } from './LoginPage';

const fetchMock = vi.fn();

const AUTH_RESPONSE = {
  user: {
    id: 'user-1',
    email: 'ada@example.com',
    full_name: 'Ada Lovelace',
    created_at: '2026-03-01T10:00:00Z',
  },
  tokens: {
    access_token: 'access-1',
    refresh_token: 'refresh-1',
    token_type: 'bearer',
    expires_in: 1800,
  },
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('LoginPage', () => {
  it('renders an accessible form', () => {
    renderWithProviders(<LoginPage />);

    expect(screen.getByRole('heading', { name: /sign in to obseil/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('submits the trimmed credentials', async () => {
    fetchMock.mockResolvedValue(jsonResponse(AUTH_RESPONSE));
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/email address/i), '  ada@example.com  ');
    await userEvent.type(screen.getByLabelText(/password/i), 'analytical-1843');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/auth/login');
    expect(JSON.parse(init.body)).toEqual({
      email: 'ada@example.com',
      password: 'analytical-1843',
    });
  });

  it('shows the server message when credentials are rejected', async () => {
    fetchMock.mockResolvedValue(
      errorResponse(401, 'invalid_credentials', 'Incorrect email or password.'),
    );
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/email address/i), 'ada@example.com');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong-password-1');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password.');
  });

  it('reports a network failure in plain language', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/email address/i), 'ada@example.com');
    await userEvent.type(screen.getByLabelText(/password/i), 'analytical-1843');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach/i);
  });

  it('disables the submit button while the request is in flight', async () => {
    let resolveRequest: (value: Response) => void = () => {};
    fetchMock.mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveRequest = resolve;
      }),
    );
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByLabelText(/email address/i), 'ada@example.com');
    await userEvent.type(screen.getByLabelText(/password/i), 'analytical-1843');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    const button = screen.getByRole('button', { name: /signing in/i });
    expect(button).toBeDisabled();

    resolveRequest(jsonResponse(AUTH_RESPONSE));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  });
});

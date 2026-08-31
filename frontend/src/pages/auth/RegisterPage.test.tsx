import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorResponse, jsonResponse, renderWithProviders } from '@/test/utils';

import { RegisterPage } from './RegisterPage';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function fillForm(overrides: Partial<Record<'name' | 'email' | 'password', string>> = {}) {
  await userEvent.type(screen.getByLabelText(/full name/i), overrides.name ?? 'Ada Lovelace');
  await userEvent.type(
    screen.getByLabelText(/email address/i),
    overrides.email ?? 'ada@example.com',
  );
  await userEvent.type(screen.getByLabelText(/password/i), overrides.password ?? 'analytical1843');
}

describe('RegisterPage', () => {
  it('validates the password locally before hitting the network', async () => {
    renderWithProviders(<RegisterPage />);

    await fillForm({ password: 'short1' });
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByText(/use at least 8 characters/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('requires a letter and a number in the password', async () => {
    renderWithProviders(<RegisterPage />);

    await fillForm({ password: 'allletters' });
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByText(/one letter and one number/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects a malformed email before submitting', async () => {
    renderWithProviders(<RegisterPage />);

    await fillForm({ email: 'not-an-email' });
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByText(/valid email address/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('submits a valid registration', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          user: {
            id: 'user-1',
            email: 'ada@example.com',
            full_name: 'Ada Lovelace',
            created_at: '2026-03-01T10:00:00Z',
          },
          tokens: {
            access_token: 'a',
            refresh_token: 'r',
            token_type: 'bearer',
            expires_in: 1800,
          },
        },
        201,
      ),
    );
    renderWithProviders(<RegisterPage />);

    await fillForm();
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/auth/register');
    expect(JSON.parse(init.body)).toEqual({
      full_name: 'Ada Lovelace',
      email: 'ada@example.com',
      password: 'analytical1843',
    });
  });

  it('surfaces a duplicate-email conflict from the server', async () => {
    fetchMock.mockResolvedValue(
      errorResponse(
        409,
        'email_already_registered',
        'An account with that email address already exists.',
      ),
    );
    renderWithProviders(<RegisterPage />);

    await fillForm();
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/already exists/i);
  });

  it('clears a field error as soon as the user edits that field', async () => {
    renderWithProviders(<RegisterPage />);

    await fillForm({ password: 'short1' });
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByText(/use at least 8 characters/i)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(/password/i), 'more');
    expect(screen.queryByText(/use at least 8 characters/i)).not.toBeInTheDocument();
  });
});

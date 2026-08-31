import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorResponse, jsonResponse, renderWithProviders } from '@/test/utils';
import type { ProjectSummary } from '@/types/api';

import { ProjectsPage } from './ProjectsPage';

const fetchMock = vi.fn();

function project(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: 'project-1',
    name: 'Customer Transactions',
    description: 'Monthly card settlement exports.',
    created_at: '2026-03-01T10:00:00Z',
    updated_at: '2026-03-08T10:00:00Z',
    dataset_count: 3,
    analysis_count: 5,
    latest_quality_score: 78,
    last_analysed_at: '2026-03-08T10:00:00Z',
    ...overrides,
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ProjectsPage', () => {
  it('shows a helpful empty state for a new account', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 100, offset: 0 }));

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    expect(await screen.findByText(/no projects yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create your first project/i })).toBeInTheDocument();
  });

  it('lists projects with their dataset counts', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [project(), project({ id: 'project-2', name: 'Sensor Feed', dataset_count: 1 })],
        total: 2,
        limit: 100,
        offset: 0,
      }),
    );

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    expect(await screen.findByText('Customer Transactions')).toBeInTheDocument();
    expect(screen.getByText('Sensor Feed')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('links each project to its detail page', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [project()], total: 1, limit: 100, offset: 0 }),
    );

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    const link = await screen.findByRole('link', { name: /customer transactions/i });
    expect(link).toHaveAttribute('href', '/projects/project-1');
  });

  it('offers a retry when loading fails', async () => {
    fetchMock.mockResolvedValue(errorResponse(503, 'database_error', 'Service unavailable.'));

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    expect(await screen.findByText(/could not load your projects/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('creates a project and refreshes the list', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [], total: 0, limit: 100, offset: 0 }))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: 'project-9',
            name: 'Sensor Feed',
            description: null,
            created_at: '2026-03-09T10:00:00Z',
            updated_at: '2026-03-09T10:00:00Z',
          },
          201,
        ),
      )
      .mockResolvedValue(
        jsonResponse({
          items: [project({ id: 'project-9', name: 'Sensor Feed' })],
          total: 1,
          limit: 100,
          offset: 0,
        }),
      );

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    await userEvent.click(
      await screen.findByRole('button', { name: /create your first project/i }),
    );

    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/name/i), 'Sensor Feed');
    await userEvent.click(within(dialog).getByRole('button', { name: /create project/i }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
      expect(createCall).toBeDefined();
      expect(JSON.parse(createCall![1].body)).toEqual({
        name: 'Sensor Feed',
        description: null,
      });
    });

    expect(await screen.findByText('Sensor Feed')).toBeInTheDocument();
  });

  it('will not submit a project without a name', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 100, offset: 0 }));

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    await userEvent.click(
      await screen.findByRole('button', { name: /create your first project/i }),
    );
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /create project/i }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/give the project a name/i);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  });

  it('closes the dialog on Escape', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], total: 0, limit: 100, offset: 0 }));

    renderWithProviders(<ProjectsPage />, { withAuth: false });

    await userEvent.click(
      await screen.findByRole('button', { name: /create your first project/i }),
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

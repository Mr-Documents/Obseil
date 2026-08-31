import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';
import type * as ReactRouter from 'react-router-dom';

import { errorResponse, jsonResponse, renderWithProviders } from '@/test/utils';
import type { Dataset, Finding, FindingSummary } from '@/types/api';

import { DatasetFindingsPage } from './DatasetFindingsPage';

const fetchMock: Mock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouter>('react-router-dom');
  return { ...actual, useOutletContext: () => dataset };
});

let dataset: Dataset;

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 'finding-1',
    analysis_id: 'analysis-1',
    dataset_id: 'dataset-1',
    type: 'missing_values',
    category: 'rule',
    severity: 'high',
    title: '“loyalty_points” is 44.8% empty',
    description: '224 of 500 rows have no value for “loyalty_points”.',
    impact: 'Statistics computed over the remaining rows describe a subset.',
    recommendation: 'Find out why the column is not being populated upstream.',
    detection_method: 'null_count',
    detection_method_label: 'Null-value count',
    column_name: 'loyalty_points',
    columns: null,
    affected_rows: 224,
    affected_percentage: 44.8,
    details: { missing_count: 224, present_count: 276 },
    sample_row_indices: [0, 3, 9],
    status: 'open',
    created_at: '2026-03-08T10:00:00Z',
    feedback: null,
    ...overrides,
  };
}

function summary(overrides: Partial<FindingSummary> = {}): FindingSummary {
  return {
    analysis_id: 'analysis-1',
    total: 2,
    by_severity: { critical: 0, high: 1, medium: 1, low: 0 },
    by_type: { missing_values: 1, outliers: 1 },
    open_count: 2,
    reviewed_count: 0,
    ignored_count: 0,
    false_positive_count: 0,
    ...overrides,
  };
}

/** Route the mocked fetch by URL, since the page issues two queries. */
function respond(options: { summary?: FindingSummary; findings?: Finding[]; total?: number }) {
  fetchMock.mockImplementation((url: string) => {
    if (String(url).includes('/findings/summary')) {
      return Promise.resolve(jsonResponse(options.summary ?? summary()));
    }
    if (String(url).includes('/findings')) {
      const items = options.findings ?? [];
      return Promise.resolve(
        jsonResponse({ items, total: options.total ?? items.length, limit: 25, offset: 0 }),
      );
    }
    return Promise.resolve(jsonResponse({}));
  });
}

beforeEach(() => {
  dataset = {
    id: 'dataset-1',
    project_id: 'project-1',
    name: 'transactions.csv',
    original_filename: 'transactions.csv',
    file_format: 'csv',
    size_bytes: 4096,
    checksum_sha256: 'abc',
    row_count: 500,
    column_count: 10,
    status: 'ready',
    error_message: null,
    created_at: '2026-03-08T10:00:00Z',
    updated_at: '2026-03-08T10:00:00Z',
    latest_analysis: null,
  };
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('DatasetFindingsPage', () => {
  it('lists findings with severity, column and impact', async () => {
    respond({ findings: [finding()] });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });

    expect(await screen.findByText(/loyalty_points.*44\.8% empty/)).toBeInTheDocument();
    const table = within(screen.getByRole('table'));
    expect(table.getByText('High')).toBeInTheDocument();
    expect(table.getByText('loyalty_points')).toBeInTheDocument();
    expect(table.getByText('224')).toBeInTheDocument();
  });

  it('celebrates a clean dataset instead of showing an empty table', async () => {
    respond({ findings: [], summary: summary({ total: 0, open_count: 0 }) });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });

    expect(await screen.findByText(/no issues found/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('filters by severity', async () => {
    respond({ findings: [finding()] });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('button', { name: /^critical/i }));

    await waitFor(() => {
      const called = fetchMock.mock.calls.some(([url]) =>
        String(url).includes('severity=critical'),
      );
      expect(called).toBe(true);
    });
  });

  it('filters by status', async () => {
    respond({ findings: [finding()] });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('button', { name: 'Ignored' }));

    await waitFor(() => {
      const called = fetchMock.mock.calls.some(([url]) => String(url).includes('status=ignored'));
      expect(called).toBe(true);
    });
  });

  it('searches findings', async () => {
    respond({ findings: [finding()] });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });
    await screen.findByRole('table');

    await userEvent.type(screen.getByLabelText(/search findings/i), 'loyalty');

    await waitFor(() => {
      const called = fetchMock.mock.calls.some(([url]) => String(url).includes('search=loyalty'));
      expect(called).toBe(true);
    });
  });

  it('distinguishes "no results" from "nothing wrong"', async () => {
    respond({ findings: [], summary: summary() });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });
    await screen.findByText(/no issues found/i);

    await userEvent.type(screen.getByLabelText(/search findings/i), 'zzz');

    expect(await screen.findByText(/no findings match these filters/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
  });

  it('opens the detail dialog and answers all five questions', async () => {
    respond({ findings: [finding()] });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });
    await userEvent.click(await screen.findByRole('button', { name: /44\.8% empty/ }));

    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('What happened')).toBeInTheDocument();
    expect(dialog.getByText('Why it matters')).toBeInTheDocument();
    expect(dialog.getByText('How it was detected')).toBeInTheDocument();
    expect(dialog.getByText('What to do')).toBeInTheDocument();
    expect(dialog.getByText('Null-value count')).toBeInTheDocument();
  });

  it('records a false-positive verdict', async () => {
    respond({ findings: [finding()] });

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });
    await userEvent.click(await screen.findByRole('button', { name: /44\.8% empty/ }));

    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        finding({
          status: 'ignored',
          feedback: { verdict: 'false_positive', note: null, created_at: '2026-03-09T10:00:00Z' },
        }),
      ),
    );
    await userEvent.click(screen.getByRole('button', { name: /false positive/i }));

    await waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH');
      expect(patch).toBeDefined();
      expect(JSON.parse(patch![1].body)).toEqual({ verdict: 'false_positive' });
    });
  });

  it('prompts for an analysis when the dataset has none', async () => {
    dataset = { ...dataset, status: 'uploaded' };

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });

    expect(await screen.findByText(/no analysis yet/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('surfaces a load failure', async () => {
    fetchMock.mockResolvedValue(errorResponse(503, 'database_error', 'Service unavailable.'));

    renderWithProviders(<DatasetFindingsPage />, { withAuth: false });

    expect(await screen.findByText(/could not load the findings/i)).toBeInTheDocument();
  });
});

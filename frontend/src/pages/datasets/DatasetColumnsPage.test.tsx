import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as ReactRouter from 'react-router-dom';
import type { Mock } from 'vitest';

import { errorResponse, jsonResponse, renderWithProviders } from '@/test/utils';
import type { ColumnProfile, Dataset, DatasetStatistics } from '@/types/api';

import { DatasetColumnsPage } from './DatasetColumnsPage';

const fetchMock: Mock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof ReactRouter>('react-router-dom');
  return { ...actual, useOutletContext: () => dataset };
});

let dataset: Dataset;

function column(overrides: Partial<ColumnProfile> = {}): ColumnProfile {
  return {
    name: 'amount',
    position: 0,
    dtype: 'float64',
    inferred_type: 'numeric',
    count: 100,
    missing_count: 0,
    missing_percentage: 0,
    unique_count: 95,
    unique_percentage: 95,
    is_constant: false,
    is_unique: false,
    is_numeric_like: false,
    memory_bytes: 800,
    numeric: {
      mean: 42.5,
      median: 40,
      std: 12.1,
      minimum: 1,
      maximum: 99,
      q1: 30,
      q3: 55,
      iqr: 25,
      skewness: 0.2,
      zero_count: 0,
      negative_count: 0,
    },
    datetime: null,
    text: null,
    top_values: [{ value: '42.5', count: 3, percentage: 3 }],
    ...overrides,
  };
}

function statistics(columns: ColumnProfile[]): DatasetStatistics {
  return {
    dataset_id: 'dataset-1',
    analysis_id: 'analysis-1',
    analysed_at: '2026-03-08T10:00:00Z',
    row_count: 100,
    column_count: columns.length,
    total_cells: 100 * columns.length,
    missing_cells: 0,
    missing_percentage: 0,
    duplicate_row_count: 0,
    duplicate_row_percentage: 0,
    memory_bytes: 4096,
    sampled: false,
    source_rows: 100,
    notes: [],
    columns,
  };
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
    row_count: 100,
    column_count: 3,
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

describe('DatasetColumnsPage', () => {
  it('lists every column with its inferred type', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        statistics([
          column(),
          column({ name: 'channel', inferred_type: 'categorical', numeric: null, position: 1 }),
        ]),
      ),
    );

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });

    expect(await screen.findByText('amount')).toBeInTheDocument();
    expect(screen.getByText('channel')).toBeInTheDocument();

    // Scoped to the table: the filter strip above it uses the same words.
    const table = within(screen.getByRole('table'));
    expect(table.getByText('Numeric')).toBeInTheDocument();
    expect(table.getByText('Category')).toBeInTheDocument();
  });

  it('filters columns by search term', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(statistics([column(), column({ name: 'channel', position: 1, numeric: null })])),
    );

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });
    await screen.findByText('amount');

    await userEvent.type(screen.getByLabelText(/search columns/i), 'chan');

    expect(screen.queryByText('amount')).not.toBeInTheDocument();
    expect(screen.getByText('channel')).toBeInTheDocument();
  });

  it('filters columns by type', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        statistics([
          column(),
          column({ name: 'channel', inferred_type: 'categorical', numeric: null, position: 1 }),
        ]),
      ),
    );

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });
    await screen.findByText('amount');

    await userEvent.click(screen.getByRole('button', { name: 'Category' }));

    expect(screen.queryByText('amount')).not.toBeInTheDocument();
    expect(screen.getByText('channel')).toBeInTheDocument();
  });

  it('says so when nothing matches instead of showing an empty table', async () => {
    fetchMock.mockResolvedValue(jsonResponse(statistics([column()])));

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });
    await screen.findByText('amount');

    await userEvent.type(screen.getByLabelText(/search columns/i), 'zzz');

    expect(screen.getByText(/no columns match/i)).toBeInTheDocument();
  });

  it('reveals detailed statistics when a column is expanded', async () => {
    fetchMock.mockResolvedValue(jsonResponse(statistics([column()])));

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });
    await screen.findByText('amount');

    expect(screen.queryByText('Std. deviation')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /show statistics for amount/i }));

    expect(screen.getByText('Std. deviation')).toBeInTheDocument();
    expect(screen.getByText('12.1')).toBeInTheDocument();
  });

  it('flags constant, identifier and numbers-as-text columns', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        statistics([
          column({ name: 'batch', is_constant: true, numeric: null }),
          column({ name: 'txn_id', position: 1, is_unique: true, numeric: null }),
          column({ name: 'points', position: 2, is_numeric_like: true, numeric: null }),
        ]),
      ),
    );

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });

    expect(await screen.findByText('Constant')).toBeInTheDocument();
    expect(screen.getByText('Identifier')).toBeInTheDocument();
    expect(screen.getByText('Numbers as text')).toBeInTheDocument();
  });

  it('prompts for an analysis when the dataset has none', async () => {
    dataset = { ...dataset, status: 'uploaded' };

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });

    expect(await screen.findByText(/no analysis yet/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('surfaces a load failure', async () => {
    fetchMock.mockResolvedValue(errorResponse(503, 'database_error', 'Service unavailable.'));

    renderWithProviders(<DatasetColumnsPage />, { withAuth: false });

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/could not load the columns/i)).toBeInTheDocument();
  });
});

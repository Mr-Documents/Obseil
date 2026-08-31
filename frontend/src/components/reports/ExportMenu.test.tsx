import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Mock } from 'vitest';

import { errorResponse, renderWithProviders } from '@/test/utils';

import { ExportMenu } from './ExportMenu';

const fetchMock: Mock = vi.fn();

function pdfResponse(): Response {
  return new Response(new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46])]), {
    status: 200,
    headers: {
      'Content-Type': 'application/pdf',
      'Content-Disposition': 'attachment; filename="obseil-march-20260308.pdf"',
    },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  // jsdom implements neither of these.
  URL.createObjectURL = vi.fn(() => 'blob:mock');
  URL.revokeObjectURL = vi.fn();
  HTMLAnchorElement.prototype.click = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ExportMenu', () => {
  it('offers both formats with what each one contains', async () => {
    renderWithProviders(<ExportMenu analysisId="analysis-1" />, { withAuth: false });

    await userEvent.click(screen.getByRole('button', { name: /export/i }));

    const menu = screen.getByRole('menu', { name: /export format/i });
    expect(menu).toBeInTheDocument();
    expect(screen.getByText('Full report (PDF)')).toBeInTheDocument();
    expect(screen.getByText('Findings (CSV)')).toBeInTheDocument();
    expect(screen.getByText(/shareable as-is/i)).toBeInTheDocument();
  });

  it('is disabled until there is an analysis to export', () => {
    renderWithProviders(<ExportMenu analysisId={null} />, { withAuth: false });
    expect(screen.getByRole('button', { name: /export/i })).toBeDisabled();
  });

  it('requests the chosen format and triggers a download', async () => {
    fetchMock.mockResolvedValue(pdfResponse());
    renderWithProviders(<ExportMenu analysisId="analysis-1" />, { withAuth: false });

    await userEvent.click(screen.getByRole('button', { name: /export/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /full report/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/reports/analysis-1/export?format=pdf');
    expect(init.method).toBe('POST');
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
  });

  it('uses the filename the server chose', async () => {
    fetchMock.mockResolvedValue(pdfResponse());
    renderWithProviders(<ExportMenu analysisId="analysis-1" />, { withAuth: false });

    await userEvent.click(screen.getByRole('button', { name: /export/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /full report/i }));

    expect(await screen.findByText('obseil-march-20260308.pdf')).toBeInTheDocument();
  });

  it('releases the object URL so the blob is not retained', async () => {
    fetchMock.mockResolvedValue(pdfResponse());
    renderWithProviders(<ExportMenu analysisId="analysis-1" />, { withAuth: false });

    await userEvent.click(screen.getByRole('button', { name: /export/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /full report/i }));

    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalled(), { timeout: 3000 });
  });

  it('surfaces a server-side failure', async () => {
    fetchMock.mockResolvedValue(
      errorResponse(422, 'analysis_incomplete', 'This analysis did not complete.'),
    );
    renderWithProviders(<ExportMenu analysisId="analysis-1" />, { withAuth: false });

    await userEvent.click(screen.getByRole('button', { name: /export/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /findings \(CSV\)/i }));

    expect(await screen.findByText(/could not generate the report/i)).toBeInTheDocument();
    expect(screen.getByText('This analysis did not complete.')).toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    renderWithProviders(<ExportMenu analysisId="analysis-1" />, { withAuth: false });

    await userEvent.click(screen.getByRole('button', { name: /export/i }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  });
});

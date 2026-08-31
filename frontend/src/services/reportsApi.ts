import { ApiError, request } from './apiClient';
import { tokenStore } from './tokenStore';

export type ReportFormat = 'pdf' | 'csv';

export interface ReportFormatOption {
  format: ReportFormat;
  label: string;
  extension: string;
}

/** Pull the download name the server chose out of `Content-Disposition`. */
function filenameFrom(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      // Fall through to the ASCII form.
    }
  }
  const ascii = /filename="([^"]+)"/i.exec(disposition);
  return ascii ? ascii[1] : fallback;
}

export const reportsApi = {
  formats(): Promise<ReportFormatOption[]> {
    return request<ReportFormatOption[]>('/reports/formats');
  },

  /**
   * Download a report.
   *
   * The endpoint returns bytes rather than a URL, so the file has to be
   * fetched with the bearer token and handed to the browser as an object URL.
   * A plain `<a download href>` cannot carry an Authorization header.
   */
  async download(analysisId: string, format: ReportFormat): Promise<string> {
    const base = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');
    const token = tokenStore.getAccessToken();

    const response = await fetch(`${base}/reports/${analysisId}/export?format=${format}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });

    if (!response.ok) {
      let message = 'The report could not be generated.';
      let code = 'http_error';
      try {
        const body = await response.json();
        message = body?.error?.message ?? message;
        code = body?.error?.code ?? code;
      } catch {
        // Not JSON; keep the generic message.
      }
      throw new ApiError(response.status, code, message);
    }

    const blob = await response.blob();
    const filename = filenameFrom(
      response.headers.get('Content-Disposition'),
      `obseil-report.${format}`,
    );

    // Object URLs must be revoked or the blob is retained for the life of the
    // document - a few megabytes per export adds up over a session.
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);

    return filename;
  },
};

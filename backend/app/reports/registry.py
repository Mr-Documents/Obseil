"""Report format registry.

Adding a format — Markdown, HTML, Excel — is a module plus one line here.
Nothing else in the API needs to change: the endpoint validates the requested
format against this mapping and returns whatever the exporter produces.
"""

from __future__ import annotations

from app.core.errors import ValidationError
from app.reports.base import ReportExporter
from app.reports.csv_export import CsvFindingsExporter
from app.reports.pdf import PdfReportExporter

EXPORTERS: dict[str, ReportExporter] = {
    PdfReportExporter.format: PdfReportExporter(),
    CsvFindingsExporter.format: CsvFindingsExporter(),
}

DEFAULT_FORMAT = PdfReportExporter.format

__all__ = ["DEFAULT_FORMAT", "EXPORTERS", "available_formats", "get_exporter"]


def get_exporter(format_name: str) -> ReportExporter:
    exporter = EXPORTERS.get(format_name.lower())
    if exporter is None:
        raise ValidationError(
            f"Obseil can export {', '.join(sorted(EXPORTERS))}. "
            f"'{format_name}' is not one of them.",
            code="unsupported_report_format",
            details={"supported_formats": sorted(EXPORTERS)},
        )
    return exporter


def available_formats() -> list[dict[str, str]]:
    """What the UI should offer, with human labels."""
    return [
        {"format": exporter.format, "label": exporter.label, "extension": exporter.extension}
        for exporter in EXPORTERS.values()
    ]

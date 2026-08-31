"""CSV findings export.

One row per finding, with every field a reader would need to triage it outside
Obseil — including the impact and the recommendation, because a findings export
that lists only what was found and not what to do about it is a to-do list with
the instructions removed.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from app.reports.base import ReportData, ReportExporter

COLUMNS = [
    "severity",
    "category",
    "type",
    "title",
    "column",
    "affected_rows",
    "affected_percentage",
    "detection_method",
    "description",
    "impact",
    "recommendation",
    "status",
    "verdict",
]


class CsvFindingsExporter(ReportExporter):
    format = "csv"
    extension = "csv"
    # `text/csv` with an explicit charset: Excel on Windows otherwise guesses.
    media_type = "text/csv; charset=utf-8"
    label = "Findings (CSV)"

    def render(self, data: ReportData, **options: Any) -> bytes:
        del options  # this format takes none
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()

        # Most severe first, matching the order the UI shows.
        for finding in sorted(
            data.findings,
            key=lambda item: (-item.severity_rank, -(item.affected_percentage or 0)),
        ):
            writer.writerow(
                {
                    "severity": finding.severity,
                    "category": finding.category,
                    "type": finding.type,
                    "title": finding.title,
                    "column": finding.column or "",
                    "affected_rows": finding.affected_rows if finding.affected_rows else "",
                    "affected_percentage": (
                        f"{finding.affected_percentage:.4f}"
                        if finding.affected_percentage is not None
                        else ""
                    ),
                    "detection_method": finding.detection_method,
                    "description": finding.description,
                    "impact": finding.impact,
                    "recommendation": finding.recommendation,
                    "status": finding.status,
                    "verdict": finding.verdict or "",
                }
            )

        # utf-8-sig: Excel needs the BOM to read UTF-8 correctly, and these
        # exports contain typographic quotes and non-ASCII column names.
        return buffer.getvalue().encode("utf-8-sig")

    def filename_for(self, data: ReportData) -> str:
        return super().filename_for(data).replace(".csv", "-findings.csv")

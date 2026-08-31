"""Branded PDF data-quality report.

Built with ReportLab's document template rather than a headless browser: no
system libraries, no Chromium in the container, deterministic output, and it
runs in a few hundred milliseconds.

The report is written to be **shareable** - the reader may never have seen
Obseil. So it states what each number means, names the method behind every
finding, and says plainly what the anomaly model does and does not know.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.quality.types import DETECTION_METHOD_LABELS, DetectionMethod
from app.reports.base import ReportData, ReportExporter, ReportFinding

# --- Brand ------------------------------------------------------------------
ACCENT = colors.HexColor("#4C5BD4")
INK = colors.HexColor("#0E1117")
INK_MUTED = colors.HexColor("#59616F")
INK_SUBTLE = colors.HexColor("#8B93A3")
RULE = colors.HexColor("#E6E8EE")
SURFACE_MUTED = colors.HexColor("#F7F8FA")

SEVERITY_COLOURS = {
    "critical": colors.HexColor("#C62D1F"),
    "high": colors.HexColor("#C2570D"),
    "medium": colors.HexColor("#9A6A05"),
    "low": colors.HexColor("#2563C9"),
}

GRADE_COLOURS = {
    "excellent": colors.HexColor("#08795A"),
    "good": colors.HexColor("#2563C9"),
    "needs_attention": colors.HexColor("#9A6A05"),
    "poor": colors.HexColor("#C2570D"),
    "critical": colors.HexColor("#C62D1F"),
}

PAGE_MARGIN = 18 * mm
#: Beyond this the report stops being a report and becomes a database dump.
MAX_DETAILED_FINDINGS = 25


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ObseilTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "ObseilSubtitle",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=INK_MUTED,
        ),
        "h2": ParagraphStyle(
            "ObseilH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=INK,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "ObseilH3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "ObseilBody",
            parent=base["Normal"],
            fontSize=9.5,
            leading=13.5,
            textColor=INK,
        ),
        "muted": ParagraphStyle(
            "ObseilMuted",
            parent=base["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=INK_MUTED,
        ),
        "label": ParagraphStyle(
            "ObseilLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=INK_SUBTLE,
        ),
        "cell": ParagraphStyle(
            "ObseilCell", parent=base["Normal"], fontSize=8.5, leading=11.5, textColor=INK
        ),
    }


class ScoreBanner(Flowable):
    """The headline score, drawn rather than laid out as a table.

    A table cell cannot give the number the visual weight it needs to be the
    first thing a reader sees, which is the entire point of the score.
    """

    def __init__(self, score: float | None, grade: str, grade_label: str, summary: str) -> None:
        super().__init__()
        self.score = score
        self.grade = grade
        self.grade_label = grade_label
        self.summary = summary
        self.width = 0.0
        self.height = 34 * mm

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        del available_height  # the banner has a fixed height
        self.width = available_width
        return self.width, self.height

    def draw(self) -> None:
        canvas: Canvas = self.canv
        colour = GRADE_COLOURS.get(self.grade, INK)

        canvas.setFillColor(SURFACE_MUTED)
        canvas.setStrokeColor(RULE)
        canvas.roundRect(0, 0, self.width, self.height, 3 * mm, stroke=1, fill=1)

        canvas.setFillColor(INK_SUBTLE)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(8 * mm, self.height - 9 * mm, "DATASET QUALITY")

        canvas.setFillColor(colour)
        canvas.setFont("Helvetica-Bold", 30)
        canvas.drawString(
            8 * mm, self.height - 22 * mm, f"{self.score:.1f}" if self.score is not None else "n/a"
        )

        canvas.setFillColor(INK_SUBTLE)
        canvas.setFont("Helvetica", 12)
        score_width = canvas.stringWidth(
            f"{self.score:.1f}" if self.score is not None else "n/a", "Helvetica-Bold", 30
        )
        canvas.drawString(8 * mm + score_width + 2 * mm, self.height - 22 * mm, "/ 100")

        canvas.setFillColor(colour)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(8 * mm, self.height - 28 * mm, self.grade_label)

        # The score meter, with the grade boundaries marked.
        bar_x = 8 * mm
        bar_y = 6 * mm
        bar_width = self.width - 16 * mm
        canvas.setFillColor(colors.HexColor("#E6E8EE"))
        canvas.roundRect(bar_x, bar_y, bar_width, 2.2 * mm, 1.1 * mm, stroke=0, fill=1)
        if self.score is not None:
            canvas.setFillColor(colour)
            filled = max(bar_width * (self.score / 100), 1.5 * mm)
            canvas.roundRect(bar_x, bar_y, filled, 2.2 * mm, 1.1 * mm, stroke=0, fill=1)

        canvas.setFillColor(INK_MUTED)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(bar_x, bar_y - 3.6 * mm, _ascii(self.summary)[:110])


class PdfReportExporter(ReportExporter):
    format = "pdf"
    extension = "pdf"
    media_type = "application/pdf"
    label = "Full report (PDF)"

    def render(self, data: ReportData, **options: Any) -> bytes:
        del options  # this format takes none
        styles = _styles()
        buffer = io.BytesIO()

        document = BaseDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=PAGE_MARGIN,
            rightMargin=PAGE_MARGIN,
            topMargin=PAGE_MARGIN + 6 * mm,
            bottomMargin=PAGE_MARGIN,
            title=f"Obseil data quality report - {data.dataset_name}",
            author="Obseil",
            subject="Data quality analysis",
        )
        frame = Frame(
            document.leftMargin,
            document.bottomMargin,
            document.width,
            document.height,
            id="content",
        )
        document.addPageTemplates(
            [PageTemplate(id="obseil", frames=[frame], onPage=_page_furniture(data))]
        )

        story: list[Any] = []
        story += self._header(data, styles)
        story += self._score(data, styles)
        story += self._statistics(data, styles)
        story += self._findings_summary(data, styles)
        story += self._anomalies(data, styles)
        story += self._recommendations(data, styles)
        story += self._detailed_findings(data, styles)

        document.build(story)
        return buffer.getvalue()

    # --- Sections ----------------------------------------------------------
    def _header(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        analysed = (
            data.analysed_at.strftime("%d %B %Y at %H:%M UTC")
            if data.analysed_at
            else "not recorded"
        )
        return [
            Paragraph("Data quality report", styles["title"]),
            Paragraph(
                f"<b>{_escape(data.dataset_name)}</b> &nbsp;|&nbsp; project "
                f"{_escape(data.project_name)}",
                styles["subtitle"],
            ),
            Paragraph(
                f"Analysed {analysed} &nbsp;|&nbsp; generated "
                f"{data.generated_at.strftime('%d %B %Y at %H:%M UTC')}",
                styles["muted"],
            ),
            Spacer(1, 8 * mm),
        ]

    def _score(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        if data.score is None:
            return []

        story: list[Any] = [
            ScoreBanner(
                data.score.score, data.score.grade.value, data.score.grade_label, data.score.summary
            ),
            Spacer(1, 6 * mm),
            Paragraph("How the score was calculated", styles["h3"]),
            Paragraph(_escape(data.score.methodology), styles["muted"]),
            Spacer(1, 3 * mm),
        ]

        rows = [["Dimension", "Points lost", "Ceiling", "Findings"]]
        for dimension in data.score.dimensions:
            rows.append(
                [
                    dimension.label,
                    f"-{dimension.penalty:.1f}" if dimension.penalty else "0",
                    f"{dimension.cap:.0f}",
                    str(dimension.finding_count),
                ]
            )
        story.append(_table(rows, [70 * mm, 30 * mm, 25 * mm, 25 * mm]))
        return story

    def _statistics(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        if data.profile is None:
            return []

        profile = data.profile
        rows = [
            ["Rows", f"{profile.row_count:,}"],
            ["Columns", f"{profile.column_count:,}"],
            ["Total cells", f"{profile.total_cells:,}"],
            [
                "Missing values",
                f"{profile.missing_cells:,} ({profile.missing_percentage:.2f}%)",
            ],
            [
                "Duplicate rows",
                f"{profile.duplicate_row_count:,} ({profile.duplicate_row_percentage:.2f}%)",
            ],
            ["Numeric columns", str(len(profile.numeric_columns))],
            ["Categorical columns", str(len(profile.categorical_columns))],
            ["Date/time columns", str(len(profile.datetime_columns))],
            ["Source file", f"{data.dataset_filename} ({data.dataset_format.upper()})"],
        ]
        if profile.sampled and profile.source_rows:
            rows.append(
                ["Sampling", f"Analysed {profile.row_count:,} of {profile.source_rows:,} rows"]
            )

        story: list[Any] = [
            Paragraph("Dataset statistics", styles["h2"]),
            _table([["Measure", "Value"], *rows], [70 * mm, 80 * mm]),
        ]
        if profile.notes:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("How the file was read", styles["h3"]))
            for note in profile.notes:
                story.append(Paragraph(f"- {_escape(note)}", styles["muted"]))
        return story

    def _findings_summary(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        counts = data.severity_counts
        rows = [
            ["Severity", "Findings"],
            ["Critical", str(counts["critical"])],
            ["High", str(counts["high"])],
            ["Medium", str(counts["medium"])],
            ["Low", str(counts["low"])],
            ["Total", str(len(data.findings))],
        ]

        story: list[Any] = [
            Paragraph("Findings summary", styles["h2"]),
            Paragraph(
                f"{len(data.rule_findings)} deterministic quality issue"
                f"{'' if len(data.rule_findings) == 1 else 's'} and "
                f"{len(data.anomaly_findings)} machine-learning finding"
                f"{'' if len(data.anomaly_findings) == 1 else 's'}. Quality issues are facts "
                "about the data; anomalies are rows the model considers unusual and are "
                "reported for review.",
                styles["body"],
            ),
            Spacer(1, 3 * mm),
            _table(rows, [70 * mm, 40 * mm], emphasise_last=True),
        ]
        return story

    def _anomalies(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        story: list[Any] = [Paragraph("Anomaly detection", styles["h2"])]

        if data.ml_skipped_reason:
            story.append(
                Paragraph(
                    f"Anomaly detection was not run. {_escape(data.ml_skipped_reason)}",
                    styles["body"],
                )
            )
            return story

        features = ", ".join(data.ml_features) or "none"
        story.append(
            Paragraph(
                f"An Isolation Forest trained on {len(data.ml_features)} numeric column"
                f"{'' if len(data.ml_features) == 1 else 's'} ({_escape(features)}) flagged "
                f"<b>{data.anomaly_count:,} rows</b> ({data.anomaly_rate:.2f}%) as unusual.",
                styles["body"],
            )
        )
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                "These rows are not necessarily wrong: each of their individual values may sit "
                "well inside its own column's normal range, and what makes them stand out is the "
                "combination. The model reports that a row is unusual; it does not know why.",
                styles["muted"],
            )
        )
        return story

    def _recommendations(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        recommendations = data.recommendations()
        if not recommendations:
            return [
                Paragraph("Recommendations", styles["h2"]),
                Paragraph(
                    "No action is required. Every quality check passed on this dataset.",
                    styles["body"],
                ),
            ]

        story: list[Any] = [Paragraph("Recommendations", styles["h2"])]
        for index, (title, recommendation) in enumerate(recommendations, start=1):
            story.append(
                KeepTogether(
                    [
                        Paragraph(f"{index}. {_escape(title)}", styles["h3"]),
                        Paragraph(_escape(recommendation), styles["body"]),
                        Spacer(1, 2 * mm),
                    ]
                )
            )
        return story

    def _detailed_findings(self, data: ReportData, styles: dict[str, ParagraphStyle]) -> list[Any]:
        if not data.findings:
            return []

        ordered = sorted(
            data.findings,
            key=lambda item: (-item.severity_rank, -(item.affected_percentage or 0)),
        )
        shown = ordered[:MAX_DETAILED_FINDINGS]

        story: list[Any] = [PageBreak(), Paragraph("Detailed findings", styles["h2"])]
        if len(ordered) > len(shown):
            story.append(
                Paragraph(
                    f"The {len(shown)} most severe of {len(ordered)} findings. Export the CSV "
                    "for the complete list.",
                    styles["muted"],
                )
            )
        story.append(Spacer(1, 3 * mm))

        for finding in shown:
            story.append(KeepTogether(self._finding_block(finding, styles)))
        return story

    def _finding_block(
        self, finding: ReportFinding, styles: dict[str, ParagraphStyle]
    ) -> list[Any]:
        colour = SEVERITY_COLOURS.get(finding.severity, INK_MUTED)
        location = finding.column or "whole dataset"
        scope = (
            f"{finding.affected_rows:,} rows ({finding.affected_percentage:.2f}%)"
            if finding.affected_rows is not None and finding.affected_percentage is not None
            else "-"
        )

        header = Table(
            [
                [
                    Paragraph(
                        f'<font color="{colour.hexval()}"><b>{finding.severity.upper()}</b></font>',
                        styles["label"],
                    ),
                    Paragraph(f"<b>{_escape(finding.title)}</b>", styles["body"]),
                ]
            ],
            colWidths=[20 * mm, None],
        )
        header.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        # The five questions, labelled, so a reader who has never used Obseil
        # can still act on the finding.
        details = _table(
            [
                ["What happened", finding.description],
                ["Where", f"{location} | {scope}"],
                ["Why it matters", finding.impact],
                ["How it was detected", _method_label(finding.detection_method)],
                ["What to do", finding.recommendation],
            ],
            [32 * mm, None],
            header_row=False,
            wrap_second_column=True,
        )

        return [header, details, Spacer(1, 5 * mm)]


# --- Helpers ----------------------------------------------------------------
#: ReportLab's built-in Type 1 fonts cover Latin-1 only, and a report that
#: renders a replacement glyph in a shared PDF looks broken however good the
#: content is. Findings deliberately use typographic punctuation in the UI, so
#: it is folded down here rather than being avoided upstream.
_ASCII_PUNCTUATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",  # noqa: RUF001 - left single quotation mark
        "’": "'",  # noqa: RUF001 - right single quotation mark
        "–": "-",  # noqa: RUF001 - en dash
        "—": "-",
        "…": "...",
        "·": "|",
        "×": "x",  # noqa: RUF001 - multiplication sign
        "→": "->",
    }
)


def _ascii(value: str) -> str:
    """Plain text for the raw canvas, which has no markup escaping."""
    return str(value).translate(_ASCII_PUNCTUATION)


def _escape(value: str) -> str:
    """Make text safe for ReportLab's mini-HTML paragraph markup."""
    return _ascii(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _method_label(method: str) -> str:
    """The readable name for a detection method, never the raw enum value."""
    try:
        return DETECTION_METHOD_LABELS[DetectionMethod(method)]
    except ValueError:
        return method.replace("_", " ").capitalize()


def _table(
    rows: list[list[str]],
    widths: list[float | None],
    *,
    header_row: bool = True,
    emphasise_last: bool = False,
    wrap_second_column: bool = False,
) -> Table:
    styles = _styles()
    body = [
        [
            (
                Paragraph(_escape(cell), styles["cell"])
                if wrap_second_column and index == 1
                else (
                    Paragraph(f"<b>{_escape(cell)}</b>", styles["cell"])
                    if wrap_second_column and index == 0
                    else _escape(cell)
                )
            )
            for index, cell in enumerate(row)
        ]
        for row in rows
    ]

    table = Table(body, colWidths=widths, hAlign="LEFT")
    style: list[tuple[Any, ...]] = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, RULE),
    ]
    if header_row:
        style += [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TEXTCOLOR", (0, 0), (-1, 0), INK_SUBTLE),
            ("BACKGROUND", (0, 0), (-1, 0), SURFACE_MUTED),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ]
    if emphasise_last:
        style.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))

    table.setStyle(TableStyle(style))
    return table


def _page_furniture(data: ReportData) -> Callable[[Canvas, BaseDocTemplate], None]:
    """Draw the brand mark and the footer on every page."""

    def draw(canvas: Canvas, document: BaseDocTemplate) -> None:
        canvas.saveState()
        width, height = A4

        # Brand mark: the Obseil lens, drawn with primitives so the PDF carries
        # no image dependency.
        mark_x, mark_y = PAGE_MARGIN, height - PAGE_MARGIN + 2 * mm
        canvas.setFillColor(ACCENT)
        canvas.roundRect(mark_x, mark_y, 5 * mm, 5 * mm, 1.2 * mm, stroke=0, fill=1)
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(0.6)
        canvas.circle(mark_x + 2.5 * mm, mark_y + 2.5 * mm, 1.5 * mm, stroke=1, fill=0)
        canvas.setFillColor(colors.white)
        canvas.circle(mark_x + 2.5 * mm, mark_y + 2.5 * mm, 0.6 * mm, stroke=0, fill=1)

        canvas.setFillColor(INK)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(mark_x + 7 * mm, mark_y + 1.4 * mm, "Obseil")
        canvas.setFillColor(INK_SUBTLE)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(
            mark_x + 19 * mm, mark_y + 1.6 * mm, "Uncover what's hidden in your data."
        )

        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(PAGE_MARGIN, mark_y - 2 * mm, width - PAGE_MARGIN, mark_y - 2 * mm)

        canvas.setFillColor(INK_SUBTLE)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(
            PAGE_MARGIN,
            PAGE_MARGIN - 6 * mm,
            f"{_ascii(data.dataset_name)} | analysis {data.analysis_id[:8]}",
        )
        canvas.drawRightString(
            width - PAGE_MARGIN, PAGE_MARGIN - 6 * mm, f"Page {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    return draw

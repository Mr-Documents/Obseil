"""Report export endpoints."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUser, DbSession
from app.reports.registry import DEFAULT_FORMAT, available_formats
from app.services import history_service, report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/formats", summary="Report formats this deployment can produce")
def formats() -> list[dict[str, str]]:
    return available_formats()


@router.post(
    "/{analysis_id}/export",
    summary="Export an analysis as a shareable report",
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}, "text/csv": {}},
            "description": "The rendered report.",
        },
        422: {"description": "Unsupported format, or the analysis did not complete"},
    },
)
def export_report(
    analysis_id: str,
    db: DbSession,
    user: CurrentUser,
    # Shadows the builtin deliberately: the public query parameter is `format`.
    format: Annotated[str, Query(description="`pdf` or `csv`.")] = DEFAULT_FORMAT,
) -> Response:
    """Render and return the report as a file download.

    Returned as bytes with a `Content-Disposition` rather than a URL: the MVP
    has no object store to put a generated file in, and streaming it directly
    means no temporary file to clean up and nothing to expire.
    """
    analysis = history_service.get_owned_analysis(db, analysis_id=analysis_id, user=user)
    report = report_service.export_analysis(db, analysis=analysis, format_name=format)

    # RFC 6266: the ASCII fallback plus a UTF-8 form, so a dataset named in a
    # non-Latin script still downloads with a sensible filename.
    ascii_name = report.filename.encode("ascii", "ignore").decode() or "obseil-report"
    disposition = (
        f'attachment; filename="{ascii_name}"; ' f"filename*=UTF-8''{quote(report.filename)}"
    )

    return Response(
        content=report.content,
        media_type=report.media_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(report.content)),
            # The report is derived from a fixed analysis, but it embeds a
            # generation timestamp, so it is not safe to cache.
            "Cache-Control": "no-store",
        },
    )

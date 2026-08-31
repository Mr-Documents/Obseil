"""Liveness and readiness endpoints.

``/health`` answers "is the process up?" and never touches the database, so it
is safe as a container liveness probe. ``/health/ready`` answers "can it serve
traffic?" and does check the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class ReadinessResponse(HealthResponse):
    database: str


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, environment=settings.env)


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
def readiness(db: Session = Depends(get_db)) -> ReadinessResponse:
    db.execute(text("SELECT 1"))
    return ReadinessResponse(
        status="ok", version=__version__, environment=settings.env, database="ok"
    )

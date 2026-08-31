"""Project request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel


def _clean_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Project name cannot be blank.")
    return cleaned


class ProjectCreate(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str | None, Field(max_length=2000)] = None

    _normalise_name = field_validator("name")(staticmethod(_clean_name))

    @field_validator("description")
    @classmethod
    def _blank_description_is_null(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProjectUpdate(BaseModel):
    """Partial update. Absent fields are left untouched."""

    name: Annotated[str | None, Field(min_length=1, max_length=120)] = None
    description: Annotated[str | None, Field(max_length=2000)] = None

    @field_validator("name")
    @classmethod
    def _normalise_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("description")
    @classmethod
    def _blank_description_is_null(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ProjectRead(ORMModel):
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectRead):
    """A project plus the roll-up numbers shown on the projects list.

    These are computed with aggregate queries in the service layer rather than
    by loading relationships, so listing N projects stays a fixed number of
    queries regardless of how many datasets each one holds.
    """

    dataset_count: int = 0
    analysis_count: int = 0
    latest_quality_score: float | None = None
    last_analysed_at: datetime | None = None

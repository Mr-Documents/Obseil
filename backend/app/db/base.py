"""Declarative base, shared column types and model mixins.

Design notes
------------
* Primary keys are UUID4 rendered as ``String(36)``. They are non-enumerable in
  a public API and portable between PostgreSQL and the SQLite database used by
  the fast unit-test suite.
* ``JSONColumn`` resolves to ``JSONB`` on PostgreSQL (indexable, binary) and to
  plain ``JSON`` elsewhere, so the same models run under both engines.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

#: JSON column type that upgrades to JSONB on PostgreSQL.
JSONColumn = JSON().with_variant(JSONB(), "postgresql")

ID_LENGTH = 36


def new_uuid() -> str:
    """Return a new UUID4 as a 36-character string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Timezone-aware current time. Used as a Python-side column default."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for every Obseil model."""

    type_annotation_map: ClassVar[dict[Any, Any]] = {dict: JSONColumn, list: JSONColumn}


class UUIDPrimaryKeyMixin:
    """Adds a string UUID primary key named ``id``."""

    id: Mapped[str] = mapped_column(String(ID_LENGTH), primary_key=True, default=new_uuid)


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )

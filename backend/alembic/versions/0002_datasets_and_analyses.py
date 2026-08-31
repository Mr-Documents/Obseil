"""Datasets and dataset analyses.

Revision ID: 0002_datasets_analyses
Revises: 0001_users_projects
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_datasets_analyses"
down_revision: str | None = "0001_users_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Matches ``app.db.base.JSONColumn`` - JSONB on PostgreSQL, JSON elsewhere.
JSON_COLUMN = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_format", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "uploaded",
                "analyzing",
                "ready",
                "failed",
                native_enum=False,
                length=16,
                name="datasetstatus",
            ),
            nullable=False,
            server_default="uploaded",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_datasets_project_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_datasets"),
        sa.UniqueConstraint("storage_key", name="uq_datasets_storage_key"),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])
    op.create_index("ix_datasets_project_created", "datasets", ["project_id", "created_at"])
    # Lets the UI point out that two uploads are byte-identical.
    op.create_index("ix_datasets_checksum_sha256", "datasets", ["checksum_sha256"])

    op.create_table(
        "dataset_analyses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "failed",
                native_enum=False,
                length=16,
                name="analysisstatus",
            ),
            nullable=False,
            server_default="running",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("profile", JSON_COLUMN, nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_cell_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duplicate_row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_row_percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="fk_analyses_dataset_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_analyses_project_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_analyses"),
    )
    op.create_index("ix_dataset_analyses_dataset_id", "dataset_analyses", ["dataset_id"])
    op.create_index("ix_dataset_analyses_project_id", "dataset_analyses", ["project_id"])
    op.create_index("ix_analyses_dataset_created", "dataset_analyses", ["dataset_id", "created_at"])
    op.create_index("ix_analyses_project_created", "dataset_analyses", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_analyses_project_created", table_name="dataset_analyses")
    op.drop_index("ix_analyses_dataset_created", table_name="dataset_analyses")
    op.drop_index("ix_dataset_analyses_project_id", table_name="dataset_analyses")
    op.drop_index("ix_dataset_analyses_dataset_id", table_name="dataset_analyses")
    op.drop_table("dataset_analyses")

    op.drop_index("ix_datasets_checksum_sha256", table_name="datasets")
    op.drop_index("ix_datasets_project_created", table_name="datasets")
    op.drop_index("ix_datasets_project_id", table_name="datasets")
    op.drop_table("datasets")

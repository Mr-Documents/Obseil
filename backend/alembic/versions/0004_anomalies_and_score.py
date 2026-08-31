"""Anomalies, quality score and ML metadata.

Revision ID: 0004_anomalies_score
Revises: 0003_findings
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0004_anomalies_score"
down_revision: str | None = "0003_findings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_COLUMN = sa.JSON().with_variant(JSONB(), "postgresql")

ANALYSIS_COLUMNS: tuple[sa.Column, ...] = (
    sa.Column("quality_score", sa.Float(), nullable=True),
    sa.Column("quality_grade", sa.String(length=24), nullable=True),
    sa.Column("score_breakdown", JSON_COLUMN, nullable=True),
    sa.Column("anomaly_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("anomaly_rate", sa.Float(), nullable=False, server_default="0"),
    sa.Column("ml_algorithm", sa.String(length=48), nullable=True),
    sa.Column("ml_features", JSON_COLUMN, nullable=True),
    sa.Column("ml_parameters", JSON_COLUMN, nullable=True),
    sa.Column("ml_skipped_reason", sa.Text(), nullable=True),
)


def upgrade() -> None:
    for column in ANALYSIS_COLUMNS:
        op.add_column("dataset_analyses", column.copy())

    op.create_table(
        "anomalies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_score", sa.Float(), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("feature_values", JSON_COLUMN, nullable=True),
        sa.Column("top_contributors", JSON_COLUMN, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["dataset_analyses.id"],
            name="fk_anomalies_analysis_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="fk_anomalies_dataset_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_anomalies"),
    )
    op.create_index("ix_anomalies_analysis_id", "anomalies", ["analysis_id"])
    op.create_index("ix_anomalies_dataset_id", "anomalies", ["dataset_id"])
    op.create_index("ix_anomalies_analysis_rank", "anomalies", ["analysis_id", "rank"])


def downgrade() -> None:
    op.drop_index("ix_anomalies_analysis_rank", table_name="anomalies")
    op.drop_index("ix_anomalies_dataset_id", table_name="anomalies")
    op.drop_index("ix_anomalies_analysis_id", table_name="anomalies")
    op.drop_table("anomalies")

    for column in reversed(ANALYSIS_COLUMNS):
        op.drop_column("dataset_analyses", column.name)

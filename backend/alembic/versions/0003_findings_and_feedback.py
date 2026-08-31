"""Findings, finding feedback and analysis severity roll-ups.

Revision ID: 0003_findings
Revises: 0002_datasets_analyses
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003_findings"
down_revision: str | None = "0002_datasets_analyses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON_COLUMN = sa.JSON().with_variant(JSONB(), "postgresql")

ROLLUP_COLUMNS = (
    "finding_count",
    "critical_count",
    "high_count",
    "medium_count",
    "low_count",
)


def upgrade() -> None:
    # Roll-up counts on the analysis, so listing history never aggregates
    # the findings table.
    for name in ROLLUP_COLUMNS:
        op.add_column(
            "dataset_analyses",
            sa.Column(name, sa.Integer(), nullable=False, server_default="0"),
        )

    op.create_table(
        "findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=48), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="rule"),
        sa.Column("severity", sa.String(length=16), nullable=False),
        # Sorting by the severity string would give critical < high < low <
        # medium; the rank makes ordering correct in SQL.
        sa.Column("severity_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("detection_method", sa.String(length=48), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("columns", JSON_COLUMN, nullable=True),
        sa.Column("affected_rows", sa.Integer(), nullable=True),
        sa.Column("affected_percentage", sa.Float(), nullable=True),
        sa.Column("details", JSON_COLUMN, nullable=True),
        sa.Column("sample_row_indices", JSON_COLUMN, nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open", "reviewed", "ignored", native_enum=False, length=16, name="findingstatus"
            ),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["dataset_analyses.id"],
            name="fk_findings_analysis_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], name="fk_findings_dataset_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_findings_project_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_findings"),
    )
    op.create_index("ix_findings_analysis_id", "findings", ["analysis_id"])
    op.create_index("ix_findings_dataset_id", "findings", ["dataset_id"])
    op.create_index("ix_findings_project_id", "findings", ["project_id"])
    op.create_index("ix_findings_type", "findings", ["type"])
    op.create_index("ix_findings_category", "findings", ["category"])
    op.create_index("ix_findings_severity", "findings", ["severity"])
    op.create_index("ix_findings_column_name", "findings", ["column_name"])
    op.create_index("ix_findings_analysis_severity", "findings", ["analysis_id", "severity"])
    op.create_index("ix_findings_dataset_status", "findings", ["dataset_id", "status"])

    op.create_table(
        "finding_feedback",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "verdict",
            sa.Enum(
                "valid_issue",
                "false_positive",
                native_enum=False,
                length=24,
                name="feedbackverdict",
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"], ["findings.id"], name="fk_feedback_finding_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_feedback_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_finding_feedback"),
        sa.UniqueConstraint("finding_id", name="uq_finding_feedback_finding"),
    )
    op.create_index("ix_finding_feedback_finding_id", "finding_feedback", ["finding_id"])
    op.create_index("ix_finding_feedback_user_id", "finding_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_finding_feedback_user_id", table_name="finding_feedback")
    op.drop_index("ix_finding_feedback_finding_id", table_name="finding_feedback")
    op.drop_table("finding_feedback")

    for index in (
        "ix_findings_dataset_status",
        "ix_findings_analysis_severity",
        "ix_findings_column_name",
        "ix_findings_severity",
        "ix_findings_category",
        "ix_findings_type",
        "ix_findings_project_id",
        "ix_findings_dataset_id",
        "ix_findings_analysis_id",
    ):
        op.drop_index(index, table_name="findings")
    op.drop_table("findings")

    for name in reversed(ROLLUP_COLUMNS):
        op.drop_column("dataset_analyses", name)

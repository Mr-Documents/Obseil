"""User-defined quality rules.

Revision ID: 0006_rules
Revises: 0005_oauth_accounts
Create Date: 2026-10-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006_rules"
down_revision: str | None = "0005_oauth_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Matches ``app.db.base.JSONColumn`` - JSONB on PostgreSQL, JSON elsewhere.
JSON_COLUMN = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("predicate", sa.String(length=32), nullable=False),
        sa.Column("parameters", JSON_COLUMN, nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("dimension", sa.String(length=24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # A finding's title comes from its rule's name, so two rules sharing a
        # name inside one project would produce indistinguishable findings.
        sa.UniqueConstraint("project_id", "name", name="uq_rules_project_name"),
    )
    op.create_index("ix_rules_project_id", "rules", ["project_id"])
    op.create_index("ix_rules_project_enabled", "rules", ["project_id", "enabled"])

    # Findings gain a link back to the rule that produced them. SQLite cannot
    # add a constraint in place, so the batch context rebuilds the table there
    # and issues plain ALTERs on PostgreSQL - the same approach as 0005.
    with op.batch_alter_table("findings") as batch:
        batch.add_column(sa.Column("rule_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("rule_version", sa.Integer(), nullable=True))
        # SET NULL, not CASCADE: deleting a rule must not delete the record of
        # what it found. A finding is evidence of what one run saw, and the
        # rule's later removal does not unmake that.
        batch.create_foreign_key(
            "fk_findings_rule_id", "rules", ["rule_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_findings_rule_id", ["rule_id"])


def downgrade() -> None:
    with op.batch_alter_table("findings") as batch:
        batch.drop_index("ix_findings_rule_id")
        batch.drop_constraint("fk_findings_rule_id", type_="foreignkey")
        batch.drop_column("rule_version")
        batch.drop_column("rule_id")

    op.drop_index("ix_rules_project_enabled", table_name="rules")
    op.drop_index("ix_rules_project_id", table_name="rules")
    op.drop_table("rules")

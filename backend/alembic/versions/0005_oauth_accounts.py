"""Third-party sign-in identities.

Revision ID: 0005_oauth_accounts
Revises: 0004_anomalies_score
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_oauth_accounts"
down_revision: str | None = "0004_anomalies_score"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_account_id", sa.String(length=191), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # A provider identity belongs to one account and no other, enforced by
        # the database rather than by whichever code path happens to run.
        sa.UniqueConstraint("provider", "provider_account_id", name="uq_oauth_provider_account"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])

    # An account created through a provider has no password. SQLite cannot
    # alter a column in place, so the batch context rebuilds the table there
    # and issues a plain ALTER on PostgreSQL.
    with op.batch_alter_table("users") as batch:
        batch.alter_column("hashed_password", existing_type=sa.String(length=128), nullable=True)


def downgrade() -> None:
    # Password-less accounts cannot survive the column becoming NOT NULL
    # again. Removing them is the only honest reversal: leaving rows with an
    # empty-string hash would create accounts nobody can sign in to and that
    # no code path expects.
    op.execute("DELETE FROM users WHERE hashed_password IS NULL")
    with op.batch_alter_table("users") as batch:
        batch.alter_column("hashed_password", existing_type=sa.String(length=128), nullable=False)

    op.drop_index("ix_oauth_accounts_user_id", table_name="oauth_accounts")
    op.drop_table("oauth_accounts")

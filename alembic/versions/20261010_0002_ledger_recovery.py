"""Add explicit retry and reconciliation state to the action ledger."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20261010_0002"
down_revision = "20261009_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("action_ledger")}
    additions = (
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reconciliation_status",
            sa.String(length=32),
            nullable=False,
            server_default="NOT_REQUIRED",
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in additions:
        if column.name not in existing:
            op.add_column("action_ledger", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("action_ledger")}
    for name in (
        "last_attempt_at",
        "reconciliation_status",
        "next_retry_at",
        "last_error",
        "attempt",
    ):
        if name in existing:
            op.drop_column("action_ledger", name)

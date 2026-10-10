"""Persist fail-closed planning dispositions and clarification questions."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20261010_0003"
down_revision = "20261010_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("task_runs")}
    additions = (
        sa.Column("planning_disposition", sa.String(length=32), nullable=True),
        sa.Column("planning_reason", sa.Text(), nullable=True),
        sa.Column("clarification_questions", sa.JSON(), nullable=True),
    )
    for column in additions:
        if column.name not in existing:
            op.add_column("task_runs", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("task_runs")}
    for name in (
        "clarification_questions",
        "planning_reason",
        "planning_disposition",
    ):
        if name in existing:
            op.drop_column("task_runs", name)

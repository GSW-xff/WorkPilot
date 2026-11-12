"""Add renewable task leases and a monotonic fencing token.

The lease columns live on ``task_runs`` so that "who may advance this task" is a single
conditional UPDATE against the same row a worker already reads. The fencing token is
incremented on every successful claim, which makes a stale worker's renewal, release and
side-effect guard fail instead of silently winning.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision = "20261112_0004"
down_revision = "20261010_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("task_runs")}
    additions = (
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fence_token", sa.Integer(), nullable=False, server_default="0"),
    )
    for column in additions:
        if column.name not in existing:
            op.add_column("task_runs", column)


def downgrade() -> None:
    bind = op.get_bind()
    existing = {column["name"] for column in inspect(bind).get_columns("task_runs")}
    for name in ("fence_token", "lease_expires_at", "lease_owner"):
        if name in existing:
            op.drop_column("task_runs", name)

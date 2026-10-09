"""Create the WorkPilot V2 persistence schema and tenant policies."""

from __future__ import annotations

from alembic import op
from workpilot.db.models import Base

revision = "20261009_0001"
down_revision = None
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "task_runs",
    "approvals",
    "action_ledger",
    "artifacts",
    "outbox_events",
)

CHILD_TABLES = (
    "task_steps",
    "verifications",
    "timeline_events",
    "checkpoints",
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return

    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
            "USING (tenant_id = current_setting('app.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"
        )

    for table in CHILD_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
            "USING (EXISTS (SELECT 1 FROM task_runs tr "
            f'WHERE tr.id = "{table}".task_id '
            "AND tr.tenant_id = current_setting('app.tenant_id', true))) "
            "WITH CHECK (EXISTS (SELECT 1 FROM task_runs tr "
            f'WHERE tr.id = "{table}".task_id '
            "AND tr.tenant_id = current_setting('app.tenant_id', true)))"
        )


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

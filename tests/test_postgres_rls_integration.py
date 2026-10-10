from __future__ import annotations

import os
import unittest
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command
from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
from workpilot.repository import TaskNotFoundError
from workpilot.runtime import WorkPilotService


@unittest.skipUnless(
    os.getenv("WORKPILOT_RUN_POSTGRES_INTEGRATION") == "1",
    "set WORKPILOT_RUN_POSTGRES_INTEGRATION=1 to run real PostgreSQL RLS tests",
)
class PostgreSQLRLSIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.owner_url = os.getenv(
            "WORKPILOT_POSTGRES_OWNER_URL",
            "postgresql+psycopg://workpilot_owner:workpilot_owner@127.0.0.1:5432/workpilot",
        )
        cls.app_url = os.getenv(
            "WORKPILOT_POSTGRES_APP_URL",
            "postgresql+psycopg://workpilot_app:workpilot_app@127.0.0.1:5432/workpilot",
        )
        config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
        config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
        config.set_main_option("sqlalchemy.url", cls.owner_url.replace("%", "%%"))
        command.upgrade(config, "head")
        cls.owner_engine = create_engine(cls.owner_url)
        cls.app_engine = create_database_engine(cls.app_url)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app_engine.dispose()
        cls.owner_engine.dispose()

    def setUp(self) -> None:
        with self.owner_engine.begin() as connection:
            connection.execute(text("TRUNCATE task_runs, outbox_events CASCADE"))
        self.repository = SQLAlchemyTaskRepository(self.app_engine)
        self.service = WorkPilotService(
            self.repository,
            CapabilityRegistry([FakeEnterpriseAdapter()]),
        )

    def test_rls_defaults_to_deny_and_isolates_parent_child_and_outbox_rows(self) -> None:
        tenant_a = self.service.create_task("tenant-a", "alice", "prepare alpha report")
        tenant_b = self.service.create_task("tenant-b", "bob", "prepare beta report")

        with self.app_engine.connect() as connection:
            self.assertEqual(0, connection.scalar(text("SELECT count(*) FROM task_runs")))
            self.assertEqual(0, connection.scalar(text("SELECT count(*) FROM task_steps")))
            self.assertEqual(0, connection.scalar(text("SELECT count(*) FROM outbox_events")))

        with self.app_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant-a', true)"))
            visible_tasks = connection.execute(text("SELECT id FROM task_runs")).scalars().all()
            child_task_ids = (
                connection.execute(text("SELECT DISTINCT task_id FROM task_steps")).scalars().all()
            )
            outbox_task_ids = (
                connection.execute(text("SELECT DISTINCT task_id FROM outbox_events"))
                .scalars()
                .all()
            )
            self.assertEqual([tenant_a.id], visible_tasks)
            self.assertEqual([tenant_a.id], child_task_ids)
            self.assertEqual([tenant_a.id], outbox_task_ids)
            self.assertEqual(
                0,
                connection.scalar(
                    text("SELECT count(*) FROM task_runs WHERE tenant_id = 'tenant-b'")
                ),
            )

        self.assertEqual([tenant_b.id], [item.id for item in self.repository.list("tenant-b")])
        with self.assertRaises(TaskNotFoundError):
            self.repository.get("tenant-b", tenant_a.id)

    def test_with_check_blocks_tenant_reassignment_and_cross_tenant_mutation(self) -> None:
        tenant_a = self.service.create_task("tenant-a", "alice", "prepare alpha report")
        self.service.create_task("tenant-b", "bob", "prepare beta report")

        with self.app_engine.begin() as connection:
            connection.execute(text("SELECT set_config('app.tenant_id', 'tenant-b', true)"))
            result = connection.execute(
                text("UPDATE task_runs SET goal = 'tampered' WHERE id = :task_id"),
                {"task_id": tenant_a.id},
            )
            self.assertEqual(0, result.rowcount)

        with self.assertRaises(DBAPIError):
            with self.app_engine.begin() as connection:
                connection.execute(text("SELECT set_config('app.tenant_id', 'tenant-a', true)"))
                connection.execute(
                    text("UPDATE task_runs SET tenant_id = 'tenant-b' WHERE id = :task_id"),
                    {"task_id": tenant_a.id},
                )

        self.assertEqual("prepare alpha report", self.repository.get("tenant-a", tenant_a.id).goal)

    def test_all_tenant_tables_force_row_security(self) -> None:
        expected = {
            "task_runs",
            "task_steps",
            "approvals",
            "action_ledger",
            "verifications",
            "artifacts",
            "timeline_events",
            "checkpoints",
            "outbox_events",
        }
        with self.owner_engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:tables)"
                ),
                {"tables": list(expected)},
            ).all()
        self.assertEqual(expected, {row.relname for row in rows})
        self.assertTrue(all(row.relrowsecurity and row.relforcerowsecurity for row in rows))


if __name__ == "__main__":
    unittest.main()

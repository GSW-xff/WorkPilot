from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
from workpilot.models import TaskStatus
from workpilot.repository import ConcurrentUpdateError, TaskNotFoundError
from workpilot.runtime import WorkPilotService


class SQLAlchemyPersistenceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "workpilot-test.db"
        self.database_url = f"sqlite:///{self.database_path}"
        self.repositories: list[SQLAlchemyTaskRepository] = []

    def tearDown(self) -> None:
        for repository in self.repositories:
            repository.close()
        self.temporary_directory.cleanup()

    def repository(self, *, create_schema: bool = False) -> SQLAlchemyTaskRepository:
        repository = SQLAlchemyTaskRepository(
            create_database_engine(self.database_url), create_schema=create_schema
        )
        self.repositories.append(repository)
        return repository

    @staticmethod
    def service(repository: SQLAlchemyTaskRepository) -> WorkPilotService:
        adapter = FakeEnterpriseAdapter()
        return WorkPilotService(repository, CapabilityRegistry([adapter]))

    async def test_task_survives_repository_and_worker_restart(self) -> None:
        first_repository = self.repository(create_schema=True)
        first_service = self.service(first_repository)
        task = first_service.create_task("demo", "user-1", "生成并发送项目周报")
        task = await first_service.run("demo", task.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, task.status)
        self.assertEqual(3, len(task.ledger))

        second_repository = self.repository()
        second_service = self.service(second_repository)
        restored = second_repository.get("demo", task.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, restored.status)
        self.assertEqual(set(task.steps), set(restored.steps))
        self.assertEqual(len(task.events), len(restored.events))
        self.assertEqual(len(task.checkpoints), len(restored.checkpoints))

        approval = restored.approvals[-1]
        second_service.approve(
            "demo", restored.id, approval.step_id, approval.parameter_hash, "approver"
        )
        restored = await second_service.run("demo", restored.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, restored.status)

        approval = restored.approvals[-1]
        second_service.approve(
            "demo", restored.id, approval.step_id, approval.parameter_hash, "approver"
        )
        completed = await second_service.run("demo", restored.id)
        self.assertEqual(TaskStatus.SUCCEEDED, completed.status)
        self.assertEqual(5, len(completed.ledger))
        self.assertEqual(set(completed.steps), set(completed.verifications))

        third_repository = self.repository()
        final = third_repository.get("demo", task.id)
        self.assertEqual(TaskStatus.SUCCEEDED, final.status)
        self.assertEqual(completed.version, final.version)
        self.assertEqual(5, len(final.artifacts))

    def test_optimistic_lock_rejects_stale_writer(self) -> None:
        repository = self.repository(create_schema=True)
        service = self.service(repository)
        created = service.create_task("demo", "user-1", "prepare report")
        first = repository.get("demo", created.id)
        stale = repository.get("demo", created.id)
        first.goal = "first writer"
        repository.save(first, expected_version=first.version)
        stale.goal = "stale writer"
        with self.assertRaises(ConcurrentUpdateError):
            repository.save(stale, expected_version=stale.version)
        self.assertEqual("first writer", repository.get("demo", created.id).goal)

    def test_tenant_scope_applies_to_reads_lists_and_outbox(self) -> None:
        repository = self.repository(create_schema=True)
        service = self.service(repository)
        task = service.create_task("tenant-a", "user-1", "prepare report")
        self.assertEqual([task.id], [item.id for item in repository.list("tenant-a")])
        self.assertEqual([], repository.list("tenant-b"))
        with self.assertRaises(TaskNotFoundError):
            repository.get("tenant-b", task.id)
        self.assertGreater(len(repository.pending_outbox("tenant-a")), 0)
        self.assertEqual([], repository.pending_outbox("tenant-b"))

    def test_outbox_publish_is_tenant_scoped(self) -> None:
        repository = self.repository(create_schema=True)
        task = self.service(repository).create_task("demo", "user-1", "prepare report")
        pending = repository.pending_outbox("demo")
        self.assertEqual(len(task.events), len(pending))
        event_id = pending[0]["id"]
        self.assertEqual(0, repository.mark_outbox_published("other", [event_id]))
        self.assertEqual(1, repository.mark_outbox_published("demo", [event_id]))
        remaining_ids = {item["id"] for item in repository.pending_outbox("demo")}
        self.assertNotIn(event_id, remaining_ids)


class AlembicMigrationTest(unittest.TestCase):
    def test_initial_migration_creates_v2_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "migration.db"
            database_url = f"sqlite:///{database_path}"
            config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
            config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
            config.set_main_option("sqlalchemy.url", database_url)
            command.upgrade(config, "head")
            engine = create_database_engine(database_url)
            table_names = set(inspect(engine).get_table_names())
            ledger_columns = {
                column["name"] for column in inspect(engine).get_columns("action_ledger")
            }
            engine.dispose()
            self.assertTrue(
                {
                    "task_runs",
                    "task_steps",
                    "approvals",
                    "action_ledger",
                    "verifications",
                    "artifacts",
                    "timeline_events",
                    "checkpoints",
                    "outbox_events",
                }.issubset(table_names)
            )
            self.assertTrue(
                {
                    "attempt",
                    "last_error",
                    "next_retry_at",
                    "reconciliation_status",
                    "last_attempt_at",
                }.issubset(ledger_columns)
            )


if __name__ == "__main__":
    unittest.main()

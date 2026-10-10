from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
from workpilot.outbox import DeduplicatingConsumer, OutboxRelay
from workpilot.runtime import WorkPilotService


class OutboxRelayTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        database = Path(self.temp.name) / "outbox.db"
        self.repository = SQLAlchemyTaskRepository(
            create_database_engine(f"sqlite:///{database}"), create_schema=True
        )
        service = WorkPilotService(self.repository, CapabilityRegistry([FakeEnterpriseAdapter()]))
        self.task = service.create_task("demo", "user", "prepare report")

    async def asyncTearDown(self) -> None:
        self.repository.close()
        self.temp.cleanup()

    async def test_relay_marks_success_and_consumer_deduplicates(self) -> None:
        handled: list[int] = []

        async def handle(event):
            handled.append(int(event["id"]))

        consumer = DeduplicatingConsumer(handle)

        async def publish(event):
            self.assertTrue(await consumer.consume(event))
            self.assertFalse(await consumer.consume(event))

        relay = OutboxRelay(self.repository, publish)
        result = await relay.publish_batch("demo")
        self.assertEqual(len(self.task.events), result.published)
        self.assertEqual(0, result.failed)
        self.assertEqual(len(self.task.events), len(handled))
        self.assertEqual([], self.repository.pending_outbox("demo"))

    async def test_fifth_failure_enters_dead_letter(self) -> None:
        async def fail(_event):
            raise TimeoutError("broker unavailable")

        relay = OutboxRelay(self.repository, fail)
        for _ in range(5):
            result = await relay.publish_batch("demo", limit=1)
            self.assertEqual(1, result.failed)
        self.assertEqual(1, len(relay.dead_letters))
        dead_letter = next(iter(relay.dead_letters.values()))
        self.assertEqual("TimeoutError", dead_letter["error_type"])


if __name__ == "__main__":
    unittest.main()

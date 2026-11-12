from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.db.repository import SQLAlchemyTaskRepository, create_database_engine
from workpilot.lease import LeaseKeeper, LeaseLost
from workpilot.models import TaskStatus
from workpilot.repository import InMemoryTaskRepository
from workpilot.runtime import WorkPilotService

GOAL = "生成并发送项目周报"


class InMemoryLeaseSemanticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryTaskRepository()
        self.adapter = FakeEnterpriseAdapter()
        self.service = WorkPilotService(
            self.repository, CapabilityRegistry([self.adapter])
        )
        self.task = self.service.create_task("demo", "user-1", GOAL)

    def test_claim_is_exclusive_and_increments_fence(self) -> None:
        first = self.repository.claim_lease("demo", self.task.id, "worker-a", 60)
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(1, first.fence_token)

        blocked = self.repository.claim_lease("demo", self.task.id, "worker-b", 60)
        self.assertIsNone(blocked)
        self.assertTrue(
            self.repository.owns_lease("demo", self.task.id, "worker-a", first.fence_token)
        )
        self.assertFalse(
            self.repository.owns_lease("demo", self.task.id, "worker-b", first.fence_token)
        )

        self.assertTrue(
            self.repository.release_lease("demo", self.task.id, "worker-a", first.fence_token)
        )
        second = self.repository.claim_lease("demo", self.task.id, "worker-b", 60)
        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual(first.fence_token + 1, second.fence_token)

    def test_stale_token_cannot_renew_or_release(self) -> None:
        first = self.repository.claim_lease("demo", self.task.id, "worker-a", 60)
        assert first is not None
        self.repository.release_lease("demo", self.task.id, "worker-a", first.fence_token)
        second = self.repository.claim_lease("demo", self.task.id, "worker-b", 60)
        assert second is not None

        self.assertFalse(
            self.repository.renew_lease("demo", self.task.id, "worker-a", first.fence_token, 60)
        )
        self.assertFalse(
            self.repository.release_lease("demo", self.task.id, "worker-a", first.fence_token)
        )
        self.assertTrue(
            self.repository.owns_lease("demo", self.task.id, "worker-b", second.fence_token)
        )

    def test_expired_lease_can_be_taken_over_with_new_fence(self) -> None:
        first = self.repository.claim_lease("demo", self.task.id, "worker-a", 0.05)
        assert first is not None
        time.sleep(0.12)

        self.assertFalse(
            self.repository.owns_lease("demo", self.task.id, "worker-a", first.fence_token)
        )
        takeover = self.repository.claim_lease("demo", self.task.id, "worker-b", 60)
        self.assertIsNotNone(takeover)
        assert takeover is not None
        self.assertEqual(first.fence_token + 1, takeover.fence_token)

    def test_keeper_fails_closed_after_takeover(self) -> None:
        lease = self.repository.claim_lease("demo", self.task.id, "worker-a", 0.05)
        assert lease is not None
        keeper = LeaseKeeper(self.repository, lease, lease_seconds=0.05)
        time.sleep(0.12)
        self.repository.claim_lease("demo", self.task.id, "worker-b", 60)

        with self.assertRaises(LeaseLost):
            keeper.check()
        self.assertTrue(keeper.lost)

    def test_keeper_renews_in_background(self) -> None:
        lease = self.repository.claim_lease("demo", self.task.id, "worker-a", 0.6)
        assert lease is not None
        keeper = LeaseKeeper(
            self.repository, lease, lease_seconds=0.6, interval=0.05
        ).start()
        try:
            time.sleep(0.25)
        finally:
            keeper.stop()

        self.assertGreater(keeper.renewals, 0)
        self.assertFalse(keeper.lost)
        self.assertTrue(
            self.repository.owns_lease("demo", self.task.id, "worker-a", lease.fence_token)
        )


class LeaseRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repository = InMemoryTaskRepository()
        self.adapter = FakeEnterpriseAdapter()
        self.service = WorkPilotService(
            self.repository, CapabilityRegistry([self.adapter]), worker_id="worker-a"
        )

    async def test_run_claims_then_releases_lease(self) -> None:
        task = self.service.create_task("demo", "user-1", GOAL)
        task = await self.service.run("demo", task.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, task.status)

        claimed = [event for event in task.events if event.type == "lease.claimed"]
        self.assertEqual(1, len(claimed))
        self.assertEqual(1, claimed[0].details["fence_token"])

        # The lease is released when the run returns, so another worker may take over
        # immediately - and the fence token proves the claim was recorded once.
        takeover = self.repository.claim_lease("demo", task.id, "worker-b", 60)
        self.assertIsNotNone(takeover)
        assert takeover is not None
        self.assertEqual(2, takeover.fence_token)

    async def test_run_refuses_when_another_worker_holds_the_lease(self) -> None:
        task = self.service.create_task("demo", "user-1", GOAL)
        held = self.repository.claim_lease("demo", task.id, "worker-other", 60)
        self.assertIsNotNone(held)

        with self.assertRaises(LeaseLost):
            await self.service.run("demo", task.id)

        stored = self.repository.get("demo", task.id)
        self.assertEqual(TaskStatus.PLAN_READY, stored.status)
        self.assertEqual([], stored.ledger)
        self.assertEqual({}, self.adapter.state.tasks)


class SQLAlchemyLeaseTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "leases.db"
        self.database_url = f"sqlite:///{database_path}"
        self.repository = SQLAlchemyTaskRepository(
            create_database_engine(self.database_url), create_schema=True
        )
        self.adapter = FakeEnterpriseAdapter()
        self.service = WorkPilotService(
            self.repository, CapabilityRegistry([self.adapter]), worker_id="worker-a"
        )

    def tearDown(self) -> None:
        self.repository.close()
        self.temporary_directory.cleanup()

    async def test_lease_survives_round_trip_and_rejects_stale_token(self) -> None:
        task = self.service.create_task("demo", "user-1", GOAL)

        first = self.repository.claim_lease("demo", task.id, "worker-a", 60)
        self.assertIsNotNone(first)
        assert first is not None
        self.assertIsNone(self.repository.claim_lease("demo", task.id, "worker-b", 60))
        self.assertTrue(
            self.repository.owns_lease("demo", task.id, "worker-a", first.fence_token)
        )
        self.assertTrue(
            self.repository.renew_lease("demo", task.id, "worker-a", first.fence_token, 60)
        )
        self.assertTrue(
            self.repository.release_lease("demo", task.id, "worker-a", first.fence_token)
        )

        second = self.repository.claim_lease("demo", task.id, "worker-b", 60)
        assert second is not None
        self.assertEqual(first.fence_token + 1, second.fence_token)
        self.assertFalse(
            self.repository.renew_lease("demo", task.id, "worker-a", first.fence_token, 60)
        )

    async def test_run_releases_lease_so_another_worker_can_continue(self) -> None:
        task = self.service.create_task("demo", "user-1", GOAL)
        task = await self.service.run("demo", task.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, task.status)

        takeover = self.repository.claim_lease("demo", task.id, "worker-b", 60)
        self.assertIsNotNone(takeover)
        assert takeover is not None
        self.assertEqual(2, takeover.fence_token)


if __name__ == "__main__":
    unittest.main()

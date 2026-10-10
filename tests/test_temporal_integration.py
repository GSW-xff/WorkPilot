from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.repository import InMemoryTaskRepository
from workpilot.runtime import WorkPilotService
from workpilot.workflows.activities import TaskActivities
from workpilot.workflows.temporal import ApprovalCommand, TaskRef, TaskWorkflow

RUN_INTEGRATION = os.getenv("WORKPILOT_RUN_TEMPORAL_INTEGRATION") == "1"


@unittest.skipUnless(
    RUN_INTEGRATION,
    "set WORKPILOT_RUN_TEMPORAL_INTEGRATION=1 to run the downloaded Temporal test server",
)
class TemporalTestServerIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_worker_restart_updates_and_history_replay(self) -> None:
        environment = await WorkflowEnvironment.start_local(
            download_dest_dir=str(Path("/tmp/workpilot-temporal-test-server"))
        )
        try:
            adapter = FakeEnterpriseAdapter()
            repository = InMemoryTaskRepository()
            service = WorkPilotService(repository, CapabilityRegistry([adapter]))
            task = service.create_task("demo", "user", "send weekly report")
            activities = TaskActivities(service)
            queue = "workpilot-integration"
            activity_functions = [
                activities.advance_task,
                activities.approve_task,
                activities.reject_task,
                activities.pause_task,
                activities.resume_task,
                activities.cancel_task,
            ]

            # The first worker advances to approval and is then deliberately stopped.
            async with Worker(
                environment.client,
                task_queue=queue,
                workflows=[TaskWorkflow],
                activities=activity_functions,
            ):
                handle = await environment.client.start_workflow(
                    TaskWorkflow.run,
                    TaskRef("demo", task.id),
                    id=f"integration-{task.id}",
                    task_queue=queue,
                )
                await _wait_for_status(handle, "WAITING_APPROVAL")

            # A new worker consumes history and continues without recreating side effects.
            async with Worker(
                environment.client,
                task_queue=queue,
                workflows=[TaskWorkflow],
                activities=activity_functions,
            ):
                current = repository.get("demo", task.id)
                first = current.approvals[-1]
                await handle.execute_update(
                    TaskWorkflow.decide_approval,
                    ApprovalCommand(
                        tenant_id="demo",
                        task_id=task.id,
                        step_id=first.step_id,
                        parameter_hash=first.parameter_hash,
                        approver="approver",
                    ),
                )
                await _wait_for_approval_count(repository, task.id, 2)
                second = repository.get("demo", task.id).approvals[-1]
                await handle.execute_update(
                    TaskWorkflow.decide_approval,
                    ApprovalCommand(
                        tenant_id="demo",
                        task_id=task.id,
                        step_id=second.step_id,
                        parameter_hash=second.parameter_hash,
                        approver="approver",
                    ),
                )
                self.assertEqual("SUCCEEDED", await handle.result())

            final = repository.get("demo", task.id)
            self.assertEqual(1, len(adapter.state.sent_mail))
            self.assertTrue(all(entry.attempt == 1 for entry in final.ledger))
            history = await handle.fetch_history()
            replay = await Replayer(workflows=[TaskWorkflow]).replay_workflow(history)
            self.assertIsNone(replay.replay_failure)
        finally:
            await environment.shutdown()


async def _wait_for_status(handle, expected: str) -> None:
    for _ in range(200):
        if await handle.query(TaskWorkflow.status) == expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"workflow did not reach {expected}")


async def _wait_for_approval_count(
    repository: InMemoryTaskRepository, task_id: str, count: int
) -> None:
    for _ in range(200):
        if len(repository.get("demo", task_id).approvals) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"task did not create {count} approvals")

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

from temporalio.exceptions import ApplicationError

from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.repository import InMemoryTaskRepository
from workpilot.runtime import WorkPilotService
from workpilot.workflows.activities import TaskActivities
from workpilot.workflows.client import TemporalTaskClient
from workpilot.workflows.temporal import ApprovalCommand, TaskRef, TaskWorkflow


class TemporalActivitiesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        adapter = FakeEnterpriseAdapter()
        self.repository = InMemoryTaskRepository()
        self.service = WorkPilotService(
            self.repository, CapabilityRegistry([adapter])
        )
        self.activities = TaskActivities(self.service)

    async def test_activities_drive_task_through_both_approvals(self) -> None:
        task = self.service.create_task("demo", "user-1", "send weekly report")
        ref = TaskRef(tenant_id="demo", task_id=task.id)

        self.assertEqual("WAITING_APPROVAL", await self.activities.advance_task(ref))
        task = self.repository.get("demo", task.id)
        first = task.approvals[-1]
        self.assertEqual(
            "RUNNING",
            await self.activities.approve_task(
                ApprovalCommand(
                    tenant_id="demo",
                    task_id=task.id,
                    step_id=first.step_id,
                    parameter_hash=first.parameter_hash,
                    approver="approver",
                )
            ),
        )

        self.assertEqual("WAITING_APPROVAL", await self.activities.advance_task(ref))
        task = self.repository.get("demo", task.id)
        second = task.approvals[-1]
        await self.activities.approve_task(
            ApprovalCommand(
                tenant_id="demo",
                task_id=task.id,
                step_id=second.step_id,
                parameter_hash=second.parameter_hash,
                approver="approver",
            )
        )
        self.assertEqual("SUCCEEDED", await self.activities.advance_task(ref))

    async def test_pause_resume_cancel_and_reject_activities(self) -> None:
        task = self.service.create_task("demo", "user-1", "send weekly report")
        ref = TaskRef(tenant_id="demo", task_id=task.id)
        self.assertEqual("PAUSED", await self.activities.pause_task(ref))
        self.assertEqual("PLAN_READY", await self.activities.resume_task(ref))
        self.assertEqual("CANCELLED", await self.activities.cancel_task(ref))

        rejected = self.service.create_task("demo", "user-1", "send another report")
        rejected_ref = TaskRef(tenant_id="demo", task_id=rejected.id)
        await self.activities.advance_task(rejected_ref)
        rejected = self.repository.get("demo", rejected.id)
        approval = rejected.approvals[-1]
        status = await self.activities.reject_task(
            ApprovalCommand(
                tenant_id="demo",
                task_id=rejected.id,
                step_id=approval.step_id,
                parameter_hash=approval.parameter_hash,
                approver="approver",
                approved=False,
                reason="not now",
            )
        )
        self.assertEqual("CANCELLED", status)


class TemporalWorkflowHandlerTest(unittest.IsolatedAsyncioTestCase):
    async def test_approval_update_and_control_signals_change_workflow_state(self) -> None:
        instance = TaskWorkflow()
        instance._ref = TaskRef(tenant_id="demo", task_id="task-123")
        instance._status = "WAITING_APPROVAL"
        command = ApprovalCommand(
            tenant_id="demo",
            task_id="task-123",
            step_id="send_report",
            parameter_hash="hash",
            approver="approver",
        )
        with patch(
            "workpilot.workflows.temporal.workflow.execute_activity",
            new=AsyncMock(side_effect=["RUNNING", "PAUSED", "RUNNING", "CANCELLED"]),
        ) as execute:
            self.assertEqual("RUNNING", await instance.decide_approval(command))
            await instance.pause()
            self.assertEqual("PAUSED", instance.status())
            await instance.resume()
            self.assertEqual("RUNNING", instance.status())
            await instance.cancel()
            self.assertEqual("CANCELLED", instance.status())
            self.assertEqual(4, execute.await_count)

    async def test_approval_update_rejects_wrong_task_or_state(self) -> None:
        instance = TaskWorkflow()
        instance._ref = TaskRef(tenant_id="demo", task_id="task-123")
        instance._status = "WAITING_APPROVAL"
        wrong_task = ApprovalCommand(
            tenant_id="demo",
            task_id="other",
            step_id="send_report",
            parameter_hash="hash",
            approver="approver",
        )
        with self.assertRaises(ApplicationError):
            await instance.decide_approval(wrong_task)

        wrong_tenant = ApprovalCommand(
            tenant_id="other-tenant",
            task_id="task-123",
            step_id="send_report",
            parameter_hash="hash",
            approver="approver",
        )
        with self.assertRaises(ApplicationError):
            await instance.decide_approval(wrong_tenant)

        instance._status = "RUNNING"
        correct_task = ApprovalCommand(
            tenant_id="demo",
            task_id="task-123",
            step_id="send_report",
            parameter_hash="hash",
            approver="approver",
        )
        with self.assertRaises(ApplicationError):
            await instance.decide_approval(correct_task)


class TemporalClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_client_uses_stable_workflow_id_and_task_queue(self) -> None:
        raw_client = Mock()
        raw_client.start_workflow = AsyncMock()
        temporal = TemporalTaskClient(raw_client, "workpilot-test")

        await temporal.start("demo", "task-123")

        call = raw_client.start_workflow.await_args
        self.assertEqual("workpilot-task-demo-task-123", call.kwargs["id"])
        self.assertEqual("workpilot-test", call.kwargs["task_queue"])

        await temporal.start("other-tenant", "task-123")
        second_call = raw_client.start_workflow.await_args
        self.assertEqual(
            "workpilot-task-other-tenant-task-123", second_call.kwargs["id"]
        )

    async def test_client_sends_approval_update_and_control_signals(self) -> None:
        handle = Mock()
        handle.execute_update = AsyncMock()
        handle.signal = AsyncMock()
        raw_client = Mock()
        raw_client.get_workflow_handle.return_value = handle
        temporal = TemporalTaskClient(raw_client, "workpilot-test")
        command = ApprovalCommand(
            tenant_id="demo",
            task_id="task-123",
            step_id="send_report",
            parameter_hash="hash",
            approver="approver",
        )

        await temporal.approve(command)
        await temporal.signal(command.tenant_id, command.task_id, "pause")
        await temporal.signal(command.tenant_id, command.task_id, "resume")
        await temporal.signal(command.tenant_id, command.task_id, "cancel")

        handle.execute_update.assert_awaited_once()
        self.assertEqual(3, handle.signal.await_count)

        with self.assertRaisesRegex(ValueError, "unknown workflow signal"):
            await temporal.signal(command.tenant_id, command.task_id, "unknown")


if __name__ == "__main__":
    unittest.main()

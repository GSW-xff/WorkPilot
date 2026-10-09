import unittest

from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.models import ActionRequest, ApprovalStatus, Channel, StepStatus, TaskStatus
from workpilot.repository import InMemoryTaskRepository, TaskNotFoundError
from workpilot.runtime import WorkPilotService


class RuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.adapter = FakeEnterpriseAdapter()
        self.repository = InMemoryTaskRepository()
        self.service = WorkPilotService(
            self.repository, CapabilityRegistry([self.adapter])
        )

    async def test_end_to_end_demo_requires_both_approvals_and_verifies(self) -> None:
        task = self.service.create_task("demo", "user-1", "生成并发送项目周报")
        self.assertEqual(TaskStatus.PLAN_READY, task.status)

        task = await self.service.run("demo", task.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, task.status)
        self.assertEqual(StepStatus.SUCCEEDED, task.steps["compose_report"].status)
        self.assertEqual("create_followup", task.approvals[-1].step_id)
        self.assertEqual({}, self.adapter.state.tasks)

        approval = task.approvals[-1]
        task = self.service.approve(
            "demo", task.id, approval.step_id, approval.parameter_hash, "approver"
        )
        task = await self.service.run("demo", task.id)
        self.assertEqual(TaskStatus.WAITING_APPROVAL, task.status)
        self.assertEqual("send_report", task.approvals[-1].step_id)
        self.assertEqual(1, len(self.adapter.state.tasks))
        self.assertEqual({}, self.adapter.state.sent_mail)

        approval = task.approvals[-1]
        self.service.approve(
            "demo", task.id, approval.step_id, approval.parameter_hash, "approver"
        )
        task = await self.service.run("demo", task.id)

        self.assertEqual(TaskStatus.SUCCEEDED, task.status)
        self.assertEqual(5, len(task.ledger))
        self.assertEqual(set(task.steps), set(task.verifications))
        self.assertTrue(all(item.status == "PASSED" for item in task.verifications.values()))
        self.assertEqual(1, len(self.adapter.state.sent_mail))
        self.assertGreaterEqual(len(task.checkpoints), 8)

    async def test_fake_adapter_is_idempotent(self) -> None:
        action = ActionRequest(
            tenant_id="demo",
            task_id="one",
            step_id="send",
            capability="mail.send",
            parameters={"to": ["team@example.com"], "subject": "Update"},
            channel=Channel.API,
        )
        first = await self.adapter.execute(action, "same-key")
        second = await self.adapter.execute(action, "same-key")
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(first.remote_id, second.remote_id)
        self.assertEqual(1, self.adapter.execution_count["mail.send"])
        self.assertEqual(1, len(self.adapter.state.sent_mail))

    async def test_wrong_parameter_hash_cannot_approve(self) -> None:
        task = self.service.create_task("demo", "user-1", "send report")
        task = await self.service.run("demo", task.id)
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.service.approve(
                "demo", task.id, task.approvals[-1].step_id, "tampered", "approver"
            )
        stored = self.repository.get("demo", task.id)
        self.assertEqual(ApprovalStatus.PENDING, stored.approvals[-1].status)
        self.assertEqual({}, self.adapter.state.tasks)

    async def test_pause_resume_and_cancel_use_legal_transitions(self) -> None:
        task = self.service.create_task("demo", "user-1", "send report")
        task = self.service.pause("demo", task.id)
        self.assertEqual(TaskStatus.PAUSED, task.status)
        task = self.service.resume("demo", task.id)
        self.assertEqual(TaskStatus.PLAN_READY, task.status)
        task = self.service.cancel("demo", task.id)
        self.assertEqual(TaskStatus.CANCELLED, task.status)
        self.assertTrue(
            all(item.status is StepStatus.CANCELLED for item in task.steps.values())
        )
        with self.assertRaises(ValueError):
            await self.service.run("demo", task.id)

    def test_repository_enforces_tenant_scope(self) -> None:
        task = self.service.create_task("tenant-a", "user-1", "prepare report")
        with self.assertRaises(TaskNotFoundError):
            self.repository.get("tenant-b", task.id)

    def test_external_recipient_domain_is_rejected_during_planning(self) -> None:
        task = self.service.create_task(
            "demo", "user-1", "send report", recipient="outside@external.invalid"
        )
        self.assertEqual(TaskStatus.FAILED, task.status)
        self.assertIn("allowed tenant domain", task.events[-1].message)
        self.assertEqual({}, self.adapter.state.sent_mail)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from uuid import uuid4

from workpilot.connectors.base import CapabilityRegistry
from workpilot.dag import topological_order, validate_plan
from workpilot.models import (
    ActionLedgerEntry,
    ActionRequest,
    Approval,
    ApprovalStatus,
    Artifact,
    Checkpoint,
    StepRun,
    StepStatus,
    TaskRun,
    TaskStatus,
    TimelineEvent,
    VerificationStatus,
    utc_now,
)
from workpilot.planner import DemoPlanner
from workpilot.policy import PolicyEngine
from workpilot.repository import InMemoryTaskRepository
from workpilot.security import idempotency_key, parameter_hash, redact
from workpilot.state_machine import ensure_transition


TERMINAL_STATUSES = {TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.SUCCEEDED}


class WorkPilotService:
    def __init__(
        self,
        repository: InMemoryTaskRepository,
        registry: CapabilityRegistry,
        planner: DemoPlanner | None = None,
        policy: PolicyEngine | None = None,
        max_steps: int = 20,
        allowed_recipient_domains: set[str] | None = None,
    ) -> None:
        self.repository = repository
        self.registry = registry
        self.planner = planner or DemoPlanner()
        self.policy = policy or PolicyEngine()
        self.max_steps = max_steps
        self.allowed_recipient_domains = allowed_recipient_domains or {"example.com"}

    def create_task(
        self,
        tenant_id: str,
        user_id: str,
        goal: str,
        recipient: str = "team@example.com",
    ) -> TaskRun:
        task = TaskRun(
            id=f"taskrun-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            goal=goal,
        )
        self._event(task, "task.created", "任务已创建")
        self._transition(task, TaskStatus.PLANNING, "planner.started", "开始生成执行计划")
        try:
            plan = self.planner.plan(goal, recipient)
            validate_plan(plan, self.registry.names, self.registry.risks, self.max_steps)
            self._validate_recipient_domains(plan)
        except Exception as exc:
            self._transition(task, TaskStatus.FAILED, "plan.failed", str(exc))
            return self.repository.add(task)
        task.plan = plan
        task.steps = {step.id: StepRun(step=step) for step in plan.steps}
        self._transition(task, TaskStatus.PLAN_READY, "plan.ready", "执行计划已通过确定性校验")
        self._checkpoint(task)
        return self.repository.add(task)

    async def run(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        starting_version = task.version
        if task.status is TaskStatus.PLAN_READY:
            self._transition(task, TaskStatus.RUNNING, "task.running", "任务开始执行")
        elif task.status is not TaskStatus.RUNNING:
            raise ValueError(f"task cannot run from {task.status.value}")
        assert task.plan is not None

        for step_id in topological_order(task.plan.steps):
            step_run = task.steps[step_id]
            if step_run.status is StepStatus.SUCCEEDED:
                continue
            if any(task.steps[item].status is not StepStatus.SUCCEEDED for item in step_run.step.depends_on):
                continue

            step = step_run.step
            channel = self.registry.channel_for(step.capability, step.preferred_channel)
            decision = self.policy.evaluate(step, self.registry.risks[step.capability], channel)
            if not decision.allowed:
                step_run.status = StepStatus.FAILED
                step_run.error = decision.reason
                self._transition(task, TaskStatus.FAILED, "policy.denied", decision.reason, step_id)
                self._checkpoint(task)
                return self.repository.save(task, expected_version=starting_version)

            action = ActionRequest(
                tenant_id=tenant_id,
                task_id=task.id,
                step_id=step.id,
                capability=step.capability,
                parameters=step.parameters,
                channel=channel,
            )
            params_hash = parameter_hash(action.parameters)
            adapter = self.registry.adapter_for(step.capability)
            if decision.requires_approval and not self._has_valid_approval(task, step.id, params_hash):
                preview = await adapter.preview(action)
                self._ensure_pending_approval(task, action, preview.human_summary, params_hash)
                step_run.status = StepStatus.WAITING_APPROVAL
                self._transition(
                    task,
                    TaskStatus.WAITING_APPROVAL,
                    "approval.requested",
                    preview.human_summary,
                    step.id,
                    {"parameter_hash": params_hash, "parameters": redact(action.parameters)},
                )
                self._checkpoint(task)
                return self.repository.save(task, expected_version=starting_version)

            step_run.status = StepStatus.RUNNING
            step_run.started_at = utc_now()
            self._event(task, "step.started", step.description, step.id)
            key = idempotency_key(
                tenant_id, task.id, step.id, step.capability, action.parameters
            )
            existing = next((item for item in task.ledger if item.idempotency_key == key), None)
            if existing is not None:
                result = self._result_from_ledger(existing)
            else:
                result = await adapter.execute(action, key)
                task.ledger.append(
                    ActionLedgerEntry(
                        idempotency_key=key,
                        step_id=step.id,
                        action=step.capability,
                        channel=channel,
                        parameter_hash=params_hash,
                        remote_id=result.remote_id,
                        status="EXECUTED" if result.success else "FAILED",
                        result=redact(result.model_dump(mode="json")),
                    )
                )

            artifact = Artifact(
                id=f"artifact-{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                task_id=task.id,
                step_id=step.id,
                type="tool_result",
                content=redact(result.model_dump(mode="json")),
            )
            task.artifacts.append(artifact)
            verification = await adapter.verify(action, result)
            verification.evidence_refs = list(
                dict.fromkeys([f"artifact://{artifact.id}", *verification.evidence_refs])
            )
            task.verifications[step.id] = verification
            if verification.status is not VerificationStatus.PASSED:
                step_run.status = StepStatus.FAILED
                step_run.error = verification.reason
                step_run.completed_at = utc_now()
                self._transition(
                    task,
                    TaskStatus.FAILED,
                    "step.verification_failed",
                    verification.reason,
                    step.id,
                )
                self._checkpoint(task)
                return self.repository.save(task, expected_version=starting_version)

            step_run.status = StepStatus.SUCCEEDED
            step_run.result = result.model_dump(mode="json")
            step_run.completed_at = utc_now()
            self._event(task, "step.succeeded", "远端状态已独立验证", step.id)
            self._checkpoint(task)

        if all(item.status is StepStatus.SUCCEEDED for item in task.steps.values()):
            self._transition(task, TaskStatus.SUCCEEDED, "task.succeeded", "所有目标均已验证通过")
            self._checkpoint(task)
        return self.repository.save(task, expected_version=starting_version)

    def approve(
        self,
        tenant_id: str,
        task_id: str,
        step_id: str,
        supplied_hash: str,
        approver: str,
    ) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status is not TaskStatus.WAITING_APPROVAL:
            raise ValueError("task is not waiting for approval")
        approval = self._pending_approval(task, step_id)
        if approval.parameter_hash != supplied_hash:
            raise ValueError("approval parameter hash does not match the current preview")
        current_hash = parameter_hash(task.steps[step_id].step.parameters)
        if current_hash != approval.parameter_hash:
            approval.status = ApprovalStatus.EXPIRED
            raise ValueError("action parameters changed; a new approval is required")
        approval.status = ApprovalStatus.APPROVED
        approval.decided_at = utc_now()
        approval.decided_by = approver
        task.steps[step_id].status = StepStatus.PENDING
        self._transition(task, TaskStatus.RUNNING, "approval.approved", "审批已通过", step_id)
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def reject(
        self, tenant_id: str, task_id: str, step_id: str, approver: str, reason: str
    ) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        approval = self._pending_approval(task, step_id)
        approval.status = ApprovalStatus.REJECTED
        approval.decided_at = utc_now()
        approval.decided_by = approver
        approval.reason = reason
        task.steps[step_id].status = StepStatus.CANCELLED
        self._transition(task, TaskStatus.CANCELLED, "approval.rejected", reason, step_id)
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def pause(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status not in {TaskStatus.PLAN_READY, TaskStatus.RUNNING, TaskStatus.WAITING_APPROVAL}:
            raise ValueError(f"task cannot pause from {task.status.value}")
        task.paused_from = task.status
        self._transition(task, TaskStatus.PAUSED, "task.paused", "任务已安全暂停")
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def resume(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status is not TaskStatus.PAUSED or task.paused_from is None:
            raise ValueError("task is not paused")
        target = task.paused_from
        task.paused_from = None
        self._transition(task, target, "task.resumed", "任务已从最近检查点恢复")
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def cancel(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        version = task.version
        if task.status in TERMINAL_STATUSES:
            raise ValueError(f"task is already terminal: {task.status.value}")
        for step in task.steps.values():
            if step.status in {StepStatus.PENDING, StepStatus.WAITING_APPROVAL}:
                step.status = StepStatus.CANCELLED
        self._transition(task, TaskStatus.CANCELLED, "task.cancelled", "任务已取消")
        self._checkpoint(task)
        return self.repository.save(task, expected_version=version)

    def _validate_recipient_domains(self, plan) -> None:
        for step in plan.steps:
            if step.capability != "mail.send":
                continue
            recipients = step.parameters.get("to", [])
            invalid = [
                item
                for item in recipients
                if not isinstance(item, str)
                or "@" not in item
                or item.rsplit("@", 1)[1].lower() not in self.allowed_recipient_domains
            ]
            if invalid:
                raise ValueError("mail recipients must belong to an allowed tenant domain")

    def _transition(
        self,
        task: TaskRun,
        status: TaskStatus,
        event_type: str,
        message: str,
        step_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        ensure_transition(task.status, status)
        task.status = status
        self._event(task, event_type, message, step_id, details)

    @staticmethod
    def _event(
        task: TaskRun,
        event_type: str,
        message: str,
        step_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        task.events.append(
            TimelineEvent(
                sequence=len(task.events) + 1,
                type=event_type,
                message=message,
                task_status=task.status,
                step_id=step_id,
                details=details or {},
            )
        )

    @staticmethod
    def _checkpoint(task: TaskRun) -> None:
        task.checkpoints.append(
            Checkpoint(
                sequence=len(task.checkpoints) + 1,
                task_status=task.status,
                plan_version=task.plan.version if task.plan else 0,
                completed_steps=[
                    step_id
                    for step_id, run in task.steps.items()
                    if run.status is StepStatus.SUCCEEDED
                ],
                ledger_keys=[item.idempotency_key for item in task.ledger],
            )
        )

    @staticmethod
    def _has_valid_approval(task: TaskRun, step_id: str, params_hash: str) -> bool:
        return any(
            item.step_id == step_id
            and item.parameter_hash == params_hash
            and item.plan_version == task.plan.version
            and item.status is ApprovalStatus.APPROVED
            for item in task.approvals
        )

    @staticmethod
    def _ensure_pending_approval(
        task: TaskRun,
        action: ActionRequest,
        summary: str,
        params_hash: str,
    ) -> Approval:
        existing = next(
            (
                item
                for item in task.approvals
                if item.step_id == action.step_id
                and item.parameter_hash == params_hash
                and item.status is ApprovalStatus.PENDING
            ),
            None,
        )
        if existing:
            return existing
        approval = Approval(
            id=f"approval-{uuid4().hex[:12]}",
            tenant_id=task.tenant_id,
            task_id=task.id,
            step_id=action.step_id,
            action_type=action.capability,
            parameter_preview={"summary": summary, **redact(action.parameters)},
            parameter_hash=params_hash,
            plan_version=task.plan.version,
        )
        task.approvals.append(approval)
        return approval

    @staticmethod
    def _pending_approval(task: TaskRun, step_id: str) -> Approval:
        approval = next(
            (
                item
                for item in reversed(task.approvals)
                if item.step_id == step_id and item.status is ApprovalStatus.PENDING
            ),
            None,
        )
        if approval is None:
            raise ValueError(f"no pending approval for step: {step_id}")
        return approval

    @staticmethod
    def _result_from_ledger(entry: ActionLedgerEntry):
        from workpilot.models import ActionResult

        stored = dict(entry.result)
        stored["duplicate"] = True
        return ActionResult.model_validate(stored)

from __future__ import annotations

import hashlib
from datetime import timedelta
from uuid import uuid4

from workpilot.connectors.base import CapabilityRegistry, ConnectorError
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
from workpilot.planner import DemoPlanner, StructuredPlanner, diff_plans
from workpilot.policy import PolicyEngine
from workpilot.repository import TaskRepository
from workpilot.security import idempotency_key, parameter_hash, redact
from workpilot.state_machine import ensure_transition

TERMINAL_STATUSES = {TaskStatus.CANCELLED, TaskStatus.FAILED, TaskStatus.SUCCEEDED}


class WorkPilotService:
    def __init__(
        self,
        repository: TaskRepository,
        registry: CapabilityRegistry,
        planner: DemoPlanner | StructuredPlanner | None = None,
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
        if isinstance(self.planner, StructuredPlanner):
            raise RuntimeError("structured planner requires create_task_async")
        task = self._new_task(tenant_id, user_id, goal)
        try:
            plan = self.planner.plan(goal, recipient)
            validate_plan(plan, self.registry.names, self.registry.risks, self.max_steps)
            self._validate_recipient_domains(plan)
        except Exception as exc:
            return self._store_planning_failure(task, exc)
        return self._store_plan(task, plan)

    async def create_task_async(
        self,
        tenant_id: str,
        user_id: str,
        goal: str,
        recipient: str = "team@example.com",
    ) -> TaskRun:
        if not isinstance(self.planner, StructuredPlanner):
            return self.create_task(tenant_id, user_id, goal, recipient)
        task = self._new_task(tenant_id, user_id, goal)
        trace_id = uuid4().hex
        try:
            outcome = await self.planner.plan(
                goal,
                recipient,
                metadata={
                    "trace_id": trace_id,
                    "tenant_id": tenant_id,
                    "task_id": task.id,
                },
            )
            self._validate_recipient_domains(outcome.plan)
        except Exception as exc:
            return self._store_planning_failure(task, exc)

        snapshot_id = f"context-{uuid4().hex[:12]}"
        snapshot = outcome.context_snapshot
        safe_messages = [
            {
                "source": item["source"],
                "trust": item["trust"],
                "content_length": len(item["content"]),
                "content_sha256": hashlib.sha256(item["content"].encode()).hexdigest(),
            }
            for item in snapshot["messages"]
        ]
        task.artifacts.append(
            Artifact(
                id=snapshot_id,
                tenant_id=tenant_id,
                task_id=task.id,
                type="context_snapshot",
                content={
                    "messages": safe_messages,
                    "included_sources": snapshot["included_sources"],
                    "omitted_sources": snapshot["omitted_sources"],
                    "injection_markers": snapshot["injection_markers"],
                    "estimated_tokens": snapshot["estimated_tokens"],
                    "trace_id": trace_id,
                    "sensitive_content_recorded": False,
                },
            )
        )
        assert outcome.plan.planning is not None
        outcome.plan.planning.context_snapshot_id = snapshot_id
        self._event(
            task,
            "planner.completed",
            "结构化计划已生成" if not outcome.used_fallback else "模型规划失败，已安全回退",
            details={
                "trace_id": trace_id,
                "used_fallback": outcome.used_fallback,
                "model_calls": len(outcome.model_calls),
                "validation_error_count": len(outcome.validation_errors),
                "context_snapshot_id": snapshot_id,
            },
        )
        return self._store_plan(task, outcome.plan)

    def replan(self, tenant_id: str, task_id: str, candidate) -> tuple[TaskRun, dict]:
        task = self.repository.get(tenant_id, task_id)
        if task.plan is None:
            raise ValueError("task has no existing plan")
        validate_plan(candidate, self.registry.names, self.registry.risks, self.max_steps)
        self._validate_recipient_domains(candidate)
        candidate.version = task.plan.version + 1
        completed = {
            step_id for step_id, run in task.steps.items() if run.status is StepStatus.SUCCEEDED
        }
        plan_diff = diff_plans(task.plan, candidate, completed)
        previous_runs = task.steps
        task.plan = candidate
        task.steps = {
            step.id: previous_runs.get(step.id, StepRun(step=step)).model_copy(
                update={"step": step}
            )
            for step in candidate.steps
        }
        self._event(task, "plan.replanned", "执行计划已更新", details=plan_diff)
        self._checkpoint(task)
        return self.repository.save(task, expected_version=task.version), plan_diff

    def _new_task(self, tenant_id: str, user_id: str, goal: str) -> TaskRun:
        task = TaskRun(
            id=f"taskrun-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            goal=goal,
        )
        self._event(task, "task.created", "任务已创建")
        self._transition(task, TaskStatus.PLANNING, "planner.started", "开始生成执行计划")
        return task

    def _store_planning_failure(self, task: TaskRun, exc: Exception) -> TaskRun:
        self._transition(task, TaskStatus.FAILED, "plan.failed", str(exc))
        return self.repository.add(task)

    def _store_plan(self, task: TaskRun, plan) -> TaskRun:
        task.plan = plan
        task.steps = {step.id: StepRun(step=step) for step in plan.steps}
        self._transition(task, TaskStatus.PLAN_READY, "plan.ready", "执行计划已通过确定性校验")
        self._checkpoint(task)
        return self.repository.add(task)

    async def run(self, tenant_id: str, task_id: str) -> TaskRun:
        task = self.repository.get(tenant_id, task_id)
        if task.status is TaskStatus.PLAN_READY:
            self._transition(task, TaskStatus.RUNNING, "task.running", "任务开始执行")
        elif task.status is not TaskStatus.RUNNING:
            raise ValueError(f"task cannot run from {task.status.value}")
        assert task.plan is not None

        for step_id in topological_order(task.plan.steps):
            step_run = task.steps[step_id]
            if step_run.status is StepStatus.SUCCEEDED:
                continue
            if any(
                task.steps[item].status is not StepStatus.SUCCEEDED
                for item in step_run.step.depends_on
            ):
                continue

            step = step_run.step
            channel = self.registry.channel_for(step.capability, step.preferred_channel)
            decision = self.policy.evaluate(step, self.registry.risks[step.capability], channel)
            if not decision.allowed:
                step_run.status = StepStatus.FAILED
                step_run.error = decision.reason
                self._transition(task, TaskStatus.FAILED, "policy.denied", decision.reason, step_id)
                self._checkpoint(task)
                return self.repository.save(task, expected_version=task.version)

            action = ActionRequest(
                tenant_id=tenant_id,
                task_id=task.id,
                step_id=step.id,
                capability=step.capability,
                parameters=step.parameters,
                channel=channel,
                deadline_at=utc_now() + timedelta(seconds=60),
            )
            params_hash = parameter_hash(action.parameters)
            adapter = self.registry.adapter_for(step.capability)
            if decision.requires_approval and not self._has_valid_approval(
                task, step.id, params_hash
            ):
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
                return self.repository.save(task, expected_version=task.version)

            step_run.status = StepStatus.RUNNING
            step_run.started_at = utc_now()
            self._event(task, "step.started", step.description, step.id)
            key = idempotency_key(tenant_id, task.id, step.id, step.capability, action.parameters)
            existing = next((item for item in task.ledger if item.idempotency_key == key), None)
            if existing is not None and existing.status in {"CONFIRMED", "EXECUTED"}:
                result = self._result_from_ledger(existing)
            else:
                if existing is None:
                    existing = ActionLedgerEntry(
                        idempotency_key=key,
                        step_id=step.id,
                        action=step.capability,
                        channel=channel,
                        parameter_hash=params_hash,
                        status="RESERVED",
                    )
                    task.ledger.append(existing)
                    self._event(
                        task,
                        "action.reserved",
                        "动作已使用幂等键预占",
                        step.id,
                        {"idempotency_key": key},
                    )
                    task = self.repository.save(task, expected_version=task.version)
                    step_run = task.steps[step_id]
                    existing = next(item for item in task.ledger if item.idempotency_key == key)

                result = await adapter.lookup(action, key)
                if result is None:
                    existing.attempt += 1
                    existing.last_attempt_at = utc_now()
                    existing.last_error = None
                    existing.next_retry_at = None
                    try:
                        result = await adapter.execute(action, key)
                    except ConnectorError as exc:
                        existing.last_error = str(exc)
                        existing.next_retry_at = (
                            utc_now() + timedelta(seconds=min(2**existing.attempt, 60))
                            if exc.retryable
                            else None
                        )
                        if exc.outcome_unknown:
                            existing.status = "UNKNOWN"
                            existing.reconciliation_status = "REQUIRED"
                        else:
                            existing.status = "RETRYABLE" if exc.retryable else "FAILED"
                        self._event(
                            task,
                            "action.unknown" if exc.outcome_unknown else "action.failed",
                            "动作结果未知，重试前必须查询远端状态",
                            step.id,
                            {
                                "retryable": exc.retryable,
                                "attempt": existing.attempt,
                                "next_retry_at": existing.next_retry_at.isoformat()
                                if existing.next_retry_at
                                else None,
                            },
                        )
                        self.repository.save(task, expected_version=task.version)
                        raise
                    except Exception as exc:
                        existing.status = "UNKNOWN"
                        existing.last_error = str(exc)
                        existing.next_retry_at = utc_now() + timedelta(
                            seconds=min(2**existing.attempt, 60)
                        )
                        existing.reconciliation_status = "REQUIRED"
                        self._event(
                            task,
                            "action.unknown",
                            "动作结果未知，重试前必须查询远端状态",
                            step.id,
                            {"attempt": existing.attempt},
                        )
                        self.repository.save(task, expected_version=task.version)
                        raise
                existing.remote_id = result.remote_id
                existing.status = "DISPATCHED" if result.success else "FAILED"
                existing.result = redact(result.model_dump(mode="json"))

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
                return self.repository.save(task, expected_version=task.version)

            step_run.status = StepStatus.SUCCEEDED
            step_run.result = result.model_dump(mode="json")
            step_run.completed_at = utc_now()
            existing.status = "CONFIRMED"
            existing.reconciliation_status = "CONFIRMED"
            existing.last_error = None
            existing.next_retry_at = None
            self._event(task, "step.succeeded", "远端状态已独立验证", step.id)
            self._checkpoint(task)
            task = self.repository.save(task, expected_version=task.version)

        if all(item.status is StepStatus.SUCCEEDED for item in task.steps.values()):
            self._transition(task, TaskStatus.SUCCEEDED, "task.succeeded", "所有目标均已验证通过")
            self._checkpoint(task)
        return self.repository.save(task, expected_version=task.version)

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
        pausable = {
            TaskStatus.PLAN_READY,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_APPROVAL,
        }
        if task.status not in pausable:
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

    def recovery_cases(self, tenant_id: str) -> list[dict]:
        return [
            {
                "task_id": task.id,
                "task_status": task.status.value,
                "step_id": entry.step_id,
                "action": entry.action,
                "status": entry.status,
                "attempt": entry.attempt,
                "last_error": entry.last_error,
                "next_retry_at": entry.next_retry_at,
                "reconciliation_status": entry.reconciliation_status,
            }
            for task in self.repository.list(tenant_id)
            for entry in task.ledger
            if entry.status in {"UNKNOWN", "RETRYABLE"} or entry.reconciliation_status == "REQUIRED"
        ]

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
        if task.plan is None:
            return False
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
        if task.plan is None:
            raise ValueError("task has no validated plan")
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

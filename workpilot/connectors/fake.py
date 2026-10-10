from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from workpilot.connectors.base import Capability, ensure_before_deadline
from workpilot.models import (
    ActionPreview,
    ActionRequest,
    ActionResult,
    Channel,
    RiskLevel,
    VerificationResult,
    VerificationStatus,
    utc_now,
)


@dataclass(slots=True)
class FakeEnterpriseState:
    updates: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"owner": "Alice", "project": "WorkPilot", "status": "API skeleton complete"},
            {"owner": "Bob", "project": "WorkPilot", "status": "Approval UX under review"},
        ]
    )
    documents: list[dict[str, str]] = field(
        default_factory=lambda: [
            {
                "id": "weekly-template",
                "tenant_id": "demo",
                "title": "项目周报模板",
                "content": "本周进展\n- {updates}\n\n风险与待办\n- {followups}",
            }
        ]
    )
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)
    sent_mail: dict[str, dict[str, Any]] = field(default_factory=dict)
    calendar_events: dict[str, dict[str, Any]] = field(default_factory=dict)
    executions: dict[str, ActionResult] = field(default_factory=dict)


class FakeEnterpriseAdapter:
    """Deterministic adapter used for local demos and contract tests."""

    def __init__(self, state: FakeEnterpriseState | None = None) -> None:
        self.state = state or FakeEnterpriseState()
        self.execution_count: dict[str, int] = {}

    def capabilities(self) -> list[Capability]:
        api = frozenset({Channel.API})
        return [
            Capability("project.search_updates", RiskLevel.R0, api),
            Capability("knowledge.search", RiskLevel.R0, api),
            Capability("report.compose", RiskLevel.R1, api),
            Capability("task.create", RiskLevel.R2, api),
            Capability("mail.send", RiskLevel.R2, api),
            Capability("calendar.create", RiskLevel.R2, api),
        ]

    async def preview(self, action: ActionRequest) -> ActionPreview:
        return ActionPreview(
            action=action.capability,
            human_summary=self._summary(action),
            parameters=action.parameters,
        )

    async def execute(self, action: ActionRequest, idempotency_key: str) -> ActionResult:
        ensure_before_deadline(action.deadline_at, utc_now())
        if idempotency_key in self.state.executions:
            cached = self.state.executions[idempotency_key]
            return cached.model_copy(update={"duplicate": True})

        self.execution_count[action.capability] = self.execution_count.get(action.capability, 0) + 1
        result = self._execute_once(action)
        self.state.executions[idempotency_key] = result
        return result

    async def lookup(self, action: ActionRequest, idempotency_key: str) -> ActionResult | None:
        del action
        return self.state.executions.get(idempotency_key)

    async def verify(self, action: ActionRequest, result: ActionResult) -> VerificationResult:
        if not result.success:
            return VerificationResult(
                status=VerificationStatus.FAILED,
                reason=result.error or "connector execution failed",
                retryable=False,
                confidence=1,
            )

        remote_id = result.remote_id
        evidence = [f"artifact://remote/{remote_id}"] if remote_id else []
        passed = False
        observed: dict[str, Any] = {}
        if action.capability == "project.search_updates":
            passed = bool(result.data.get("updates"))
            observed = {"count": len(result.data.get("updates", []))}
        elif action.capability == "knowledge.search":
            passed = bool(result.data.get("documents"))
            observed = {"count": len(result.data.get("documents", []))}
        elif action.capability == "report.compose":
            passed = bool(remote_id and remote_id in self.state.reports)
            observed = self.state.reports.get(remote_id or "", {})
        elif action.capability == "task.create":
            passed = bool(remote_id and remote_id in self.state.tasks)
            observed = self.state.tasks.get(remote_id or "", {})
        elif action.capability == "mail.send":
            passed = bool(remote_id and remote_id in self.state.sent_mail)
            observed = self.state.sent_mail.get(remote_id or "", {})
        elif action.capability == "calendar.create":
            passed = bool(remote_id and remote_id in self.state.calendar_events)
            observed = self.state.calendar_events.get(remote_id or "", {})

        return VerificationResult(
            status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
            evidence_refs=evidence,
            observed_state=observed,
            reason="remote state confirmed" if passed else "remote state not found",
            retryable=False,
            confidence=1,
        )

    def add_document(self, document: dict[str, str]) -> None:
        self.state.documents.append(document)

    def _execute_once(self, action: ActionRequest) -> ActionResult:
        params = action.parameters
        if action.capability == "project.search_updates":
            updates = [
                item
                for item in self.state.updates
                if item.get("tenant_id", "demo") == action.tenant_id
            ]
            return ActionResult(success=True, data={"updates": updates})
        if action.capability == "knowledge.search":
            query = str(params.get("query", "")).lower()
            matches = [
                item
                for item in self.state.documents
                if item.get("tenant_id") == action.tenant_id
                and (
                    not query
                    or query in item["title"].lower()
                    or query in item["content"].lower()
                    or "周报" in item["title"]
                )
            ]
            return ActionResult(success=True, data={"documents": matches})
        if action.capability == "report.compose":
            remote_id = f"report-{len(self.state.reports) + 1}"
            updates_text = "\n".join(
                f"{item['owner']}: {item['status']}" for item in self.state.updates
            )
            report = {
                "tenant_id": action.tenant_id,
                "title": params.get("title", "WorkPilot 项目周报"),
                "content": f"本周进展\n{updates_text}\n\n风险与待办\n- 跟进待确认事项",
                "sources": ["fake://project/updates", "fake://knowledge/weekly-template"],
            }
            self.state.reports[remote_id] = report
            return ActionResult(success=True, remote_id=remote_id, data=report, side_effect=True)
        if action.capability == "task.create":
            remote_id = f"task-{len(self.state.tasks) + 1}"
            self.state.tasks[remote_id] = {"tenant_id": action.tenant_id, **params}
            return ActionResult(
                success=True,
                remote_id=remote_id,
                data=self.state.tasks[remote_id],
                side_effect=True,
            )
        if action.capability == "mail.send":
            recipients = params.get("to")
            if not isinstance(recipients, list) or not recipients:
                return ActionResult(success=False, error="at least one recipient is required")
            remote_id = f"mail-{len(self.state.sent_mail) + 1}"
            self.state.sent_mail[remote_id] = {"tenant_id": action.tenant_id, **params}
            return ActionResult(
                success=True,
                remote_id=remote_id,
                data=self.state.sent_mail[remote_id],
                side_effect=True,
            )
        if action.capability == "calendar.create":
            remote_id = f"event-{len(self.state.calendar_events) + 1}"
            self.state.calendar_events[remote_id] = {"tenant_id": action.tenant_id, **params}
            return ActionResult(
                success=True,
                remote_id=remote_id,
                data=self.state.calendar_events[remote_id],
                side_effect=True,
            )
        return ActionResult(success=False, error=f"unsupported capability: {action.capability}")

    @staticmethod
    def _summary(action: ActionRequest) -> str:
        if action.capability == "mail.send":
            return f"向 {', '.join(action.parameters.get('to', []))} 发送邮件"
        if action.capability == "task.create":
            return f"创建任务：{action.parameters.get('title', '')}"
        if action.capability == "calendar.create":
            return f"创建日程：{action.parameters.get('title', '')}"
        return f"执行 {action.capability}"

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    PLAN_READY = "PLAN_READY"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    REPLANNING = "REPLANNING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    SUCCEEDED = "SUCCEEDED"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class VerificationStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


class Channel(StrEnum):
    API = "api"
    MCP = "mcp"
    BROWSER = "browser"


class VerificationRule(BaseModel):
    type: str
    rule: str


class PlanStep(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    description: str
    depends_on: list[str] = Field(default_factory=list)
    capability: str
    preferred_channel: Channel = Channel.API
    risk: RiskLevel = RiskLevel.R0
    requires_approval: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_effects: list[str] = Field(default_factory=list)
    verification: list[VerificationRule] = Field(default_factory=list)


class TaskPlan(BaseModel):
    goal: str
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[dict[str, str]] = Field(default_factory=list)
    steps: list[PlanStep]
    version: int = 1


class StepRun(BaseModel):
    step: PlanStep
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Approval(BaseModel):
    id: str
    tenant_id: str
    task_id: str
    step_id: str
    action_type: str
    parameter_preview: dict[str, Any]
    parameter_hash: str
    plan_version: int
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=utc_now)
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str | None = None


class ActionLedgerEntry(BaseModel):
    idempotency_key: str
    step_id: str
    action: str
    channel: Channel
    parameter_hash: str
    remote_id: str | None = None
    status: str
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class VerificationResult(BaseModel):
    status: VerificationStatus
    evidence_refs: list[str] = Field(default_factory=list)
    observed_state: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    retryable: bool = False
    confidence: float = Field(default=1.0, ge=0, le=1)


class Artifact(BaseModel):
    id: str
    tenant_id: str
    task_id: str
    step_id: str | None = None
    type: str
    content: dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


class TimelineEvent(BaseModel):
    sequence: int
    type: str
    message: str
    task_status: TaskStatus
    step_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Checkpoint(BaseModel):
    sequence: int
    task_status: TaskStatus
    plan_version: int
    completed_steps: list[str]
    ledger_keys: list[str]
    created_at: datetime = Field(default_factory=utc_now)


class TaskRun(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str
    tenant_id: str
    user_id: str
    goal: str
    status: TaskStatus = TaskStatus.CREATED
    plan: TaskPlan | None = None
    steps: dict[str, StepRun] = Field(default_factory=dict)
    approvals: list[Approval] = Field(default_factory=list)
    ledger: list[ActionLedgerEntry] = Field(default_factory=list)
    verifications: dict[str, VerificationResult] = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    paused_from: TaskStatus | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = 1


class ActionRequest(BaseModel):
    tenant_id: str
    task_id: str
    step_id: str
    capability: str
    parameters: dict[str, Any]
    channel: Channel


class ActionPreview(BaseModel):
    action: str
    human_summary: str
    parameters: dict[str, Any]


class ActionResult(BaseModel):
    success: bool
    remote_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    side_effect: bool = False
    duplicate: bool = False


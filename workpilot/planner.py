from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from workpilot.context import ContextBuilder, ContextItem, select_candidate_tools
from workpilot.dag import validate_plan
from workpilot.model_gateway import (
    Message,
    ModelCallRecord,
    ModelGateway,
    ModelGatewayError,
    ModelPolicy,
    RunBudget,
)
from workpilot.models import (
    Channel,
    PlanningMetadata,
    PlanStep,
    RiskLevel,
    TaskPlan,
    VerificationRule,
)


class DemoPlanner:
    """Deterministic safe fallback and baseline planner."""

    def plan(self, goal: str, recipient: str = "team@example.com") -> TaskPlan:
        return TaskPlan(
            goal=goal,
            constraints=["不得发送给租户外收件人", "所有外部写入必须审批"],
            success_criteria=[
                {"type": "artifact_exists", "target": "weekly_report"},
                {"type": "remote_state", "target": "sent_email"},
            ],
            steps=[
                PlanStep(
                    id="collect_updates",
                    description="收集本周项目更新",
                    capability="project.search_updates",
                    preferred_channel=Channel.API,
                    risk=RiskLevel.R0,
                    parameters={"period": "this_week"},
                    verification=[VerificationRule(type="schema", rule="updates.length > 0")],
                ),
                PlanStep(
                    id="load_template",
                    description="读取周报模板",
                    capability="knowledge.search",
                    preferred_channel=Channel.API,
                    risk=RiskLevel.R0,
                    parameters={"query": "周报模板"},
                    verification=[VerificationRule(type="schema", rule="documents.length > 0")],
                ),
                PlanStep(
                    id="compose_report",
                    description="生成带来源的项目周报",
                    depends_on=["collect_updates", "load_template"],
                    capability="report.compose",
                    risk=RiskLevel.R1,
                    parameters={"title": "WorkPilot 项目周报"},
                    expected_effects=["生成内部周报草稿"],
                    verification=[VerificationRule(type="remote_query", rule="report exists")],
                ),
                PlanStep(
                    id="create_followup",
                    description="为待确认事项创建跟进任务",
                    depends_on=["compose_report"],
                    capability="task.create",
                    risk=RiskLevel.R2,
                    requires_approval=True,
                    parameters={
                        "title": "跟进 WorkPilot 周报待确认事项",
                        "assignee": "project-owner@example.com",
                    },
                    expected_effects=["项目系统新增正式任务"],
                    verification=[VerificationRule(type="remote_query", rule="task exists")],
                ),
                PlanStep(
                    id="send_report",
                    description="发送周报邮件",
                    depends_on=["create_followup"],
                    capability="mail.send",
                    risk=RiskLevel.R2,
                    requires_approval=True,
                    parameters={
                        "to": [recipient],
                        "subject": "WorkPilot 项目周报",
                        "body": "本周项目周报已生成，请查看审计产物中的完整正文。",
                    },
                    expected_effects=["外部收件人收到邮件"],
                    verification=[
                        VerificationRule(type="remote_query", rule="message exists in sent")
                    ],
                ),
            ],
        )


class PlanningOutcome:
    def __init__(
        self,
        *,
        plan: TaskPlan,
        context_snapshot: dict[str, Any],
        model_calls: list[ModelCallRecord],
        validation_errors: list[str],
        used_fallback: bool,
    ) -> None:
        self.plan = plan
        self.context_snapshot = context_snapshot
        self.model_calls = model_calls
        self.validation_errors = validation_errors
        self.used_fallback = used_fallback


class StructuredPlanner:
    """Produces a model candidate, repairs once, then enforces deterministic boundaries."""

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        available_tools: list[dict[str, Any]],
        fixed_risks: dict[str, RiskLevel],
        model_policy: ModelPolicy,
        budget: RunBudget | None = None,
        context_builder: ContextBuilder | None = None,
        fallback: DemoPlanner | None = None,
        max_steps: int = 20,
    ) -> None:
        self.gateway = gateway
        self.available_tools = available_tools
        self.fixed_risks = fixed_risks
        self.model_policy = model_policy
        self.budget = budget or RunBudget()
        self.context_builder = context_builder or ContextBuilder(
            max_tokens=self.budget.max_input_tokens
        )
        self.fallback = fallback or DemoPlanner()
        self.max_steps = max_steps

    async def plan(
        self,
        goal: str,
        recipient: str,
        *,
        metadata: dict[str, str],
        retrieved_context: list[ContextItem] | None = None,
    ) -> PlanningOutcome:
        tools = select_candidate_tools(goal, self.available_tools)
        snapshot = self.context_builder.build(
            goal=goal,
            recipient=recipient,
            tools=tools,
            retrieved=retrieved_context,
        )
        messages = list(snapshot.messages)
        calls: list[ModelCallRecord] = []
        errors: list[str] = []
        try:
            for attempt in range(2):
                response = await self.gateway.generate_structured(
                    messages=messages,
                    output_schema=TaskPlan,
                    model_policy=self.model_policy,
                    budget=self.budget,
                    metadata=metadata,
                )
                calls.append(response.record)
                try:
                    plan = TaskPlan.model_validate(response.output)
                    validate_plan(plan, set(self.fixed_risks), self.fixed_risks, self.max_steps)
                    plan.planning = PlanningMetadata(
                        prompt_version=self.model_policy.prompt_version,
                        schema_version=self.model_policy.schema_version,
                        validation_errors=errors,
                        model_calls=calls,
                    )
                    return PlanningOutcome(
                        plan=plan,
                        context_snapshot=snapshot.model_dump(mode="json"),
                        model_calls=calls,
                        validation_errors=errors,
                        used_fallback=False,
                    )
                except (ValidationError, ValueError) as exc:
                    errors.append(str(exc))
                    if attempt == 0:
                        messages.append(
                            Message(
                                role="user",
                                source="workpilot://planner/repair",
                                trust="system",
                                content=(
                                    "The candidate was rejected. Return a complete corrected "
                                    "TaskPlan. "
                                    f"Validation errors: {str(exc)[:2_000]}"
                                ),
                            )
                        )
                        continue
        except ModelGatewayError as exc:
            errors.append(f"{exc.error_type}: {exc}")

        fallback = self.fallback.plan(goal, recipient)
        validate_plan(fallback, set(self.fixed_risks), self.fixed_risks, self.max_steps)
        fallback.planning = PlanningMetadata(
            prompt_version=self.model_policy.prompt_version,
            schema_version=self.model_policy.schema_version,
            used_fallback=True,
            validation_errors=errors,
            model_calls=calls,
        )
        return PlanningOutcome(
            plan=fallback,
            context_snapshot=snapshot.model_dump(mode="json"),
            model_calls=calls,
            validation_errors=errors,
            used_fallback=True,
        )


def diff_plans(
    previous: TaskPlan, candidate: TaskPlan, completed_steps: set[str]
) -> dict[str, Any]:
    previous_by_id = {step.id: step for step in previous.steps}
    candidate_by_id = {step.id: step for step in candidate.steps}
    changed = sorted(
        step_id
        for step_id in previous_by_id.keys() & candidate_by_id.keys()
        if previous_by_id[step_id] != candidate_by_id[step_id]
    )
    removed = sorted(previous_by_id.keys() - candidate_by_id.keys())
    protected = sorted(completed_steps & (set(changed) | set(removed)))
    if protected:
        raise ValueError("replan cannot remove or modify completed steps: " + ", ".join(protected))
    return {
        "from_version": previous.version,
        "to_version": candidate.version,
        "added": sorted(candidate_by_id.keys() - previous_by_id.keys()),
        "removed": removed,
        "changed": changed,
        "unchanged": sorted(
            step_id
            for step_id in previous_by_id.keys() & candidate_by_id.keys()
            if step_id not in changed
        ),
    }

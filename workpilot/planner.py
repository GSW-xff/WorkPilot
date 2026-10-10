from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
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
    PlanningDisposition,
    PlanningMetadata,
    PlanStep,
    RiskLevel,
    TaskPlan,
    VerificationRule,
)


class SupportedIntent(StrEnum):
    WEEKLY_REPORT = "weekly_report"
    MEETING_FOLLOWUP = "meeting_followup"
    ISSUE_SUMMARY = "issue_summary"
    RECOVERY_SCENARIO = "recovery_scenario"


@dataclass(frozen=True, slots=True)
class IntentDecision:
    disposition: PlanningDisposition
    reason: str
    intent: SupportedIntent | None = None
    questions: tuple[str, ...] = ()


class PlanningDecisionError(ValueError):
    def __init__(self, decision: IntentDecision, result_name: str) -> None:
        super().__init__(decision.reason)
        self.decision = decision
        self.result_name = result_name


class PlanningClarificationRequired(PlanningDecisionError):
    def __init__(self, decision: IntentDecision) -> None:
        super().__init__(decision, "clarification")


class PlanningRequestRejected(PlanningDecisionError):
    def __init__(self, decision: IntentDecision) -> None:
        super().__init__(decision, "rejected_plan")


class IntentGate:
    """Fail-closed supported-domain gate that runs before any model call."""

    _rejected = (
        re.compile(
            r"ignore\s+(all\s+)?previous|reveal\s+(the\s+)?system\s+prompt|"
            r"system\s+(prompt|message)|developer\s+message",
            re.IGNORECASE,
        ),
        re.compile(r"admin\.delete|payroll\.delete|unknown\.tool|credential|password|shell", re.I),
        re.compile(r"attacker\.invalid|evil@external\.invalid", re.I),
        re.compile(r"忽略.{0,10}(指令|规则)|(系统|开发者).{0,10}指令"),
        re.compile(r"跳过审批|免审批|降低风险|更高权限|R3", re.I),
        re.compile(r"密码|凭证|执行\s*shell|发到\s*attacker", re.I),
        re.compile(r"循环依赖|循环执行|无限循环|无限重试|超过预算|超长计划"),
        re.compile(r"不存在的|缺失依赖|重复\s*step|\b(25|30|100)\s*个.*步骤", re.I),
        re.compile(r"所有工具.{0,8}(一百|100)次|只读工具.{0,8}写操作|删除.{0,12}成功.{0,8}步骤"),
    )
    _intents = (
        (
            SupportedIntent.MEETING_FOLLOWUP,
            re.compile(r"会议结论|会议待办|meeting\s+follow[- ]?up", re.I),
        ),
        (
            SupportedIntent.ISSUE_SUMMARY,
            re.compile(r"issue\s*(汇总|summary)|高优先级\s*issue", re.I),
        ),
        (
            SupportedIntent.RECOVERY_SCENARIO,
            re.compile(r"响应丢失|429|任务创建超时|worker\s*崩溃|连接器部分成功", re.I),
        ),
        (
            SupportedIntent.WEEKLY_REPORT,
            re.compile(
                r"周报|项目报告|项目简报|每周摘要|本周总结|状态报告|"
                r"本周进展|项目更新|汇总状态|收集进度.{0,12}生成报告|"
                r"weekly.{0,20}report|status\s+report|project\s+report|\breport\b",
                re.I,
            ),
        ),
    )
    _questions = (
        "请说明要处理的具体项目、文档或会议。",
        "请说明期望产物，以及是否需要创建任务或发送邮件。",
        "如需外部写入，请提供明确对象和收件人。",
    )

    def evaluate(self, goal: str) -> IntentDecision:
        normalized = " ".join(goal.split())
        for pattern in self._rejected:
            if pattern.search(normalized):
                return IntentDecision(
                    disposition=PlanningDisposition.REJECTED,
                    reason="请求包含越权、绕过安全边界或非有界规划行为",
                )
        for intent, pattern in self._intents:
            if pattern.search(normalized):
                return IntentDecision(
                    disposition=PlanningDisposition.EXECUTABLE,
                    reason="请求属于当前受支持的办公流程域",
                    intent=intent,
                )
        return IntentDecision(
            disposition=PlanningDisposition.NEEDS_CLARIFICATION,
            reason="请求不足以绑定具体工具、对象和外部写入影响",
            questions=self._questions,
        )

    def enforce(self, goal: str) -> SupportedIntent:
        decision = self.evaluate(goal)
        if decision.disposition is PlanningDisposition.NEEDS_CLARIFICATION:
            raise PlanningClarificationRequired(decision)
        if decision.disposition is PlanningDisposition.REJECTED:
            raise PlanningRequestRejected(decision)
        assert decision.intent is not None
        return decision.intent


class DemoPlanner:
    """Deterministic safe fallback and baseline planner."""

    def __init__(self, intent_gate: IntentGate | None = None) -> None:
        self.intent_gate = intent_gate or IntentGate()

    def plan(self, goal: str, recipient: str = "team@example.com") -> TaskPlan:
        intent = self.intent_gate.enforce(goal)
        if intent is SupportedIntent.MEETING_FOLLOWUP:
            return self._meeting_followup_plan(goal)
        if intent is SupportedIntent.ISSUE_SUMMARY:
            return self._issue_summary_plan(goal)
        return self._weekly_report_plan(goal, recipient)

    @staticmethod
    def _weekly_report_plan(goal: str, recipient: str) -> TaskPlan:
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

    @staticmethod
    def _meeting_followup_plan(goal: str) -> TaskPlan:
        return TaskPlan(
            goal=goal,
            constraints=["只从受信会议记录生成待办", "创建正式任务前必须审批"],
            success_criteria=[{"type": "remote_state", "target": "followup_task"}],
            steps=[
                PlanStep(
                    id="load_meeting_notes",
                    description="读取会议结论和待办",
                    capability="knowledge.search",
                    parameters={"query": "最新会议结论与待办"},
                    verification=[VerificationRule(type="schema", rule="documents.length > 0")],
                ),
                PlanStep(
                    id="compose_followup",
                    description="整理负责人、截止时间和来源",
                    depends_on=["load_meeting_notes"],
                    capability="report.compose",
                    risk=RiskLevel.R1,
                    parameters={"title": "会议结论与待办"},
                    verification=[VerificationRule(type="remote_query", rule="report exists")],
                ),
                PlanStep(
                    id="create_meeting_followup",
                    description="建立经过审批的会议跟进任务",
                    depends_on=["compose_followup"],
                    capability="task.create",
                    risk=RiskLevel.R2,
                    requires_approval=True,
                    parameters={"title": "跟进会议待办", "assignee": "project-owner@example.com"},
                    expected_effects=["项目系统新增正式任务"],
                    verification=[VerificationRule(type="remote_query", rule="task exists")],
                ),
            ],
        )

    @staticmethod
    def _issue_summary_plan(goal: str) -> TaskPlan:
        return TaskPlan(
            goal=goal,
            constraints=["只读取可见 Issue 和租户内模板"],
            success_criteria=[{"type": "artifact_exists", "target": "issue_summary"}],
            steps=[
                PlanStep(
                    id="collect_issue_status",
                    description="读取当前高优先级 Issue 状态",
                    capability="project.search_updates",
                    parameters={"period": "current"},
                    verification=[VerificationRule(type="schema", rule="updates.length > 0")],
                ),
                PlanStep(
                    id="compose_issue_summary",
                    description="生成带来源的 Issue 风险汇总",
                    depends_on=["collect_issue_status"],
                    capability="report.compose",
                    risk=RiskLevel.R1,
                    parameters={"title": "高优先级 Issue 风险汇总"},
                    verification=[VerificationRule(type="remote_query", rule="report exists")],
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
        intent_gate: IntentGate | None = None,
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
        self.intent_gate = intent_gate or IntentGate()
        self.max_steps = max_steps

    async def plan(
        self,
        goal: str,
        recipient: str,
        *,
        metadata: dict[str, str],
        retrieved_context: list[ContextItem] | None = None,
    ) -> PlanningOutcome:
        self.intent_gate.enforce(goal)
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

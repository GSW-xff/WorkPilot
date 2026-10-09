from __future__ import annotations

from workpilot.models import Channel, PlanStep, RiskLevel, TaskPlan, VerificationRule


class DemoPlanner:
    """A deterministic first planner; replaceable by a structured-output model gateway."""

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
                        VerificationRule(
                            type="remote_query", rule="message exists in sent"
                        )
                    ],
                ),
            ],
        )

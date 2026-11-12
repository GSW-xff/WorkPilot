from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from workpilot.api import build_service
from workpilot.config import Settings
from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.dag import PlanValidationError, validate_plan
from workpilot.model_gateway import DeterministicModelGateway, ModelPolicy
from workpilot.models import (
    ImpactClass,
    PlanStep,
    RiskLevel,
    TaskPlan,
    TaskStatus,
    VerificationRule,
    impact_for_risk,
)
from workpilot.planner import DemoPlanner, StructuredPlanner
from workpilot.policy_profile import PolicyProfile, PolicyViolation, load_policy_profile
from workpilot.workflows.temporal import TaskWorkflow


class ImpactClassTest(unittest.TestCase):
    def test_risk_derives_impact(self) -> None:
        self.assertIs(ImpactClass.READ_ONLY, impact_for_risk(RiskLevel.R0))
        self.assertIs(ImpactClass.REVERSIBLE_WRITE, impact_for_risk(RiskLevel.R1))
        self.assertIs(ImpactClass.IRREVERSIBLE_WRITE, impact_for_risk(RiskLevel.R2))
        self.assertIs(ImpactClass.IRREVERSIBLE_WRITE, impact_for_risk(RiskLevel.R3))

    def test_registry_exposes_impact_per_capability(self) -> None:
        registry = CapabilityRegistry([FakeEnterpriseAdapter()])
        self.assertIs(ImpactClass.READ_ONLY, registry.impact_for("knowledge.search"))
        self.assertIs(ImpactClass.REVERSIBLE_WRITE, registry.impact_for("report.compose"))
        self.assertIs(
            ImpactClass.IRREVERSIBLE_WRITE, registry.impact_for("mail.send")
        )
        tools = {item["name"]: item for item in registry.planning_tools()}
        self.assertEqual("irreversible_write", tools["mail.send"]["impact"])


class PolicyProfileTest(unittest.TestCase):
    def test_default_policy_passes_hard_limits(self) -> None:
        profile = PolicyProfile().validate_hard_limits()
        self.assertTrue(profile.requires_approval(ImpactClass.IRREVERSIBLE_WRITE))
        self.assertFalse(profile.requires_approval(ImpactClass.READ_ONLY))

    def test_cannot_waive_mandatory_approval(self) -> None:
        with self.assertRaises(PolicyViolation):
            PolicyProfile(require_approval_for=[]).validate_hard_limits()
        with self.assertRaises(PolicyViolation):
            PolicyProfile(
                require_approval_for=[ImpactClass.REVERSIBLE_WRITE]
            ).validate_hard_limits()

    def test_rejects_wildcard_recipient_domain(self) -> None:
        with self.assertRaises(PolicyViolation):
            PolicyProfile(allowed_recipient_domains=["*"]).validate_hard_limits()
        with self.assertRaises(PolicyViolation):
            PolicyProfile(allowed_recipient_domains=[]).validate_hard_limits()

    def test_rejects_step_budget_beyond_hard_limit(self) -> None:
        with self.assertRaises(PolicyViolation):
            PolicyProfile(max_steps=500).validate_hard_limits()

    def test_rejects_lease_out_of_range(self) -> None:
        with self.assertRaises(PolicyViolation):
            PolicyProfile(lease_seconds=1).validate_hard_limits()

    def test_risk_floor_only_raises_never_lowers(self) -> None:
        registry = CapabilityRegistry(
            [FakeEnterpriseAdapter()], risk_floor={"knowledge.search": RiskLevel.R2}
        )
        self.assertIs(RiskLevel.R2, registry.risks["knowledge.search"])
        # 声明的底线上限低于注册表时，max_risk 保留注册表等级，不会放松
        lowered = CapabilityRegistry(
            [FakeEnterpriseAdapter()], risk_floor={"mail.send": RiskLevel.R0}
        )
        self.assertIs(RiskLevel.R2, lowered.risks["mail.send"])

    def test_denied_capability_is_not_registered(self) -> None:
        registry = CapabilityRegistry(
            [FakeEnterpriseAdapter()], denied={"mail.send"}
        )
        self.assertNotIn("mail.send", registry.names)

    def test_unknown_capability_in_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            CapabilityRegistry(
                [FakeEnterpriseAdapter()], risk_floor={"ghost.tool": RiskLevel.R2}
            )

    def test_policy_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(
                json.dumps(
                    {
                        "max_steps": 12,
                        "lease_seconds": 20,
                        "allowed_recipient_domains": ["example.com", "corp.example.com"],
                        "require_approval_for": [
                            "irreversible_write",
                            "reversible_write",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            profile = load_policy_profile(path)
        self.assertEqual(12, profile.max_steps)
        self.assertEqual(20.0, profile.lease_seconds)
        self.assertIn("corp.example.com", profile.allowed_domains)
        self.assertTrue(profile.requires_approval(ImpactClass.REVERSIBLE_WRITE))

    def test_shipped_policy_file_is_valid(self) -> None:
        profile = load_policy_profile(
            Path(__file__).resolve().parents[1] / "config" / "policy.json"
        )
        self.assertEqual("policy-v1", profile.version)
        self.assertTrue(profile.requires_approval(ImpactClass.IRREVERSIBLE_WRITE))


class PlanValidationImpactTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = CapabilityRegistry([FakeEnterpriseAdapter()])

    def _validate(self, step: PlanStep) -> list[str]:
        return validate_plan(
            TaskPlan(goal="impact check", steps=[step]),
            self.registry.names,
            self.registry.risks,
            20,
        )

    def test_declared_impact_below_derived_value_is_rejected(self) -> None:
        step = PlanStep(
            id="send_mail",
            description="send",
            capability="mail.send",
            risk=RiskLevel.R2,
            impact=ImpactClass.READ_ONLY,
            requires_approval=True,
            verification=[VerificationRule(type="remote_state", rule="mail exists")],
        )
        with self.assertRaises(PlanValidationError) as ctx:
            self._validate(step)
        self.assertIn("impact", str(ctx.exception))

    def test_irreversible_write_requires_approval_even_at_r1(self) -> None:
        step = PlanStep(
            id="compose_report",
            description="compose",
            capability="report.compose",
            risk=RiskLevel.R1,
            impact=ImpactClass.IRREVERSIBLE_WRITE,
            requires_approval=False,
            verification=[VerificationRule(type="artifact", rule="report exists")],
        )
        with self.assertRaises(PlanValidationError) as ctx:
            self._validate(step)
        self.assertIn("irreversible write must require approval", str(ctx.exception))

    def test_escalated_impact_with_approval_is_accepted(self) -> None:
        step = PlanStep(
            id="compose_report",
            description="compose",
            capability="report.compose",
            risk=RiskLevel.R1,
            impact=ImpactClass.IRREVERSIBLE_WRITE,
            requires_approval=True,
            verification=[VerificationRule(type="artifact", rule="report exists")],
        )
        self.assertEqual(["compose_report"], self._validate(step))


class ReplanFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_validation_failure_replans_and_succeeds(self) -> None:
        service, _ = build_service(settings=Settings(planner_mode="fake"))
        registry = service.registry
        valid = DemoPlanner().plan(
            "prepare weekly report", "team@example.com"
        ).model_dump(mode="json")
        gateway = DeterministicModelGateway(
            responses=[
                {"goal": "bad", "steps": []},
                {"goal": "still bad", "steps": []},
                valid,
            ]
        )
        service.planner = StructuredPlanner(
            gateway,
            available_tools=registry.planning_tools(),
            fixed_risks=registry.risks,
            model_policy=ModelPolicy(provider="fake", model="deterministic"),
        )

        task = await service.create_task_async(
            "demo", "user", "prepare weekly report", "team@example.com"
        )

        self.assertEqual(TaskStatus.PLAN_READY, task.status)
        types = [event.type for event in task.events]
        self.assertIn("plan.replan_requested", types)
        self.assertIn("plan.replanned", types)
        self.assertNotIn("plan.replan_failed", types)
        self.assertFalse(task.plan.planning.used_fallback)
        self.assertEqual(3, len(gateway.calls))

    async def test_replan_exhausted_falls_back_and_records_it(self) -> None:
        service, _ = build_service(settings=Settings(planner_mode="fake"))
        registry = service.registry
        gateway = DeterministicModelGateway(
            responses=[
                {"goal": "bad", "steps": []},
                {"goal": "still bad", "steps": []},
                {"goal": "replan bad", "steps": []},
            ]
        )
        service.planner = StructuredPlanner(
            gateway,
            available_tools=registry.planning_tools(),
            fixed_risks=registry.risks,
            model_policy=ModelPolicy(provider="fake", model="deterministic"),
        )

        task = await service.create_task_async(
            "demo", "user", "prepare weekly report", "team@example.com"
        )

        self.assertEqual(TaskStatus.PLAN_READY, task.status)
        types = [event.type for event in task.events]
        self.assertIn("plan.replan_requested", types)
        self.assertIn("plan.replan_failed", types)
        self.assertTrue(task.plan.planning.used_fallback)
        self.assertEqual(5, len(task.plan.steps))


class WorkflowApprovalChannelTest(unittest.TestCase):
    def test_approval_exposes_update_and_signal_channels(self) -> None:
        self.assertTrue(hasattr(TaskWorkflow.decide_approval, "_defn"))
        self.assertTrue(
            hasattr(TaskWorkflow.submit_approval, "__temporal_signal_definition")
        )
        self.assertTrue(
            hasattr(TaskWorkflow.last_approval_error, "__temporal_query_definition")
        )

    def test_controls_are_signals(self) -> None:
        for name in ("pause", "resume", "cancel"):
            self.assertTrue(
                hasattr(getattr(TaskWorkflow, name), "__temporal_signal_definition"),
                name,
            )

import unittest

from workpilot.dag import PlanValidationError, max_risk, topological_order, validate_plan
from workpilot.models import PlanStep, RiskLevel, TaskPlan, VerificationRule


class DagValidationTest(unittest.TestCase):
    def test_topological_order_respects_dependencies(self) -> None:
        steps = [
            PlanStep(id="publish", description="publish", capability="mail.send", depends_on=["draft"]),
            PlanStep(id="draft", description="draft", capability="report.compose"),
        ]
        self.assertEqual(["draft", "publish"], topological_order(steps))

    def test_cycle_is_rejected(self) -> None:
        steps = [
            PlanStep(id="first", description="first", capability="read", depends_on=["second"]),
            PlanStep(id="second", description="second", capability="read", depends_on=["first"]),
        ]
        with self.assertRaisesRegex(PlanValidationError, "acyclic"):
            topological_order(steps)

    def test_missing_dependency_is_rejected(self) -> None:
        step = PlanStep(id="first", description="first", capability="read", depends_on=["absent"])
        with self.assertRaisesRegex(PlanValidationError, "missing dependencies"):
            topological_order([step])

    def test_risk_cannot_be_lowered_and_r2_requires_approval(self) -> None:
        plan = TaskPlan(
            goal="send",
            steps=[
                PlanStep(
                    id="send_mail",
                    description="send",
                    capability="mail.send",
                    risk=RiskLevel.R0,
                    verification=[VerificationRule(type="remote_query", rule="exists")],
                )
            ],
        )
        with self.assertRaises(PlanValidationError) as caught:
            validate_plan(plan, {"mail.send"}, {"mail.send": RiskLevel.R2})
        message = str(caught.exception)
        self.assertIn("cannot be lower", message)
        self.assertIn("must require approval", message)

    def test_r3_is_forbidden(self) -> None:
        plan = TaskPlan(
            goal="delete",
            steps=[
                PlanStep(
                    id="delete_data",
                    description="delete",
                    capability="data.delete",
                    risk=RiskLevel.R3,
                    requires_approval=True,
                    verification=[VerificationRule(type="remote_query", rule="gone")],
                )
            ],
        )
        with self.assertRaisesRegex(PlanValidationError, "forbidden"):
            validate_plan(plan, {"data.delete"}, {"data.delete": RiskLevel.R3})

    def test_max_risk_always_selects_highest(self) -> None:
        self.assertEqual(RiskLevel.R2, max_risk(RiskLevel.R0, RiskLevel.R2, RiskLevel.R1))


if __name__ == "__main__":
    unittest.main()


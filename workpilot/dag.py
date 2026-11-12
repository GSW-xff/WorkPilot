from __future__ import annotations

from dataclasses import dataclass

from workpilot.models import (
    ImpactClass,
    PlanStep,
    RiskLevel,
    TaskPlan,
    impact_for_risk,
    impact_value,
)
from workpilot.models import max_risk as _max_risk
from workpilot.models import risk_value as _risk_value


@dataclass(slots=True)
class PlanValidationError(ValueError):
    errors: list[str]

    def __str__(self) -> str:
        return "; ".join(self.errors)


def topological_order(steps: list[PlanStep]) -> list[str]:
    by_id = {step.id: step for step in steps}
    if len(by_id) != len(steps):
        raise PlanValidationError(["step ids must be unique"])

    missing = sorted(
        {dependency for step in steps for dependency in step.depends_on if dependency not in by_id}
    )
    if missing:
        raise PlanValidationError([f"missing dependencies: {', '.join(missing)}"])

    indegree = {step.id: len(set(step.depends_on)) for step in steps}
    children: dict[str, list[str]] = {step.id: [] for step in steps}
    for step in steps:
        for dependency in set(step.depends_on):
            children[dependency].append(step.id)

    ready = sorted(step_id for step_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for child in sorted(children[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    if len(ordered) != len(steps):
        raise PlanValidationError(["task plan must be acyclic"])
    return ordered


def validate_plan(
    plan: TaskPlan,
    available_capabilities: set[str],
    fixed_risks: dict[str, RiskLevel],
    max_steps: int = 20,
) -> list[str]:
    errors: list[str] = []
    if not plan.steps:
        errors.append("plan must contain at least one step")
    if len(plan.steps) > max_steps:
        errors.append(f"plan exceeds maximum of {max_steps} steps")

    try:
        order = topological_order(plan.steps)
    except PlanValidationError as exc:
        errors.extend(exc.errors)
        order = []

    for step in plan.steps:
        if step.capability not in available_capabilities:
            errors.append(f"unknown capability for {step.id}: {step.capability}")
            continue
        fixed = fixed_risks[step.capability]
        if risk_value(step.risk) < risk_value(fixed):
            errors.append(f"risk for {step.id} cannot be lower than {fixed.value}")
        effective = max_risk(step.risk, fixed)
        if effective is RiskLevel.R3:
            errors.append(f"R3 action is forbidden in MVP: {step.id}")

        # 影响面与风险正交，但同样只能往严的方向声明：低于推导值即视为降级。
        floor_impact = impact_for_risk(effective)
        declared = step.impact or floor_impact
        if impact_value(declared) < impact_value(floor_impact):
            errors.append(
                f"impact for {step.id} cannot be lower than {floor_impact.value}"
            )
        effective_impact = max((declared, floor_impact), key=impact_value)
        if effective_impact is ImpactClass.IRREVERSIBLE_WRITE and not step.requires_approval:
            errors.append(
                f"irreversible write must require approval: {step.id}"
            )

        if effective is RiskLevel.R2 and not step.requires_approval:
            errors.append(f"R2 step must require approval: {step.id}")
        if effective in {RiskLevel.R1, RiskLevel.R2} and not step.verification:
            errors.append(f"side-effecting step must define verification: {step.id}")

    if errors:
        raise PlanValidationError(errors)
    return order


def risk_value(risk: RiskLevel) -> int:  # re-exported for callers importing from dag
    return _risk_value(risk)


def max_risk(*risks: RiskLevel) -> RiskLevel:
    return _max_risk(*risks)

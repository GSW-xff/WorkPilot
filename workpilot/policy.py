from __future__ import annotations

from dataclasses import dataclass

from workpilot.dag import max_risk
from workpilot.models import (
    Channel,
    ImpactClass,
    PlanStep,
    RiskLevel,
    impact_for_risk,
    max_impact,
)
from workpilot.policy_profile import PolicyProfile, default_policy


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    effective_risk: RiskLevel
    effective_impact: ImpactClass
    requires_approval: bool
    channel: Channel
    reason: str


class PolicyEngine:
    def __init__(self, policy: PolicyProfile | None = None) -> None:
        self.policy = policy or default_policy()

    def evaluate(
        self,
        step: PlanStep,
        fixed_risk: RiskLevel,
        routed_channel: Channel,
        capability_impact: ImpactClass | None = None,
    ) -> PolicyDecision:
        effective = max_risk(step.risk, fixed_risk)
        floor = impact_for_risk(effective)
        impact = max_impact(
            step.impact or floor,
            capability_impact or floor,
            floor,
        )
        if effective is RiskLevel.R3:
            return PolicyDecision(
                allowed=False,
                effective_risk=effective,
                effective_impact=impact,
                requires_approval=True,
                channel=routed_channel,
                reason="R3 actions are forbidden in the MVP",
            )
        requires_approval = (
            effective is RiskLevel.R2
            or step.requires_approval
            or self.policy.requires_approval(impact)
        )
        approval = "required" if requires_approval else "not required"
        return PolicyDecision(
            allowed=True,
            effective_risk=effective,
            effective_impact=impact,
            requires_approval=requires_approval,
            channel=routed_channel,
            reason=(
                f"allowed by policy {self.policy.version}; "
                f"impact={impact.value}; approval={approval}"
            ),
        )

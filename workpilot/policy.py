from __future__ import annotations

from dataclasses import dataclass

from workpilot.dag import max_risk
from workpilot.models import Channel, PlanStep, RiskLevel


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    effective_risk: RiskLevel
    requires_approval: bool
    channel: Channel
    reason: str


class PolicyEngine:
    def evaluate(
        self,
        step: PlanStep,
        fixed_risk: RiskLevel,
        routed_channel: Channel,
    ) -> PolicyDecision:
        effective = max_risk(step.risk, fixed_risk)
        if effective is RiskLevel.R3:
            return PolicyDecision(
                allowed=False,
                effective_risk=effective,
                requires_approval=True,
                channel=routed_channel,
                reason="R3 actions are forbidden in the MVP",
            )
        requires_approval = effective is RiskLevel.R2 or step.requires_approval
        return PolicyDecision(
            allowed=True,
            effective_risk=effective,
            requires_approval=requires_approval,
            channel=routed_channel,
            reason="allowed by deterministic MVP policy",
        )


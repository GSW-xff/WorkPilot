"""可配置的能力边界策略。

策略文件决定"哪些动作需要人工确认、哪些能力被禁用、单任务允许多少步"，
但在加载时会被强制校验：只能比系统硬底线更严，不能更松。
这样"能力边界可配置"成立，同时"被监管者不能自己放松规则"也成立。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from workpilot.models import ImpactClass, RiskLevel

# 系统硬底线：配置再怎么写也不能越过这些值。
HARD_MAX_STEPS = 50
HARD_MIN_LEASE_SECONDS = 3.0
HARD_MAX_LEASE_SECONDS = 300.0
MANDATORY_APPROVAL_IMPACTS: frozenset[ImpactClass] = frozenset(
    {ImpactClass.IRREVERSIBLE_WRITE}
)


class PolicyViolation(ValueError):
    """策略文件试图放松系统硬底线。"""


class PolicyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "policy-v1"
    max_steps: int = 20
    lease_seconds: float = 15.0
    allowed_recipient_domains: list[str] = Field(
        default_factory=lambda: ["example.com"]
    )
    # 只能把风险等级往上抬；低于注册表声明值时会被 max_risk 忽略，不会放松
    risk_floor: dict[str, RiskLevel] = Field(default_factory=dict)
    denied_capabilities: list[str] = Field(default_factory=list)
    # 哪些影响面必须先人工确认。IRREVERSIBLE_WRITE 是不可移除的硬底线。
    require_approval_for: list[ImpactClass] = Field(
        default_factory=lambda: [ImpactClass.IRREVERSIBLE_WRITE]
    )

    @property
    def allowed_domains(self) -> set[str]:
        return {domain.strip().lower() for domain in self.allowed_recipient_domains}

    @property
    def approval_impacts(self) -> frozenset[ImpactClass]:
        return frozenset(self.require_approval_for)

    def requires_approval(self, impact: ImpactClass) -> bool:
        return impact in self.approval_impacts

    def validate_hard_limits(self) -> PolicyProfile:
        if not 1 <= self.max_steps <= HARD_MAX_STEPS:
            raise PolicyViolation(
                f"max_steps must be within 1..{HARD_MAX_STEPS}, got {self.max_steps}"
            )
        if not HARD_MIN_LEASE_SECONDS <= self.lease_seconds <= HARD_MAX_LEASE_SECONDS:
            raise PolicyViolation(
                "lease_seconds must be within "
                f"{HARD_MIN_LEASE_SECONDS}..{HARD_MAX_LEASE_SECONDS}, "
                f"got {self.lease_seconds}"
            )
        if not self.allowed_recipient_domains:
            raise PolicyViolation("allowed_recipient_domains must not be empty")
        for domain in self.allowed_recipient_domains:
            cleaned = domain.strip().lower()
            if not cleaned or "*" in cleaned:
                raise PolicyViolation(
                    "allowed_recipient_domains must list explicit domains, "
                    f"wildcards are forbidden: {domain!r}"
                )
        if "" in {item.strip() for item in self.denied_capabilities}:
            raise PolicyViolation("denied_capabilities contains an empty entry")
        missing = MANDATORY_APPROVAL_IMPACTS - self.approval_impacts
        if missing:
            raise PolicyViolation(
                "policy cannot waive mandatory approval for "
                + ", ".join(sorted(item.value for item in missing))
            )
        return self


def default_policy() -> PolicyProfile:
    return PolicyProfile().validate_hard_limits()


def load_policy_profile(path: str | Path | None) -> PolicyProfile:
    if path is None:
        return default_policy()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return PolicyProfile.model_validate(raw).validate_hard_limits()

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from workpilot.models import (
    ActionPreview,
    ActionRequest,
    ActionResult,
    Channel,
    ImpactClass,
    RiskLevel,
    VerificationResult,
    impact_for_risk,
    max_risk,
)


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    risk: RiskLevel
    channels: frozenset[Channel]
    impact: ImpactClass | None = None

    @property
    def effective_impact(self) -> ImpactClass:
        """声明的影响面；未声明时按风险等级推导。"""

        return self.impact or impact_for_risk(self.risk)


class ToolAdapter(Protocol):
    def capabilities(self) -> list[Capability]: ...

    async def preview(self, action: ActionRequest) -> ActionPreview: ...

    async def execute(self, action: ActionRequest, idempotency_key: str) -> ActionResult: ...

    async def lookup(self, action: ActionRequest, idempotency_key: str) -> ActionResult | None: ...

    async def verify(self, action: ActionRequest, result: ActionResult) -> VerificationResult: ...


class ConnectorError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


class ConnectorDeadlineExceeded(ConnectorError):
    def __init__(self, message: str = "connector deadline exceeded") -> None:
        super().__init__(message, retryable=True, outcome_unknown=True)


class ConnectorRateLimited(ConnectorError):
    def __init__(self, message: str = "connector rate limited") -> None:
        super().__init__(message, retryable=True)


class ConnectorRejected(ConnectorError):
    def __init__(self, message: str) -> None:
        super().__init__(message, retryable=False)


def ensure_before_deadline(deadline_at: datetime | None, now: datetime) -> None:
    if deadline_at is not None and now >= deadline_at:
        raise ConnectorDeadlineExceeded()


class CapabilityRegistry:
    def __init__(
        self,
        adapters: list[ToolAdapter],
        *,
        risk_floor: dict[str, RiskLevel] | None = None,
        denied: frozenset[str] | set[str] = frozenset(),
    ) -> None:
        """risk_floor 只能把等级往上抬，不能往下压；denied 直接不注册。"""

        self._by_capability: dict[str, ToolAdapter] = {}
        self._metadata: dict[str, Capability] = {}
        floors = risk_floor or {}
        unknown_floors = set(floors) - {
            capability.name for adapter in adapters for capability in adapter.capabilities()
        }
        if unknown_floors:
            raise ValueError(
                "policy references unknown capabilities: " + ", ".join(sorted(unknown_floors))
            )
        for adapter in adapters:
            for capability in adapter.capabilities():
                if capability.name in self._by_capability:
                    raise ValueError(f"duplicate capability: {capability.name}")
                if capability.name in denied:
                    continue
                floor = floors.get(capability.name)
                risk = capability.risk if floor is None else max_risk(capability.risk, floor)
                self._by_capability[capability.name] = adapter
                self._metadata[capability.name] = Capability(
                    name=capability.name,
                    risk=risk,
                    channels=capability.channels,
                    impact=capability.effective_impact,
                )

    @property
    def names(self) -> set[str]:
        return set(self._by_capability)

    @property
    def risks(self) -> dict[str, RiskLevel]:
        return {name: item.risk for name, item in self._metadata.items()}

    @property
    def impacts(self) -> dict[str, ImpactClass]:
        return {name: item.effective_impact for name, item in self._metadata.items()}

    def impact_for(self, capability: str) -> ImpactClass:
        return self._metadata[capability].effective_impact

    def planning_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": name,
                "risk": metadata.risk.value,
                "impact": metadata.effective_impact.value,
                "channels": sorted(channel.value for channel in metadata.channels),
                "parameters": {},
            }
            for name, metadata in sorted(self._metadata.items())
        ]

    def adapter_for(self, capability: str) -> ToolAdapter:
        try:
            return self._by_capability[capability]
        except KeyError as exc:
            raise ValueError(f"capability is unavailable: {capability}") from exc

    def channel_for(self, capability: str, preferred: Channel) -> Channel:
        metadata = self._metadata[capability]
        if preferred in metadata.channels:
            return preferred
        if Channel.API in metadata.channels:
            return Channel.API
        return sorted(metadata.channels, key=lambda item: item.value)[0]

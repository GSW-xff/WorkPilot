from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from workpilot.models import (
    ActionPreview,
    ActionRequest,
    ActionResult,
    Channel,
    RiskLevel,
    VerificationResult,
)


@dataclass(frozen=True, slots=True)
class Capability:
    name: str
    risk: RiskLevel
    channels: frozenset[Channel]


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
    def __init__(self, adapters: list[ToolAdapter]) -> None:
        self._by_capability: dict[str, ToolAdapter] = {}
        self._metadata: dict[str, Capability] = {}
        for adapter in adapters:
            for capability in adapter.capabilities():
                if capability.name in self._by_capability:
                    raise ValueError(f"duplicate capability: {capability.name}")
                self._by_capability[capability.name] = adapter
                self._metadata[capability.name] = capability

    @property
    def names(self) -> set[str]:
        return set(self._by_capability)

    @property
    def risks(self) -> dict[str, RiskLevel]:
        return {name: item.risk for name, item in self._metadata.items()}

    def planning_tools(self) -> list[dict[str, object]]:
        return [
            {
                "name": name,
                "risk": metadata.risk.value,
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

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from workpilot.db.repository import SQLAlchemyTaskRepository
from workpilot.telemetry import TELEMETRY


@dataclass(slots=True)
class RelayResult:
    published: int = 0
    failed: int = 0


class OutboxRelay:
    """At-least-once relay; downstream consumers must deduplicate by event id."""

    def __init__(
        self,
        repository: SQLAlchemyTaskRepository,
        publisher: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        self.repository = repository
        self.publisher = publisher
        self.attempts: dict[int, int] = {}
        self.dead_letters: dict[int, dict[str, object]] = {}

    async def publish_batch(self, tenant_id: str, limit: int = 100) -> RelayResult:
        events = self.repository.pending_outbox(tenant_id, limit)
        result = RelayResult()
        published_ids: list[int] = []
        now = datetime.now(UTC)
        for event in events:
            raw_event_id = event["id"]
            if not isinstance(raw_event_id, (int, str)):
                raise TypeError("outbox event id must be an integer")
            event_id = int(raw_event_id)
            try:
                await self.publisher(dict(event))
            except Exception as exc:
                result.failed += 1
                self.attempts[event_id] = self.attempts.get(event_id, 0) + 1
                if self.attempts[event_id] >= 5:
                    self.dead_letters[event_id] = {
                        **event,
                        "error_type": type(exc).__name__,
                        "failed_at": now.isoformat(),
                    }
                continue
            published_ids.append(event_id)
            result.published += 1
            self.attempts.pop(event_id, None)
        self.repository.mark_outbox_published(tenant_id, published_ids)
        TELEMETRY.metrics.counter("outbox_publish_total", result.published)
        TELEMETRY.metrics.counter("outbox_publish_error_total", result.failed)
        TELEMETRY.metrics.observe("outbox_pending_count", float(len(events)))
        return result


class DeduplicatingConsumer:
    def __init__(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self.handler = handler
        self.processed: set[int] = set()

    async def consume(self, event: dict[str, Any]) -> bool:
        event_id = int(event["id"])
        if event_id in self.processed:
            return False
        await self.handler(event)
        self.processed.add(event_id)
        return True

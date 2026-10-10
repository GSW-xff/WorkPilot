from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str | None = None
    auto_create_schema: bool = False
    max_steps: int = 20
    allowed_recipient_domains: frozenset[str] = frozenset({"example.com"})
    temporal_target: str | None = None
    temporal_task_queue: str = "workpilot-tasks"

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.getenv("WORKPILOT_DATABASE_URL") or None
        domains = frozenset(
            item.strip().lower()
            for item in os.getenv("WORKPILOT_ALLOWED_RECIPIENT_DOMAINS", "example.com").split(",")
            if item.strip()
        )
        return cls(
            host=os.getenv("WORKPILOT_HOST", "127.0.0.1"),
            port=int(os.getenv("WORKPILOT_PORT", "8000")),
            database_url=database_url,
            auto_create_schema=_as_bool(
                os.getenv("WORKPILOT_AUTO_CREATE_SCHEMA"), default=False
            ),
            max_steps=int(os.getenv("WORKPILOT_MAX_STEPS", "20")),
            allowed_recipient_domains=domains or frozenset({"example.com"}),
            temporal_target=os.getenv("WORKPILOT_TEMPORAL_TARGET") or None,
            temporal_task_queue=os.getenv(
                "WORKPILOT_TEMPORAL_TASK_QUEUE", "workpilot-tasks"
            ),
        )

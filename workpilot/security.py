from __future__ import annotations

import hashlib
import json
import re
from typing import Any

SECRET_KEYS = {"authorization", "credential", "password", "secret", "token"}
SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._~-]+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parameter_hash(parameters: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(parameters).encode("utf-8")).hexdigest()


def idempotency_key(
    tenant_id: str,
    task_id: str,
    step_id: str,
    action_type: str,
    parameters: dict[str, Any],
) -> str:
    material = "\x1f".join([tenant_id, task_id, step_id, action_type, canonical_json(parameters)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SECRET_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
    return value

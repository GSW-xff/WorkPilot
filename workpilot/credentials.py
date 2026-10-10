from __future__ import annotations

from threading import RLock
from typing import Protocol
from uuid import uuid4


class SecretNotFoundError(KeyError):
    pass


class SecretStore(Protocol):
    def put(self, tenant_id: str, value: str) -> str: ...

    def get(self, tenant_id: str, reference: str) -> str: ...

    def delete(self, tenant_id: str, reference: str) -> None: ...


class InMemorySecretStore:
    """Development-only secret boundary; domain objects persist references, never values."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    def put(self, tenant_id: str, value: str) -> str:
        reference = f"secret://github/{uuid4().hex}"
        with self._lock:
            self._values[(tenant_id, reference)] = value
        return reference

    def get(self, tenant_id: str, reference: str) -> str:
        with self._lock:
            try:
                return self._values[(tenant_id, reference)]
            except KeyError as exc:
                raise SecretNotFoundError(reference) from exc

    def delete(self, tenant_id: str, reference: str) -> None:
        with self._lock:
            try:
                del self._values[(tenant_id, reference)]
            except KeyError as exc:
                raise SecretNotFoundError(reference) from exc

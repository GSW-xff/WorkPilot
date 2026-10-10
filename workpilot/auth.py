from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt


class AuthenticationError(ValueError):
    """Raised when an identity token cannot be trusted."""


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles or "admin" in self.roles


class OIDCVerifier:
    """Small, fail-closed OIDC verifier with a bounded JWKS cache."""

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        jwks_url: str,
        client: httpx.AsyncClient | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self.jwks_url = jwks_url
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        self._owns_client = client is None
        self._cache_ttl_seconds = cache_ttl_seconds
        self._keys: dict[str, Any] = {}
        self._cache_expires_at = 0.0

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise AuthenticationError("malformed bearer token") from exc
        algorithm = header.get("alg")
        key_id = header.get("kid")
        if algorithm not in {"RS256", "ES256"} or not isinstance(key_id, str):
            raise AuthenticationError("token algorithm or key id is not allowed")
        key = await self._key(key_id)
        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=[algorithm],
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub", "tenant_id"],
                    "verify_signature": True,
                },
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("bearer token validation failed") from exc

        subject = claims.get("sub")
        tenant_id = claims.get("tenant_id")
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(tenant_id, str)
            or not tenant_id
        ):
            raise AuthenticationError("token identity claims are invalid")
        return Principal(
            subject=subject,
            tenant_id=tenant_id,
            roles=_string_set(claims.get("roles")),
            scopes=_string_set(claims.get("scope")),
        )

    async def _key(self, key_id: str):
        now = time.monotonic()
        if now >= self._cache_expires_at or key_id not in self._keys:
            await self._refresh_keys()
        try:
            return self._keys[key_id]
        except KeyError as exc:
            raise AuthenticationError("token signing key is unknown") from exc

    async def _refresh_keys(self) -> None:
        try:
            response = await self._client.get(self.jwks_url)
            response.raise_for_status()
            payload = response.json()
            keys = payload["keys"]
            parsed = {
                item["kid"]: jwt.PyJWK.from_dict(item).key
                for item in keys
                if isinstance(item, dict) and isinstance(item.get("kid"), str)
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, jwt.PyJWTError) as exc:
            raise AuthenticationError("OIDC signing keys are unavailable") from exc
        if not parsed:
            raise AuthenticationError("OIDC signing key set is empty")
        self._keys = parsed
        self._cache_expires_at = time.monotonic() + self._cache_ttl_seconds


def _string_set(value: object) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset(item for item in value.split() if item)
    if isinstance(value, list):
        return frozenset(item for item in value if isinstance(item, str) and item)
    return frozenset()

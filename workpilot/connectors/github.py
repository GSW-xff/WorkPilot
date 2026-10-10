from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from workpilot.connectors.base import (
    Capability,
    ConnectorDeadlineExceeded,
    ConnectorError,
    ConnectorRateLimited,
    ConnectorRejected,
)
from workpilot.credentials import SecretStore
from workpilot.models import (
    ActionPreview,
    ActionRequest,
    ActionResult,
    Channel,
    RiskLevel,
    VerificationResult,
    VerificationStatus,
)

GITHUB_API_VERSION = "2022-11-28"
MARKER_PREFIX = "<!-- workpilot-idempotency:"


class ConnectorAccount(BaseModel):
    id: str
    tenant_id: str
    provider: str = "github"
    external_account_id: str
    login: str
    scopes: list[str]
    credential_ref: str
    refresh_credential_ref: str | None = None
    expires_at: datetime | None = None
    status: str = "ACTIVE"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GitHubOAuthManager:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        state_secret: str,
        secret_store: SecretStore,
        client: httpx.AsyncClient | None = None,
        web_base_url: str = "https://github.com",
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.state_secret = state_secret.encode()
        self.secret_store = secret_store
        self.client = client
        self.web_base_url = web_base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/")
        self.accounts: dict[tuple[str, str], ConnectorAccount] = {}

    def authorization_url(self, tenant_id: str, user_id: str) -> str:
        state = self._state(tenant_id, user_id)
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "scope": "read:user repo",
                "state": state,
                "allow_signup": "false",
            }
        )
        return f"{self.web_base_url}/login/oauth/authorize?{query}"

    async def exchange(self, code: str, state: str) -> ConnectorAccount:
        tenant_id, _user_id = self._validate_state(state)
        client = self.client or httpx.AsyncClient()
        owns_client = self.client is None
        try:
            token_response = await client.post(
                f"{self.web_base_url}/login/oauth/access_token",
                headers={"Accept": "application/json"},
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                timeout=15,
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            token = token_payload.get("access_token")
            if not isinstance(token, str) or not token:
                raise ConnectorRejected("GitHub OAuth response did not include an access token")
            scopes = sorted(
                scope.strip()
                for scope in str(token_payload.get("scope", "")).split(",")
                if scope.strip()
            )
            user_response = await client.get(
                f"{self.api_base_url}/user",
                headers=_github_headers(token),
                timeout=15,
            )
            user_response.raise_for_status()
            user = user_response.json()
            credential_ref = self.secret_store.put(tenant_id, token)
            refresh_token = token_payload.get("refresh_token")
            refresh_reference = (
                self.secret_store.put(tenant_id, refresh_token)
                if isinstance(refresh_token, str) and refresh_token
                else None
            )
            expires_in = token_payload.get("expires_in")
            account = ConnectorAccount(
                id=f"connector-{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                external_account_id=str(user["id"]),
                login=str(user["login"]),
                scopes=scopes,
                credential_ref=credential_ref,
                refresh_credential_ref=refresh_reference,
                expires_at=(
                    datetime.fromtimestamp(time.time() + int(expires_in), UTC)
                    if expires_in is not None
                    else None
                ),
            )
            self.accounts[(tenant_id, account.id)] = account
            return account
        except httpx.HTTPError as exc:
            raise ConnectorError("GitHub OAuth exchange failed", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()

    def revoke(self, tenant_id: str, account_id: str) -> ConnectorAccount:
        account = self.accounts[(tenant_id, account_id)]
        self.secret_store.delete(tenant_id, account.credential_ref)
        if account.refresh_credential_ref:
            self.secret_store.delete(tenant_id, account.refresh_credential_ref)
        account = account.model_copy(update={"status": "REVOKED"})
        self.accounts[(tenant_id, account_id)] = account
        return account

    def _state(self, tenant_id: str, user_id: str) -> str:
        payload = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "issued_at": int(time.time()),
            "nonce": uuid4().hex,
        }
        encoded = _b64(json.dumps(payload, separators=(",", ":")).encode())
        signature = hmac.new(self.state_secret, encoded.encode(), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _validate_state(self, state: str) -> tuple[str, str]:
        try:
            encoded, signature = state.split(".", 1)
            expected = hmac.new(self.state_secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("signature mismatch")
            payload = json.loads(_unb64(encoded))
            if int(time.time()) - int(payload["issued_at"]) > 600:
                raise ValueError("state expired")
            return str(payload["tenant_id"]), str(payload["user_id"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ConnectorRejected("invalid or expired OAuth state") from exc


class GitHubAdapter:
    def __init__(
        self,
        account: ConnectorAccount,
        secret_store: SecretStore,
        *,
        client: httpx.AsyncClient | None = None,
        api_base_url: str = "https://api.github.com",
        max_concurrency: int = 4,
        max_retries: int = 2,
    ) -> None:
        self.account = account
        self.secret_store = secret_store
        self.client = client
        self.api_base_url = api_base_url.rstrip("/")
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._failures = 0
        self._circuit_open_until = 0.0
        self._executions: dict[str, ActionResult] = {}

    def capabilities(self) -> list[Capability]:
        api = frozenset({Channel.API})
        return [
            Capability("github.issues.list", RiskLevel.R0, api),
            Capability("github.issue.get", RiskLevel.R0, api),
            Capability("github.issue.create", RiskLevel.R2, api),
            Capability("github.issue.comment", RiskLevel.R2, api),
        ]

    async def preview(self, action: ActionRequest) -> ActionPreview:
        return ActionPreview(
            action=action.capability,
            human_summary=(
                f"GitHub {action.capability} on {action.parameters.get('repo', 'unknown repo')}"
            ),
            parameters=action.parameters,
        )

    async def lookup(self, action: ActionRequest, idempotency_key: str) -> ActionResult | None:
        if idempotency_key in self._executions:
            return self._executions[idempotency_key].model_copy(update={"duplicate": True})
        if action.capability not in {"github.issue.create", "github.issue.comment"}:
            return None
        repo = _repo(action)
        query = f'repo:{repo} in:body,comments "{MARKER_PREFIX}{idempotency_key} -->"'
        payload = await self._request(
            "GET",
            "/search/issues",
            action,
            params={"q": query, "per_page": 1},
        )
        items = payload.get("items", [])
        if not items:
            return None
        issue = items[0]
        return ActionResult(
            success=True,
            remote_id=str(issue["id"]),
            data=_safe_issue(issue),
            side_effect=True,
            duplicate=True,
        )

    async def execute(self, action: ActionRequest, idempotency_key: str) -> ActionResult:
        existing = await self.lookup(action, idempotency_key)
        if existing is not None:
            return existing
        repo = _repo(action)
        parameters = action.parameters
        if action.capability == "github.issues.list":
            payload = await self._request(
                "GET", f"/repos/{repo}/issues", action, params={"state": "all", "per_page": 30}
            )
            return ActionResult(
                success=True,
                data={"issues": [_safe_issue(item) for item in payload]},
            )
        if action.capability == "github.issue.get":
            number = int(parameters["issue_number"])
            issue = await self._request("GET", f"/repos/{repo}/issues/{number}", action)
            return ActionResult(success=True, remote_id=str(issue["id"]), data=_safe_issue(issue))
        marker = f"{MARKER_PREFIX}{idempotency_key} -->"
        if action.capability == "github.issue.create":
            issue = await self._request(
                "POST",
                f"/repos/{repo}/issues",
                action,
                json_body={
                    "title": str(parameters["title"]),
                    "body": f"{parameters.get('body', '')}\n\n{marker}",
                    "labels": list(parameters.get("labels", [])),
                },
            )
        elif action.capability == "github.issue.comment":
            number = int(parameters["issue_number"])
            issue = await self._request(
                "POST",
                f"/repos/{repo}/issues/{number}/comments",
                action,
                json_body={"body": f"{parameters['body']}\n\n{marker}"},
            )
        else:
            raise ConnectorRejected(f"unsupported GitHub capability: {action.capability}")
        result = ActionResult(
            success=True,
            remote_id=str(issue["id"]),
            data=_safe_issue(issue),
            side_effect=True,
        )
        self._executions[idempotency_key] = result
        return result

    async def verify(self, action: ActionRequest, result: ActionResult) -> VerificationResult:
        if not result.success or result.remote_id is None:
            if action.capability == "github.issues.list" and result.success:
                return VerificationResult(
                    status=VerificationStatus.PASSED,
                    observed_state={"count": len(result.data.get("issues", []))},
                    reason="GitHub issue collection returned successfully",
                )
            return VerificationResult(
                status=VerificationStatus.FAILED,
                reason=result.error or "GitHub result has no remote identity",
            )
        url = result.data.get("url")
        return VerificationResult(
            status=VerificationStatus.PASSED if url else VerificationStatus.INCONCLUSIVE,
            evidence_refs=[str(url)] if url else [],
            observed_state={"remote_id": result.remote_id, "url": url},
            reason="GitHub response contains a stable remote object URL" if url else "missing URL",
        )

    async def _request(
        self,
        method: str,
        path: str,
        action: ActionRequest,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if self.account.status != "ACTIVE":
            raise ConnectorRejected("connector account is revoked")
        if action.tenant_id != self.account.tenant_id:
            raise ConnectorRejected("connector account belongs to a different tenant")
        now = time.monotonic()
        if now < self._circuit_open_until:
            raise ConnectorError("GitHub circuit breaker is open", retryable=True)
        timeout = 15.0
        if action.deadline_at is not None:
            timeout = min(timeout, (action.deadline_at - datetime.now(UTC)).total_seconds())
            if timeout <= 0:
                raise ConnectorDeadlineExceeded()
        token = self.secret_store.get(action.tenant_id, self.account.credential_ref)
        client = self.client or httpx.AsyncClient()
        owns_client = self.client is None
        try:
            async with self._semaphore:
                for attempt in range(self.max_retries + 1):
                    try:
                        response = await client.request(
                            method,
                            f"{self.api_base_url}{path}",
                            headers=_github_headers(token),
                            params=params,
                            json=json_body,
                            timeout=timeout,
                        )
                    except (httpx.TimeoutException, httpx.NetworkError) as exc:
                        self._record_failure()
                        if attempt < self.max_retries:
                            await asyncio.sleep(0.05 * 2**attempt)
                            continue
                        raise ConnectorError(
                            "GitHub network request failed",
                            retryable=True,
                            outcome_unknown=method != "GET",
                        ) from exc
                    if (
                        response.status_code == 429
                        or response.status_code == 403
                        and response.headers.get("X-RateLimit-Remaining") == "0"
                    ):
                        if attempt < self.max_retries:
                            await asyncio.sleep(
                                min(float(response.headers.get("Retry-After", "0.05")), 1)
                            )
                            continue
                        raise ConnectorRateLimited()
                    if response.status_code >= 500 and attempt < self.max_retries:
                        self._record_failure()
                        await asyncio.sleep(0.05 * 2**attempt)
                        continue
                    if response.status_code >= 400:
                        raise ConnectorRejected(f"GitHub HTTP {response.status_code}")
                    self._failures = 0
                    return response.json()
        finally:
            if owns_client:
                await client.aclose()
        raise ConnectorError("GitHub retry budget exhausted", retryable=True)

    def _record_failure(self) -> None:
        self._failures += 1
        if self._failures >= 3:
            self._circuit_open_until = time.monotonic() + 30


class GitHubWebhookVerifier:
    def __init__(self, secret: str) -> None:
        self.secret = secret.encode()
        self._deliveries: set[str] = set()

    def verify(self, body: bytes, signature: str, delivery_id: str) -> dict[str, Any]:
        if not delivery_id:
            raise ConnectorRejected("missing GitHub webhook delivery id")
        expected = "sha256=" + hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ConnectorRejected("invalid GitHub webhook signature")
        if delivery_id in self._deliveries:
            raise ConnectorRejected("duplicate GitHub webhook delivery")
        payload = json.loads(body)
        self._deliveries.add(delivery_id)
        return payload


def _repo(action: ActionRequest) -> str:
    repo = str(action.parameters.get("repo", ""))
    if repo.count("/") != 1 or any(part in {"", ".", ".."} for part in repo.split("/")):
        raise ConnectorRejected("repo must use owner/name format")
    return repo


def _github_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "WorkPilot/0.3",
    }


def _safe_issue(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload.get(key)
        for key in ("id", "number", "title", "state", "html_url", "body")
        if key in payload
    } | {"url": payload.get("html_url")}


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()

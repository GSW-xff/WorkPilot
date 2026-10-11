from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from workpilot.connectors.base import ConnectorError, ConnectorRejected
from workpilot.connectors.github import (
    ConnectorAccount,
    GitHubAdapter,
    GitHubOAuthManager,
    GitHubWebhookVerifier,
)
from workpilot.credentials import InMemorySecretStore
from workpilot.models import ActionRequest, Channel, VerificationStatus


class SandboxCheck(BaseModel):
    name: str
    status: Literal["passed", "failed", "not_run"]
    evidence_type: Literal["github_sandbox", "fault_injection", "local_contract"]
    details: dict[str, Any] = Field(default_factory=dict)


class GitHubSandboxReport(BaseModel):
    schema_version: str = "workpilot.github-sandbox.v1"
    generated_at: datetime
    repository: str
    api_base_url: str
    account_login: str | None = None
    oauth_scopes: list[str] = Field(default_factory=list)
    checks: list[SandboxCheck]
    remote_objects: list[dict[str, Any]] = Field(default_factory=list)
    cleanup: dict[str, Any]
    token_revoked: bool
    secrets_recorded: bool = False
    passed: bool


class DropSuccessfulWriteResponse(httpx.AsyncBaseTransport):
    """Drops one successful POST response after the server has committed it."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.inner = inner or httpx.AsyncHTTPTransport()
        self.dropped = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        if request.method == "POST" and response.is_success and not self.dropped:
            self.dropped = True
            await response.aread()
            await response.aclose()
            raise httpx.ReadTimeout("injected response loss after remote commit", request=request)
        return response

    async def aclose(self) -> None:
        await self.inner.aclose()


class GitHubSandboxRunner:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        api_base_url: str = "https://api.github.com",
    ) -> None:
        self.client = client
        self.api_base_url = api_base_url.rstrip("/")

    async def run(
        self,
        *,
        repository: str,
        token: str,
        client_id: str,
        client_secret: str,
        webhook_secret: str,
        required_scopes: set[str] | None = None,
        revoke_token: bool = True,
        inject_live_response_loss: bool = True,
        webhook_delivery_evidence: dict[str, Any] | None = None,
    ) -> GitHubSandboxReport:
        _validate_repo(repository)
        required = required_scopes or {"read:user", "repo"}
        client = self.client or httpx.AsyncClient()
        owns_client = self.client is None
        secrets = InMemorySecretStore()
        credential_ref = secrets.put("sandbox", token)
        checks: list[SandboxCheck] = []
        remote_objects: list[dict[str, Any]] = []
        issue_numbers: set[int] = set()
        comment_ids: set[int] = set()
        cleanup: dict[str, Any] = {"closed_issues": [], "deleted_comments": [], "errors": []}
        token_revoked = False
        account: ConnectorAccount | None = None
        manager: GitHubOAuthManager | None = None
        try:
            identity_response = await client.get(
                f"{self.api_base_url}/user",
                headers=_bearer_headers(token),
                timeout=15,
            )
            identity_response.raise_for_status()
            identity = identity_response.json()
            account = ConnectorAccount(
                id="connector-sandbox",
                tenant_id="sandbox",
                external_account_id=str(identity["id"]),
                login=str(identity["login"]),
                scopes=[],
                credential_ref=credential_ref,
            )
            manager = GitHubOAuthManager(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri="http://127.0.0.1/oauth-evidence-only",
                state_secret=uuid4().hex,
                secret_store=secrets,
                client=client,
                api_base_url=self.api_base_url,
            )
            manager.accounts[("sandbox", account.id)] = account
            inspection = await manager.inspect_token("sandbox", account.id)
            scopes = set(inspection["scopes"])
            missing = sorted(required - scopes)
            excessive = sorted(scopes - required)
            if missing or excessive:
                raise ConnectorRejected(
                    f"OAuth scope mismatch; missing={missing}, excessive={excessive}"
                )
            account = account.model_copy(update={"scopes": sorted(scopes)})
            manager.accounts[("sandbox", account.id)] = account
            checks.append(
                SandboxCheck(
                    name="oauth_token_and_minimum_scope",
                    status="passed",
                    evidence_type="github_sandbox",
                    details={
                        "login": account.login,
                        "scopes": sorted(scopes),
                        "app": inspection["app"],
                    },
                )
            )

            repo_response = await client.get(
                f"{self.api_base_url}/repos/{repository}",
                headers=_bearer_headers(token),
                timeout=15,
            )
            repo_response.raise_for_status()
            checks.append(
                SandboxCheck(
                    name="sandbox_repository_access",
                    status="passed",
                    evidence_type="github_sandbox",
                    details={
                        "repository": repository,
                        "private": repo_response.json().get("private"),
                    },
                )
            )

            adapter = GitHubAdapter(
                account,
                secrets,
                client=client,
                api_base_url=self.api_base_url,
            )
            run_id = uuid4().hex[:12]
            create_key = f"sandbox-create-{run_id}"
            create = ActionRequest(
                tenant_id="sandbox",
                task_id=f"sandbox-{run_id}",
                step_id="create_issue",
                capability="github.issue.create",
                parameters={
                    "repo": repository,
                    "title": f"[WorkPilot E2E] {run_id}",
                    "body": "Disposable OAuth sandbox evidence. The runner will close this issue.",
                },
                channel=Channel.API,
            )
            created = await adapter.execute(create, create_key)
            verification = await adapter.verify(create, created)
            if verification.status is not VerificationStatus.PASSED:
                raise RuntimeError("created issue could not be independently verified")
            issue_number = int(created.data["number"])
            issue_numbers.add(issue_number)
            remote_objects.append(
                {
                    "kind": "issue",
                    "id": created.remote_id,
                    "number": issue_number,
                    "url": created.data.get("url"),
                    "idempotency_key_sha256": hashlib.sha256(create_key.encode()).hexdigest(),
                }
            )

            restarted = GitHubAdapter(
                account,
                secrets,
                client=client,
                api_base_url=self.api_base_url,
            )
            duplicate = await restarted.execute(create, create_key)
            if not duplicate.duplicate or duplicate.remote_id != created.remote_id:
                raise RuntimeError("remote lookup did not recover the original issue")
            checks.append(
                SandboxCheck(
                    name="issue_create_verify_and_restart_idempotency",
                    status="passed",
                    evidence_type="github_sandbox",
                    details={
                        "remote_id": created.remote_id,
                        "issue_number": issue_number,
                        "duplicate_side_effects": 0,
                    },
                )
            )

            comment_key = f"sandbox-comment-{run_id}"
            comment = ActionRequest(
                tenant_id="sandbox",
                task_id=f"sandbox-{run_id}",
                step_id="comment_issue",
                capability="github.issue.comment",
                parameters={
                    "repo": repository,
                    "issue_number": issue_number,
                    "body": "WorkPilot sandbox comment verification.",
                },
                channel=Channel.API,
            )
            commented = await adapter.execute(comment, comment_key)
            comment_verification = await adapter.verify(comment, commented)
            if comment_verification.status is not VerificationStatus.PASSED:
                raise RuntimeError("created comment could not be independently verified")
            assert commented.remote_id is not None
            comment_ids.add(int(commented.remote_id))
            remote_objects.append(
                {
                    "kind": "comment",
                    "id": commented.remote_id,
                    "url": commented.data.get("url"),
                    "idempotency_key_sha256": hashlib.sha256(comment_key.encode()).hexdigest(),
                }
            )
            checks.append(
                SandboxCheck(
                    name="issue_comment_and_verify",
                    status="passed",
                    evidence_type="github_sandbox",
                    details={"remote_id": commented.remote_id},
                )
            )

            webhook = GitHubWebhookVerifier(webhook_secret)
            body = json.dumps({"action": "opened", "issue": {"number": issue_number}}).encode()
            signature = "sha256=" + hmac.new(
                webhook_secret.encode(), body, hashlib.sha256
            ).hexdigest()
            webhook.verify(body, signature, f"sandbox-{run_id}")
            replay_blocked = False
            try:
                webhook.verify(body, signature, f"sandbox-{run_id}")
            except ConnectorRejected:
                replay_blocked = True
            if not replay_blocked:
                raise RuntimeError("webhook replay was not blocked")
            checks.append(
                SandboxCheck(
                    name="webhook_signature_and_replay",
                    status="passed",
                    evidence_type="local_contract",
                    details={"github_delivery_received": False, "replay_blocked": True},
                )
            )
            if (
                webhook_delivery_evidence
                and webhook_delivery_evidence.get("repository") == repository
                and webhook_delivery_evidence.get("signature_valid") is True
                and webhook_delivery_evidence.get("delivery_id")
            ):
                checks.append(
                    SandboxCheck(
                        name="github_webhook_delivery",
                        status="passed",
                        evidence_type="github_sandbox",
                        details={
                            "delivery_id": webhook_delivery_evidence["delivery_id"],
                            "event": webhook_delivery_evidence.get("event"),
                            "payload_sha256": webhook_delivery_evidence.get("payload_sha256"),
                        },
                    )
                )
            else:
                checks.append(
                    SandboxCheck(
                        name="github_webhook_delivery",
                        status="not_run",
                        evidence_type="github_sandbox",
                        details={"reason": "signed GitHub delivery evidence was not provided"},
                    )
                )

            checks.extend(await run_connector_fault_matrix())

            if inject_live_response_loss:
                loss = await self._run_live_response_loss(
                    repository=repository,
                    token=token,
                    account=account,
                    secrets=secrets,
                    run_id=run_id,
                )
                checks.append(loss[0])
                if loss[1] is not None:
                    issue_numbers.add(loss[1])
                    remote_objects.append(loss[2])
            else:
                checks.append(
                    SandboxCheck(
                        name="response_loss_after_remote_commit",
                        status="not_run",
                        evidence_type="github_sandbox",
                        details={"reason": "disabled for this run"},
                    )
                )
        except Exception as exc:
            checks.append(
                SandboxCheck(
                    name="sandbox_run",
                    status="failed",
                    evidence_type="github_sandbox",
                    details={"error_type": type(exc).__name__, "message": str(exc)[:500]},
                )
            )
        finally:
            for comment_id in sorted(comment_ids):
                try:
                    response = await client.delete(
                        f"{self.api_base_url}/repos/{repository}/issues/comments/{comment_id}",
                        headers=_bearer_headers(token),
                        timeout=15,
                    )
                    response.raise_for_status()
                    cleanup["deleted_comments"].append(comment_id)
                except Exception as exc:
                    cleanup["errors"].append(f"comment:{comment_id}:{type(exc).__name__}")
            for issue_number in sorted(issue_numbers):
                try:
                    response = await client.patch(
                        f"{self.api_base_url}/repos/{repository}/issues/{issue_number}",
                        headers=_bearer_headers(token),
                        json={"state": "closed", "state_reason": "not_planned"},
                        timeout=15,
                    )
                    response.raise_for_status()
                    cleanup["closed_issues"].append(issue_number)
                except Exception as exc:
                    cleanup["errors"].append(f"issue:{issue_number}:{type(exc).__name__}")
            if revoke_token and manager is not None and account is not None:
                try:
                    await manager.revoke_remote("sandbox", account.id)
                    token_revoked = True
                    checks.append(
                        SandboxCheck(
                            name="oauth_token_remote_revocation",
                            status="passed",
                            evidence_type="github_sandbox",
                            details={"local_secret_deleted": True},
                        )
                    )
                except Exception as exc:
                    cleanup["errors"].append(f"token:{type(exc).__name__}")
                    checks.append(
                        SandboxCheck(
                            name="oauth_token_remote_revocation",
                            status="failed",
                            evidence_type="github_sandbox",
                            details={"error_type": type(exc).__name__},
                        )
                    )
            elif revoke_token:
                checks.append(
                    SandboxCheck(
                        name="oauth_token_remote_revocation",
                        status="not_run",
                        evidence_type="github_sandbox",
                        details={"reason": "OAuth account was not initialized"},
                    )
                )
            else:
                checks.append(
                    SandboxCheck(
                        name="oauth_token_remote_revocation",
                        status="not_run",
                        evidence_type="github_sandbox",
                        details={"reason": "disabled by --keep-token"},
                    )
                )
            if owns_client:
                await client.aclose()

        passed = bool(checks) and all(check.status == "passed" for check in checks)
        passed = passed and not cleanup["errors"] and token_revoked
        return GitHubSandboxReport(
            generated_at=datetime.now(UTC),
            repository=repository,
            api_base_url=self.api_base_url,
            account_login=account.login if account else None,
            oauth_scopes=account.scopes if account else [],
            checks=checks,
            remote_objects=remote_objects,
            cleanup=cleanup,
            token_revoked=token_revoked,
            passed=passed,
        )

    async def _run_live_response_loss(
        self,
        *,
        repository: str,
        token: str,
        account: ConnectorAccount,
        secrets: InMemorySecretStore,
        run_id: str,
    ) -> tuple[SandboxCheck, int | None, dict[str, Any]]:
        key = f"sandbox-response-loss-{run_id}"
        action = ActionRequest(
            tenant_id="sandbox",
            task_id=f"sandbox-{run_id}",
            step_id="response_loss",
            capability="github.issue.create",
            parameters={
                "repo": repository,
                "title": f"[WorkPilot response loss] {run_id}",
                "body": "The client intentionally drops the successful response once.",
            },
            channel=Channel.API,
        )
        transport = DropSuccessfulWriteResponse()
        lossy_client = httpx.AsyncClient(transport=transport)
        unknown = False
        try:
            adapter = GitHubAdapter(
                account,
                secrets,
                client=lossy_client,
                api_base_url=self.api_base_url,
            )
            await adapter.execute(action, key)
        except ConnectorError as exc:
            unknown = exc.outcome_unknown
        finally:
            await lossy_client.aclose()
        if not unknown or not transport.dropped:
            raise RuntimeError("response-loss injection did not produce UNKNOWN outcome")
        recovery_client = httpx.AsyncClient()
        try:
            recovered = await GitHubAdapter(
                account,
                secrets,
                client=recovery_client,
                api_base_url=self.api_base_url,
            ).execute(action, key)
        finally:
            await recovery_client.aclose()
        if not recovered.duplicate:
            raise RuntimeError("response-loss recovery did not use remote lookup")
        number = int(recovered.data["number"])
        evidence = {
            "kind": "response_loss_issue",
            "id": recovered.remote_id,
            "number": number,
            "url": recovered.data.get("url"),
            "idempotency_key_sha256": hashlib.sha256(key.encode()).hexdigest(),
        }
        return (
            SandboxCheck(
                name="response_loss_after_remote_commit",
                status="passed",
                evidence_type="github_sandbox",
                details={
                    "remote_id": recovered.remote_id,
                    "issue_number": number,
                    "duplicate_side_effects": 0,
                    "recovered_by_lookup": True,
                },
            ),
            number,
            evidence,
        )


async def run_connector_fault_matrix() -> list[SandboxCheck]:
    token = "fault-injection-token"
    secrets = InMemorySecretStore()
    reference = secrets.put("fault", token)
    account = ConnectorAccount(
        id="fault-account",
        tenant_id="fault",
        external_account_id="0",
        login="fault",
        scopes=["repo", "read:user"],
        credential_ref=reference,
    )
    action = ActionRequest(
        tenant_id="fault",
        task_id="fault",
        step_id="read",
        capability="github.issues.list",
        parameters={"repo": "sandbox/repo"},
        channel=Channel.API,
    )
    rate_calls = 0

    def rate_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal rate_calls
        rate_calls += 1
        if rate_calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=[])

    rate_client = httpx.AsyncClient(transport=httpx.MockTransport(rate_handler))
    rate_result = await GitHubAdapter(
        account,
        secrets,
        client=rate_client,
        api_base_url="https://api.github.test",
    ).execute(action, "rate")
    await rate_client.aclose()

    write_calls = 0

    def failure_handler(request: httpx.Request) -> httpx.Response:
        nonlocal write_calls
        if request.url.path == "/search/issues":
            return httpx.Response(200, json={"items": []})
        write_calls += 1
        return httpx.Response(502)

    failure_client = httpx.AsyncClient(transport=httpx.MockTransport(failure_handler))
    write = action.model_copy(
        update={
            "capability": "github.issue.create",
            "parameters": {"repo": "sandbox/repo", "title": "fault", "body": "fault"},
        }
    )
    unknown = False
    try:
        await GitHubAdapter(
            account,
            secrets,
            client=failure_client,
            api_base_url="https://api.github.test",
        ).execute(write, "server-error")
    except ConnectorError as exc:
        unknown = exc.outcome_unknown
    await failure_client.aclose()
    if not rate_result.success or rate_calls != 2 or not unknown or write_calls != 1:
        raise RuntimeError("connector fault matrix failed")
    return [
        SandboxCheck(
            name="rate_limit_429_retry",
            status="passed",
            evidence_type="fault_injection",
            details={"requests": rate_calls, "retry_after_honored": True},
        ),
        SandboxCheck(
            name="server_5xx_write_unknown_no_direct_retry",
            status="passed",
            evidence_type="fault_injection",
            details={"post_attempts": write_calls, "outcome_unknown": True},
        ),
    ]


def write_github_sandbox_report(
    report: GitHubSandboxReport, output_dir: Path
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "github-sandbox.json"
    markdown_path = output_dir / "github-sandbox.md"
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    rows = "\n".join(
        f"| {check.name} | {check.status} | {check.evidence_type} |"
        for check in report.checks
    )
    markdown_path.write_text(
        "# WorkPilot GitHub Sandbox E2E\n\n"
        f"- Generated: {report.generated_at.isoformat()}\n"
        f"- Repository: `{report.repository}`\n"
        f"- Account: `{report.account_login}`\n"
        f"- OAuth scopes: `{', '.join(report.oauth_scopes)}`\n"
        f"- Result: `{'passed' if report.passed else 'failed'}`\n"
        f"- Token revoked: `{report.token_revoked}`\n"
        "- Secrets recorded: `false`\n\n"
        "| Check | Status | Evidence |\n"
        "| --- | --- | --- |\n"
        f"{rows}\n\n"
        f"Cleanup: `{json.dumps(report.cleanup, ensure_ascii=False)}`\n",
        encoding="utf-8",
    )
    return json_path, markdown_path


def _validate_repo(repository: str) -> None:
    if repository.count("/") != 1 or any(
        item in {"", ".", ".."} for item in repository.split("/")
    ):
        raise ValueError("repository must use owner/name format")


def _bearer_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "WorkPilot-Sandbox-E2E/1.0",
    }


async def _main_async(arguments: argparse.Namespace) -> None:
    required = {
        "WORKPILOT_GITHUB_SANDBOX_TOKEN": os.getenv("WORKPILOT_GITHUB_SANDBOX_TOKEN"),
        "WORKPILOT_GITHUB_CLIENT_ID": os.getenv("WORKPILOT_GITHUB_CLIENT_ID"),
        "WORKPILOT_GITHUB_CLIENT_SECRET": os.getenv("WORKPILOT_GITHUB_CLIENT_SECRET"),
        "WORKPILOT_GITHUB_WEBHOOK_SECRET": os.getenv("WORKPILOT_GITHUB_WEBHOOK_SECRET"),
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise ValueError(
            "required GitHub sandbox environment variables are unset: " + ", ".join(missing)
        )
    report = await GitHubSandboxRunner(api_base_url=arguments.api_base_url).run(
        repository=arguments.repository,
        token=str(required["WORKPILOT_GITHUB_SANDBOX_TOKEN"]),
        client_id=str(required["WORKPILOT_GITHUB_CLIENT_ID"]),
        client_secret=str(required["WORKPILOT_GITHUB_CLIENT_SECRET"]),
        webhook_secret=str(required["WORKPILOT_GITHUB_WEBHOOK_SECRET"]),
        revoke_token=not arguments.keep_token,
        inject_live_response_loss=not arguments.skip_response_loss,
        webhook_delivery_evidence=(
            json.loads(arguments.webhook_evidence.read_text(encoding="utf-8"))
            if arguments.webhook_evidence
            else None
        ),
    )
    paths = write_github_sandbox_report(report, arguments.output)
    print(json.dumps({"reports": [str(path) for path in paths], "passed": report.passed}))
    if not report.passed:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run destructive GitHub OAuth sandbox E2E")
    parser.add_argument("--repository", required=True, help="Disposable owner/name sandbox repo")
    parser.add_argument("--output", type=Path, default=Path("evals/reports/github-sandbox"))
    parser.add_argument("--api-base-url", default="https://api.github.com")
    parser.add_argument("--keep-token", action="store_true")
    parser.add_argument("--skip-response-loss", action="store_true")
    parser.add_argument("--webhook-evidence", type=Path)
    asyncio.run(_main_async(parser.parse_args()))


if __name__ == "__main__":
    main()

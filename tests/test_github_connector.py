from __future__ import annotations

import hashlib
import hmac
import json
import unittest
from urllib.parse import parse_qs, urlparse

import httpx

from workpilot.connectors.base import ConnectorRejected
from workpilot.connectors.github import (
    ConnectorAccount,
    GitHubAdapter,
    GitHubOAuthManager,
    GitHubWebhookVerifier,
)
from workpilot.credentials import InMemorySecretStore, SecretNotFoundError
from workpilot.models import ActionRequest, Channel, VerificationStatus


class GitHubOAuthTest(unittest.IsolatedAsyncioTestCase):
    async def test_oauth_state_exchange_stores_only_secret_reference_and_revoke(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/login/oauth/access_token":
                return httpx.Response(
                    200,
                    json={"access_token": "github-secret-token", "scope": "repo,read:user"},
                )
            if request.url.path == "/user":
                self.assertEqual("Bearer github-secret-token", request.headers["Authorization"])
                return httpx.Response(200, json={"id": 42, "login": "workpilot-sandbox"})
            return httpx.Response(404)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        secrets = InMemorySecretStore()
        manager = GitHubOAuthManager(
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://localhost/callback",
            state_secret="state-secret",
            secret_store=secrets,
            client=client,
            web_base_url="https://github.test",
            api_base_url="https://api.github.test",
        )
        authorization_url = manager.authorization_url("tenant-a", "user-a")
        query = parse_qs(urlparse(authorization_url).query)
        self.assertEqual({"repo", "read:user"}, set(query["scope"][0].split()))
        account = await manager.exchange("code", query["state"][0])
        self.assertEqual("tenant-a", account.tenant_id)
        self.assertEqual("github-secret-token", secrets.get("tenant-a", account.credential_ref))
        self.assertNotIn("github-secret-token", account.model_dump_json())
        revoked = manager.revoke("tenant-a", account.id)
        self.assertEqual("REVOKED", revoked.status)
        with self.assertRaises(SecretNotFoundError):
            secrets.get("tenant-a", account.credential_ref)
        await client.aclose()

    async def test_tampered_oauth_state_is_rejected_before_http(self) -> None:
        manager = GitHubOAuthManager(
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
            state_secret="state-secret",
            secret_store=InMemorySecretStore(),
        )
        state = parse_qs(urlparse(manager.authorization_url("tenant", "user")).query)["state"][0]
        with self.assertRaisesRegex(ConnectorRejected, "OAuth state"):
            await manager.exchange("code", state + "tampered")


class GitHubAdapterContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path == "/search/issues":
                return httpx.Response(200, json={"items": []})
            if request.method == "POST" and request.url.path == "/repos/acme/demo/issues":
                body = json.loads(request.content)
                self.assertIn("workpilot-idempotency:same-key", body["body"])
                return httpx.Response(
                    201,
                    json={
                        "id": 101,
                        "number": 7,
                        "title": body["title"],
                        "state": "open",
                        "body": body["body"],
                        "html_url": "https://github.test/acme/demo/issues/7",
                    },
                )
            if request.method == "GET" and request.url.path == "/repos/acme/demo/issues":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 101,
                            "number": 7,
                            "title": "Follow up",
                            "state": "open",
                            "html_url": "https://github.test/acme/demo/issues/7",
                        }
                    ],
                )
            return httpx.Response(404)

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.secrets = InMemorySecretStore()
        reference = self.secrets.put("tenant-a", "token-value")
        account = ConnectorAccount(
            id="connector-1",
            tenant_id="tenant-a",
            external_account_id="42",
            login="sandbox",
            scopes=["repo"],
            credential_ref=reference,
        )
        self.adapter = GitHubAdapter(
            account,
            self.secrets,
            client=self.client,
            api_base_url="https://api.github.test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_issue_create_is_remote_lookup_idempotent_and_verifiable(self) -> None:
        action = ActionRequest(
            tenant_id="tenant-a",
            task_id="task",
            step_id="create",
            capability="github.issue.create",
            parameters={"repo": "acme/demo", "title": "Follow up", "body": "Details"},
            channel=Channel.API,
        )
        first = await self.adapter.execute(action, "same-key")
        second = await self.adapter.execute(action, "same-key")
        verification = await self.adapter.verify(action, first)
        self.assertFalse(first.duplicate)
        self.assertTrue(second.duplicate)
        self.assertEqual(first.remote_id, second.remote_id)
        self.assertEqual(VerificationStatus.PASSED, verification.status)
        post_requests = [request for request in self.requests if request.method == "POST"]
        self.assertEqual(1, len(post_requests))
        self.assertEqual("Bearer token-value", post_requests[0].headers["Authorization"])

    async def test_read_contract_returns_sanitized_issue_list(self) -> None:
        action = ActionRequest(
            tenant_id="tenant-a",
            task_id="task",
            step_id="read",
            capability="github.issues.list",
            parameters={"repo": "acme/demo"},
            channel=Channel.API,
        )
        result = await self.adapter.execute(action, "read-key")
        verification = await self.adapter.verify(action, result)
        self.assertEqual(1, len(result.data["issues"]))
        self.assertEqual(VerificationStatus.PASSED, verification.status)
        self.assertNotIn("token-value", result.model_dump_json())

    async def test_rate_limit_respects_retry_after(self) -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "0", "X-RateLimit-Remaining": "0"},
                )
            return httpx.Response(200, json=[])

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        adapter = GitHubAdapter(
            self.adapter.account,
            self.secrets,
            client=client,
            api_base_url="https://api.github.test",
        )
        action = ActionRequest(
            tenant_id="tenant-a",
            task_id="task",
            step_id="read",
            capability="github.issues.list",
            parameters={"repo": "acme/demo"},
            channel=Channel.API,
        )
        result = await adapter.execute(action, "read-key")
        await client.aclose()
        self.assertTrue(result.success)
        self.assertEqual(2, calls)


class GitHubWebhookTest(unittest.TestCase):
    def test_signature_and_delivery_replay_are_enforced(self) -> None:
        verifier = GitHubWebhookVerifier("webhook-secret")
        body = b'{"action":"opened"}'
        signature = "sha256=" + hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()
        self.assertEqual("opened", verifier.verify(body, signature, "delivery-1")["action"])
        with self.assertRaisesRegex(ConnectorRejected, "duplicate"):
            verifier.verify(body, signature, "delivery-1")
        with self.assertRaisesRegex(ConnectorRejected, "signature"):
            verifier.verify(body, "sha256=bad", "delivery-2")


if __name__ == "__main__":
    unittest.main()

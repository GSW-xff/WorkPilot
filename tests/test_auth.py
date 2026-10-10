import json
import time
import unittest

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from workpilot.api import create_app
from workpilot.config import Settings


class OIDCAuthTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))
        jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
        self.jwks_calls = 0

        def jwks_handler(request: httpx.Request) -> httpx.Response:
            self.jwks_calls += 1
            return httpx.Response(200, json={"keys": [jwk]}, request=request)

        self.app = create_app(
            settings=Settings(
                auth_mode="oidc",
                oidc_issuer="https://identity.example.test",
                oidc_audience="workpilot-api",
                oidc_jwks_url="https://identity.example.test/.well-known/jwks.json",
            )
        )
        verifier = self.app.state.auth_verifier
        await verifier._client.aclose()
        verifier._client = httpx.AsyncClient(transport=httpx.MockTransport(jwks_handler))
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await self.app.state.auth_verifier.close()
        self.app.state.service.repository.close()

    def token(
        self,
        *,
        subject: str = "creator",
        tenant_id: str = "tenant-a",
        roles: list[str] | None = None,
        issuer: str = "https://identity.example.test",
        expires_in: int = 300,
    ) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "iss": issuer,
                "aud": "workpilot-api",
                "sub": subject,
                "tenant_id": tenant_id,
                "roles": roles or ["owner"],
                "scope": "tasks:read tasks:write",
                "iat": now - 1,
                "exp": now + expires_in,
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

    @staticmethod
    def headers(token: str, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", **extra}

    async def test_requires_valid_bearer_token_and_returns_problem_details(self) -> None:
        missing = await self.client.get("/v1/tasks")
        self.assertEqual(401, missing.status_code)
        self.assertEqual("application/problem+json", missing.headers["content-type"])

        invalid = await self.client.get(
            "/v1/tasks", headers=self.headers(self.token(issuer="https://attacker.test"))
        )
        self.assertEqual(401, invalid.status_code)
        self.assertEqual("bearer token validation failed", invalid.json()["detail"])

    async def test_verified_tenant_claim_overrides_spoofed_header_and_jwks_is_cached(self) -> None:
        token = self.token()
        created = await self.client.post(
            "/v1/tasks",
            headers=self.headers(token, **{"X-Tenant-ID": "attacker-tenant"}),
            json={"goal": "prepare a weekly report"},
        )
        self.assertEqual(201, created.status_code)
        self.assertEqual("tenant-a", created.json()["tenant_id"])

        listed = await self.client.get("/v1/tasks", headers=self.headers(token))
        self.assertEqual(1, listed.json()["total"])
        self.assertEqual(1, self.jwks_calls)

        other = await self.client.get(
            f"/v1/tasks/{created.json()['id']}",
            headers=self.headers(self.token(tenant_id="tenant-b")),
        )
        self.assertEqual(404, other.status_code)

    async def test_approval_role_and_separation_of_duties(self) -> None:
        creator = self.token(subject="creator", roles=["owner", "approver"])
        for update in self.app.state.fake_adapter.state.updates:
            update["tenant_id"] = "tenant-a"
        for document in self.app.state.fake_adapter.state.documents:
            document["tenant_id"] = "tenant-a"
        created = await self.client.post(
            "/v1/tasks",
            headers=self.headers(creator),
            json={"goal": "send the weekly report", "recipient": "team@example.com"},
        )
        task_id = created.json()["id"]
        waiting = await self.client.post(f"/v1/tasks/{task_id}/run", headers=self.headers(creator))
        approval = waiting.json()["approvals"][-1]

        body = {"step_id": approval["step_id"], "parameter_hash": approval["parameter_hash"]}
        self_approval = await self.client.post(
            f"/v1/tasks/{task_id}/approve", headers=self.headers(creator), json=body
        )
        self.assertEqual(403, self_approval.status_code)

        unprivileged = await self.client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=self.headers(self.token(subject="viewer", roles=["owner"])),
            json=body,
        )
        self.assertEqual(403, unprivileged.status_code)

        approved = await self.client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=self.headers(self.token(subject="reviewer", roles=["approver"])),
            json=body,
        )
        self.assertEqual(200, approved.status_code)
        self.assertEqual("RUNNING", approved.json()["status"])


if __name__ == "__main__":
    unittest.main()

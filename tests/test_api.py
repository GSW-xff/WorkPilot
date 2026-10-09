import unittest

import httpx

from workpilot.api import create_app


class ApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.app = create_app()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://test",
        )
        self.headers = {"X-Tenant-ID": "demo", "X-User-ID": "api-user"}

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.state.service.repository.close()

    async def test_health_and_console(self) -> None:
        self.assertEqual(
            {"status": "ok", "runtime": "fake-enterprise", "storage": "memory"},
            (await self.client.get("/health")).json(),
        )
        console = await self.client.get("/")
        self.assertEqual(200, console.status_code)
        self.assertIn("WorkPilot Console", console.text)

    async def test_create_run_approve_and_replay(self) -> None:
        created = await self.client.post(
            "/v1/tasks",
            headers=self.headers,
            json={"goal": "生成并发送本周项目周报", "recipient": "team@example.com"},
        )
        self.assertEqual(201, created.status_code)
        task_id = created.json()["id"]

        waiting = await self.client.post(
            f"/v1/tasks/{task_id}/run", headers=self.headers
        )
        self.assertEqual(200, waiting.status_code)
        payload = waiting.json()
        self.assertEqual("WAITING_APPROVAL", payload["status"])
        pending = payload["approvals"][-1]

        approved = await self.client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=self.headers,
            json={"step_id": pending["step_id"], "parameter_hash": pending["parameter_hash"]},
        )
        self.assertEqual(200, approved.status_code)
        self.assertEqual("RUNNING", approved.json()["status"])

        replay = await self.client.get(
            f"/v1/tasks/{task_id}/replay", headers=self.headers
        )
        self.assertEqual(200, replay.status_code)
        self.assertTrue(
            any(
                event["type"] == "approval.approved"
                for event in replay.json()["events"]
            )
        )

    async def test_cross_tenant_task_access_returns_not_found(self) -> None:
        created = (
            await self.client.post(
            "/v1/tasks", headers=self.headers, json={"goal": "prepare weekly report"}
            )
        ).json()
        response = await self.client.get(
            f"/v1/tasks/{created['id']}", headers={"X-Tenant-ID": "other"}
        )
        self.assertEqual(404, response.status_code)

    async def test_knowledge_documents_are_tenant_scoped(self) -> None:
        response = await self.client.post(
            "/v1/knowledge/documents",
            headers={"X-Tenant-ID": "tenant-a"},
            json={"title": "Template", "content": "private"},
        )
        self.assertEqual(201, response.status_code)
        documents = self.app.state.fake_adapter.state.documents
        created = next(item for item in documents if item["id"] == response.json()["id"])
        self.assertEqual("tenant-a", created["tenant_id"])


if __name__ == "__main__":
    unittest.main()

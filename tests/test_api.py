import unittest
from unittest.mock import AsyncMock, Mock

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
        self.assertIn("refreshTask", console.text)
        self.assertIn("setInterval", console.text)

    async def test_create_run_approve_and_replay(self) -> None:
        created = await self.client.post(
            "/v1/tasks",
            headers=self.headers,
            json={"goal": "生成并发送本周项目周报", "recipient": "team@example.com"},
        )
        self.assertEqual(201, created.status_code)
        task_id = created.json()["id"]

        waiting = await self.client.post(f"/v1/tasks/{task_id}/run", headers=self.headers)
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

        replay = await self.client.get(f"/v1/tasks/{task_id}/replay", headers=self.headers)
        self.assertEqual(200, replay.status_code)
        self.assertTrue(
            any(event["type"] == "approval.approved" for event in replay.json()["events"])
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

    async def test_replan_returns_diff_and_increments_version(self) -> None:
        created = (
            await self.client.post(
                "/v1/tasks", headers=self.headers, json={"goal": "prepare weekly report"}
            )
        ).json()
        candidate = created["plan"]
        candidate["steps"].append(
            {
                "id": "search_more",
                "description": "search another source",
                "depends_on": [],
                "capability": "knowledge.search",
                "preferred_channel": "api",
                "risk": "R0",
                "requires_approval": False,
                "parameters": {"query": "risk"},
                "expected_effects": [],
                "verification": [{"type": "schema", "rule": "documents.length > 0"}],
            }
        )
        response = await self.client.post(
            f"/v1/tasks/{created['id']}/replan", headers=self.headers, json=candidate
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(2, payload["task"]["plan"]["version"])
        self.assertEqual(["search_more"], payload["diff"]["added"])

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

    async def test_temporal_dispatch_is_tenant_scoped(self) -> None:
        created = (
            await self.client.post(
                "/v1/tasks",
                headers=self.headers,
                json={"goal": "prepare weekly report"},
            )
        ).json()
        task_id = created["id"]
        temporal = Mock()
        temporal.start = AsyncMock()
        temporal.approve = AsyncMock()
        temporal.signal = AsyncMock()
        self.app.state.temporal = temporal

        response = await self.client.post(f"/v1/tasks/{task_id}/run", headers=self.headers)
        self.assertEqual(200, response.status_code)
        temporal.start.assert_awaited_once_with("demo", task_id)

        not_found = await self.client.post(
            f"/v1/tasks/{task_id}/run", headers={"X-Tenant-ID": "other"}
        )
        self.assertEqual(404, not_found.status_code)
        temporal.start.assert_awaited_once()

        waiting = await self.app.state.service.run("demo", task_id)
        approval = waiting.approvals[-1]
        approved = await self.client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=self.headers,
            json={
                "step_id": approval.step_id,
                "parameter_hash": approval.parameter_hash,
            },
        )
        self.assertEqual(200, approved.status_code)
        command = temporal.approve.await_args.args[0]
        self.assertEqual("demo", command.tenant_id)
        self.assertEqual(task_id, command.task_id)

        for action in ("pause", "resume", "cancel"):
            response = await self.client.post(f"/v1/tasks/{task_id}/{action}", headers=self.headers)
            self.assertEqual(200, response.status_code)
        self.assertEqual(3, temporal.signal.await_count)


if __name__ == "__main__":
    unittest.main()

import unittest

from fastapi.testclient import TestClient

from workpilot.api import create_app


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.headers = {"X-Tenant-ID": "demo", "X-User-ID": "api-user"}

    def test_health_and_console(self) -> None:
        self.assertEqual({"status": "ok", "runtime": "fake-enterprise"}, self.client.get("/health").json())
        console = self.client.get("/")
        self.assertEqual(200, console.status_code)
        self.assertIn("WorkPilot Console", console.text)

    def test_create_run_approve_and_replay(self) -> None:
        created = self.client.post(
            "/v1/tasks",
            headers=self.headers,
            json={"goal": "生成并发送本周项目周报", "recipient": "team@example.com"},
        )
        self.assertEqual(201, created.status_code)
        task_id = created.json()["id"]

        waiting = self.client.post(f"/v1/tasks/{task_id}/run", headers=self.headers)
        self.assertEqual(200, waiting.status_code)
        payload = waiting.json()
        self.assertEqual("WAITING_APPROVAL", payload["status"])
        pending = payload["approvals"][-1]

        approved = self.client.post(
            f"/v1/tasks/{task_id}/approve",
            headers=self.headers,
            json={"step_id": pending["step_id"], "parameter_hash": pending["parameter_hash"]},
        )
        self.assertEqual(200, approved.status_code)
        self.assertEqual("RUNNING", approved.json()["status"])

        replay = self.client.get(f"/v1/tasks/{task_id}/replay", headers=self.headers)
        self.assertEqual(200, replay.status_code)
        self.assertTrue(any(event["type"] == "approval.approved" for event in replay.json()["events"]))

    def test_cross_tenant_task_access_returns_not_found(self) -> None:
        created = self.client.post(
            "/v1/tasks", headers=self.headers, json={"goal": "prepare weekly report"}
        ).json()
        response = self.client.get(
            f"/v1/tasks/{created['id']}", headers={"X-Tenant-ID": "other"}
        )
        self.assertEqual(404, response.status_code)

    def test_knowledge_documents_are_tenant_scoped(self) -> None:
        response = self.client.post(
            "/v1/knowledge/documents",
            headers={"X-Tenant-ID": "tenant-a"},
            json={"title": "Template", "content": "private"},
        )
        self.assertEqual(201, response.status_code)
        documents = self.client.app.state.fake_adapter.state.documents
        created = next(item for item in documents if item["id"] == response.json()["id"])
        self.assertEqual("tenant-a", created["tenant_id"])


if __name__ == "__main__":
    unittest.main()

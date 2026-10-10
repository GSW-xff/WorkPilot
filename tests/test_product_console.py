import unittest
from pathlib import Path

import httpx

from workpilot.api import create_app

ROOT = Path(__file__).parents[1]


class ProductConsoleApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.app = create_app()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )
        self.headers = {"X-Tenant-ID": "demo", "X-User-ID": "creator"}

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.app.state.service.repository.close()

    async def test_templates_approval_inbox_audit_feedback_and_eval_dashboard(self) -> None:
        auth = await self.client.get("/v1/auth/config")
        self.assertEqual("headers", auth.json()["mode"])
        templates = await self.client.get("/v1/templates", headers=self.headers)
        self.assertEqual(
            {"weekly-report", "meeting-followup", "issue-summary"},
            {item["id"] for item in templates.json()},
        )

        created = await self.client.post(
            "/v1/tasks",
            headers=self.headers,
            json={"goal": "prepare and send a weekly report"},
        )
        task_id = created.json()["id"]
        await self.client.post(f"/v1/tasks/{task_id}/run", headers=self.headers)

        inbox = await self.client.get("/v1/approvals", headers=self.headers)
        self.assertEqual(1, len(inbox.json()))
        self.assertEqual(task_id, inbox.json()[0]["task_id"])

        audit = await self.client.get(f"/v1/tasks/{task_id}/audit-export", headers=self.headers)
        self.assertEqual("workpilot.audit.v1", audit.json()["schema"])
        self.assertIn("attachment", audit.headers["content-disposition"])
        self.assertEqual(
            len(audit.json()["task"]["events"]), audit.json()["integrity"]["event_count"]
        )

        feedback = await self.client.post(
            "/v1/feedback",
            headers=self.headers,
            json={"task_id": task_id, "category": "confusing", "rating": 2, "comment": "risk copy"},
        )
        self.assertEqual({"id": "feedback-1", "accepted": True}, feedback.json())
        self.assertEqual("demo", self.app.state.feedback[0]["tenant_id"])

        evaluations = await self.client.get("/v1/evaluations/latest", headers=self.headers)
        self.assertEqual(60, evaluations.json()["agent"]["dataset_cases"])
        self.assertEqual(10, evaluations.json()["retrieval"]["case_count"])

    def test_console_contains_required_product_surfaces(self) -> None:
        page = (ROOT / "apps" / "web" / "index.html").read_text()
        for surface in (
            "审批 Inbox",
            "计划 DAG",
            "实时 Timeline",
            "知识与引用",
            "受控 Memory",
            "恢复中心",
            "评测看板",
            "导出审计包",
            "OIDC Bearer Token",
            "授权 GitHub",
        ):
            with self.subTest(surface=surface):
                self.assertIn(surface, page)
        self.assertIn("refreshTask", page)
        self.assertIn("setInterval", page)


if __name__ == "__main__":
    unittest.main()

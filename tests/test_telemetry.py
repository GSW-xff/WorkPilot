from __future__ import annotations

import unittest

import httpx

from workpilot.api import create_app
from workpilot.connectors.base import CapabilityRegistry
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.model_gateway import DeterministicModelGateway, Message, ModelPolicy, RunBudget
from workpilot.models import TaskPlan
from workpilot.planner import DemoPlanner
from workpilot.repository import InMemoryTaskRepository
from workpilot.runtime import WorkPilotService
from workpilot.telemetry import TELEMETRY


class TelemetryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        TELEMETRY.reset()

    async def test_runtime_emits_layered_spans_and_metrics_without_parameters(self) -> None:
        service = WorkPilotService(
            InMemoryTaskRepository(), CapabilityRegistry([FakeEnterpriseAdapter()])
        )
        task = service.create_task("demo", "user", "private project report")
        await service.run("demo", task.id)
        names = {span.name for span in TELEMETRY.finished_spans}
        self.assertTrue(
            {"task.run", "policy.evaluate", "tool.lookup", "tool.execute", "tool.verify"} <= names
        )
        serialized = repr(TELEMETRY.finished_spans)
        self.assertNotIn("private project report", serialized)
        self.assertNotIn("project-owner@example.com", serialized)
        metrics = TELEMETRY.metrics.render_prometheus()
        self.assertIn("tool_call_total", metrics)
        self.assertIn("task_duration_seconds_count", metrics)

    async def test_model_usage_cost_and_latency_are_observable(self) -> None:
        candidate = DemoPlanner().plan("report").model_dump(mode="json")
        gateway = DeterministicModelGateway(responses=[candidate])
        await gateway.generate_structured(
            messages=[Message(role="user", content="sensitive prompt")],
            output_schema=TaskPlan,
            model_policy=ModelPolicy(
                provider="fake",
                model="deterministic",
                input_cost_per_million=1,
                output_cost_per_million=1,
            ),
            budget=RunBudget(),
            metadata={"tenant_id": "demo", "task_id": "task", "trace_id": "trace"},
        )
        metrics = TELEMETRY.metrics.render_prometheus()
        self.assertIn("model_token_usage_total", metrics)
        self.assertIn("model_cost_usd_total", metrics)
        self.assertIn("model_latency_seconds_count", metrics)
        span = next(item for item in TELEMETRY.finished_spans if item.name == "model.plan")
        self.assertNotIn("sensitive prompt", repr(span))

    async def test_api_propagates_request_id_and_exposes_prometheus(self) -> None:
        app = create_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            health = await client.get("/health", headers={"X-Request-ID": "request-123"})
            self.assertEqual("request-123", health.headers["X-Request-ID"])
            metrics = await client.get("/metrics")
            self.assertEqual(200, metrics.status_code)
            self.assertIn("api_request_duration_seconds", metrics.text)
        app.state.service.repository.close()


if __name__ == "__main__":
    unittest.main()

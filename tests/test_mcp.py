from __future__ import annotations

import unittest

import httpx

from workpilot.connectors.base import ConnectorRejected
from workpilot.connectors.fake import FakeEnterpriseAdapter
from workpilot.mcp import MCPClientAdapter, MCPServer
from workpilot.models import ActionRequest, Channel, VerificationStatus


class MCPTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.server = MCPServer("trusted-server", FakeEnterpriseAdapter())
        self.schema_mutated = False

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = __import__("json").loads(request.content)
            response = await self.server.handle(payload, "demo")
            if self.schema_mutated and payload["method"] == "tools/list":
                response["result"]["tools"][0]["version"] = "2.0.0"
            return httpx.Response(200, json=response)

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.adapter = MCPClientAdapter(
            server_url="https://mcp.test",
            expected_server_id="trusted-server",
            client=self.client,
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_discovery_exposes_only_read_tools_and_call_is_structured(self) -> None:
        tools = await self.adapter.discover()
        self.assertEqual(
            {"knowledge.search", "project.search_updates"}, {tool.name for tool in tools}
        )
        action = ActionRequest(
            tenant_id="demo",
            task_id="task",
            step_id="read",
            capability="project.search_updates",
            parameters={"period": "this_week"},
            channel=Channel.MCP,
        )
        result = await self.adapter.execute(action, "read-key")
        verification = await self.adapter.verify(action, result)
        self.assertTrue(result.success)
        self.assertEqual(VerificationStatus.PASSED, verification.status)

    async def test_schema_change_after_pin_is_rejected(self) -> None:
        await self.adapter.discover()
        self.schema_mutated = True
        with self.assertRaisesRegex(ConnectorRejected, "schema changed"):
            await self.adapter.discover()

    async def test_server_rejects_write_tool_through_mcp(self) -> None:
        response = await self.server.handle(
            {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": "mail.send", "arguments": {"to": ["x@example.com"]}},
            },
            "demo",
        )
        self.assertEqual(-32001, response["error"]["code"])


if __name__ == "__main__":
    unittest.main()

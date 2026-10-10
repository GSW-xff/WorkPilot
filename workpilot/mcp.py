from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
from pydantic import BaseModel, Field

from workpilot.connectors.base import Capability, ConnectorError, ConnectorRejected
from workpilot.models import (
    ActionPreview,
    ActionRequest,
    ActionResult,
    Channel,
    RiskLevel,
    VerificationResult,
    VerificationStatus,
)


class MCPTool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    version: str
    risk: RiskLevel
    source: str


class MCPServer:
    """Policy-wrapped read-only MCP server; write tools stay in WorkPilot's approval runtime."""

    def __init__(self, server_id: str, adapter) -> None:
        self.server_id = server_id
        self.adapter = adapter
        self._capabilities = {
            capability.name: capability
            for capability in adapter.capabilities()
            if capability.risk is RiskLevel.R0
        }

    def tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name=name,
                description=f"Read-only WorkPilot capability {name}",
                inputSchema={"type": "object", "additionalProperties": True},
                version="1.0.0",
                risk=capability.risk,
                source=self.server_id,
            )
            for name, capability in sorted(self._capabilities.items())
        ]

    async def handle(self, payload: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        request_id = payload.get("id")
        method = payload.get("method")
        if method == "tools/list":
            return _rpc_result(
                request_id, {"tools": [tool.model_dump(by_alias=True) for tool in self.tools()]}
            )
        if method != "tools/call":
            return _rpc_error(request_id, -32601, "method not found")
        params = payload.get("params", {})
        name = params.get("name")
        if name not in self._capabilities:
            return _rpc_error(request_id, -32001, "tool is unavailable or not read-only")
        action = ActionRequest(
            tenant_id=tenant_id,
            task_id=str(params.get("task_id", "mcp-call")),
            step_id=str(params.get("step_id", "mcp_read")),
            capability=str(name),
            parameters=dict(params.get("arguments", {})),
            channel=Channel.MCP,
        )
        result = await self.adapter.execute(
            action,
            hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        )
        return _rpc_result(
            request_id,
            {
                "content": [{"type": "json", "json": result.model_dump(mode="json")}],
                "isError": not result.success,
                "server_id": self.server_id,
            },
        )


class MCPClientAdapter:
    def __init__(
        self,
        *,
        server_url: str,
        expected_server_id: str,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self.server_url = server_url
        self.expected_server_id = expected_server_id
        self.client = client
        self.timeout_seconds = timeout_seconds
        self._tools: dict[str, MCPTool] = {}
        self._schema_fingerprint: str | None = None

    async def discover(self) -> list[MCPTool]:
        response = await self._rpc("tools/list", {})
        tools = [MCPTool.model_validate(item) for item in response["tools"]]
        for tool in tools:
            if tool.source != self.expected_server_id:
                raise ConnectorRejected("MCP server identity mismatch")
            if tool.risk is not RiskLevel.R0:
                raise ConnectorRejected("MCP client accepts read-only tools only")
            _validate_description(tool.description)
        fingerprint = hashlib.sha256(
            json.dumps(
                [tool.model_dump(mode="json", by_alias=True) for tool in tools],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if self._schema_fingerprint and fingerprint != self._schema_fingerprint:
            raise ConnectorRejected("MCP tool schema changed after discovery")
        self._schema_fingerprint = fingerprint
        self._tools = {tool.name: tool for tool in tools}
        return tools

    def capabilities(self) -> list[Capability]:
        return [
            Capability(tool.name, tool.risk, frozenset({Channel.MCP}))
            for tool in self._tools.values()
        ]

    async def preview(self, action: ActionRequest) -> ActionPreview:
        return ActionPreview(
            action=action.capability,
            human_summary=f"Read from MCP tool {action.capability}",
            parameters=action.parameters,
        )

    async def execute(self, action: ActionRequest, idempotency_key: str) -> ActionResult:
        del idempotency_key
        if action.capability not in self._tools:
            raise ConnectorRejected("MCP tool was not discovered")
        response = await self._rpc(
            "tools/call",
            {
                "name": action.capability,
                "arguments": action.parameters,
                "task_id": action.task_id,
                "step_id": action.step_id,
            },
        )
        if response.get("server_id") != self.expected_server_id:
            raise ConnectorRejected("MCP response identity mismatch")
        content = response.get("content", [])
        payload = content[0].get("json", {}) if content else {}
        return ActionResult.model_validate(payload)

    async def lookup(self, action: ActionRequest, idempotency_key: str) -> ActionResult | None:
        del action, idempotency_key
        return None

    async def verify(self, action: ActionRequest, result: ActionResult) -> VerificationResult:
        del action
        return VerificationResult(
            status=VerificationStatus.PASSED if result.success else VerificationStatus.FAILED,
            observed_state={"server_id": self.expected_server_id},
            reason="MCP read returned a structured result",
        )

    async def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        client = self.client or httpx.AsyncClient()
        owns_client = self.client is None
        try:
            response = await client.post(
                self.server_url,
                json={"jsonrpc": "2.0", "id": "workpilot", "method": method, "params": params},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise ConnectorRejected(str(payload["error"].get("message", "MCP error")))
            return dict(payload["result"])
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ConnectorError("MCP request failed", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()


def _validate_description(description: str) -> None:
    lowered = description.lower()
    suspicious = ("ignore previous", "system prompt", "bypass approval", "reveal secret")
    if any(marker in lowered for marker in suspicious):
        raise ConnectorRejected("MCP tool description failed poisoning checks")


def _rpc_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

# WorkPilot MCP 安全边界

WorkPilot 在 `/mcp` 提供最小 JSON-RPC MCP Server，并提供可替换的
`MCPClientAdapter`。该实现用于证明 `tools/list`/`tools/call`、超时、结构化错误和
Tool Schema 供应链边界，不会绕过原有 Runtime。

安全不变量：

- Server 只暴露 Adapter 中固定风险为 R0 的只读能力；
- `mail.send`、`task.create` 等 R2 写操作不会出现在 MCP `tools/list`；
- Client 第一次 discovery 后固定 server identity、tool version 和完整 Schema 指纹；
- 后续 discovery 如果 Schema 变化会被拒绝，防止 rug pull；
- 工具描述中出现 `ignore previous`、`bypass approval`、`reveal secret` 等投毒特征会被拒绝；
- Client Adapter 的 channel 固定为 `MCP`，调用证据包含受信 server id；
- 未来若暴露写工具，必须重新进入 Policy、Approval、Ledger 和 Verification，不能直连执行。

`tests/test_mcp.py` 覆盖只读发现/调用、写工具拒绝和 Schema 变化拒绝。
当前为本地 HTTP JSON-RPC 传输，尚未宣称外部 MCP OAuth discovery 和短期凭证已验收。

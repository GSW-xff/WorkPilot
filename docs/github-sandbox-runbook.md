# GitHub OAuth 沙箱 E2E Runbook

## 前置条件

使用专用 OAuth App、一次性授权 token 和允许留下已关闭测试 Issue 的专用仓库。OAuth token
Scope 必须严格等于 `repo read:user`；runner 会拒绝缺失或额外 Scope。配置：

```bash
export WORKPILOT_GITHUB_CLIENT_ID='...'
export WORKPILOT_GITHUB_CLIENT_SECRET='...'
export WORKPILOT_GITHUB_WEBHOOK_SECRET='...'
export WORKPILOT_GITHUB_SANDBOX_TOKEN='...'
export WORKPILOT_GITHUB_SANDBOX_REPO='owner/disposable-repository'
```

GitHub 不提供删除 Issue 的 API，因此 fixture 清理策略是删除测试评论并关闭测试 Issue；报告会
记录所有远端 id 和清理错误。默认运行结束会通过 OAuth App token endpoint 远程撤销 token，
随后删除本地 Secret。`--keep-token` 仅用于调试，使用后报告不能作为完整 P0-3 证据。

## Webhook delivery 证据

把 OAuth App/仓库 webhook 指向可访问的 WorkPilot
`POST /v1/connectors/github/webhook`。响应中的 `evidence` 只含 delivery id、event、repository、
payload SHA-256 和 `signature_valid=true`，不含 payload 或 Secret。将该对象保存为 JSON，并在
验收时传入：

```bash
uv run workpilot-github-sandbox \
  --repository "$WORKPILOT_GITHUB_SANDBOX_REPO" \
  --webhook-evidence /path/to/webhook-evidence.json
```

## 验收矩阵

| 检查 | 证据来源 |
| --- | --- |
| OAuth token 归属、用户和严格最小 Scope | GitHub sandbox |
| 仓库访问、Issue、评论、读取验证和重启后幂等 lookup | GitHub sandbox |
| 成功 POST 后发生响应丢失，下一次 lookup 恢复且重复副作用为 0 | GitHub sandbox |
| GitHub webhook delivery | GitHub 返回的签名验证 evidence |
| 签名错误/重放拒绝 | 本地确定性契约 |
| 429 遵守 Retry-After | 故障注入 |
| 写入 5xx 标记 UNKNOWN 且不直接重试 POST | 故障注入 |
| 评论删除、Issue 关闭、OAuth token 远程撤销 | GitHub sandbox |

只有全部检查为 `passed`、cleanup 无错误、token 已撤销时，命令才返回 0。JSON/Markdown 报告
默认写入 `evals/reports/github-sandbox/`，其中不包含 token、client secret 或 webhook secret。

## 当前状态

runner、安全重试修复和 MockTransport/故障注入测试已完成。2026-10-11 的本机环境没有 OAuth
凭证、专用仓库或真实 delivery evidence，因此尚无真实 GitHub 沙箱通过报告。

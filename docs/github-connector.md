# GitHub Issues 连接器

WorkPilot 的第一个真实 HTTP 连接器面向 GitHub Issues。它提供 Issue 列表/读取、
创建 Issue 和评论能力，写操作固定为 R2，仍必须经过 WorkPilot 的参数哈希审批、
Action Ledger 和独立验证。

## OAuth 配置

在 GitHub OAuth App 中把 callback URL 设为：

```text
http://127.0.0.1:8000/v1/connectors/github/callback
```

然后配置：

```bash
export WORKPILOT_GITHUB_CLIENT_ID='...'
export WORKPILOT_GITHUB_CLIENT_SECRET='...'
export WORKPILOT_GITHUB_STATE_SECRET='a-long-random-local-secret'
export WORKPILOT_GITHUB_WEBHOOK_SECRET='...'
```

访问 `GET /v1/connectors/github/authorize` 取得授权 URL。OAuth state 绑定 tenant/user、
带 HMAC 签名并在 10 分钟后过期。令牌值只进入 `SecretStore`，ConnectorAccount、
Planner、Timeline、Artifact 和日志只能看到 `secret://...` 引用。开发环境的
`InMemorySecretStore` 不适用于生产，生产应替换为 Vault 或云 Secret Manager。

## 可靠性与安全边界

- API 请求带 15 秒上限，并继承 Runtime 的 action deadline；
- 同一 Adapter 默认最多 4 个并发请求；
- 429/限流响应遵守 `Retry-After`，5xx/网络错误有有限退避；
- 连续网络/5xx 失败会打开 30 秒熔断器；
- 写操作在正文写入幂等 marker，重试前使用 GitHub Search 对账；
- Webhook 验证 `X-Hub-Signature-256`，并按 `X-GitHub-Delivery` 拒绝重放；
- Adapter 会拒绝使用其他租户的 ConnectorAccount；
- 撤销后 Secret 立即删除，账户状态变为 `REVOKED`。

## 测试证据与尚未声明的能力

`tests/test_github_connector.py` 使用 HTTP MockTransport 对 OAuth、Scope、Secret 隔离、
Issue 契约、幂等查询、限流和 Webhook 进行自动化测试。这些是真实 GitHub HTTP
契约的离线验证，不是沙箱账号 E2E。在配置用户自己的 GitHub OAuth App 和沙箱
仓库并跑通前，不应在简历中写“GitHub 沙箱端到端已验收”。

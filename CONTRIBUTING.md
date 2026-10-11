# 参与贡献

感谢你改进 WorkPilot。项目优先接受可验证、范围明确，并且不削弱安全边界的改动。

## 开发环境

需要 Python 3.12+、Git 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <repository-url>
cd WorkPilot
uv sync --extra dev --locked
make check
```

本地演示不依赖数据库、Temporal 或外部账号：

```bash
uv run workpilot
```

如需自定义配置，复制 `.env.example`，只在本地 `.env` 中填写凭据，并使用
`uv run --env-file .env workpilot` 启动。不要提交 `.env`、真实 token、用户数据或外部服务报告。

## 提交改动

1. 从最新的 `main` 创建短生命周期分支。
2. 为行为变化增加或更新自动化测试。
3. 同步更新 README、运行手册或架构文档。
4. 运行 `make release-check`，确认 lint、类型检查、测试和构建全部通过。
5. 使用清晰的 Conventional Commit 风格提交，例如 `fix: reject stale approval hashes`。
6. 创建 PR，并说明问题、方案、验证结果和安全影响。

涉及外部 SaaS 写入、OAuth、审批、租户隔离、幂等或凭据边界的改动，必须说明失败模式和回滚方式。
真实模型、GitHub 沙箱和用户研究结果必须来自可复现的实际运行，不得用模拟结果替代。

## 报告安全问题

不要为漏洞创建公开 Issue。请按照 [安全策略](SECURITY.md) 使用 GitHub Private
Vulnerability Reporting 联系维护者。

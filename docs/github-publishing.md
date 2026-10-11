# GitHub 发布清单

本文用于把当前仓库作为一个可复现、可协作的公开项目首次发布到 GitHub。仓库不会自动创建远端，
也不会把本地凭据或未验证的外部运行结果上传。

## 1. 发布前验证

在仓库根目录运行：

```bash
make release-check
git status --short
git log -1 --oneline
```

预期结果：lint、mypy、pytest 和 Python sdist/wheel 构建全部通过，`git diff --check` 无输出，
`git status --short` 为空。可选的 Temporal、PostgreSQL、浏览器和真实 SaaS 集成测试需要对应服务或
凭据，默认测试会明确跳过它们。

发布前还应人工确认：

- `.env`、数据库、缓存、Office 临时文件和本地评测 profile 未被 Git 跟踪；
- 仓库及其历史中没有 token、私钥、用户数据或内部 URL；
- README 中对真实模型、GitHub 沙箱、生产 SLO 和用户研究的声明与证据一致；
- 许可证选择符合所有贡献者和依赖的授权要求。

## 2. 创建并推送远端

在 GitHub 创建一个**空仓库**，不要额外生成 README、`.gitignore` 或 LICENSE。然后运行：

```bash
git remote add origin git@github.com:<owner>/WorkPilot.git
git push -u origin main
```

若使用 HTTPS，把远端替换为 `https://github.com/<owner>/WorkPilot.git`。如果已经存在 `origin`，先用
`git remote -v` 核对，不要直接覆盖未知远端。

## 3. GitHub 仓库设置

首次 Actions 完成后建议启用：

1. `main` 分支保护，要求 PR、至少一次 review、分支为最新状态，并选择已经出现的 CI 检查为必需；
2. Secret scanning、Push protection、Dependabot alerts 和 Private Vulnerability Reporting；
3. 自动删除已合并分支，并禁用不需要的 merge 策略；
4. Actions 默认 `contents: read`，只让工作流中的特定 job 提升权限；
5. 仓库描述与 topics，例如 `ai-agent`、`workflow-automation`、`fastapi`、`temporal`、`python`。

## 4. 首次远端验收

- CI 的质量、PostgreSQL RLS、CodeQL、镜像扫描、SBOM 和 Helm contract job 通过；
- GitHub 正确识别 MIT License、README、贡献指南和安全策略；
- 新建测试 Issue/PR，确认模板和分支保护工作正常；
- 从全新目录 clone，运行 `uv sync --extra dev --locked && make check && uv run workpilot`；
- 仅在真实外部验证完成后，再提交对应脱敏报告并更新能力声明。

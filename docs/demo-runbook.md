# 8 分钟面试 Demo 脚本

本脚本可以直接录屏，但仓库不声称视频已经录制。建议预先启动 Console、Prometheus、
Grafana 和 Temporal，并准备一条允许域名内的收件人。

| 时间 | 操作 | 要证明的能力 |
| --- | --- | --- |
| 0:00–0:45 | 用一句业务目标创建周报任务 | 自然语言进入结构化 DAG，而非自由执行 |
| 0:45–1:40 | 打开计划和 Context Snapshot | Schema、信任标签、预算、注入标记和可回退规划 |
| 1:40–2:40 | 执行到 R2 审批，展示预览与参数哈希 | 模型不能绕过确定性风险策略 |
| 2:40–3:30 | 用错误哈希审批一次，再用正确哈希审批 | 审批绑定具体动作参数 |
| 3:30–4:30 | 展示 Timeline、Ledger、验证和 Artifact | 工具 success 不等于业务事实，必须独立读取验证 |
| 4:30–5:30 | 讲解响应丢失报告并打开恢复中心 | UNKNOWN、lookup-before-retry、无重复副作用 |
| 5:30–6:20 | 打开 Tempo/Grafana/Prometheus 告警规则 | 跨层 Trace、P95、成本和误差预算 |
| 6:20–7:10 | 打开 Eval 面板和基线对比 | 固定数据集、失败分类、安全与回归门禁 |
| 7:10–8:00 | 打开架构图和边界页 | 说明真实证据、尚未完成的 SaaS/用户研究和取舍 |

## 录制前验收

1. `make check` 全部通过；
2. 真实 Temporal、PostgreSQL RLS 和 Browser gated tests 分别通过；
3. Alert 规则通过 `promtool check config`；
4. 演示账号只授予必要 GitHub Scope，Secret 不出现在画面、日志或 Trace；
5. 录屏后逐项核对画面中的数字与 `docs/resume-evidence.md`，不得口述目标值为实测值。

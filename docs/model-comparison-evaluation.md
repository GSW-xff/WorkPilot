# 真实模型对比评测

## 能力与边界

`workpilot-model-eval` 在同一数据集、Prompt/Schema 版本和预算下，对至少两个
OpenAI-compatible 模型重复评测，同时嵌入确定性 Planner 基线。它记录：

- 系统通过率、Tool precision/recall、审批召回、安全违规和 disposition；
- 模型原生计划率、确定性 fallback 率、一次修复率和失败分类；
- 每次调用的脱敏 trace/request id、输入/输出 Token、重试、成本与总时延；
- P50/P95、每成功任务成本及多次运行分数方差；
- per-profile 质量、安全、延迟和成本阈值。

报告不保存 API Key 或 Prompt 正文。自动规则不能替代人工质量判断，因此同时生成随机排序的
`blind-review.jsonl` 和单独的 `blind-review-key.json`。评审者先填写 acceptable、安全问题、
遗漏能力和备注，再使用 key 解盲；不得先看模型身份。

## 配置与执行

```bash
cp evals/model-profiles.template.json evals/model-profiles.local.json
```

填写真实 provider、model、base URL、供应商当时公布的输入/输出价格及阈值。不要把 Key 写入
JSON；`api_key_env` 只填写环境变量名。然后设置两个 Key 并运行：

```bash
export WORKPILOT_PRIMARY_MODEL_API_KEY='...'
export WORKPILOT_ECONOMY_MODEL_API_KEY='...'
make eval-models
```

标准验收要求 60 cases × 3 repetitions × 2 models。`--enforce-quality` 会在任一 profile 未满足
通过率、native plan、安全、未授权写入、P95 或成本阈值时返回非零状态。报告默认写入
`evals/reports/model-comparison/`。

## 当前状态

runner、报告、质量门禁和 contract test 已完成。2026-10-11 的本机环境没有两个模型 Key，
因此仓库没有真实模型报告，也不能在简历中声称真实模型成功率、成本或延迟。

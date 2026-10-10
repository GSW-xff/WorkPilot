# 响应丢失故障注入复盘

这是一份自动化故障注入复盘，不是真实生产事故，也不虚构用户影响。对应测试为
`RuntimeTest.test_unknown_result_is_looked_up_before_retry`，完整 Temporal 证据见
`docs/reports/temporal-fault-injection.md`。

## 事件

连接器已在“远端”提交报告对象，但调用方收到超时。第一次执行后 Ledger 为
`UNKNOWN/REQUIRED`，记录 attempt、错误和下一次恢复所需状态。

## 预期风险

若直接重试写动作，可能创建第二个远端对象；若直接标记失败，用户又无法确认业务事实。

## 系统响应

恢复时先用稳定 idempotency key 调用 `lookup`。Adapter 返回已存在对象后，Runtime 把同一
Ledger 项确认成 `CONFIRMED` 并进入独立 verify，没有再次执行写动作。

## 证据

- 故障后状态：`UNKNOWN`，reconciliation：`REQUIRED`；
- 恢复后状态：`CONFIRMED`；
- `report.compose` 实际执行次数：1；
- 同键 100 次投递的远端对象数：1，重复业务副作用：0；
- 真实 Temporal 开发服务 Worker 重启与 History replay：通过。

## 后续动作

真实 GitHub 沙箱仍需制造“服务端提交成功、客户端连接断开”的可控故障，并以远端 issue id
核验。当前 Fake Adapter 证据不能替代真实 SaaS provider 行为。

# PostgreSQL 备份与恢复

WorkPilot 对 tenant 表启用了 `FORCE ROW LEVEL SECURITY`。因此应用角色和 schema owner
都不能做全租户逻辑备份，这是预期的 fail-closed 行为。备份必须使用独立、受审计、仅在备份
窗口可用的角色；该角色需要读取全部 schema/sequence/table，并具有 `BYPASSRLS`。不要复用
API/Worker 的 `workpilot_app` 凭证。

本地 Compose 为了可复现，脚本默认使用容器内 `postgres` 超级用户。生产环境应通过
`WORKPILOT_BACKUP_DATABASE_USER` 指向专用备份角色，并从 Secret Store 注入凭证。

```bash
make db-up
make backup BACKUP_PATH=/absolute/path/workpilot.dump
make restore-drill BACKUP_PATH=/absolute/path/workpilot.dump
```

备份使用 PostgreSQL custom format、`--no-owner` 和 `--no-acl`，输出字节数和 SHA-256。
恢复脚本只使用固定隔离库 `workpilot_restore_drill`，对比源库/恢复库 public 表数并检查
`alembic_version`，无论成功或失败都会删除演练库。它不会覆盖 `workpilot` 数据库。
恢复时由管理员先在隔离库安装 `vector` 扩展，再由 `workpilot_owner` 恢复业务对象。
最新实测记录见 `docs/reports/backup-restore-drill.md`。

当前演练是单机逻辑备份，不证明 PITR、WAL 归档、跨区域恢复或生产 RPO/RTO；这些能力必须
在目标云和存储保留策略确定后单独验收。

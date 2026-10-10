# PostgreSQL 备份恢复演练报告

- 执行日期：2026-10-10
- 数据库：`pgvector/pgvector:pg16`（Docker Desktop）
- 备份格式：PostgreSQL custom format，`--no-owner --no-acl`
- 最终结果：通过

## 最终实测

| 项目 | 结果 |
| --- | --- |
| 备份大小 | 31,418 bytes |
| 备份 SHA-256 | `46f56d972d6901807174dd0ac1cd9c99ea8dc29c4a88ef811e8a253653710a8c` |
| 本地备份耗时 | 0.44 s |
| 本地恢复与校验耗时 | 0.99 s |
| 源库 public 基础表 | 10 |
| 恢复库 public 基础表 | 10 |
| 恢复库 Alembic 行数 | 1 |
| 演练库清理后残留 | 0 |

## 演练发现并修复的问题

1. 首次使用 `workpilot_owner` 备份失败：`FORCE ROW LEVEL SECURITY` 正确阻止了全租户
   读取。备份脚本改为可配置专用备份身份；本地 Compose 默认 `postgres`，生产要求独立
   `BYPASSRLS` 备份角色。
2. 首次恢复时 owner 无权创建 `vector` 扩展。流程改为管理员先在隔离库安装扩展，再由
   `workpilot_owner` 恢复业务 schema，并跳过不影响业务数据的扩展注释。

脚本通过 `trap` 在成功或失败时删除固定隔离库 `workpilot_restore_drill`，没有覆盖源库。

## 证据边界

0.99 秒是本机 31 KB 空数据/小数据逻辑备份的恢复时间，不是生产 RTO；单次 dump 也不能
定义生产 RPO。尚未验证 WAL/PITR、对象存储保留、加密密钥恢复、跨区域下载或大数据量恢复。

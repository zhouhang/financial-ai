# MCP 数据库迁移脚本

当前目录包含基线脚本与后续增量脚本，按文件名顺序执行即可完成初始化和功能演进。

## 执行顺序

按文件名顺序执行以下脚本：

1. **001_initial_schema.sql** - 当前完整表结构、函数、索引、触发器、外键、视图
2. **002_seed_data.sql** - 当前完整初始化数据
3. **003_company_channel_configs.sql** - 公司通知渠道配置
4. **004_data_connection_tables.sql** - 数据连接（平台应用、店铺连接、授权、同步源、授权会话）
5. **005_unified_data_source_model.sql** - 通用数据连接模型（data_sources、sync_jobs 等）
6. **006_recon_auto_closure_tables.sql** - 自动对账任务与异常闭环模型（recon_auto_tasks / recon_auto_runs / recon_exception_tasks / recon_run_jobs）
7. **007_data_source_datasets_and_health.sql** - 数据集目录模型（data_source_datasets）与 source/dataset 健康状态字段
8. **008_recon_auto_tasks_rule_id.sql** - 为 recon_auto_tasks 增量补齐 rule_id 字段
9. **009_execution_scheme_run_model.sql** - 对账方案与运行计划模型（execution_schemes / execution_run_plans / execution_runs / execution_run_exceptions）
10. **016_dataset_collection_records.sql** - 采集资产层明细记录，替代旧 raw/snapshot 主链路
11. **017_drop_raw_snapshot_collection_tables.sql** - 删除旧 raw/snapshot/checkpoint 表
12. **018_drop_sync_jobs_idempotency_index.sql** - 删除采集任务级幂等索引，任务只保留审计记录，幂等由采集数据层处理

## 使用方法

```bash
# 在 finance-mcp 目录下执行
cd finance-mcp

# 按文件名顺序执行全部迁移
for file in auth/migrations/*.sql; do
  psql -h localhost -p 5432 -U tally_user -d tally -v ON_ERROR_STOP=1 -f "$file"
done
```

或使用环境变量一次性执行：

```bash
for file in auth/migrations/*.sql; do
  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -v ON_ERROR_STOP=1 -f "$file"
done
```

## 数据说明

`001_initial_schema.sql` 当前包含：
- `admins`
- `company`
- `conversations`
- `departments`
- `messages`
- `rule_detail`
- `user_tasks`
- `users`

`002_seed_data.sql` 当前包含上述表在导出时刻的真实数据快照，包括：
- 管理员、公司、部门、用户
- 当前任务与规则数据
- 对话与消息历史

## 注意事项

- `001_initial_schema.sql` 基于当前库的 schema dump 生成，并补充了 `uuid-ossp` 扩展创建语句
- `002_seed_data.sql` 直接基于当前库的 data dump 生成
- `003` 之后的脚本为基线之后的增量迁移，需继续按文件名顺序执行
- 首次安装请先创建空数据库：`CREATE DATABASE tally;`
- 若需重建，请先 `DROP DATABASE tally; CREATE DATABASE tally;` 再按顺序执行

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
10. **010_execution_run_plans_add_monthly_schedule.sql** - 为运行计划增加月度调度配置
11. **011_rule_detail_supported_entry_modes.sql** - 为规则详情增加支持的入口模式
12. **012_ods_yxst_trd_order_di_o_structure.sql** - 新增有赞订单 ODS 明细结构
13. **013_data_source_dataset_catalog_fields.sql** - 补齐数据集目录发布与检索字段
14. **014_expand_dataset_bindings_scope_role_constraints.sql** - 扩展数据集绑定范围与角色约束
15. **015_remove_file_count_from_file_validation_rules.sql** - 删除文件校验规则中的 file_count 字段
16. **016_dataset_collection_records.sql** - 采集资产层明细记录，替代旧 raw/snapshot 主链路
17. **017_drop_raw_snapshot_collection_tables.sql** - 删除旧 raw/snapshot/checkpoint 表
18. **018_drop_sync_jobs_idempotency_index.sql** - 删除采集任务级幂等索引，任务只保留审计记录，幂等由采集数据层处理
19. **019_recon_execution_queue.sql** - 新增对账执行队列表
20. **020_execution_runs_trigger_type_manual_rerun.sql** - 为 execution_runs.trigger_type 增加 manual / rerun 语义
21. **021_drop_dataset_verified_status.sql** - 删除数据集语义验证状态字段，发布即代表语义已确认
22. **022_platform_order_lines.sql** - 电商平台订单明细物理表，用于高频订单采集数据集
23. **023_tally_service_provider_company.sql** - 初始化 Tally 服务商公司
24. **024_auth_sessions_extra.sql** - 为平台授权会话增加 extra 元数据，用于记录支付宝商户显示名称等授权上下文
25. **025_platform_alipay_bill_lines.sql** - 支付宝账单行物理表，用于支付宝授权采集后的资金账单和交易账单
26. **026_platform_pending_authorizations.sql** - 平台待授权会话
27. **027_sync_jobs_trigger_modes_initial_schedule.sql** - 同步任务触发模式与首次调度字段
28. **028_drop_alipay_derived_business_columns.sql** - 删除支付宝账单英文派生业务列，业务字段仅保留明细 payload
29. **029_clean_alipay_semantic_profiles.sql** - 清理支付宝账单历史语义档案中的隐藏元数据和旧英文派生字段
30. **030_messages_seq_ordering.sql** - 为 messages 表新增单调自增 seq 列,修复聊天记录加载顺序乱序
31. **031_browser_playbook_collection.sql** - 浏览器采集 Playbook、采集记录、文件审计与等待数据队列字段
32. **032_data_sources_browser_playbook_source_kind.sql** - 为数据源 source_kind 增加 browser_playbook
33. **033_browser_handoff_sessions.sql** - 浏览器人工接管会话
34. **034_browser_handoff_lifecycle.sql** - 浏览器人工接管生命周期字段
35. **035_sync_jobs_handoff_statuses.sql** - 同步任务增加人工验证与恢复状态
36. **036_execution_run_exceptions_pending_index.sql** - 待处理异常同步待办状态的部分索引
37. **037_storage_objects_and_browser_capture_oss.sql** - 存储对象元数据表与浏览器采集 OSS 文件字段
38. **038_browser_capture_files_idempotent.sql** - 浏览器采集文件幂等约束
39. **039_recon_period_rollup.sql** - 对账日报全量金额聚合落点
40. **040_recon_view_layout.sql** - 老板/财务公开详情页通用布局配置
41. **041_recon_digest_foundation_tables.sql** - 对账日报 digest、差异明细、归因与预警通用表
42. **042_recon_digest_subscriptions_deliveries.sql** - 对账日报订阅与投递幂等记录

## 使用方法（推荐：迁移运行器 `auth/migrate.py`）

运行器把每个已应用的文件记录在 `schema_migrations` 表里，保证**每条只跑一次、可重复执行、失败即回滚中止**，并用 pg advisory lock 串行化并发运行。连接取 `DATABASE_URL`（缺省则由 `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` 拼装）。

```bash
# 在 finance-mcp 目录下执行
cd finance-mcp

python -m auth.migrate            # 应用全部待执行迁移（默认；发版时自动跑这个）
python -m auth.migrate status     # 查看已应用/待应用，并检测文件漂移（checksum 不匹配）
python -m auth.migrate backfill              # 把现有文件标记为已应用而不执行——“已存在的库”一次性接入
python -m auth.migrate backfill --through 038 # 只回填到指定版本号（含）
```

- **新增迁移**：在 `auth/migrations/` 加 `NNN_xxx.sql`（版本号递增），本地 `python -m auth.migrate` 验证，连同代码一起提交。发版时 GitHub Actions 构建镜像、ECS 端在 `compose pull` 后、`up -d` 前自动执行 `python -m auth.migrate`，只跑新增的那条；失败则中止发版、服务不动。
- 当前最新增量迁移：`043_recon_digest_subscription_natural_key.sql`。
- **全新空库**（本地开发/新环境）：直接 `python -m auth.migrate`，从 001 全量执行，无需 backfill。
- **已存在的库**（本运行器接入前就有数据）：先 `python -m auth.migrate backfill` 标记历史迁移，再 apply。生产库已于接入时完成回填（001–038）。
- 安全护栏：若 `schema_migrations` 为空但库里已有基线表，`apply` 会拒绝执行并提示先 backfill（确需从 001 重跑可设 `MIGRATE_ALLOW_DIRTY_BASELINE=1`）。

> 兜底（无 Python 环境时）：仍可用 psql 按文件名顺序手动执行，但不再推荐——它不追踪状态、易导致 drift。
>
> ```bash
> for file in auth/migrations/*.sql; do
>   psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$file"
> done
> ```

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

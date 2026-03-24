# MCP 数据库迁移脚本

当前目录只保留两份基线脚本，直接对应现在本地 PostgreSQL `tally` 库的真实结构和真实数据，用于初始化或重建数据库。

## 执行顺序

按文件名顺序执行以下两份脚本：

1. **001_initial_schema.sql** - 当前完整表结构、函数、索引、触发器、外键、视图
2. **002_seed_data.sql** - 当前完整初始化数据

## 使用方法

```bash
# 在 finance-mcp 目录下执行
cd finance-mcp

# 按文件名顺序执行全部迁移
for file in auth/migrations/*.sql; do
  psql -h localhost -p 5432 -U tally_user -d tally -f "$file"
done
```

或使用环境变量一次性执行：

```bash
for file in auth/migrations/*.sql; do
  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f "$file"
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
- `v_users_full`

`002_seed_data.sql` 当前包含上述表在导出时刻的真实数据快照，包括：
- 管理员、公司、部门、用户
- 当前任务与规则数据
- 对话与消息历史

## 注意事项

- `001_initial_schema.sql` 基于当前库的 schema dump 生成，并补充了 `uuid-ossp` 扩展创建语句
- `002_seed_data.sql` 直接基于当前库的 data dump 生成
- 目录中已不再保留历史增量迁移；这是“总量基线”，不是“演进历史”
- 首次安装请先创建空数据库：`CREATE DATABASE tally;`
- 若需重建，请先 `DROP DATABASE tally; CREATE DATABASE tally;` 再按顺序执行

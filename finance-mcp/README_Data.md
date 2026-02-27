# MCP 数据库迁移脚本

基于本地 PostgreSQL tally 库的结构和数据生成，用于初始化或重建数据库。

## 执行顺序

1. **001_initial_schema.sql** - 完整表结构（扩展、函数、表、约束、索引、触发器、视图）
2. **002_seed_data.sql** - 初始数据（公司、部门、用户、对账规则、对话记录等）

## 使用方法

```bash
# 在 finance-mcp 目录下执行
cd finance-mcp

# 1. 先执行表结构
psql -h localhost -p 5432 -U tally_user -d tally -f auth/migrations/001_initial_schema.sql

# 2. 再导入数据
psql -h localhost -p 5432 -U tally_user -d tally -f auth/migrations/002_seed_data.sql
```

或使用环境变量一次性执行：

```bash
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f auth/migrations/001_initial_schema.sql
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f auth/migrations/002_seed_data.sql
```

## 数据说明

002_seed_data.sql 包含 tally 库的完整数据导出：
- admins、company、departments、users
- conversations、messages（对话历史）
- reconciliation_rules（对账规则）
- 其他关联表数据

## 注意事项

- 脚本使用 `CREATE TABLE` 而非 `CREATE TABLE IF NOT EXISTS`，在已有表时会报错
- 首次安装请先创建空数据库：`CREATE DATABASE tally;`
- 若需重建，请先 `DROP DATABASE tally; CREATE DATABASE tally;` 再按顺序执行

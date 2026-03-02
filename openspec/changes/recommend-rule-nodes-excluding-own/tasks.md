## 1. 修改数据库函数

- [x] 1.1 修改 `finance-mcp/auth/db.py` 中的 `search_rules_by_field_mapping` 函数，添加可选的 `user_id` 参数
- [x] 1.2 在 SQL 查询中添加过滤条件：当 `user_id` 存在时，排除 `created_by = user_id` 的规则

## 2. 修改 MCP 工具处理器

- [x] 2.1 修改 `finance-mcp/auth/tools.py` 中的 `_handle_search_rules_by_mapping` 函数
- [x] 2.2 从 `auth_token` 中提取当前用户信息
- [x] 2.3 将 `user_id` 传递给 `search_rules_by_field_mapping` 数据库函数

## 3. 测试验证

- [x] 3.1 使用登录用户测试推荐结果，确认不包含自己创建的规则
- [x] 3.2 使用访客用户测试推荐结果，确认包含所有匹配规则
- [x] 3.3 重启服务并验证功能正常

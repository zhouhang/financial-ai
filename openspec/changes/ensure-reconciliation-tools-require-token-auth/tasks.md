## 1. 代码修改

- [x] 1.1 在 `tools.py` 中创建 `_require_auth(args)` 辅助函数，验证 token 并返回用户信息
- [x] 1.2 修改 `_reconciliation_status` 函数，添加 auth_token 参数验证
- [x] 1.3 修改 `_reconciliation_result` 函数，添加 auth_token 参数验证和任务访问权限验证
- [x] 1.4 修改 `_reconciliation_list_tasks` 函数，添加 auth_token 参数验证，只返回当前用户的任务
- [x] 1.5 修改 `_file_upload` 函数，添加 auth_token 参数验证
- [x] 1.6 修改 `_get_reconciliation` 函数，添加 auth_token 参数验证
- [x] 1.7 修改 `_analyze_files` 函数，添加 auth_token 参数验证

## 2. TaskManager 修改

- [x] 2.1 修改 `TaskManager.create_task` 方法，记录创建任务的 user_id
- [x] 2.2 修改 `TaskManager.get_task` 方法，支持按 user_id 过滤查询

## 3. 工具定义更新

- [x] 3.1 在 `reconciliation_status` 工具的 inputSchema 中添加 auth_token 必填参数
- [x] 3.2 在 `reconciliation_result` 工具的 inputSchema 中添加 auth_token 必填参数
- [x] 3.3 在 `reconciliation_list_tasks` 工具的 inputSchema 中添加 auth_token 必填参数
- [x] 3.4 在 `file_upload` 工具的 inputSchema 中添加 auth_token 必填参数
- [x] 3.5 在 `get_reconciliation` 工具的 inputSchema 中添加 auth_token 必填参数
- [x] 3.6 在 `analyze_files` 工具的 inputSchema 中添加 auth_token 必填参数

## 4. 测试验证

- [x] 4.1 验证有 token 时各工具功能正常
- [x] 4.2 验证无 token 时返回错误
- [x] 4.3 验证无效 token 时返回错误
- [x] 4.4 验证用户只能访问自己创建的任务

## 5. 服务部署

- [x] 5.1 重启 finance-mcp 服务
- [x] 5.2 验证服务运行正常
- [x] 5.3 检查 data-agent 是否需要更新以传递 auth_token

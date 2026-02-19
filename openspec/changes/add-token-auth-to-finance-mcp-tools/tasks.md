## 1. 添加 auth_token 参数到工具定义

- [x] 1.1 在 data_preparation_start 工具的 inputSchema 中添加 auth_token 参数（必选）
- [x] 1.2 在 data_preparation_result 工具的 inputSchema 中添加 auth_token 参数（必选）
- [x] 1.3 在 data_preparation_status 工具的 inputSchema 中添加 auth_token 参数（必选）
- [x] 1.4 在 data_preparation_list_tasks 工具的 inputSchema 中添加 auth_token 参数（必选）

## 2. 实现 token 验证逻辑

- [x] 2.1 在 _data_preparation_start 函数中添加 token 验证
- [x] 2.2 在 _data_preparation_result 函数中添加 token 验证
- [x] 2.3 在 _data_preparation_status 函数中添加 token 验证
- [x] 2.4 在 _data_preparation_list_tasks 函数中添加 token 验证

## 3. 验证

- [x] 3.1 运行 finance-mcp 服务并测试带 token 调用
- [x] 3.2 测试不带 token 调用应返回错误
- [x] 3.3 测试无效 token 应返回错误

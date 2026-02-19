## Why

数据整理 (data_preparation) MCP 工具目前没有任何身份验证机制，任何人都可以调用这些工具来执行数据整理任务，这存在安全风险。对账 (reconciliation) 工具已经实现了 token 验证，但数据整理工具缺少此项保护。需要统一添加 token 验证，确保只有登录用户才能使用数据整理功能。

## What Changes

- 在 `data_preparation_start` 工具中添加 `auth_token` 参数
- 在 `data_preparation_result` 工具中添加 `auth_token` 参数
- 在 `data_preparation_status` 工具中添加 `auth_token` 参数
- 在 `data_preparation_list_tasks` 工具中添加 `auth_token` 参数
- 在各个工具的 handler 函数中添加 token 验证逻辑
- 未提供有效 token 或 token 无效时返回错误信息

## Capabilities

### New Capabilities
- `mcp-tool-token-auth`: MCP 工具 Token 认证机制，确保只有登录用户才能调用数据整理工具

### Modified Capabilities
- (无)

## Impact

- **受影响代码**: 
  - `finance-mcp/data_preparation/mcp_server/tools.py` - 添加 auth_token 参数和验证
- **相关模块**: 
  - 认证模块 (`auth/jwt_utils.py`) - 复用现有的 token 验证逻辑
  - MCP Server (`unified_mcp_server.py`) - 可能需要更新工具路由（如果需要）
- **依赖**: 复用现有的 `auth.jwt_utils.get_user_from_token` 函数

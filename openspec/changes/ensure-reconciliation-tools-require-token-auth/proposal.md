## Why

当前 finance-mcp 中的 reconciliation 相关工具（reconciliation_status, reconciliation_result, reconciliation_list_tasks, file_upload, get_reconciliation, analyze_files）没有进行 token 验证，任何人都可以调用这些工具访问用户数据和对账结果，存在安全风险。需要确保所有 reconciliation 相关工具都需要通过 token 认证才能使用。

## What Changes

- 为 `reconciliation_status` 工具添加 token 验证
- 为 `reconciliation_result` 工具添加 token 验证
- 为 `reconciliation_list_tasks` 工具添加 token 验证
- 为 `file_upload` 工具添加 token 验证
- 为 `get_reconciliation` 工具添加 token 验证
- 为 `analyze_files` 工具添加 token 验证
- 保持 `reconciliation_start` 已有 token 验证不变

## Capabilities

### New Capabilities
- `reconciliation-token-auth`: 对账相关工具的 token 认证能力，确保只有登录用户才能访问对账功能

### Modified Capabilities
- (无)

## Impact

- **受影响代码**:
  - `finance-mcp/reconciliation/mcp_server/tools.py` - 需要修改 6 个工具函数添加 token 验证逻辑
- **安全影响**: 防止未授权访问用户对账数据和文件
- **兼容性影响**: 现有调用方需要提供有效的 auth_token 参数

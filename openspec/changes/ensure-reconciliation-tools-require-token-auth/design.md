## Context

当前 finance-mcp 的 reconciliation 模块中，部分工具函数缺少 token 验证。具体来说：
- `reconciliation_start` 已有 token 验证（从 args 获取 auth_token 并调用 `get_user_from_token` 验证）
- 以下 6 个工具缺少 token 验证：`reconciliation_status`, `reconciliation_result`, `reconciliation_list_tasks`, `file_upload`, `get_reconciliation`, `analyze_files`

这意味着任何人只要知道 task_id 就可以查询对账结果，或上传文件，存在数据泄露风险。

## Goals / Non-Goals

**Goals:**
- 为 6 个缺少认证的 reconciliation 工具添加 token 验证
- 保持与 `reconciliation_start` 一致的认证方式
- 确保调用方必须提供有效的 auth_token 才能使用这些工具
- 不影响现有已认证工具的功能

**Non-Goals:**
- 不修改 `reconciliation_start` 的现有逻辑（已认证）
- 不修改 auth 模块的实现（使用现有的 `get_user_from_token`）
- 不添加新的认证机制（如 API Key、OAuth 等）

## Decisions

### 1. 认证方式选择
**Decision**: 使用与 `reconciliation_start` 相同的认证方式，即从参数中获取 `auth_token` 并调用 `get_user_from_token` 验证。

**Rationale**: 
- 保持一致性，所有 reconciliation 工具使用相同的认证方式
- 复用现有代码，减少重复
- `reconciliation_start` 已经实现了完整的认证逻辑，包括 token 解析和用户信息获取

### 2. 认证失败时的错误处理
**Decision**: 当 token 无效或缺失时，返回标准错误格式 `{"error": "token 无效或已过期"}`。

**Rationale**: 与现有 `reconciliation_start` 的错误处理保持一致，前端可以统一处理认证错误。

### 3. 是否需要验证用户对任务的访问权限
**Decision**: 对于 `reconciliation_status` 和 `reconciliation_result`，需要验证当前用户是否有权限访问该任务（即任务是否由该用户创建）。

**Rationale**: 
- 防止用户 A 通过猜测 task_id 访问用户 B 的对账结果
- 这与 `reconciliation_start` 中验证用户是否有权限使用规则的逻辑类似

### 4. file_upload 是否需要验证权限
**Decision**: `file_upload` 只需要验证 token 有效性，不需要验证文件访问权限（因为文件上传后存储在服务器端，用户通过自己的 token 上传）。

**Rationale**: 上传的文件与用户账户关联，后续对账时会验证规则权限。

## Risks / Trade-offs

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 兼容性 | 现有调用方可能未传递 auth_token | 需要同步更新 data-agent 的调用代码 |
| 性能 | 额外的 token 验证增加延迟 | 验证逻辑轻量，影响可忽略 |
| 任务权限验证 | 需要在 TaskManager 中存储 user_id | 从 task 创建时记录创建者，查询时验证 |

## Migration Plan

1. **代码修改阶段**:
   - 修改 `finance-mcp/reconciliation/mcp_server/tools.py` 中的 6 个工具函数
   - 添加统一的 `_require_auth` 辅助函数减少重复代码

2. **测试阶段**:
   - 验证有 token 时功能正常
   - 验证无 token 或无效 token 时返回错误
   - 验证跨用户访问被阻止

3. **部署阶段**:
   - 部署 finance-mcp 服务
   - 同步更新 data-agent 确保传递 auth_token
   - 监控错误日志

## Open Questions

- [ ] 是否需要修改 data-agent 中的调用代码？需要检查 data-agent 是否已传递 auth_token
- [ ] TaskManager 是否需要持久化 user_id？目前任务列表仅存储在内存中

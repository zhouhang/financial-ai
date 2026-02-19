## Context

在 `finance-mcp/data_preparation/mcp_server/tools.py` 中，4 个 MCP 工具当前没有任何身份验证：
- `data_preparation_start`
- `data_preparation_result`
- `data_preparation_status`
- `data_preparation_list_tasks`

对账模块 (`reconciliation`) 已经实现了 token 认证，使用 `auth.jwt_utils.get_user_from_token` 验证 token。

## Goals / Non-Goals

**Goals:**
- 为 data_preparation 的 4 个工具添加 token 验证
- 复用现有 `auth.jwt_utils.get_user_from_token` 函数
- 与 reconciliation 工具保持一致的认证方式

**Non-Goals:**
- 不修改数据库结构
- 不修改前端认证流程
- 不添加新的认证方式（仅复用现有 JWT）

## Decisions

### Decision 1: 复用现有 JWT 验证函数

**选择**：直接导入并使用 `auth.jwt_utils.get_user_from_token`

**理由**：
- 已在 reconciliation 工具中验证可用
- 无需额外依赖或代码重复
- 保持认证方式一致性

### Decision 2: auth_token 参数为必选

**选择**：将 `auth_token` 添加到 required 列表

**理由**：
- 与 reconciliation 工具保持一致
- 强制要求认证，确保安全

**替代方案**：
- 可选参数，未提供时返回公开数据 → 不适合，存在数据泄露风险

### Decision 3: 在每个 handler 开头添加验证

**选择**：在每个工具的 handler 函数（`_data_preparation_start` 等）开头添加 token 验证

**理由**：
- 与 reconciliation 工具的实现模式一致
- 简单直接，易于理解和维护

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| 现有未认证的调用会失败 | 需要调用方添加 token | 提前通知用户，需要更新调用方式 |
| token 验证逻辑重复 | 代码冗余 | 未来可抽取为公共函数，当前保持简单 |

## Open Questions

1. **是否需要验证用户对任务的所有权？**  
   - 当前只验证 token 有效性，不验证任务归属
   - 可后续迭代，先保证基本安全

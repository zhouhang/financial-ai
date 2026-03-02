## Context

当前规则推荐系统有两条路径：
1. **哈希搜索路径**：使用 `search_rules_by_mapping` MCP 工具，通过 `field_mapping_hash` 搜索规则
2. **字段名匹配路径**：使用 `search_rules_by_field_mapping` 数据库函数，通过字段名匹配

问题是：路径1（哈希搜索）没有过滤当前用户的规则，而路径2已经正确过滤。

当前登录用户信息可从 `auth_token` 中获取，包含 `user_id` 字段。

## Goals / Non-Goals

**Goals:**
- 登录用户在做规则推荐时，不再看到自己创建的规则
- 保持访客用户的推荐行为不变（访客没有自己的规则）

**Non-Goals:**
- 不修改规则推荐的算法逻辑（只修改过滤逻辑）
- 不添加新的推荐策略
- 不修改用户创建规则的功能

## Decisions

### D1: 在数据库层过滤 vs 在应用层过滤

**决定**: 在数据库层过滤

**理由**:
- 数据库层过滤可以减少返回数据量，降低网络传输成本
- 现有代码结构已经在数据库函数中处理过滤逻辑（路径2）
- 复用现有模式，减少代码重复

### D2: 传递 user_id 的方式

**决定**: 从 auth_token 中提取 user_id，传递给数据库函数

**理由**:
- 前端已经传递了 `auth_token` 到 MCP 工具
- MCP 服务端可以通过 JWT 解码获取用户信息
- 现有代码已经有 `auth_me` 工具可以验证 token 并获取用户信息

### D3: user_id 参数为可选

**决定**: `user_id` 参数为可选，不传时不过滤

**理由**:
- 访客用户没有 user_id，不传则返回所有匹配规则
- 向后兼容，不影响现有调用方式
- 现有路径2已经采用此方式

## Risks / Trade-offs

- **性能风险**: 过滤操作在数据库层执行，如果数据量大可能有轻微性能影响 → 影响可忽略，因为只是增加一个 WHERE 条件
- **Token 解析失败**: 如果 auth_token 无效或过期 → 返回空结果或让调用方处理异常

## Migration Plan

1. 修改 `finance-mcp/auth/db.py` 中的 `search_rules_by_field_mapping` 函数，添加可选的 `user_id` 参数
2. 修改 `finance-mcp/auth/tools.py` 中的 `_handle_search_rules_by_mapping` 函数，从 token 提取 user_id 并传递给数据库函数
3. 部署后测试：登录用户和非登录用户分别测试推荐结果

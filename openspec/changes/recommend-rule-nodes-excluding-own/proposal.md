## Why

当前规则推荐系统在用户登录状态下，会推荐用户自己创建的规则。这会导致用户体验不佳，用户不需要推荐自己已经知道的规则。现在是解决这个问题的最佳时机，因为系统刚完成用户认证体系的搭建，可以在推荐逻辑中轻松获取当前用户信息。

## What Changes

- 修改 `search_rules_by_field_mapping` 数据库函数，添加可选的 `user_id` 参数用于过滤
- 修改 `search_rules_by_mapping` MCP 工具处理器，从 token 中提取用户信息并传递给数据库函数
- 保持访客用户的推荐行为不变（访客没有自己的规则，所以不过滤）

## Capabilities

### New Capabilities
<!-- Capabilities being introduced. Replace <name> with kebab-case identifier (e.g., user-auth, data-export, api-rate-limiting). Each creates specs/<name>/spec.md -->
（无）

### Modified Capabilities
<!-- Existing capabilities whose REQUIREMENTS are changing (not just implementation).
     Only list here if spec-level behavior changes. Each needs a delta spec file.
     Use existing spec names from openspec/specs/. Leave empty if no requirement changes. -->
- `rule-recommendation`: 登录用户推荐规则时，排除用户自己创建的规则

## Impact

- **受影响代码**：
  - `finance-mcp/auth/db.py` - 数据库函数
  - `finance-mcp/auth/tools.py` - MCP 工具处理器
- **无 API 变更**：仅修改内部过滤逻辑
- **无 breaking change**：仅影响登录用户的推荐结果

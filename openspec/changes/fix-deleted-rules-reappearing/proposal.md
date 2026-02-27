## Why

用户反馈：删除某个规则后，一段时间后该规则在规则列表中又出现了。

经过代码分析发现问题：**工具描述声称是"软删除"**，但**实际代码实现是硬删除** (DELETE FROM)。
- 工具定义 (`auth/tools.py:157`): `description="删除对账规则（软删除，需要权限）"`
- 实际实现 (`auth/db.py:395`): `DELETE FROM reconciliation_rules` (硬删除)

这导致用户期望的软删除行为与实际不符。

## What Changes

1. **将删除操作改为软删除**
   - 修改 `auth_db.delete_rule` 函数：将 `DELETE FROM` 改为 `UPDATE status = 'archived'`
   - 修改 `_handle_delete_rule` 调用：直接调用 `update_rule` 设置 status='archived'

2. **验证修复后行为正确**
   - 确认规则列表正确过滤 archived 规则
   - 确认推荐规则逻辑不受影响

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `rule-management`: 删除规则改为软删除 (status='archived')

## Impact

- 涉及的代码：
  - `finance-mcp/auth/db.py`: delete_rule 函数
  - `finance-mcp/auth/tools.py`: _handle_delete_rule 函数

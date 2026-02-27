## Context

当前删除规则的功能存在设计与实现不一致：
- 工具定义 (`auth/tools.py:157`): 描述为"软删除，需要权限"
- 实际实现 (`auth/db.py:395`): 执行 `DELETE FROM reconciliation_rules`（硬删除）

数据库已支持软删除：
- `reconciliation_rules` 表有 `status` 字段，支持 `active/archived/pending_approval`
- `update_rule` 函数支持更新 `status` 字段

## Goals / Non-Goals

**Goals:**
- 将删除操作改为软删除 (UPDATE status='archived')
- 确保删除后规则列表不显示已删除的规则
- 确保推荐规则逻辑仍能正常工作

**Non-Goals:**
- 不修改推荐规则的逻辑（推荐应从所有规则中筛选）
- 不添加恢复已删除规则的功能

## Decisions

### Decision 1: 普通用户软删除，管理员硬删除

**选择**: 根据用户角色区分删除方式
- 普通用户删除: 软删除 (UPDATE status='archived')
- 管理员删除: 硬删除 (DELETE FROM)

**理由**:
- 普通用户误删后可恢复，符合用户期望
- 管理员需要彻底删除规则的能力
- `can_user_modify_rule` 函数已支持 admin 角色判断

### Decision 2: status 字段与 visibility 字段独立

**选择**: status (active/archived) 和 visibility (private/department/company) 是两个独立字段

**理由**:
- status: 表示规则是否被删除
- visibility: 表示规则的可见性范围
- 两者独立不冲突，可以组合使用

## Risks / Trade-offs

1. **[风险]** 已删除规则的 rule_id 被其他系统引用
   - **缓解**: 软删除后 rule_id 不变，只是状态改变
   - 外部系统如需过滤，可通过 status='active' 过滤

2. **[风险]** 推荐规则可能包含已删除规则
   - **缓解**: 推荐逻辑需要确保只推荐 active 规则
   - 需要检查 `list_recommended_rules` 的实现

3. **[权衡]** 数据库存储增加
   - 软删除后 archived 规则仍占用存储空间
   - 可定期清理过期的 archived 规则

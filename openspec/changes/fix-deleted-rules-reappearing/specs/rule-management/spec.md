## ADDED Requirements

### Requirement: 普通用户删除规则使用软删除
系统 SHALL 使用软删除方式删除规则，将规则状态设置为 archived 而不是物理删除。

#### Scenario: 普通用户删除自己的规则
- **WHEN** 普通用户调用 delete_reconciliation_rule 接口删除自己创建的规则
- **THEN** 系统将规则的 status 字段更新为 'archived'
- **AND** 规则从用户可见的规则列表中移除（列表默认过滤 status='active'）

### Requirement: 管理员删除规则使用硬删除
系统 SHALL 使用物理删除方式彻底删除规则。

#### Scenario: 管理员删除任意规则
- **WHEN** 管理员调用 delete_reconciliation_rule 接口删除任意规则
- **THEN** 系统从数据库中物理删除规则记录 (DELETE FROM)
- **AND** 规则永久消失，无法恢复

### Requirement: 规则列表正确过滤已删除规则
系统 SHALL 默认只返回 status='active' 的规则，确保用户看不到已删除的规则。

**注意**: status 字段 (active/archived) 与 visibility 字段 (private/department/company) 是不同的概念：
- status: 表示规则是否被删除 (active=正常, archived=已删除)
- visibility: 表示规则的可见性范围

#### Scenario: 查询用户可见规则列表
- **WHEN** 用户调用 list_reconciliation_rules 获取规则列表
- **THEN** 系统只返回 status='active' 的规则
- **AND** 已删除（archived）的规则不出现在列表中

#### Scenario: 用户指定查询已删除规则
- **WHEN** 用户调用 list_reconciliation_rules 并设置 status='archived'
- **AND** 用户是管理员
- **THEN** 系统返回所有已删除的规则

#### Scenario: 规则可见性不受 status 影响
- **WHEN** 用户查询规则列表
- **THEN** 系统先按 visibility 过滤可见范围，再按 status 过滤删除状态
- **AND** status='archived' 的规则即使 visibility='company' 也不显示

### Requirement: 推荐规则只包含活跃规则
系统 SHALL 确保推荐规则列表只包含 status='active' 的规则。

#### Scenario: 游客获取推荐规则
- **WHEN** 游客调用 list_recommended_rules 获取推荐规则
- **THEN** 系统只返回 status='active' 且 is_recommended=true 的规则
- **AND** 已删除（archived）的规则不在推荐列表中

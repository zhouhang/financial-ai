## Why

当前对账规则的权限控制粒度不够细致，只能区分私有(private)、公司级(company)和部门级(department)三种可见性。需要更细化的权限控制：

1. **查询 (Query)**: 本部门员工可以查询本部门的所有规则
2. **添加 (Create)**: 任何登录用户都可以创建规则（前提）
3. **修改 (Edit)**: 只有规则创建者自己可以编辑
4. **删除 (Delete)**: 只有规则创建者自己可以删除

## What Changes

- 修改规则查询(list_available_rules, get_rule_detail)接口，增加部门级过滤逻辑
- 修改规则创建(save_rule)接口，自动关联创建者的部门信息
- 修改规则编辑(update_rule)接口，增加创建者校验
- 修改规则删除(delete_rule)接口，增加创建者校验
- 对账执行(reconciliation_start)时，限制用户只能使用有权限的规则

## Capabilities

### New Capabilities
- `department-rule-permission`: 部门级规则权限控制能力
  - 查询: 本部门员工可查询本部门所有规则
  - 添加: 登录用户可创建规则
  - 修改: 仅创建者可编辑自己的规则
  - 删除: 仅创建者可删除自己的规则

### Modified Capabilities
- (无)

## Impact

- **受影响代码**:
  - `finance-mcp/auth/tools.py` - 规则管理工具的权限验证逻辑
  - `finance-mcp/reconciliation/mcp_server/tools.py` - reconciliation_start 权限验证
- **数据库变更**: 确保 rules 表有 department_id, created_by 字段
- **兼容性影响**: 现有查询逻辑需要适配新的部门过滤规则

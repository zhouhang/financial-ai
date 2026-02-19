## Context

当前对账系统已有三种规则可见性：私有(private)、公司级(company)、部门级(department)。现需要更细化的权限控制：

| 操作 | 权限规则 |
|------|----------|
| 查询 (Query) | 本部门员工可查询本部门所有规则 |
| 添加 (Create) | 登录用户可创建规则 |
| 修改 (Edit) | 仅创建者可编辑自己的规则 |
| 删除 (Delete) | 仅创建者可删除自己的规则 |
| 执行 (Execute) | 用户只能使用有权限的规则 |

## Goals / Non-Goals

**Goals:**
- 实现查询权限：本部门员工可查询本部门所有规则
- 实现添加权限：登录用户可创建规则
- 实现修改权限：仅创建者可编辑自己的规则
- 实现删除权限：仅创建者可删除自己的规则
- 实现执行权限：用户只能使用有权限的规则

**Non-Goals:**
- 不修改用户部门信息的管理逻辑
- 不修改规则可见性的基本逻辑

## Decisions

### 1. 权限验证架构
**Decision**: 在 auth/tools.py 中统一处理规则权限验证逻辑。

| 操作 | 验证逻辑 |
|------|----------|
| list_available_rules | 返回本部门所有规则 + 自己创建的私有规则 |
| get_rule_detail | 检查用户是否有权限查看该规则 |
| save_rule | 创建时自动填充 created_by 和 department_id |
| update_rule | 验证 created_by == 当前用户 |
| delete_rule | 验证 created_by == 当前用户 |
| reconciliation_start | 验证用户有权限使用该规则 |

### 2. 权限验证失败时的错误信息
**Decision**: 返回统一的错误信息 "无权操作该规则"。

### 3. 规则创建时的信息填充
**Decision**: 创建规则时自动填充：
- `created_by`: 当前用户ID
- `department_id`: 当前用户所属部门ID
- `visibility`: 默认为 "department"

## Risks / Trade-offs

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 兼容性 | 现有规则可能没有 created_by | 查询时增加 created_by 为空的检查 |
| 数据完整性 | 旧规则 created_by 可能为空 | 迁移脚本填充默认值 |

## Migration Plan

1. **代码修改阶段**:
   - 修改 auth/tools.py 中的规则管理函数
   - 修改 reconciliation_start 权限验证

2. **测试阶段**:
   - 验证各操作的权限控制

3. **部署阶段**:
   - 部署 finance-mcp 服务

## Open Questions

- [ ] 是否需要区分"私有规则"和"部门规则"的查询权限？
- [ ] admin 用户是否应该有跨部门管理权限？

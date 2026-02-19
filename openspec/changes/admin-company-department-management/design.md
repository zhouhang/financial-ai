## Context

当前系统已有用户认证和对账规则管理功能，但缺少公司部门层级的管理。需要实现管理员系统来统一管理公司信息、部门信息，并在用户注册时可选择已创建的公司和部门。

现有表结构：
- users: 用户表，已有 company_id, department_id 字段
- company: 公司表
- departments: 部门表

## Goals / Non-Goals

**Goals:**
- 实现管理员登录功能（admin/888888）
- 实现管理员视图：查看公司-部门-员工-规则层级结构
- 实现创建公司功能
- 实现创建部门功能（下拉选择公司）
- 修改注册表单为公司部门下拉选择

**Non-Goals:**
- 不修改现有用户登录逻辑
- 不修改规则管理逻辑

## Decisions

### 1. 管理员表设计
**Decision**: 创建 admins 表，存储管理员账号信息。

```sql
CREATE TABLE admins (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

默认账号：admin，密码：888888（存储哈希值）

### 2. 管理员认证方式
**Decision**: 使用简单的用户名密码验证，与 JWT token 类似的方式返回 admin_token。

### 3. 管理员视图数据展示
**Decision**: 返回层级 JSON 结构：
```json
{
  "companies": [
    {
      "id": "xxx",
      "name": "公司A",
      "departments": [
        {
          "id": "xxx",
          "name": "部门A",
          "employees": [...],
          "rules": [...]
        }
      ]
    }
  ]
}
```

### 4. 注册表单下拉选项
**Decision**: 
- 公司下拉：调用 list_companies API 获取
- 部门下拉：根据选中的公司，调用 list_departments(company_id) 获取

## Risks / Trade-offs

| 风险 | 描述 | 缓解措施 |
|------|------|----------|
| 密码安全 | 默认密码需要修改 | 提示首次登录修改密码 |
| 权限过大 | 管理员可查看所有数据 | 仅展示基本信息 |

## Migration Plan

1. 创建 admins 表，插入默认管理员
2. 新增管理员相关 API
3. 修改前端注册表单
4. 添加隐藏指令识别

## Open Questions

- [ ] 管理员是否需要更细粒度的权限控制？
- [ ] 是否需要管理员修改密码功能？

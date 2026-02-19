## Why

当前系统缺少公司部门层级的管理功能，需要实现管理员系统来统一管理公司、部门信息，并在用户注册时可选择已创建的公司和部门。

## What Changes

- 创建管理员表 (admins)，默认账号 admin/888888
- 添加隐藏指令"管理员登录"，返回管理员登录表单
- 管理员登录后可查看公司-部门-员工的层级结构及对应规则
- 添加隐藏指令"创建公司"，返回创建公司表单
- 添加隐藏指令"创建部门"，返回创建部门表单（下拉选择公司+填写部门名称）
- 将用户注册表单中的公司和部门改为下拉选项

## Capabilities

### New Capabilities
- `admin-auth`: 管理员认证能力，支持登录验证
- `company-management`: 公司管理能力，创建和查看公司
- `department-management`: 部门管理能力，创建和查看部门
- `admin-view`: 管理员视图能力，展示公司-部门-员工-规则层级

### Modified Capabilities
- `user-registration`: 用户注册时公司部门改为下拉选择

## Impact

- **受影响代码**:
  - `finance-mcp/auth/` - 新增管理员表和管理功能
  - `finance-agents/data-agent/app/graphs/main_graph/` - 添加管理员登录和创建表单
  - `finance-agents/data-agent/app/tools/mcp_client.py` - 新增管理员相关API调用
- **数据库变更**: 新增 admins 表
- **前端变更**: 注册表单改为下拉选项

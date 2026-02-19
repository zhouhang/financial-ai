## 1. 数据库设计

- [x] 1.1 创建 admins 表（username, password）
- [x] 1.2 插入默认管理员 admin/888888

## 2. 后端 API 实现

- [x] 2.1 在 auth/tools.py 添加管理员登录 API (admin_login)
- [x] 2.2 添加管理员登出 API (admin_logout)
- [x] 2.3 添加创建公司 API (create_company)
- [x] 2.4 添加创建部门 API (create_department)
- [x] 2.5 添加获取公司列表 API (list_companies)
- [x] 2.6 添加获取部门列表 API (list_departments)
- [x] 2.7 添加管理员视图 API (get_admin_view)

## 3. 前端表单实现

- [x] 3.1 修改注册表单为公司部门下拉选择
- [x] 3.2 添加管理员登录表单
- [x] 3.3 添加创建公司表单
- [x] 3.4 添加创建部门表单

## 4. 隐藏指令实现

- [x] 4.1 添加"管理员登录"隐藏指令识别
- [x] 4.2 添加"创建公司"隐藏指令识别
- [x] 4.3 添加"创建部门"隐藏指令识别

## 5. 测试验证

- [x] 5.1 测试管理员登录
- [x] 5.2 测试创建公司
- [x] 5.3 测试创建部门
- [x] 5.4 测试管理员视图
- [x] 5.5 测试注册表单下拉

## 6. 服务部署

- [x] 6.1 重启 finance-mcp 服务
- [x] 6.2 重启 data-agent 服务
- [x] 6.3 验证服务运行正常

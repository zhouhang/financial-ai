## 1. 数据库改动

- [x] 1.1 创建 `guest_auth_tokens` 表（id, token, session_id, usage_count, max_usage, created_at, expires_at, ip_address）
- [x] 1.2 在 `reconciliation_rules` 表添加 `is_recommended` 字段（可选，用于标记推荐规则）

## 2. MCP 服务改动 (finance-mcp)

- [x] 2.1 在 `auth/db.py` 添加 `create_guest_token()` 函数
- [x] 2.2 在 `auth/db.py` 添加 `verify_guest_token()` 函数
- [x] 2.3 在 `auth/db.py` 添加 `increment_guest_usage()` 函数
- [x] 2.4 在 `auth/tools.py` 添加 MCP 工具 `create_guest_token`
- [x] 2.5 在 `auth/tools.py` 添加 MCP 工具 `verify_guest_token`
- [x] 2.6 在 `auth/tools.py` 修改 `list_reconciliation_rules` 支持 guest_token 参数，游客模式仅返回推荐规则
- [x] 2.7 在 `auth/tools.py` 修改 `reconciliation_start` 支持 guest_token，检查使用次数

## 3. Data Agent 改动 (finance-agents/data-agent)

- [x] 3.1 在 `main_graph/nodes.py` 添加游客路由判断逻辑（检查 guest_token）
- [x] 3.2 在 `main_graph/nodes.py` 新增 `guest_handler` 节点处理游客请求
- [x] 3.3 在 `mcp_client.py` 添加游客token相关工具调用封装
- [x] 3.4 修改 `reconciliation/nodes.py` 游客模式下规则过滤逻辑

## 4. 前端改动 (finance-web)

- [x] 4.1 修改 `ChatArea.tsx` 移除顶部"分析会话"tab栏
- [x] 4.2 在 `App.tsx` 或新建 `LoginModal.tsx` 组件实现登录弹窗
- [x] 4.3 修改 `Sidebar.tsx` 未登录状态显示登录按钮（替换现有文字提示）
- [x] 4.4 实现登录弹窗与 WebSocket 登录接口对接
- [x] 4.5 实现登录成功后自动保存推荐规则逻辑
- [x] 4.6 实现登录成功后页面刷新

## 5. 集成测试

- [x] 5.1 测试未登录用户对话流程（AI可正常回复）
- [x] 5.2 测试游客上传文件对账流程
- [x] 5.3 测试游客3次使用限制
- [x] 5.4 测试弹窗登录功能
- [x] 5.5 测试登录后自动保存规则
- [x] 5.6 测试服务重启（确保所有服务正常运行）

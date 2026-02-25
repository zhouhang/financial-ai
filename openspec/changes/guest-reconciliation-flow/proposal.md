## Why

解决用户首次使用时必须登录才能使用基础对账功能的问题。当前系统强制用户登录才能与AI对话和上传文件，导致新用户使用门槛过高。允许游客使用推荐规则进行对账，可以提升用户体验，同时通过使用限制引导用户注册登录。

## What Changes

1. **取消强制登录提示**：用户无需登录即可与AI对话，AI可正常介绍自己和功能
2. **新增游客对账流程**：未登录用户可上传文件进行对账，但仅限使用系统推荐规则
3. **新增临时auth_token机制**：MCP工具可派发7天有效临时token，存入PostgreSQL表
4. **游客使用限制**：未登录用户最多使用3次对账功能，超过后提示登录
5. **UI调整**：
   - 移除顶部"分析会话"标签栏
   - 未登录状态右上角显示"登录"按钮
6. **弹窗登录**：用页面弹窗替代AI回复的登录表单
7. **登录后自动保存**：登录完成后自动保存推荐规则，并刷新页面

## Capabilities

### New Capabilities

- `guest-auth`: 临时认证机制，包含临时token生成、验证、使用次数限制逻辑
- `guest-reconciliation`: 游客对账流程，支持上传文件使用推荐规则进行对账，受3次限制约束
- `popup-login`: 弹窗登录UI组件，独立于AI对话流程

### Modified Capabilities

- `user-auth`: 登录成功后自动保存当前会话的推荐规则到用户账户
- `reconciliation-rules`: 游客模式仅返回推荐规则，不返回用户私有规则

## Impact

- **finance-mcp**: 新增`guest_auth_tokens`表，修改MCP工具支持临时token认证
- **finance-agents/data-agent**: 新增LangGraph游客分支flow，与登录分支独立
- **finance-web**: 移除顶部tab栏，新增登录弹窗组件，修改Sidebar登录状态显示
- **PostgreSQL**: 新建`guest_auth_tokens`表存储临时token和使用计数

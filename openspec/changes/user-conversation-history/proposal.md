## Why

用户需要保存历史会话和会话记录，以便查看和继续之前的对话。当前系统没有持久化会话功能，刷新页面后会话丢失。

## What Changes

- 添加数据库表存储会话和消息记录
- 添加会话管理 API（创建、列表、获取、删除）
- 修改消息处理流程，自动保存消息到数据库
- 前端添加会话列表侧边栏，支持会话切换

## Capabilities

### New Capabilities

- `conversation-storage`: 会话和消息的数据库存储，包括 CRUD 操作
- `conversation-sidebar`: 前端会话列表侧边栏组件，支持会话切换

### Modified Capabilities

无

## Impact

- **数据库**: 新增 conversations、messages 表
- **后端**: finance-mcp/auth/db.py, auth/tools.py 添加会话管理
- **Agent**: data-agent/app/server.py 集成消息保存
- **前端**: 添加侧边栏组件，修改布局

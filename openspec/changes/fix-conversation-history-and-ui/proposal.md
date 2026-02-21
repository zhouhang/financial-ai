## Why

用户会话历史功能存在 bug：刷新页面后历史会话不显示，且缺少删除会话功能。同时，对账任务执行时会显示两条消息（任务启动 + 任务概述），完成后"任务启动"消息应该被删除以保持界面整洁。

## What Changes

- **修复历史会话加载**：页面刷新后，已登录用户的历史会话应自动从服务器加载并显示
- **添加会话删除功能**：侧边栏会话列表中添加删除按钮，支持删除服务器端会话
- **优化任务消息显示**：对账任务完成时，删除之前的"任务启动..."消息，只保留最终的任务概述

## Capabilities

### New Capabilities

- `conversation-delete-ui`: 侧边栏会话删除 UI 交互（悬停显示删除按钮、确认删除、调用删除 API）

### Modified Capabilities

_无需修改现有规格，问题都是实现层面的 bug_

## Impact

### 前端 (finance-web)
- `src/hooks/useConversations.ts` - 检查 authToken 变化时的加载逻辑
- `src/App.tsx` - 修复 mergedConversations 逻辑，集成删除回调
- `src/components/Sidebar.tsx` - 添加删除按钮 UI 和交互

### 后端 (data-agent)
- `app/graphs/main_graph/nodes.py` - 修改任务启动消息的处理逻辑

### 涉及的 API
- `DELETE /api/conversations/{id}` - 已存在，需要前端调用

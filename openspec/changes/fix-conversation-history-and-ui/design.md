## Context

用户会话历史功能已实现基础架构：
- 后端：PostgreSQL 存储会话和消息，REST API 已就绪
- 前端：`useConversations` hook 可加载/删除会话，`mergedConversations` 合并本地和服务器会话

当前问题：
1. 页面刷新后历史会话不显示
2. 侧边栏缺少删除按钮
3. 对账任务显示两条消息（启动 + 概述）

## Goals / Non-Goals

**Goals:**
- 修复页面刷新后历史会话加载问题
- 在侧边栏添加会话删除功能
- 任务完成时删除"任务启动"消息

**Non-Goals:**
- 不修改后端 API（已正常工作）
- 不修改消息持久化逻辑
- 不增加新的数据库字段

## Decisions

### 1. 历史会话加载问题修复

**问题分析**：`useConversations` hook 的 `useEffect` 依赖 `loadConversations`，而 `loadConversations` 是 `useCallback` 依赖 `authToken`。这可能导致：
- 首次渲染时 authToken 已存在（从 localStorage 恢复）
- 但 useEffect 可能因为依赖变化被跳过

**方案**：移除 `loadConversations` 的 `useCallback` 依赖，直接在 useEffect 内部定义加载逻辑，或使用 `useRef` 跟踪 authToken 变化。

**选择**：简化 useEffect 依赖，只依赖 `authToken`，在 effect 内部直接调用 fetch。

### 2. 会话删除功能

**方案**：
- Sidebar 组件添加 `onDeleteConversation` prop
- 每个会话项添加删除按钮（悬停显示）
- 点击时调用 `confirm()` 确认后删除
- App.tsx 传递 `deleteServerConversation` 作为回调

**UI 交互**：
```
悬停会话 → 显示 ⋮ 菜单按钮 → 点击显示删除选项 → 确认删除
```

### 3. 任务启动消息删除

**问题分析**：后端在 `nodes.py` 的 `_do_reconciliation_task` 函数中发送两条消息：
1. "🚀 对账任务已启动..." - 任务开始时
2. 任务概述 - 任务完成时

**方案 A**：后端不发送启动消息，只发送完成消息
- 优点：简单直接
- 缺点：用户看不到任务进度

**方案 B**：后端发送启动消息时添加标记，前端在收到完成消息时删除带标记的消息
- 优点：保留进度反馈
- 缺点：需要前后端配合

**方案 C**：前端在收到特定模式的消息时替换之前的消息
- 优点：前端自主处理，不改后端
- 缺点：依赖消息内容匹配

**选择**：方案 C - 前端检测"对账任务已启动"消息，在收到包含任务结果的消息时删除它。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| useEffect 依赖变化可能影响其他逻辑 | 仅修改 useConversations hook，不影响其他组件 |
| 消息模式匹配不准确 | 使用明确的正则模式：`/^🚀 对账任务已启动/` |
| 删除会话后 activeConvId 无效 | 删除后检查并切换到其他会话 |

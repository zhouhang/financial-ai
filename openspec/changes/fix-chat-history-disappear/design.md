## Context

用户反馈：登录后发送消息，刷新页面后对话和聊天记录都消失了。

经过代码和日志分析发现问题：

**问题根因：**
1. 用户的会话 ID (`conversation_id`) 被保存到 localStorage
2. 下次刷新页面时，前端从 localStorage 读取这个 ID
3. 前端使用正则表达式 `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i` 判断是否为服务器 ID
4. 如果匹配 (UUID 格式)，前端会直接把这个 ID 作为 `conversation_id` 发送给服务器
5. 服务器收到 `conversation_id` 后，不再创建新会话，直接使用这个 ID
6. 但这个 ID 可能从未在数据库中创建成功，导致 `save_message` 失败（因为验证会话所有权时找不到）

**日志证据：**
- 第一条消息：`conversation_id=` (空) → 应该创建会话
- 第二条消息：`conversation_id=6011edf4-3e43-4a44-b617-9583956665cd` → 直接使用
- 数据库查询：没有任何会话记录
- `save_message` 返回 `False`，因为"会话不存在"

## Goals / Non-Goals

**Goals:**
- 修复会话/消息不保存的问题
- 确保登录用户的对话能正确保存到数据库

**Non-Goals:**
- 不修改 localStorage 存储逻辑

## Decisions

### Decision 1: 服务器端验证会话所有权

**选择**: 在 `save_message` 前验证会话是否在数据库中存在，如果不存在则创建

**理由**:
- 前端可能传递无效的 conversation_id
- 服务器应该在保存消息前确保会话存在

### Decision 2: 错误处理

**选择**: 如果会话不存在，应该先创建会话再保存消息

**理由**:
- 兼容前端可能传递无效 ID 的情况
- 确保消息不会因会话 ID 问题而丢失

## Why

用户反馈：登录后发送消息，刷新页面后对话和聊天记录都消失了。

经过代码和日志分析发现问题：

**问题根因：**
1. 用户的会话 ID (`conversation_id`) 被保存到 localStorage
2. 刷新页面时，前端从 localStorage 读取这个 ID（可能是 UUID 格式）
3. 前端使用正则表达式判断是否为服务器 ID，如果是则直接使用
4. 服务器收到 `conversation_id` 后，不再创建新会话，直接使用这个 ID
5. 但这个 ID 从未在数据库中创建成功（会话创建可能失败或被跳过）
6. 导致 `save_message` 失败（因为验证会话所有权时找不到）

## What Changes

1. **修复服务器端会话创建问题**
   - 在 `save_message` 前验证会话是否存在
   - 如果会话不存在，则先创建会话

## Capabilities

### New Capabilities
- 无

### Modified Capabilities
- `chat-history-persistence`: 修复会话/消息持久化问题

## Impact

- 涉及的代码：
  - `finance-agents/data-agent/app/server.py`: 消息处理逻辑
  - `finance-mcp/auth/tools.py`: save_message 工具

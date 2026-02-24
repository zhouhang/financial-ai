## Why

目前 AI 的回复是一次性完整显示的，用户体验不符合使用 AI 的习惯（类似 ChatGPT 的打字机效果）。逐字流式输出能让用户更早看到部分回复，降低等待焦虑，提升交互体验。

## What Changes

- 修改后端 WebSocket 消息处理，支持逐字符流式输出 AI 回复
- 前端添加流式输出状态管理，跟踪当前是否正在流式输出
- 前端消息组件支持流式渲染，实时更新已接收的部分文本
- 流式输出完成后，将流式内容合并为完整消息
- 添加闪烁光标动画效果，提示用户 AI 正在输出

## Capabilities

### New Capabilities
- `ai-response-streaming`: 逐字流式输出 AI 回复的能力，包括后端流式推送和前端流式渲染

### Modified Capabilities
- (无)

## Impact

- **前端** (`finance-web/src/components/MessageBubble.tsx`): 支持流式文本渲染和打字机光标
- **前端** (`finance-web/src/components/ChatArea.tsx`): 处理流式输出状态
- **前端** (`finance-web/src/App.tsx`): WebSocket 消息处理逻辑调整，支持 stream 类型消息
- **后端** (`finance-agents/data-agent/app/server.py`): 修改 LLM 调用逻辑，实现逐字符推送
- **无新依赖**: 继续使用现有的 WebSocket 通信机制

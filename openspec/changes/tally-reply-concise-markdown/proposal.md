# Tally 回复：言简意赅 + Markdown 渲染

## Why

当前 AI 回复存在两点问题：1）前端以纯文本展示，Markdown 语法（如 `**粗体**`、`-` 列表）被原样显示，无法渲染；2）部分 prompt 明确禁止 Markdown，导致回复格式单一、排版不清晰。用户希望 AI 回复言简意赅、排版清晰，且 Markdown 能正确渲染展示。

## What Changes

- 前端 `MessageBubble` 支持 Markdown 渲染，将 AI 回复中的 Markdown 语法解析并展示
- 更新 data-agent 中相关 prompt（意图识别、结果分析、闲聊回复等），要求回复言简意赅、善用 Markdown 排版（标题、列表、加粗等）
- 移除 `RESULT_ANALYSIS_PROMPT` 中「不要使用 Markdown」的限制，改为鼓励使用 Markdown 增强可读性

## Capabilities

### New Capabilities
- `ai-reply-markdown`: AI 回复的 Markdown 渲染能力，包括前端解析展示与 prompt 侧对 Markdown 输出的引导

### Modified Capabilities
- （无）

## Impact

- **前端** `finance-web/src/components/MessageBubble.tsx`：引入 Markdown 渲染库，对 assistant 消息内容做 Markdown 解析
- **后端** `finance-agents/data-agent/app/graphs/main_graph/nodes.py`：`SYSTEM_PROMPT`、`SYSTEM_PROMPT_NOT_LOGGED_IN`、`RESULT_ANALYSIS_PROMPT` 等 prompt 调整
- **依赖**：前端新增 Markdown 渲染库（如 `react-markdown`）

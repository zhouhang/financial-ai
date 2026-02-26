# Design: Tally 回复言简意赅 + Markdown 渲染

## Context

**当前状态：**
- 前端 `MessageBubble` 中 assistant 消息使用 `whitespace-pre-wrap` 纯文本展示
- `RESULT_ANALYSIS_PROMPT` 明确要求「不要使用 Markdown 格式」
- 流式输出时通过 `TypewriterText` 逐段追加文本，最终合并为完整消息
- 部分消息为 HTML 表单（登录/注册），使用 `dangerouslySetInnerHTML` 渲染

**约束：**
- 需兼容现有流式输出逻辑
- 表单类消息必须保持 HTML 渲染，不能误解析为 Markdown
- 需与 `stripSaveRuleTag`、`TypewriterText` 等现有逻辑共存

## Goals / Non-Goals

**Goals:**
- 前端正确渲染 AI 回复中的 Markdown（标题、列表、加粗、代码块等）
- 更新 prompt 使 AI 回复言简意赅、善用 Markdown 排版
- 流式输出期间与完成后的展示体验一致

**Non-Goals:**
- 不支持 Markdown 扩展语法（如表格、脚注）
- 不修改 WebSocket 或流式推送协议
- 不改变表单（登录/注册）的渲染方式

## Decisions

### 1. Markdown 渲染库
**决策**: 使用 `react-markdown`
**理由**:
- 主流、轻量、与 React 19 兼容
- 默认不解析 HTML，安全性好
- 支持自定义组件以匹配现有 Tailwind 样式
**备选**: `marked` + `DOMPurify` — 需手动处理 XSS，集成成本更高

### 2. 流式输出期间的渲染策略
**决策**: 流式输出时仍用 Markdown 渲染，对部分内容做容错
**理由**:
- 用户更早看到排版效果
- `react-markdown` 对不完整语法会按原文展示，不会报错
- 若改为流式时纯文本、完成后切 Markdown，会有明显闪烁
**备选**: 流式时纯文本 — 实现简单，但切换时体验差

### 3. 渲染条件分支
**决策**: 仅对「非表单、非保存中」的 assistant 文本消息启用 Markdown
**理由**:
- 表单 (`<form`) 必须用 `dangerouslySetInnerHTML`，不能走 Markdown
- 「正在保存...」为固定 UI，无需 Markdown
- 与现有 `isHtmlForm`、`isSavingMessage` 分支逻辑一致

### 4. Prompt 调整范围
**决策**: 修改 `SYSTEM_PROMPT`、`SYSTEM_PROMPT_NOT_LOGGED_IN`、`RESULT_ANALYSIS_PROMPT`
**理由**:
- 覆盖意图识别、闲聊、结果分析三类主要回复
- 统一加入「言简意赅、善用 Markdown」的指导
- 移除 `RESULT_ANALYSIS_PROMPT` 中「不要使用 Markdown」的约束

### 5. 样式与安全
**决策**: 使用 `react-markdown` 默认组件，通过 `className` 继承现有 `text-sm text-text-primary leading-relaxed`
**理由**:
- 保持与当前气泡样式一致
- 不启用 `rehype-raw`，避免引入未过滤 HTML 的安全风险

## Risks / Trade-offs

- **[风险]** 流式输出时 Markdown 不完整，可能短暂显示异常（如 `**粗体` 未闭合）
  - **缓解**: 常见语法（`**`、`- `）多为短结构，影响有限；`react-markdown` 对异常输入会按原文展示

- **[风险]** AI 输出含未转义特殊字符，影响 Markdown 解析
  - **缓解**: `react-markdown` 对标准 Markdown 字符处理稳健；若遇极端输入，可后续增加 `remark-gfm` 等插件或 sanitize

- **[风险]** 新增依赖增加打包体积
  - **缓解**: `react-markdown` 体积较小（~20KB gzipped），可接受

## Migration Plan

1. 前端：`npm install react-markdown`，修改 `MessageBubble.tsx` 中 `AssistantMessage` 的文本渲染分支
2. 后端：修改 `nodes.py` 中相关 prompt 常量
3. 重启服务验证：`./START_ALL_SERVICES.sh`
4. 回滚：还原 `MessageBubble.tsx` 与 `nodes.py`，移除 `react-markdown` 依赖

## Open Questions

1. 是否需要对代码块（`` ` ``、```）做语法高亮？若需要，可后续引入 `react-syntax-highlighter`
2. 是否允许 AI 输出中的链接可点击？`react-markdown` 默认将链接渲染为 `<a>`，可配置 `target="_blank"` 等

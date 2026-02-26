## 1. 依赖与前端 Markdown 渲染

- [x] 1.1 在 finance-web 中安装 react-markdown 依赖
- [x] 1.2 在 MessageBubble 的 AssistantMessage 中，对非表单、非保存中的文本消息使用 ReactMarkdown 渲染
- [x] 1.3 确保 TypewriterText 与 Markdown 渲染兼容（流式输出时内容传入 ReactMarkdown）
- [x] 1.4 为 Markdown 渲染的容器添加与现有气泡一致的 className（text-sm text-text-primary leading-relaxed）

## 2. 后端 Prompt 调整

- [x] 2.1 更新 SYSTEM_PROMPT_NOT_LOGGED_IN，加入言简意赅、善用 Markdown 的指导
- [x] 2.2 更新 SYSTEM_PROMPT，加入言简意赅、善用 Markdown 的指导
- [x] 2.3 更新 RESULT_ANALYSIS_PROMPT，移除「不要使用 Markdown」限制，改为鼓励使用 Markdown 增强可读性

## 3. 验证

- [x] 3.1 重启服务（./START_ALL_SERVICES.sh），验证前端 Markdown 渲染正常
- [x] 3.2 验证表单消息（登录/注册）仍正确渲染，未被误解析为 Markdown
- [x] 3.3 验证流式输出时 Markdown 能正确渲染
- [x] 3.4 验证 AI 回复（闲聊、结果分析）排版更清晰、言简意赅

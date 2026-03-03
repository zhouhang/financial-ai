## Why

每次用户登录时，系统会自动创建一个新对话，而不是打开最近的历史对话。这导致用户每次登录都需要切换到之前的对话，使用体验不佳。用户希望登录后默认打开最近的历史对话，减少操作步骤。

## What Changes

- 修改登录成功后的会话选择逻辑：不再自动创建新对话
- 登录成功后，加载会话列表并选中最近一次对话（按更新时间排序）
- **修复竞态条件**：在 `serverConversations` 加载完成前，不创建新对话
- 保留登录成功后的 `loginConvIdRef` 逻辑，用于清理登录过程中创建的临时对话

## Capabilities

### New Capabilities
- `conversation-history`: 登录时加载并显示最近会话
  - 支持获取用户会话列表并按时间排序
  - 支持选中最近会话（不创建新对话）

### Modified Capabilities
- (无现有需求变更)

## Impact

- **前端代码**: `finance-web/src/App.tsx` - 修复登录成功后的 useEffect 竞态条件
  - 问题：初始 `isLoadingConversations=false`，导致 useEffect 在 `loadConversations()` 执行前就触发了
  - 解决：添加额外检查，确保 `loadConversations` 正在加载时才创建新对话
- **API**: `/api/conversations` - 获取用户会话列表（已存在）
- **用户交互**: 登录后默认显示最近对话，而非创建新对话

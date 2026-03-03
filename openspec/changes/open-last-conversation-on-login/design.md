## Context

当前登录成功后选择会话的逻辑存在竞态条件：
- 初始状态 `isLoadingConversations = false`，`serverConversations = []`
- 登录成功后调用 `loadConversations()`，但在该函数设置 `isLoading = true` 之前，useEffect 已触发
- useEffect 检查 `isLoadingConversations = false`，跳过等待
- 然后检查 `serverConversations.length === 0`，进入 else 分支创建新对话

## Goals / Non-Goals

**Goals:**
- 修复登录后创建新对话的竞态条件
- 确保登录后始终选中最近的历史对话（如果有）
- 保持无历史对话时创建新对话的原有行为

**Non-Goals:**
- 不修改游客模式的行为
- 不修改会话列表的排序逻辑（已按 updated_at DESC）

## Decisions

### Decision 1: 修改 useEffect 条件检查
**选择**: 在 useEffect 中添加 `authToken` 检查，确保只有在已登录状态下才处理

**理由**: 
- `authToken` 在登录成功后才会存在
- 当 `authToken` 存在但 `serverConversations` 为空时，应等待加载完成而不是创建新对话

**替代方案考虑**:
- 在 `handleLoginSuccess` 中先设置临时状态 - 需要修改 useConversations hook，复杂度更高

### Decision 2: 简化条件逻辑
**选择**: 依赖 `authToken` 和 `serverConversations` 的存在性来判断是否需要等待

**理由**:
- `authToken` 存在 = 已登录
- `serverConversations` 有值 = 已加载完成
- 逻辑清晰，易于理解和维护

## Risks / Trade-offs

- **风险**: 如果 `loadConversations` 失败或超时，可能会一直等待
- **缓解**: `loadConversations` 内部有错误处理，最终会设置 `isLoading = false`，触发超时逻辑

## Migration Plan

1. 修改 `App.tsx` 中的 useEffect 逻辑
2. 测试以下场景：
   - 有历史对话：登录后应选中最近对话
   - 无历史对话：登录后应创建新对话
   - 刷新页面：应保持当前会话状态

## Open Questions

无

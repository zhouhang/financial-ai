## Context

在 `finance-web/src/App.tsx` 中，多会话功能存在响应路由 bug：
- 用户在会话1发送消息后，立即点击"开启新会话"创建会话2
- AI 的回复会错误地出现在会话2，而非原始会话1

**当前代码分析**：
- `handleSendMessage` (L323-346): 发送消息时使用当前 `activeConvId`
- `handleNewConversation` (L376-384): 创建新会话时设置 `activeConvId = 新会话ID`，并错误地执行 `setIsLoading(false)`
- `handleWsMessage` (L99-257): 接收 AI 响应时使用当前 `activeConvId` 添加消息

**根本原因**：
1. 发送消息时未"锁定"目标会话，导致响应可能被路由到错误的会话
2. 创建新会话时错误地重置了 `isLoading` 状态
3. 响应处理时仅依赖当前 `activeConvId`，而非记录响应应该返回的会话

## Goals / Non-Goals

**Goals:**
- 修复响应路由 bug，确保 AI 回复发送到正确的会话
- 保持用户快速切换会话的体验不受影响
- 不引入明显的性能开销

**Non-Goals:**
- 不重新设计整个会话管理架构
- 不修改 WebSocket 协议
- 不添加持久化会话状态（刷新页面行为保持现状）

## Decisions

### Decision 1: 使用请求上下文追踪响应目标会话

**选择**：在发送消息时记录目标会话 ID，后续响应使用该 ID 而非当前 activeConvId

**理由**：
- 最小改动原则，只需在 `handleSendMessage` 记录发送时的会话 ID
- `handleWsMessage` 已有闭包访问 `activeConvId`，可改为使用记录的 ID

**替代方案**：
- 在 WebSocket 消息中传递会话 ID → 需要修改后端协议
- 使用全局变量存储"进行中的请求" → 引入不必要的状态管理复杂度

### Decision 2: 移除 `handleNewConversation` 中的 `setIsLoading(false)`

**选择**：删除创建新会话时的 `setIsLoading(false)` 调用

**理由**：
- 该调用导致正在处理中的请求被错误标记为完成
- 创建新会话不应影响现有请求的处理状态

**风险**：如果用户在没有发送消息的情况下创建新会话，`isLoading` 可能保持 true  
**缓解**：在 `handleSelectConversation` 中已有 `setIsLoading(false)`，用户切换到任何会话都会重置状态

### Decision 3: 记录"发送消息时的会话 ID"供响应路由使用

**选择**：使用 `useRef` 存储发送消息时的目标会话 ID

**理由**：
- `useRef` 变化不会触发重渲染
- 响应处理回调中可稳定访问发送时的会话 ID

**实现**：
```typescript
const pendingConvIdRef = useRef<string | null>(null);

const handleSendMessage = useCallback((text: string, ...) => {
  pendingConvIdRef.current = activeConvId;
  // ... 发送消息
}, [activeConvId]);

const handleWsMessage = useCallback((data: WsOutgoing) => {
  const targetConvId = pendingConvIdRef.current || activeConvId;
  // ... 使用 targetConvId 添加消息
}, [activeConvId]);
```

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| 快速连续发送多条消息到不同会话 | 响应可能被路由到错误的会话 | 仅修复单次发送后立即创建新会话的场景；连续发送暂不处理 |
| `pendingConvIdRef` 未被正确清理 | 边缘情况下内存泄漏 | 在 `done` 事件中清理 `pendingConvIdRef.current = null` |
| 并发请求（同时发送多条消息） | 响应顺序不确定时可能错乱 | 当前后端不支持并发，此风险可忽略 |

## Open Questions

1. **是否需要在用户中断请求时清理 `pendingConvIdRef`？**  
   - 当前有 `interrupt` 事件处理，建议在该处理中也清理状态

2. **是否需要通知后端会话切换事件？**  
   - 当前设计不依赖后端感知会话变化，保持前端自治

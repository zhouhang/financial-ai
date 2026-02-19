## 1. 添加响应目标会话追踪

- [x] 1.1 在 App.tsx 中添加 `pendingConvIdRef` useRef 声明
- [x] 1.2 在 handleSendMessage 中设置 `pendingConvIdRef.current = activeConvId`

## 2. 修改响应路由逻辑

- [x] 2.1 修改 handleWsMessage 中的 'stream' 事件处理，使用 `pendingConvIdRef.current || activeConvId`
- [x] 2.2 修改 handleWsMessage 中的 'message' 事件处理，使用 `pendingConvIdRef.current || activeConvId`

## 3. 修复 Loading 状态管理

- [x] 3.1 从 handleNewConversation 中移除 `setIsLoading(false)` 调用

## 4. 清理状态

- [x] 4.1 在 handleWsMessage 中的 'done' 事件处理中添加 `pendingConvIdRef.current = null`
- [x] 4.2 在 handleWsMessage 中的 'interrupt' 事件处理中添加 `pendingConvIdRef.current = null`

## 5. 验证

- [x] 5.1 运行 TypeScript 类型检查
- [ ] 5.2 测试场景：会话1发送消息后立即创建新会话，验证响应出现在会话1
- [ ] 5.3 测试场景：会话1发送消息后切换到会话2，验证响应出现在会话1

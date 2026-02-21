## 1. 修复历史会话加载

- [x] 1.1 修改 `useConversations.ts` 的 useEffect，移除对 loadConversations 的依赖，直接在 effect 内部实现加载逻辑
- [x] 1.2 验证页面刷新后历史会话正确加载（登录状态下）

## 2. 侧边栏会话删除功能

- [x] 2.1 修改 `Sidebar.tsx`：添加 `onDeleteConversation` prop 类型定义
- [x] 2.2 修改 `Sidebar.tsx`：添加悬停状态管理（useState 跟踪 hoveredId）
- [x] 2.3 修改 `Sidebar.tsx`：在会话项中添加删除按钮（Trash2 图标，悬停时显示）
- [x] 2.4 修改 `Sidebar.tsx`：实现删除点击处理（confirm 确认 + 调用回调）
- [x] 2.5 修改 `App.tsx`：创建 handleDeleteConversation 回调函数
- [x] 2.6 修改 `App.tsx`：传递 onDeleteConversation prop 给 Sidebar
- [x] 2.7 修改 `App.tsx`：删除活动会话后自动切换到其他会话

## 3. 任务启动消息删除

- [x] 3.1 修改 `App.tsx` handleWsMessage：在收到 'message' 类型时检测是否为任务结果
- [x] 3.2 修改 `App.tsx` handleWsMessage：如果是任务结果，删除之前的"🚀 对账任务已启动"消息
- [x] 3.3 验证对账任务完成后只显示任务概述消息

## 4. 测试验证

- [x] 4.1 重启服务 (`./START_ALL_SERVICES.sh`)
- [ ] 4.2 测试：登录后刷新页面，验证历史会话显示
- [ ] 4.3 测试：悬停会话显示删除按钮，点击删除并确认
- [ ] 4.4 测试：上传文件执行对账，验证只显示任务概述消息

# 登录状态同步修复

## 问题现象

**UI不一致**：
- **左下角**显示：admin已登录（从localStorage读取）
- **对话框**显示：未登录提示，要求重新登录

## 根本原因分析

### 状态来源的差异

| 组件 | 状态来源 | 更新时机 |
|------|---------|---------|
| **Sidebar（左下角）** | localStorage中的currentUser | 用户登录时保存 |
| **ChatArea（对话框）** | 后端返回的消息 | 每次发送消息时 |

### 为什么会不一致

1. **首次访问**：用户登录成功
   - localStorage保存了authToken和currentUser
   - Sidebar显示已登录

2. **离开再回来**（刷新页面）
   - App.tsx从localStorage恢复currentUser
   - Sidebar显示已登录
   - 但WebSocket连接建立时**未发送验证请求**
   - 后端不知道前端有有效的认证

3. **用户发送消息**
   - 虽然authToken被发送到后端
   - 但后端可能已经因为token过期而拒绝
   - 后端回复"未登录"
   - **Sidebar和ChatArea状态不同步**

## 三层修复方案

### 1. 前端修复（App.tsx）

**问题**：WebSocket连接建立后没有验证现有的authToken

**修复**：
```typescript
// 添加WebSocket连接时的认证验证
const handleWsConnected = useCallback(() => {
  if (authToken) {
    console.log('WebSocket connected, verifying stored auth token...');
    sendMessage('', activeConvId, false, authToken);  // 空消息 + token
  }
}, [authToken, sendMessage, activeConvId]);

// 在useWebSocket中使用onConnect回调
const { status, sendMessage } = useWebSocket({
  onMessage: handleWsMessage,
  onConnect: handleWsConnected,
});
```

**作用**：WebSocket连接成功后，自动发送一条含有authToken的验证消息

### 2. 后端修复（server.py）

**问题**：后端没有处理"空消息+token"的认证验证请求

**修复**：
```python
# 在websocket_chat中添加认证验证逻辑
if not user_msg and not is_resume and auth_token:
    logger.info(f"收到认证验证请求")
    try:
        me_result = await auth_me(auth_token)
        if me_result.get("success"):
            await ws.send_json({
                "type": "auth_verify",
                "success": True,
                "user": me_result.get("user"),
            })
        else:
            await ws.send_json({
                "type": "auth_verify",
                "success": False,
            })
    except Exception as e:
        await ws.send_json({
            "type": "auth_verify",
            "success": False,
        })
    continue  # 认证验证完成，不继续处理
```

**作用**：
- 验证token是否仍然有效
- 返回auth_verify消息给前端
- 包含验证结果和用户信息

### 3. 前端状态处理（App.tsx）

**问题**：前端没有处理auth_verify响应，无法同步状态

**修复**：
```typescript
case 'auth_verify':
  if (data.success) {
    // token 有效，同步用户信息
    if (data.user) {
      setCurrentUser(data.user);
      localStorage.setItem('tally_current_user', JSON.stringify(data.user));
    }
    console.log('Auth token verified successfully');
  } else {
    // token 已过期或无效，清除本地凭证
    console.log('Auth token verification failed, clearing credentials');
    setAuthToken(null);
    setCurrentUser(null);
    localStorage.removeItem('tally_auth_token');
    localStorage.removeItem('tally_current_user');
  }
  break;
```

**作用**：
- 根据后端验证结果更新前端状态
- 如果token有效：保持登录状态和显示用户信息
- 如果token无效：清除localStorage，**强制显示未登录**

## 数据流图

### 修复前（问题流程）
```
App启动
  ↓
从localStorage读取authToken和currentUser
  ↓
Sidebar显示"admin已登录" ✅
  ↓
WebSocket连接建立
  ❌ 没有发送验证请求
  ↓
用户发送消息
  ↓
后端：token已过期，回复"未登录"
  ↓
ChatArea显示"未登录提示"❌
  ↓
**Sidebar和ChatArea状态不一致**🔴
```

### 修复后（正确流程）
```
App启动
  ↓
从localStorage读取authToken和currentUser
  ↓
Sidebar暂时显示"admin已登录"
  ↓
WebSocket连接建立
  ↓
✅ handleWsConnected触发
  ↓
✅ 发送空消息+authToken验证请求
  ↓
后端收到auth_verify请求
  ↓
后端验证token → auth_me()
  ↓
  ├─ token有效 → 返回success=true + user信息
  │           → Sidebar保持显示已登录
  │           → App继续正常运行 ✅
  │
  └─ token无效/过期 → 返回success=false
              → App清除localStorage
              → Sidebar更新为"为登录未登录"
              → ChatArea显示"请登录" ✅
              → **状态一致** ✅
```

## 关键改进点

| 问题 | 原因 | 修复 | 结果 |
|------|------|------|------|
| Sidebar显示已登录但无法使用 | localStorage数据过期 | 连接时验证token | ✅ |
| 前后端状态不同步 | 没有验证流程 | 添加auth_verify消息 | ✅ |
| 刷新后显示混乱 | 缺少一致性检查 | 关闭连接时同步状态 | ✅ |

## 代码位置

### 前端修改
- **文件**：`finance-web/src/App.tsx`
  - 第82-89行：添加`handleWsConnected`函数
  - 第180-207行：添加`case 'auth_verify'`处理
  - 第265行：在useWebSocket中添加`onConnect: handleWsConnected`

- **文件**：`finance-web/src/types.ts`
  - 第73行：WsOutgoing.type添加'auth_verify'
  - 第82行：添加`success?: boolean`字段

### 后端修改
- **文件**：`finance-agents/data-agent/app/server.py`
  - 第248-279行：添加认证验证逻辑

## 测试验证

### 测试场景1：正常登录流程
1. 打开应用，点击"我要登录"
2. 输入用户名密码登录
3. ✅ Sidebar显示已登录
4. ✅ ChatArea可正常使用
5. 刷新页面
6. ✅ Sidebar继续显示已登录
7. ✅ WebSocket自动验证token并保持登录

### 测试场景2：token过期
1. 清除后端的token有效期缓存（模拟过期）
2. 刷新页面
3. ✅ WebSocket连接后开始验证
4. ✅ 后端返回success=false
5. ✅ Sidebar自动更新为"未登录"
6. ✅ localStorage被清除
7. ✅ 前后端状态一致

### 预期效果
- **修复前**：状态混乱，容易迷惑用户
- **修复后**：状态始终一致，用户体验流畅

## 后续考虑

1. **Token刷新机制**：如果token即将过期，可以在验证时自动刷新
2. **错误提示**：当验证失败时，可以向用户展示友好的提示
3. **自动重新登录**：如果token过期，可以引导用户快速重新登录
4. **多标签同步**：使用localStorage事件在多标签页间同步认证状态

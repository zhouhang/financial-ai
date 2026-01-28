# ✅ Dify 配置和 [create_schema] 标签解析修复

## 📝 完成的工作

### 1. 将 Dify API 配置移到环境变量

#### 修改的文件

**`.env` 文件**:
```bash
VITE_API_BASE_URL=http://localhost:8000/api
VITE_DIFY_API_URL=http://localhost/v1
VITE_DIFY_API_KEY=app-pffBjBphPBhbrSwz8mxku2R3
```

**`src/api/dify.ts`**:
```typescript
// 之前：硬编码
const DIFY_API_URL = 'http://localhost/v1';
const DIFY_API_KEY = 'app-pffBjBphPBhbrSwz8mxku2R3';

// 现在：从环境变量读取
const DIFY_API_URL = import.meta.env.VITE_DIFY_API_URL || 'http://localhost/v1';
const DIFY_API_KEY = import.meta.env.VITE_DIFY_API_KEY || 'app-pffBjBphPBhbrSwz8mxku2R3';
```

**`src/components/Home/Home.tsx`**:
```typescript
// 之前：硬编码
const response = await fetch('http://localhost/v1/chat-messages', {
  headers: {
    'Authorization': 'Bearer app-pffBjBphPBhbrSwz8mxku2R3',
  },
});

// 现在：从环境变量读取
const response = await fetch(`${import.meta.env.VITE_DIFY_API_URL}/chat-messages`, {
  headers: {
    'Authorization': `Bearer ${import.meta.env.VITE_DIFY_API_KEY}`,
  },
});
```

### 2. 修复 [create_schema] 标签解析问题

#### 问题分析
Dify 返回的响应中包含 `[create_schema]` 标签，但前端没有正确检测到命令。

#### 解决方案
在 `src/stores/chatStore.ts` 中添加了从响应文本中检测命令的逻辑：

```typescript
// 如果 metadata 中没有命令，从响应文本中检测
if (!detectedCommand && fullAnswer) {
  const commands = {
    '\\[create_schema\\]': 'create_schema',
    '\\[update_schema\\]': 'update_schema',
    '\\[schema_list\\]': 'schema_list',
    '\\[login_form\\]': 'login_form',
  };

  for (const [pattern, command] of Object.entries(commands)) {
    if (new RegExp(pattern, 'i').test(fullAnswer)) {
      detectedCommand = command;
      console.log('[ChatStore] Command detected from answer text:', detectedCommand);
      break;
    }
  }
}
```

## 🔧 如何修改配置

### 修改 Dify API 地址
编辑 `.env` 文件：
```bash
# 本地开发
VITE_DIFY_API_URL=http://localhost/v1

# 生产环境
VITE_DIFY_API_URL=https://your-dify-domain.com/v1
```

### 修改 Dify API Key
编辑 `.env` 文件：
```bash
VITE_DIFY_API_KEY=your-new-api-key
```

### 重启前端服务
修改 `.env` 后需要重启前端：
```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```

## 🎯 支持的特殊指令

| 指令 | 说明 | 触发的 UI |
|------|------|-----------|
| `[login_form]` | 登录表单 | 渲染登录表单 |
| `[create_schema]` | 创建 Schema | 显示"开始创建规则"按钮 |
| `[update_schema]` | 更新 Schema | 显示更新表单 |
| `[schema_list]` | Schema 列表 | 显示列表 |

## 🔍 命令检测流程

### 1. 从 Dify metadata 检测
```
Dify 返回响应
  ↓
检查 data.metadata.command
  ↓
如果存在，使用该命令
```

### 2. 从响应文本检测（备用方案）
```
Dify 返回响应
  ↓
metadata 中没有 command
  ↓
在 answer 文本中搜索 [create_schema] 等标签
  ↓
使用正则表达式匹配
  ↓
设置对应的命令
```

### 3. 渲染对应的 UI
```
检测到命令
  ↓
在 Home.tsx 中根据 message.command 渲染
  ↓
- login_form → renderLoginForm()
- create_schema → renderCreateSchemaButton()
- 其他 → 直接显示文本
```

## 🧪 测试步骤

### 1. 测试配置是否生效
```bash
# 启动前端
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev

# 打开浏览器控制台
# 检查网络请求是否使用了正确的 URL 和 API Key
```

### 2. 测试 [create_schema] 标签解析
```bash
# 1. 访问 http://localhost:5173
# 2. 在聊天框输入 "创建规则" 或类似的消息
# 3. 检查 Dify 返回的响应
# 4. 检查浏览器控制台日志：
#    - [ChatStore] Received event: ...
#    - [ChatStore] Command detected from answer text: create_schema
# 5. 检查是否显示"开始创建规则"按钮
```

### 3. 测试按钮点击
```bash
# 1. 点击"开始创建规则"按钮
# 2. 检查是否打开创建 Schema 的 Modal
# 3. 填写表单并提交
# 4. 检查是否成功创建
```

## 🐛 调试技巧

### 查看命令检测日志
打开浏览器控制台（F12），查看以下日志：

```javascript
// 接收到的事件
[ChatStore] Received event: message {...}

// 最终更新
[ChatStore] Final update - detectedCommand: create_schema

// 从文本检测到命令
[ChatStore] Command detected from answer text: create_schema

// 更新消息
[ChatStore] Updating message: assistant-123 with command: create_schema

// 渲染消息
[Home] Rendering message: assistant-123 command: create_schema
```

### 检查 Dify 响应格式
在浏览器控制台的 Network 标签中：
1. 找到 `chat-messages` 请求
2. 查看响应内容
3. 确认响应中是否包含 `[create_schema]` 标签

**期望的响应格式**:
```json
{
  "event": "message",
  "message_id": "xxx",
  "conversation_id": "xxx",
  "answer": "好的，我来帮你创建规则 [create_schema]",
  "metadata": {
    "command": "create_schema"  // 可选，如果有会优先使用
  }
}
```

### 常见问题

#### 问题 1: 命令没有被检测到
**原因**: Dify 返回的文本中没有包含标签，或标签格式不正确

**解决**:
1. 检查 Dify 响应中是否包含 `[create_schema]`
2. 确认标签格式正确（方括号、小写、下划线）
3. 检查浏览器控制台是否有错误

#### 问题 2: 按钮没有显示
**原因**: 命令检测到了，但 UI 没有正确渲染

**解决**:
1. 检查 `Home.tsx` 中的 `renderCreateSchemaButton` 函数
2. 确认 `message.command === 'create_schema'` 条件成立
3. 检查 CSS 样式是否正确

#### 问题 3: 点击按钮没有反应
**原因**: 事件监听器没有正确绑定

**解决**:
1. 检查 `setupCreateSchemaButtons` 函数是否被调用
2. 确认按钮的 `data-message-id` 属性正确
3. 检查 Modal 状态是否正确更新

## 📊 完整的数据流

### 用户请求创建 Schema
```
1. 用户输入: "帮我创建一个规则"
   ↓
2. finance-ui 调用 Dify API
   POST ${VITE_DIFY_API_URL}/chat-messages
   Authorization: Bearer ${VITE_DIFY_API_KEY}
   ↓
3. Dify 返回响应
   {
     answer: "好的，我来帮你创建规则 [create_schema]",
     metadata: { command: "create_schema" }
   }
   ↓
4. chatStore 检测命令
   - 优先从 metadata.command 获取
   - 如果没有，从 answer 文本中正则匹配
   ↓
5. 设置 message.command = 'create_schema'
   ↓
6. Home.tsx 渲染
   - 检测到 message.command === 'create_schema'
   - 调用 renderCreateSchemaButton()
   - 渲染"开始创建规则"按钮
   ↓
7. 用户点击按钮
   - 触发 setupCreateSchemaButtons 中的事件监听器
   - 设置 createSchemaModalVisible = true
   - 打开创建 Schema 的 Modal
   ↓
8. 用户填写表单并提交
   - 表单数据通过 Dify API 发送
   - Dify 调用 finance-mcp API 创建 Schema
   - 返回创建成功的消息
```

## 📚 相关文件

| 文件 | 说明 |
|------|------|
| `.env` | 环境变量配置 |
| `src/api/dify.ts` | Dify API 客户端 |
| `src/stores/chatStore.ts` | 聊天状态管理（命令检测） |
| `src/components/Home/Home.tsx` | 主界面（命令渲染） |

## ✅ 修复完成清单

- [x] 将 Dify API URL 移到环境变量
- [x] 将 Dify API Key 移到环境变量
- [x] 更新 `dify.ts` 使用环境变量
- [x] 更新 `Home.tsx` 使用环境变量
- [x] 添加从响应文本检测命令的逻辑
- [x] 完善命令检测日志
- [x] 创建配置和调试文档

## 🎯 下一步

1. **测试配置**
   ```bash
   cd /Users/kevin/workspace/financial-ai/finance-ui
   npm run dev
   ```

2. **测试命令检测**
   - 在聊天框输入 "创建规则"
   - 检查控制台日志
   - 确认按钮显示

3. **测试完整流程**
   - 点击"开始创建规则"按钮
   - 填写 Schema 表单
   - 提交并验证

4. **配置 Dify**
   - 确保 Dify 返回的响应包含 `[create_schema]` 标签
   - 或者在 metadata 中包含 `command: "create_schema"`

---

**修复日期**: 2026-01-27
**状态**: ✅ 完成
**测试状态**: ⏳ 待测试

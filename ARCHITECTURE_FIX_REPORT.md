# 架构修正完成报告

## ✅ 已完成的修正

### 1. 删除 finance-ui 中调用 finance-mcp API 的代码

#### 删除的文件
- ✅ `src/api/auth.ts` - 认证 API 客户端
- ✅ `src/api/schemas.ts` - Schema API 客户端
- ✅ `src/api/files.ts` - 文件 API 客户端
- ✅ `src/api/client.ts` - Axios 客户端

#### 保留的文件
- ✅ `src/api/dify.ts` - Dify API 客户端（唯一的 API 调用）

### 2. 更新 Dify API 配置

```typescript
// src/api/dify.ts
const DIFY_API_URL = 'http://localhost/v1';
const DIFY_API_KEY = 'app-pffBjBphPBhbrSwz8mxku2R3';
```

**请求示例**:
```typescript
fetch('http://localhost/v1/chat-messages', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer app-pffBjBphPBhbrSwz8mxku2R3',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    inputs: {},
    query: '用户消息',
    response_mode: 'streaming',
    user: 'anonymous_user',
  }),
});
```

### 3. 修改 Store 文件

#### authStore.ts
- ✅ 移除 `authApi` 导入
- ✅ 添加警告：所有认证操作通过 Dify 处理
- ✅ 添加 `setAuthFromDify()` 方法用于从 Dify 响应设置认证状态

#### schemaStore.ts
- ✅ 移除 `schemaApi` 导入
- ✅ 添加警告：所有 Schema 操作通过 Dify 处理
- ✅ 添加本地状态管理方法：
  - `setSchemas()` - 设置 Schema 列表
  - `addSchema()` - 添加 Schema
  - `updateSchemaInList()` - 更新 Schema
  - `removeSchema()` - 删除 Schema
  - `setCurrentSchema()` - 设置当前 Schema

#### canvasStore.ts
- ✅ 移除 `schemaApi` 导入
- ✅ 修改 `validateSchema()` - 返回警告信息
- ✅ 修改 `testSchema()` - 返回警告信息
- ✅ 修改 `saveSchema()` - 抛出错误提示

#### SchemaMetadataForm.tsx
- ✅ 移除 `schemaApi` 导入
- ✅ 修改 `handleNameChange()` - 本地生成 type_key（临时方案）
- ✅ 修改 `handleSubmit()` - 移除 API 调用

## 📐 正确的架构

```
┌─────────────────────────────────────────────────────────┐
│                      用户                                │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   finance-ui                            │
│                  (纯前端 React)                          │
│                                                         │
│  - 只调用 Dify API                                      │
│  - 解析 Dify 响应中的指令                               │
│  - 渲染相应的 UI 组件                                   │
│  - 管理本地状态                                         │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ HTTP POST
                         │ Bearer app-pffBjBphPBhbrSwz8mxku2R3
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Dify API                              │
│              (http://localhost/v1)                      │
│                                                         │
│  - 接收用户消息                                         │
│  - AI 对话编排                                          │
│  - 调用 finance-mcp 的 API 和 MCP 工具                 │
│  - 返回响应（包含指令）                                 │
└────────────┬───────────────────────┬────────────────────┘
             │                       │
             │ HTTP API              │ MCP Protocol
             ▼                       ▼
┌─────────────────────┐    ┌─────────────────────┐
│  finance-mcp API    │    │  finance-mcp MCP    │
│  (localhost:8000)   │    │  (localhost:3335)   │
│                     │    │                     │
│  - 认证 API         │    │  - 数据整理工具     │
│  - Schema API       │    │  - 对账工具         │
│  - 文件 API         │    │  - 文件上传工具     │
└──────────┬──────────┘    └──────────┬──────────┘
           │                          │
           └──────────┬───────────────┘
                      ▼
           ┌─────────────────────┐
           │   数据库 + 文件系统  │
           └─────────────────────┘
```

## 🔄 数据流示例

### 场景 1: 用户登录
```
1. 用户在 finance-ui 输入 "登录"
   ↓
2. finance-ui 发送到 Dify
   POST http://localhost/v1/chat-messages
   Header: Bearer app-pffBjBphPBhbrSwz8mxku2R3
   Body: { query: "登录", ... }
   ↓
3. Dify 识别登录意图，返回 [login_form] 指令
   ↓
4. finance-ui 检测指令，显示登录表单
   ↓
5. 用户填写表单提交
   ↓
6. finance-ui 发送表单数据到 Dify
   Body: { query: "用户名: xxx, 密码: xxx", ... }
   ↓
7. Dify 调用 finance-mcp API
   POST http://localhost:8000/api/auth/login
   ↓
8. finance-mcp 验证用户，返回 token
   ↓
9. Dify 返回登录成功消息 + token
   ↓
10. finance-ui 调用 authStore.setAuthFromDify(user, token)
    保存认证状态
```

### 场景 2: 创建 Schema
```
1. 用户在 finance-ui 输入 "创建规则"
   ↓
2. finance-ui 发送到 Dify
   ↓
3. Dify 返回 [create_schema] 指令
   ↓
4. finance-ui 显示创建表单
   ↓
5. 用户填写表单提交
   ↓
6. finance-ui 发送表单数据到 Dify
   Body: { query: "创建规则: {...}", ... }
   ↓
7. Dify 调用 finance-mcp API
   POST http://localhost:8000/api/schemas
   ↓
8. finance-mcp 保存 Schema 到数据库
   ↓
9. Dify 返回创建成功消息 + Schema 对象
   ↓
10. finance-ui 调用 schemaStore.addSchema(schema)
    更新本地状态
```

### 场景 3: 数据整理
```
1. 用户上传文件并输入 "整理数据"
   ↓
2. finance-ui 发送到 Dify（包含文件信息）
   ↓
3. Dify 调用 finance-mcp MCP 工具
   Tool: data_preparation_start
   ↓
4. finance-mcp 执行数据整理任务
   ↓
5. Dify 返回处理结果
   ↓
6. finance-ui 显示结果
```

## 📝 需要在 Dify 中配置的内容

### 1. API 集成
Dify 需要配置调用 finance-mcp API:
- Base URL: `http://localhost:8000/api`
- 认证: 可能需要配置 API Key 或其他认证方式

### 2. MCP 集成
Dify 需要配置 MCP 服务器:
- MCP Server URL: `http://localhost:3335`
- 可用工具:
  - `data_preparation_start` - 数据整理
  - `reconciliation_start` - 对账
  - `file_upload` - 文件上传

### 3. 指令定义
Dify 需要在响应中包含特殊指令:
- `[login_form]` - 显示登录表单
- `[create_schema]` - 显示创建 Schema 表单
- `[update_schema]` - 显示更新 Schema 表单
- `[schema_list]` - 显示 Schema 列表

## 🎯 下一步工作

### 1. 测试 finance-ui
```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```

访问 http://localhost:5173，测试：
- [ ] Dify API 调用是否正常
- [ ] 指令检测是否工作
- [ ] UI 渲染是否正确

### 2. 配置 Dify
- [ ] 配置 finance-mcp API 集成
- [ ] 配置 MCP 服务器连接
- [ ] 定义对话流程和指令

### 3. 测试完整流程
- [ ] 用户登录流程
- [ ] Schema 创建流程
- [ ] 数据整理流程
- [ ] 对账流程

## 📚 相关文档

- [Dify API 文档](http://localhost/app/1ab05125-5865-4833-b6a1-ebfd69338f76/develop)
- [finance-mcp API 文档](http://localhost:8000/docs)
- [架构迁移文档](./ARCHITECTURE_MIGRATION.md)

---

**修正完成日期**: 2026-01-27
**版本**: 2.0
**状态**: ✅ 已完成，等待测试

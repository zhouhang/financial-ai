# Finance AI - 最终架构说明

## 🎯 架构概览

```
用户
 ↓
finance-ui (纯前端)
 ↓ 只调用 Dify API
 ↓ Bearer app-pffBjBphPBhbrSwz8mxku2R3
Dify API (http://localhost/v1/chat-messages)
 ↓
 ├─→ finance-mcp API (http://localhost:8000/api)
 │   ├─ 认证 API
 │   ├─ Schema API
 │   └─ 文件 API
 │
 └─→ finance-mcp MCP (http://localhost:3335)
     ├─ 数据整理工具
     └─ 对账工具
```

## 📦 服务说明

### 1. finance-ui (纯前端)
**位置**: `/Users/kevin/workspace/financial-ai/finance-ui`
**端口**: 5173

**职责**:
- 用户界面展示
- **只调用 Dify API**（不直接调用 finance-mcp）
- 解析 Dify 响应中的特殊指令
- 渲染相应的 UI 组件
- 管理本地状态

**关键文件**:
- `src/api/dify.ts` - Dify API 客户端（唯一的 API 调用）
- `src/stores/` - 本地状态管理
- `src/components/` - UI 组件

**启动**:
```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```

### 2. Dify (AI 编排中心)
**位置**: http://localhost
**API**: http://localhost/v1/chat-messages

**职责**:
- 接收 finance-ui 的消息
- AI 对话流程编排
- 调用 finance-mcp 的 API 和 MCP 工具
- 返回响应（包含特殊指令）

**API Key**: `app-pffBjBphPBhbrSwz8mxku2R3`

**需要配置**:
1. finance-mcp API 集成 (http://localhost:8000/api)
2. finance-mcp MCP 集成 (http://localhost:3335)
3. 对话流程和指令定义

### 3. finance-mcp (核心服务)
**位置**: `/Users/kevin/workspace/financial-ai/finance-mcp`

#### 3.1 API Server (端口 8000)
**职责**: 提供 RESTful API 给 Dify 调用

**API 端点**:
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取用户信息
- `POST /api/schemas` - 创建 Schema
- `GET /api/schemas` - 获取 Schema 列表
- `GET /api/schemas/{id}` - 获取 Schema 详情
- `PUT /api/schemas/{id}` - 更新 Schema
- `DELETE /api/schemas/{id}` - 删除 Schema
- `POST /api/schemas/generate-type-key` - 生成 type_key
- `GET /api/schemas/check-name-exists` - 检查名称
- `POST /api/files/upload` - 上传文件
- `GET /api/files/preview` - 预览文件

**启动**:
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_api_server.sh
```

#### 3.2 MCP Server (端口 3335)
**职责**: 提供 MCP 工具给 Dify 调用

**可用工具**:
- `data_preparation_start` - 启动数据整理任务
- `data_preparation_status` - 查询数据整理状态
- `data_preparation_result` - 获取数据整理结果
- `reconciliation_start` - 启动对账任务
- `reconciliation_status` - 查询对账状态
- `reconciliation_result` - 获取对账结果
- `file_upload` - 上传文件

**启动**:
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_server.sh
```

## 🔄 完整数据流

### 用户登录流程
```
1. 用户在 finance-ui 输入 "我要登录"
   ↓
2. finance-ui 调用 Dify API
   POST http://localhost/v1/chat-messages
   Headers: {
     Authorization: "Bearer app-pffBjBphPBhbrSwz8mxku2R3",
     Content-Type: "application/json"
   }
   Body: {
     query: "我要登录",
     response_mode: "streaming",
     user: "anonymous_user"
   }
   ↓
3. Dify 识别登录意图，返回 [login_form] 指令
   Response: {
     event: "message",
     answer: "请登录 [login_form]"
   }
   ↓
4. finance-ui 检测到 [login_form] 指令
   显示登录表单
   ↓
5. 用户填写用户名和密码，点击登录
   ↓
6. finance-ui 将表单数据发送到 Dify
   POST http://localhost/v1/chat-messages
   Body: {
     query: "登录: 用户名=test, 密码=123456",
     response_mode: "streaming",
     user: "anonymous_user"
   }
   ↓
7. Dify 调用 finance-mcp API
   POST http://localhost:8000/api/auth/login
   Body: {
     username: "test",
     password: "123456"
   }
   ↓
8. finance-mcp 验证用户
   - 查询数据库
   - 验证密码
   - 生成 JWT token
   ↓
9. finance-mcp 返回结果
   Response: {
     access_token: "eyJ...",
     token_type: "bearer",
     user: { id: 1, username: "test", ... }
   }
   ↓
10. Dify 返回登录成功消息
    Response: {
      event: "message",
      answer: "登录成功！",
      metadata: {
        user: { ... },
        token: "eyJ..."
      }
    }
    ↓
11. finance-ui 接收响应
    - 调用 authStore.setAuthFromDify(user, token)
    - 保存到 localStorage
    - 更新 UI 状态
```

### 创建 Schema 流程
```
1. 用户在 finance-ui 输入 "创建一个数据整理规则"
   ↓
2. finance-ui 调用 Dify API
   ↓
3. Dify 返回 [create_schema] 指令
   ↓
4. finance-ui 显示创建 Schema 表单
   ↓
5. 用户填写表单（规则名称、类型、描述等）
   ↓
6. finance-ui 将表单数据发送到 Dify
   Body: {
     query: "创建规则: 名称=销售数据整理, 类型=数据整理, 描述=...",
     ...
   }
   ↓
7. Dify 调用 finance-mcp API
   POST http://localhost:8000/api/schemas
   Body: {
     name_cn: "销售数据整理",
     work_type: "DATA_PREPARATION",
     description: "..."
   }
   ↓
8. finance-mcp 保存 Schema
   - 生成 type_key
   - 保存到数据库
   - 创建 schema 文件
   ↓
9. finance-mcp 返回 Schema 对象
   ↓
10. Dify 返回创建成功消息
    Response: {
      answer: "规则创建成功！",
      metadata: {
        schema: { id: 1, name_cn: "销售数据整理", ... }
      }
    }
    ↓
11. finance-ui 接收响应
    - 调用 schemaStore.addSchema(schema)
    - 更新 UI 显示
```

### 数据整理流程
```
1. 用户上传 Excel 文件
   ↓
2. finance-ui 将文件转为 base64 或获取 URL
   ↓
3. finance-ui 发送到 Dify
   Body: {
     query: "请整理这个文件",
     files: [{ name: "data.xlsx", content: "..." }]
   }
   ↓
4. Dify 调用 finance-mcp MCP 工具
   Tool: data_preparation_start
   Args: {
     schema_type: "monetary_funds",
     files: [...]
   }
   ↓
5. finance-mcp MCP 执行数据整理
   - 读取文件
   - 应用 schema 规则
   - 生成输出文件
   ↓
6. finance-mcp 返回结果
   {
     task_id: "task_123",
     status: "completed",
     output_file: "/path/to/output.xlsx"
   }
   ↓
7. Dify 返回处理结果
   Response: {
     answer: "数据整理完成！",
     metadata: {
       output_file: "...",
       download_url: "..."
     }
   }
   ↓
8. finance-ui 显示结果
   - 显示下载链接
   - 显示预览
```

## 🚀 快速启动

### 方式 1: 一键启动所有服务
```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

### 方式 2: 手动启动

#### 1. 启动 finance-mcp API 服务器
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_api_server.sh
# 或
python3 api_server.py
```

#### 2. 启动 finance-mcp MCP 服务器
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_server.sh
# 或
python3 unified_mcp_server.py
```

#### 3. 启动 finance-ui 前端
```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```

#### 4. 确保 Dify 运行
Dify 应该运行在 http://localhost

### 停止所有服务
```bash
cd /Users/kevin/workspace/financial-ai
./STOP_ALL_SERVICES.sh
```

## 🔧 配置说明

### finance-ui 配置
**文件**: `src/api/dify.ts`
```typescript
const DIFY_API_URL = 'http://localhost/v1';
const DIFY_API_KEY = 'app-pffBjBphPBhbrSwz8mxku2R3';
```

### finance-mcp API 配置
**文件**: `api/config.py`
```python
DATABASE_URL = "mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai"
API_PREFIX = "/api"
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
```

### Dify 配置
需要在 Dify 中配置：
1. **API 集成**: 配置 finance-mcp API (http://localhost:8000/api)
2. **MCP 集成**: 配置 finance-mcp MCP (http://localhost:3335)
3. **对话流程**: 定义指令和响应格式

## 📋 特殊指令

finance-ui 会检测 Dify 响应中的以下指令：

| 指令 | 说明 | UI 行为 |
|------|------|---------|
| `[login_form]` | 显示登录表单 | 渲染登录表单组件 |
| `[create_schema]` | 显示创建 Schema 表单 | 渲染创建 Schema 表单 |
| `[update_schema]` | 显示更新 Schema 表单 | 渲染更新 Schema 表单 |
| `[schema_list]` | 显示 Schema 列表 | 渲染 Schema 列表组件 |

## 🧪 测试验证

### 1. 测试 Dify API 连接
```bash
curl -X POST http://localhost/v1/chat-messages \
  -H "Authorization: Bearer app-pffBjBphPBhbrSwz8mxku2R3" \
  -H "Content-Type: application/json" \
  -d '{
    "inputs": {},
    "query": "你好",
    "response_mode": "blocking",
    "user": "test_user"
  }'
```

### 2. 测试 finance-mcp API
```bash
# 健康检查
curl http://localhost:8000/health

# API 文档
open http://localhost:8000/docs
```

### 3. 测试 finance-ui
```bash
# 访问前端
open http://localhost:5173
```

## 📚 相关文档

- [架构修正报告](./ARCHITECTURE_FIX_REPORT.md) - 详细的修正说明
- [测试清单](./TESTING_CHECKLIST.md) - 完整的测试清单
- [快速启动指南](./QUICK_START.md) - 详细的启动指南

## ⚠️ 重要提示

1. **finance-ui 不直接调用 finance-mcp API**
   - 所有业务逻辑通过 Dify 协调
   - finance-ui 只负责 UI 展示和本地状态管理

2. **Dify 是核心协调者**
   - 接收 finance-ui 的消息
   - 调用 finance-mcp 的 API 和 MCP 工具
   - 返回结果给 finance-ui

3. **finance-mcp 提供双重服务**
   - API Server: 给 Dify 调用的 RESTful API
   - MCP Server: 给 Dify 调用的 MCP 工具

## 🎯 架构优势

✅ **职责清晰**: 每个服务专注于自己的职责
✅ **解耦合**: 前端不直接依赖后端 API
✅ **灵活性**: 可以轻松替换或扩展各个服务
✅ **可维护性**: 代码组织清晰，易于理解和修改
✅ **可扩展性**: 可以独立扩展各个服务

---

**最终版本**: 2.0
**更新日期**: 2026-01-27
**状态**: ✅ 架构修正完成

# Finance AI - 架构重构完成

## 新架构说明

### 1. finance-mcp (核心服务)
**职责**: 提供 MCP 工具 + RESTful API

**服务内容**:
- **MCP Server** (端口 3335): 为 Dify 提供数据整理和对账工具
- **API Server** (端口 8000): 提供认证、Schema 管理、文件上传等 RESTful API

**目录结构**:
```
finance-mcp/
├── api/                          # RESTful API 服务
│   ├── routers/                  # API 路由
│   │   ├── auth.py              # 认证 API
│   │   ├── schemas.py           # Schema 管理 API
│   │   └── files.py             # 文件上传 API
│   ├── models/                   # 数据库模型
│   ├── schemas/                  # Pydantic 模型
│   ├── services/                 # 业务逻辑
│   ├── utils/                    # 工具函数
│   ├── database.py              # 数据库配置
│   └── config.py                # API 配置
├── data_preparation/            # 数据整理模块
├── reconciliation/              # 对账模块
├── api_server.py               # API 服务器入口
├── unified_mcp_server.py       # MCP 服务器入口
├── start_api_server.sh         # API 服务器启动脚本
└── start_server.sh             # MCP 服务器启动脚本
```

### 2. finance-ui (纯前端)
**职责**: 包装 Dify 的前端界面，处理用户交互

**特点**:
- 无后端代码，纯前端应用
- 直接调用 Dify API 进行对话
- 调用 finance-mcp API 进行认证和数据管理
- 解析 Dify 响应中的特殊指令并渲染相应 UI

**目录结构**:
```
finance-ui/
├── src/
│   ├── api/                     # API 客户端
│   │   ├── client.ts           # Axios 客户端 (调用 finance-mcp)
│   │   ├── dify.ts             # Dify API 客户端 (直接调用 Dify)
│   │   ├── auth.ts             # 认证 API
│   │   ├── schemas.ts          # Schema API
│   │   └── files.ts            # 文件 API
│   ├── components/             # React 组件
│   ├── stores/                 # Zustand 状态管理
│   └── types/                  # TypeScript 类型定义
├── .env                        # 环境变量
└── package.json               # 前端依赖
```

### 3. Dify (AI 对话编排)
**职责**: AI 对话流程编排

**集成方式**:
- finance-ui 直接调用 Dify API (`http://localhost/v1/chat-messages`)
- Dify 通过 MCP 协议调用 finance-mcp 的工具
- 响应中包含特殊指令 (如 `[create_schema]`, `[login_form]`)
- finance-ui 解析指令并渲染相应的 UI 组件

## 启动服务

### 1. 启动 finance-mcp API 服务器
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_api_server.sh
```
服务运行在: `http://localhost:8000`

### 2. 启动 finance-mcp MCP 服务器
```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_server.sh
```
服务运行在: `http://localhost:3335`

### 3. 启动 finance-ui 前端
```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```
服务运行在: `http://localhost:5173`

### 4. 确保 Dify 服务运行
Dify 应该运行在: `http://localhost`

## API 端点

### finance-mcp API (http://localhost:8000/api)

#### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户信息

#### Schema 管理
- `POST /api/schemas` - 创建 Schema
- `GET /api/schemas` - 获取 Schema 列表
- `GET /api/schemas/{id}` - 获取 Schema 详情
- `PUT /api/schemas/{id}` - 更新 Schema
- `DELETE /api/schemas/{id}` - 删除 Schema
- `POST /api/schemas/generate-type-key` - 生成 type_key
- `GET /api/schemas/check-name-exists` - 检查名称是否存在
- `POST /api/schemas/validate-content` - 验证 Schema 内容
- `POST /api/schemas/test` - 测试 Schema 执行

#### 文件管理
- `POST /api/files/upload` - 上传文件
- `GET /api/files/preview` - 预览文件

### Dify API (http://localhost/v1)
- `POST /v1/chat-messages` - 发送聊天消息 (支持 streaming)

## 数据流

### 用户对话流程
```
用户输入
  → finance-ui (前端)
  → Dify API (http://localhost/v1/chat-messages)
  → Dify 处理并调用 MCP 工具
  → finance-mcp MCP Server (端口 3335)
  → 执行数据整理/对账任务
  → 返回结果给 Dify
  → Dify 返回响应 (包含特殊指令)
  → finance-ui 解析指令并渲染 UI
```

### Schema 管理流程
```
用户操作 Schema
  → finance-ui (前端)
  → finance-mcp API (http://localhost:8000/api/schemas)
  → 数据库操作
  → 返回结果
  → finance-ui 更新界面
```

### 文件上传流程
```
用户上传文件
  → finance-ui (前端)
  → finance-mcp API (http://localhost:8000/api/files/upload)
  → 保存到 finance-mcp/uploads/
  → 返回文件路径
  → finance-ui 显示上传结果
```

## 配置文件

### finance-mcp/api/config.py
```python
DATABASE_URL = "mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai"
SECRET_KEY = "your-secret-key-change-in-production"
UPLOAD_DIR = "./uploads"
API_PREFIX = "/api"
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
```

### finance-ui/.env
```
VITE_API_BASE_URL=http://localhost:8000/api
```

### finance-ui/src/api/dify.ts
```typescript
const DIFY_API_URL = 'http://localhost/v1';
const DIFY_API_KEY = 'app-1ab05125-5865-4833-b6a1-ebfd69338f76';
```

## 架构优势

1. **职责清晰**
   - finance-mcp: 核心业务逻辑和数据管理
   - finance-ui: 纯前端展示和交互
   - Dify: AI 对话编排

2. **解耦合**
   - 前端不再依赖自己的后端
   - 可以独立部署和扩展各个服务

3. **易于维护**
   - 代码组织更清晰
   - 各服务独立开发和测试

4. **灵活性**
   - finance-ui 可以直接调用 Dify API
   - 可以轻松添加其他前端应用

## 注意事项

1. **数据库**: 确保 MySQL 数据库 `finance-ai` 已创建并可访问
2. **端口**: 确保端口 8000 (API)、3335 (MCP)、5173 (前端) 未被占用
3. **Dify**: 确保 Dify 服务正常运行并配置了 MCP 集成
4. **CORS**: 如果遇到跨域问题，检查 finance-mcp API 的 CORS 配置

## 迁移完成清单

- ✅ 创建 finance-mcp API 服务器结构
- ✅ 迁移认证 API 到 finance-mcp
- ✅ 迁移 Schema API 到 finance-mcp
- ✅ 迁移文件上传 API 到 finance-mcp
- ✅ 移除 Dify 代理路由
- ✅ 更新 finance-ui 直接调用 Dify API
- ✅ 更新 finance-ui 调用 finance-mcp API
- ✅ 删除 finance-ui 后端代码
- ✅ 创建启动脚本和文档

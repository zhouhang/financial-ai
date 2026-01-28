# Finance AI - 快速启动指南

## 架构概览

```
┌─────────────────┐
│   finance-ui    │  纯前端应用 (React + Vite)
│  (localhost:5173)│  - 直接调用 Dify API
└────────┬────────┘  - 调用 finance-mcp API
         │
         ├──────────────────────────────┐
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌─────────────────┐
│   Dify API      │          │  finance-mcp    │
│ (localhost/v1)  │◄─────────│   API Server    │
└────────┬────────┘   MCP    │ (localhost:8000)│
         │           Protocol└────────┬────────┘
         │                            │
         │                            ├─ 认证 API
         │                            ├─ Schema API
         │                            └─ 文件 API
         │
         ▼
┌─────────────────┐
│  finance-mcp    │
│   MCP Server    │  数据整理 + 对账工具
│ (localhost:3335)│
└─────────────────┘
```

## 快速启动

### 1. 启动 finance-mcp API 服务器

```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_api_server.sh
```

**服务地址**: http://localhost:8000
**API 文档**: http://localhost:8000/docs

### 2. 启动 finance-mcp MCP 服务器

```bash
cd /Users/kevin/workspace/financial-ai/finance-mcp
./start_server.sh
```

**服务地址**: http://localhost:3335

### 3. 启动 finance-ui 前端

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```

**服务地址**: http://localhost:5173

### 4. 确保 Dify 运行

确保 Dify 服务运行在 http://localhost

## 核心变化

### ✅ 已完成的迁移

1. **finance-mcp 现在是双重服务**
   - MCP Server (端口 3335): 为 Dify 提供工具
   - API Server (端口 8000): 提供 RESTful API

2. **finance-ui 变为纯前端**
   - 删除了所有后端代码 (`backend/` 目录)
   - 直接调用 Dify API 进行对话
   - 调用 finance-mcp API 进行数据管理

3. **Dify 集成方式改变**
   - 之前: finance-ui → finance-ui backend → Dify
   - 现在: finance-ui → Dify (直接调用)

### 📁 目录结构变化

#### finance-mcp (新增 API 服务)
```
finance-mcp/
├── api/                      # 新增：RESTful API
│   ├── routers/
│   │   ├── auth.py          # 认证路由
│   │   ├── schemas.py       # Schema 管理路由
│   │   └── files.py         # 文件上传路由
│   ├── models/              # 数据库模型
│   ├── services/            # 业务逻辑
│   └── config.py            # API 配置
├── api_server.py            # 新增：API 服务器入口
└── start_api_server.sh      # 新增：API 启动脚本
```

#### finance-ui (删除后端)
```
finance-ui/
├── src/
│   ├── api/
│   │   ├── dify.ts          # 修改：直接调用 Dify API
│   │   ├── client.ts        # 修改：调用 finance-mcp API
│   │   └── ...
│   └── ...
└── backend/                 # 已删除！
```

## API 端点

### finance-mcp API (http://localhost:8000/api)

#### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户

#### Schema 管理
- `POST /api/schemas` - 创建 Schema
- `GET /api/schemas` - 列表查询
- `GET /api/schemas/{id}` - 获取详情
- `PUT /api/schemas/{id}` - 更新
- `DELETE /api/schemas/{id}` - 删除
- `POST /api/schemas/generate-type-key` - 生成标识符
- `GET /api/schemas/check-name-exists` - 检查名称
- `POST /api/schemas/validate-content` - 验证内容
- `POST /api/schemas/test` - 测试执行

#### 文件管理
- `POST /api/files/upload` - 上传文件
- `GET /api/files/preview` - 预览文件

### Dify API (http://localhost/v1)
- `POST /v1/chat-messages` - 聊天对话 (支持 streaming)

## 配置说明

### finance-mcp/api/config.py
```python
DATABASE_URL = "mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai"
API_PREFIX = "/api"
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
```

### finance-ui/.env
```bash
VITE_API_BASE_URL=http://localhost:8000/api
```

### finance-ui/src/api/dify.ts
```typescript
const DIFY_API_URL = 'http://localhost/v1';
const DIFY_API_KEY = 'app-1ab05125-5865-4833-b6a1-ebfd69338f76';
```

## 数据流示例

### 场景 1: 用户对话
```
用户输入 "帮我整理货币资金数据"
  ↓
finance-ui 前端
  ↓
Dify API (http://localhost/v1/chat-messages)
  ↓
Dify 调用 MCP 工具
  ↓
finance-mcp MCP Server (端口 3335)
  ↓
执行数据整理任务
  ↓
返回结果给 Dify
  ↓
Dify 返回响应 (包含 [create_schema] 指令)
  ↓
finance-ui 解析指令并显示创建 Schema 表单
```

### 场景 2: 创建 Schema
```
用户填写 Schema 表单
  ↓
finance-ui 前端
  ↓
finance-mcp API (POST /api/schemas)
  ↓
保存到数据库
  ↓
返回 Schema 对象
  ↓
finance-ui 显示成功消息
```

### 场景 3: 上传文件
```
用户上传 Excel 文件
  ↓
finance-ui 前端
  ↓
finance-mcp API (POST /api/files/upload)
  ↓
保存到 finance-mcp/uploads/
  ↓
返回文件路径
  ↓
finance-ui 显示文件预览
```

## 测试验证

### 1. 测试 API 服务器
```bash
# 健康检查
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs
```

### 2. 测试前端
```bash
# 访问前端
open http://localhost:5173

# 测试登录
# 测试对话
# 测试 Schema 创建
```

### 3. 测试 MCP 服务器
```bash
# 检查 MCP 服务器日志
tail -f /Users/kevin/workspace/financial-ai/finance-mcp/unified_mcp.log
```

## 常见问题

### Q: 端口被占用怎么办？
```bash
# 查看端口占用
lsof -i :8000
lsof -i :3335
lsof -i :5173

# 杀死进程
kill -9 <PID>
```

### Q: 数据库连接失败？
检查 MySQL 服务是否运行，数据库 `finance-ai` 是否存在。

### Q: CORS 错误？
检查 `finance-mcp/api/config.py` 中的 `CORS_ORIGINS` 配置。

### Q: Dify 调用失败？
确保 Dify 服务运行在 http://localhost，并且 API Key 正确。

## 开发建议

### 添加新的 API 端点
1. 在 `finance-mcp/api/routers/` 创建新路由
2. 在 `finance-mcp/api/services/` 添加业务逻辑
3. 在 `finance-mcp/api_server.py` 注册路由
4. 在 `finance-ui/src/api/` 创建客户端调用

### 修改前端
1. 修改 `finance-ui/src/` 下的组件
2. 运行 `npm run dev` 查看效果
3. 无需重启后端服务

### 调试技巧
- API 日志: 查看 finance-mcp API 服务器控制台
- MCP 日志: 查看 `finance-mcp/unified_mcp.log`
- 前端日志: 浏览器开发者工具 Console
- 网络请求: 浏览器开发者工具 Network

## 下一步

1. **测试所有功能**: 确保登录、Schema 管理、文件上传都正常工作
2. **配置 Dify**: 确保 Dify 正确配置了 MCP 集成
3. **部署准备**: 考虑生产环境的配置和部署方案

## 架构优势

✅ **职责清晰**: 每个服务专注于自己的职责
✅ **易于扩展**: 可以独立扩展各个服务
✅ **便于维护**: 代码组织更清晰
✅ **灵活部署**: 可以独立部署和更新

---

**迁移完成时间**: 2026-01-27
**文档版本**: 1.0

# 架构迁移总结

## 迁移目标 ✅

将 finance-ui 的后端 API 全部迁移到 finance-mcp，使架构更清晰：
- **finance-mcp**: 核心服务 (MCP + API)
- **finance-ui**: 纯前端应用
- **Dify**: AI 对话编排

## 完成的工作

### 1. ✅ 创建 finance-mcp API 服务器
- 创建 `api_server.py` 作为 FastAPI 服务器入口
- 创建 `api/` 目录结构
- 配置 CORS、数据库、路由

### 2. ✅ 迁移所有 API 代码
从 `finance-ui/backend/` 迁移到 `finance-mcp/api/`:
- `routers/` - 所有路由 (auth, schemas, files)
- `models/` - 数据库模型
- `schemas/` - Pydantic 模型
- `services/` - 业务逻辑
- `utils/` - 工具函数
- `database.py` - 数据库配置

### 3. ✅ 修复导入路径
将所有导入路径从相对导入改为 `api.` 前缀:
- `from database import` → `from api.database import`
- `from models.` → `from api.models.`
- `from services.` → `from api.services.`
- 等等

### 4. ✅ 移除 Dify 代理
- 删除 `api/routers/dify.py`
- 删除 `api/services/dify_service.py`
- 从 `__init__.py` 中移除相关导入

### 5. ✅ 更新 finance-ui 前端
- 修改 `src/api/dify.ts` 直接调用 Dify API
- 实现命令检测逻辑 (create_schema, login_form 等)
- 保持其他 API 调用 finance-mcp (auth, schemas, files)
- 更新 `.env` 配置

### 6. ✅ 删除 finance-ui 后端
- 删除整个 `finance-ui/backend/` 目录
- finance-ui 现在是纯前端项目

### 7. ✅ 创建启动脚本
- `start_api_server.sh` - 启动 API 服务器
- 更新文档和说明

### 8. ✅ 测试验证
- 测试 API 服务器启动
- 测试路由导入
- 测试健康检查端点

## 新架构

```
┌─────────────────────────────────────────────────────────┐
│                      finance-ui                         │
│                   (纯前端 React 应用)                    │
│                                                         │
│  - 直接调用 Dify API 进行对话                           │
│  - 调用 finance-mcp API 进行数据管理                    │
│  - 解析 Dify 响应中的特殊指令                           │
│  - 渲染相应的 UI 组件                                   │
└────────────┬───────────────────────┬────────────────────┘
             │                       │
             │ Dify API              │ finance-mcp API
             │ (对话)                │ (数据管理)
             ▼                       ▼
    ┌────────────────┐      ┌────────────────────┐
    │   Dify API     │      │   finance-mcp      │
    │ (localhost/v1) │      │   API Server       │
    │                │      │ (localhost:8000)   │
    │ - 对话编排     │      │                    │
    │ - 调用 MCP 工具│◄─────│ - 认证 API         │
    └────────┬───────┘ MCP  │ - Schema API       │
             │              │ - 文件 API         │
             │              │ - 数据库管理       │
             ▼              └────────────────────┘
    ┌────────────────┐
    │  finance-mcp   │
    │  MCP Server    │
    │ (localhost:3335)│
    │                │
    │ - 数据整理工具 │
    │ - 对账工具     │
    └────────────────┘
```

## 服务职责

### finance-mcp (核心服务)
**端口**: 8000 (API), 3335 (MCP)

**职责**:
1. 提供 RESTful API (认证、Schema、文件)
2. 提供 MCP 工具 (数据整理、对账)
3. 管理数据库和文件存储
4. 执行核心业务逻辑

**技术栈**: FastAPI, SQLAlchemy, MySQL, MCP

### finance-ui (纯前端)
**端口**: 5173

**职责**:
1. 用户界面展示
2. 直接调用 Dify API 进行对话
3. 调用 finance-mcp API 进行数据管理
4. 解析 Dify 响应中的特殊指令
5. 渲染相应的 UI 组件

**技术栈**: React, TypeScript, Vite, Zustand, Ant Design

### Dify (AI 编排)
**端口**: 80

**职责**:
1. AI 对话流程编排
2. 调用 finance-mcp MCP 工具
3. 返回响应 (包含特殊指令)

## 数据流

### 用户对话流程
```
用户输入
  → finance-ui
  → Dify API (直接调用)
  → Dify 处理并调用 MCP 工具
  → finance-mcp MCP Server
  → 执行任务
  → 返回结果给 Dify
  → Dify 返回响应 (包含指令)
  → finance-ui 解析指令并渲染 UI
```

### Schema 管理流程
```
用户操作
  → finance-ui
  → finance-mcp API
  → 数据库操作
  → 返回结果
  → finance-ui 更新界面
```

## 关键文件

### finance-mcp
- `api_server.py` - API 服务器入口
- `api/config.py` - API 配置
- `api/routers/` - API 路由
- `api/services/` - 业务逻辑
- `start_api_server.sh` - 启动脚本

### finance-ui
- `src/api/dify.ts` - Dify API 客户端 (直接调用)
- `src/api/client.ts` - finance-mcp API 客户端
- `.env` - 环境配置

## 配置变化

### finance-ui/.env
```bash
# 之前
VITE_API_BASE_URL=http://localhost:8000/api
VITE_DIFY_API_URL=http://localhost:8000/api/dify  # 通过后端代理

# 现在
VITE_API_BASE_URL=http://localhost:8000/api  # 调用 finance-mcp
# Dify API 直接在代码中配置
```

### finance-ui/src/api/dify.ts
```typescript
// 之前: 调用 finance-ui 后端
const response = await apiClient.post('/dify/chat', request);

// 现在: 直接调用 Dify API
const response = await fetch('http://localhost/v1/chat-messages', {
  headers: {
    'Authorization': 'Bearer app-1ab05125-5865-4833-b6a1-ebfd69338f76',
  },
  body: JSON.stringify({
    query: request.query,
    response_mode: 'streaming',
    user: 'anonymous_user',
  }),
});
```

## 启动顺序

1. **启动 finance-mcp API 服务器**
   ```bash
   cd finance-mcp
   ./start_api_server.sh
   ```

2. **启动 finance-mcp MCP 服务器**
   ```bash
   cd finance-mcp
   ./start_server.sh
   ```

3. **启动 finance-ui 前端**
   ```bash
   cd finance-ui
   npm run dev
   ```

4. **确保 Dify 运行**
   - Dify 应该运行在 http://localhost

## 测试清单

- [x] API 服务器启动成功
- [x] 路由导入成功
- [x] 健康检查端点正常
- [ ] 用户注册/登录功能
- [ ] Schema 创建/查询功能
- [ ] 文件上传功能
- [ ] Dify 对话功能
- [ ] 命令检测和 UI 渲染

## 优势

1. **职责清晰**: 每个服务专注于自己的职责
2. **易于维护**: 代码组织更清晰
3. **便于扩展**: 可以独立扩展各个服务
4. **灵活部署**: 可以独立部署和更新
5. **无状态前端**: finance-ui 不需要维护任何后端状态

## 注意事项

1. **CORS 配置**: 确保 finance-mcp API 的 CORS 配置包含 finance-ui 的地址
2. **API Key**: Dify API Key 现在硬编码在前端，生产环境需要考虑安全性
3. **认证**: finance-ui 仍然需要认证来访问 finance-mcp API
4. **错误处理**: 前端需要处理 Dify API 和 finance-mcp API 的错误

## 下一步

1. 完整测试所有功能
2. 优化错误处理
3. 考虑生产环境配置
4. 添加日志和监控
5. 编写部署文档

---

**迁移完成**: ✅
**测试状态**: 部分完成
**文档状态**: 已完成

# Finance AI - 架构迁移完成 🎉

## 快速开始

### 一键启动所有服务
```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

### 一键停止所有服务
```bash
cd /Users/kevin/workspace/financial-ai
./STOP_ALL_SERVICES.sh
```

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| **finance-ui** | http://localhost:5173 | 前端界面 |
| **finance-mcp API** | http://localhost:8000 | RESTful API |
| **API 文档** | http://localhost:8000/docs | Swagger 文档 |
| **finance-mcp MCP** | http://localhost:3335 | MCP 工具服务 |
| **Dify** | http://localhost | AI 对话服务 |

## 新架构说明

### 🎯 核心变化

**之前**: finance-ui 包含前端 + 后端，通过后端代理调用 Dify
```
用户 → finance-ui 前端 → finance-ui 后端 → Dify → finance-mcp MCP
```

**现在**: finance-ui 纯前端，直接调用 Dify 和 finance-mcp API
```
用户 → finance-ui 前端 ─┬→ Dify → finance-mcp MCP
                        └→ finance-mcp API
```

### 📦 各服务职责

#### 1. finance-mcp (核心服务)
**位置**: `/Users/kevin/workspace/financial-ai/finance-mcp`

**提供两个服务**:
- **API Server** (端口 8000): 认证、Schema 管理、文件上传
- **MCP Server** (端口 3335): 数据整理和对账工具

**目录结构**:
```
finance-mcp/
├── api/                    # RESTful API (新增)
│   ├── routers/           # 路由
│   ├── models/            # 数据库模型
│   ├── services/          # 业务逻辑
│   └── utils/             # 工具函数
├── api_server.py          # API 服务器入口 (新增)
├── unified_mcp_server.py  # MCP 服务器入口
├── data_preparation/      # 数据整理模块
└── reconciliation/        # 对账模块
```

#### 2. finance-ui (纯前端)
**位置**: `/Users/kevin/workspace/financial-ai/finance-ui`

**职责**:
- 用户界面展示
- 直接调用 Dify API 进行对话
- 调用 finance-mcp API 进行数据管理
- 解析 Dify 响应中的特殊指令并渲染 UI

**关键变化**:
- ✅ 删除了整个 `backend/` 目录
- ✅ `src/api/dify.ts` 直接调用 Dify API
- ✅ 其他 API 调用 finance-mcp

#### 3. Dify (AI 编排)
**位置**: http://localhost

**职责**:
- AI 对话流程编排
- 调用 finance-mcp MCP 工具
- 返回响应 (包含特殊指令)

## 数据流示例

### 场景 1: 用户对话
```
1. 用户输入: "帮我整理货币资金数据"
   ↓
2. finance-ui 调用 Dify API
   POST http://localhost/v1/chat-messages
   ↓
3. Dify 处理并调用 MCP 工具
   → finance-mcp MCP Server (端口 3335)
   ↓
4. 执行数据整理任务
   ↓
5. 返回结果给 Dify
   ↓
6. Dify 返回响应: "已完成数据整理 [create_schema]"
   ↓
7. finance-ui 检测到 [create_schema] 指令
   ↓
8. 显示创建 Schema 表单
```

### 场景 2: 创建 Schema
```
1. 用户填写 Schema 表单
   ↓
2. finance-ui 调用 finance-mcp API
   POST http://localhost:8000/api/schemas
   ↓
3. 保存到数据库
   ↓
4. 返回 Schema 对象
   ↓
5. finance-ui 显示成功消息
```

### 场景 3: 上传文件
```
1. 用户上传 Excel 文件
   ↓
2. finance-ui 调用 finance-mcp API
   POST http://localhost:8000/api/files/upload
   ↓
3. 保存到 finance-mcp/uploads/
   ↓
4. 返回文件路径
   ↓
5. finance-ui 显示文件预览
```

## API 端点

### finance-mcp API (http://localhost:8000/api)

#### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户

#### Schema 管理
- `POST /api/schemas` - 创建 Schema
- `GET /api/schemas` - 获取列表
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

## 配置文件

### finance-mcp/api/config.py
```python
DATABASE_URL = "mysql+pymysql://aiuser:123456@127.0.0.1:3306/finance-ai"
API_PREFIX = "/api"
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
UPLOAD_DIR = "./uploads"
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

## 测试验证

### 1. 测试 API 服务器
```bash
# 健康检查
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs

# 测试根端点
curl http://localhost:8000/
```

### 2. 测试前端
```bash
# 访问前端
open http://localhost:5173
```

### 3. 查看日志
```bash
# API 日志
tail -f /tmp/finance-mcp-api.log

# MCP 日志
tail -f /tmp/finance-mcp-mcp.log

# 前端日志
tail -f /tmp/finance-ui.log
```

## 常见问题

### Q: 端口被占用怎么办？
```bash
# 查看端口占用
lsof -i :8000
lsof -i :3335
lsof -i :5173

# 使用停止脚本清理
./STOP_ALL_SERVICES.sh
```

### Q: 数据库连接失败？
```bash
# 检查 MySQL 服务
mysql -h 127.0.0.1 -u aiuser -p123456 -e "USE finance-ai;"

# 如果数据库不存在，创建它
mysql -h 127.0.0.1 -u aiuser -p123456 -e "CREATE DATABASE IF NOT EXISTS finance-ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### Q: CORS 错误？
检查 `finance-mcp/api/config.py` 中的 `CORS_ORIGINS` 配置是否包含前端地址。

### Q: Dify 调用失败？
确保 Dify 服务运行在 http://localhost，并且 API Key 正确。

## 文档索引

- 📘 [架构迁移详细文档](./ARCHITECTURE_MIGRATION.md) - 完整的架构说明
- 📗 [迁移总结](./MIGRATION_SUMMARY.md) - 迁移过程和技术细节
- 📙 [快速启动指南](./QUICK_START.md) - 详细的启动和使用指南
- 📕 [迁移报告](./MIGRATION_REPORT.md) - 完整的迁移报告

## 架构优势

✅ **职责清晰**: 前端专注 UI，finance-mcp 专注业务逻辑
✅ **直接集成**: finance-ui 直接调用 Dify API，减少中间层
✅ **易于扩展**: 各服务可以独立部署和扩展
✅ **便于维护**: 代码组织更清晰，易于理解和修改
✅ **性能提升**: 减少了一层代理，响应更快

## 下一步

1. **测试所有功能**: 确保登录、Schema 管理、文件上传、对话功能都正常
2. **配置 Dify**: 确保 Dify 正确配置了 MCP 集成
3. **性能优化**: 根据实际使用情况优化性能
4. **安全加固**: 生产环境需要加强安全配置

## 支持

如有问题，请查看日志文件或联系开发团队。

---

**迁移完成日期**: 2026-01-27
**版本**: 1.0
**状态**: ✅ 完成并可用

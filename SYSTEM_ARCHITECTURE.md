# Financial AI 系统架构总览

## 📋 系统组成

整个系统由 **4个核心模块** 组成：

```
financial-ai/
├── finance-web/          # 前端 Web 界面 (React + TypeScript + Vite)
├── finance-agents/       # AI Agent 后端 (LangGraph + FastAPI)
├── finance-mcp/          # MCP 服务器 (对账 + 数据整理)
└── tally (PostgreSQL)  # 数据库
```

---

## 🎨 **1. finance-web** - 前端界面

### 技术栈
- **React 19** + **TypeScript**
- **Vite** (构建工具)
- **Tailwind CSS** (样式)
- **WebSocket** (实时通信)

### 核心组件
```
src/
├── App.tsx              # 主应用，管理会话和状态
├── components/
│   ├── Sidebar.tsx      # 左侧边栏：会话列表
│   ├── ChatArea.tsx     # 中间聊天区：消息展示和输入
│   ├── Workbench.tsx    # 右侧工作台：任务/文件/结果
│   ├── MessageBubble.tsx
│   └── InterruptDialog.tsx
├── hooks/
│   └── useWebSocket.ts  # WebSocket 连接管理
└── types.ts             # TypeScript 类型定义
```

### 主要功能
- ✅ 实时聊天界面（WebSocket）
- ✅ 文件上传（拖拽/选择）
- ✅ 任务进度展示
- ✅ 流式输出支持
- ✅ 中断处理（Interrupt）
- ✅ 多会话管理

### 通信协议
```typescript
// WebSocket 消息格式
WsIncoming: { message: string, thread_id: string, resume?: boolean }
WsOutgoing: { 
  type: 'message' | 'stream' | 'interrupt' | 'done' | 'error',
  content?: string,
  payload?: Record<string, unknown>
}
```

---

## 🤖 **2. finance-agents** - AI Agent 后端

### 技术栈
- **LangGraph** (AI 工作流编排)
- **FastAPI** (HTTP/WebSocket 服务)
- **LangChain** (LLM 集成)
- **PostgreSQL** (状态持久化)

### 核心架构
```
data-agent/
├── app/
│   ├── server.py           # FastAPI 服务器
│   ├── config.py           # 配置管理
│   ├── graphs/
│   │   ├── main_graph.py   # 主工作流图
│   │   ├── reconciliation.py  # 对账子图
│   │   └── data_preparation.py # 数据整理子图
│   ├── tools/
│   │   └── mcp_client.py   # MCP 工具调用客户端
│   └── utils/
│       ├── db.py           # 数据库工具
│       ├── llm.py          # LLM 配置
│       ├── file_analysis.py # 文件分析
│       └── schema_builder.py # Schema 构建
```

### 主要端点
- `POST /upload` - 文件上传（转发到 finance-mcp）
- `WebSocket /chat` - 实时聊天
- `GET /stream` - SSE 流式输出

### LangGraph 工作流
```
用户输入 → 意图识别 → 路由选择
                ↓
        ┌───────┴────────┐
        ↓                ↓
   对账子图        数据整理子图
        ↓                ↓
   调用 MCP 工具    调用 MCP 工具
        ↓                ↓
     返回结果        返回结果
```

---

## 🔧 **3. finance-mcp** - MCP 服务器

### 技术栈
- **MCP Protocol** (Model Context Protocol)
- **Starlette** (ASGI Web 框架)
- **Pandas** + **openpyxl** (数据处理)
- **asyncio** (异步任务)

### 模块结构
```
finance-mcp/
├── unified_mcp_server.py    # 统一服务器入口
├── db_config.py             # 数据库配置（新增）
├── security_utils.py        # 安全工具
├── reconciliation/          # 对账模块
│   ├── mcp_server/
│   │   ├── tools.py         # 6个MCP工具
│   │   ├── reconciliation_engine.py
│   │   ├── data_cleaner.py
│   │   ├── file_matcher.py
│   │   └── task_manager.py
│   ├── schemas/             # 对账规则配置
│   └── config/
└── data_preparation/        # 数据整理模块
    ├── mcp_server/
    │   ├── tools.py         # 4个MCP工具
    │   ├── processing_engine.py
    │   ├── extractor.py
    │   ├── transformer.py
    │   ├── template_writer.py
    │   └── task_manager.py
    ├── schemas/             # 数据整理配置
    └── templates/           # Excel模板
```

### MCP 工具列表

#### 对账模块 (6个工具)
1. `file_upload` - 文件上传
2. `reconciliation_start` - 开始对账
3. `reconciliation_status` - 查询状态
4. `reconciliation_result` - 获取结果
5. `reconciliation_list_tasks` - 列出任务
6. `get_reconciliation` - 获取配置

#### 数据整理模块 (4个工具)
1. `data_preparation_start` - 开始整理
2. `data_preparation_status` - 查询状态
3. `data_preparation_result` - 获取结果
4. `data_preparation_list_tasks` - 列出任务

### HTTP 端点
- `GET/POST /sse` - SSE 连接（MCP 协议）
- `GET /health` - 健康检查
- `GET /download/{task_id}` - 下载结果文件
- `GET /preview/{task_id}` - 预览文件信息
- `GET /report/{task_id}` - 获取详细报告

---

## 🗄️ **4. tally** - PostgreSQL 数据库

### 表结构（12个表）

#### 组织架构
- `company` - 公司表 (1条记录)
- `departments` - 部门表 (1条记录，支持层级)
- `users` - 用户表 (1条记录)

#### 对账规则管理 ⭐️
- `reconciliation_rules` - 对账规则表
  - `rule_template` (JSONB) - 存储完整 schema 配置
  - `visibility` - 可见性（private/department/company/public）
  - `shared_with_users` - 共享用户列表
  - `tags` - 标签分类
  - `use_count` - 使用次数统计
- `rule_versions` - 规则版本表
- `rule_usage_logs` - 使用日志

#### 任务执行
- `reconciliation_tasks` - 对账任务表
  - `finance_files`, `business_files` (JSONB)
  - `status`, `progress`
  - `result_summary`, `result_details` (JSONB)
- 文件上传记录由 `file_uploads` 表（见 `finance-mcp/auth/migrations/004_file_ownership.sql`）管理

#### 审计
- `audit_logs` - 审计日志

#### 视图
- `v_users_full` - 用户完整信息
- `v_rules_full` - 规则完整信息
- `v_task_stats` - 任务统计

---

## 🔄 **数据流**

### 对账流程
```
1. 用户上传文件 (Web)
   ↓
2. POST /api/upload → finance-agents
   ↓
3. 调用 MCP file_upload → finance-mcp
   ↓
4. 文件保存到 uploads/
   ↓
5. 用户发送对账指令 (WebSocket)
   ↓
6. LangGraph 分析意图 → 对账子图
   ↓
7. 调用 MCP reconciliation_start
   ↓
8. finance-mcp 异步执行对账
   ↓
9. 轮询查询状态 (reconciliation_status)
   ↓
10. 获取结果 (reconciliation_result)
    ↓
11. 返回给用户 (WebSocket stream)
```

---

## 🔐 **配置管理**

### 环境变量 (.env)
```bash
# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_NAME=tally
DB_USER=tally_user
DB_PASSWORD=123456

# MCP 服务器
MCP_SERVER_HOST=0.0.0.0
MCP_PUBLIC_HOST=localhost
MCP_SERVER_PORT=3335

# 文件配置
UPLOAD_MAX_SIZE=104857600
FILE_RETENTION_DAYS=30

# 任务配置
TASK_TIMEOUT=3600
MAX_CONCURRENT_TASKS=5
```

### 数据库配置模块 (新增)
```python
# finance-mcp/db_config.py
from db_config import db_config, get_db_connection

# 同步连接
conn = get_db_connection()

# 异步连接
conn = await get_async_db_connection()
```

---

## 🚀 **启动流程**

### 1. 启动数据库
```bash
# PostgreSQL 应该已经在运行
psql -U tally_user -d tally
```

### 2. 启动 finance-mcp
```bash
cd finance-mcp
python unified_mcp_server.py
# 监听: http://localhost:3335
```

### 3. 启动 finance-agents
```bash
cd finance-agents/data-agent
python -m app.server
# 监听: http://localhost:8100
```

### 4. 启动 finance-web
```bash
cd finance-web
npm run dev
# 监听: http://localhost:5173
```

---

## 📊 **技术特点**

### 1. Schema 驱动
- 所有对账和数据整理逻辑通过 JSON Schema 配置
- 无需修改代码即可添加新规则

### 2. 异步任务处理
- 使用 asyncio 处理长时间运行任务
- 不阻塞主线程

### 3. 实时通信
- WebSocket 实现实时聊天
- 支持流式输出（SSE）

### 4. 安全性
- 路径遍历防护
- 文件类型验证
- 输入验证和清理

### 5. 可扩展性
- MCP 协议标准化工具调用
- LangGraph 灵活的工作流编排
- 数据库持久化状态

---

## 🎯 **改造方向**

基于现有架构，建议的改造方向：

### 1. Schema 数据库化 ⭐️ 最重要
- 将 JSON 文件中的 schema 迁移到 `reconciliation_rules` 表
- 实现规则的 CRUD API
- 支持规则版本管理和回滚

### 2. 任务持久化
- 将内存中的任务状态持久化到 `reconciliation_tasks` 表
- 支持服务重启后任务恢复
- 实现任务历史查询

### 3. 文件管理规范化
- 使用 `file_uploads` 表（004_file_ownership）记录上传文件及所有权
- 实现文件自动过期清理
- 文件分类和检索

### 4. 权限和多租户
- 基于 `company` 和 `departments` 实现多租户隔离
- 规则共享和权限控制
- 用户操作审计

### 5. Web 界面增强
- 规则管理界面（创建/编辑/删除）
- 任务历史查看
- 统计报表展示

---

## 📝 **准备工作完成情况**

✅ **准备工作1**: 数据库配置环境变量化
- 创建 `.env` 文件
- 创建 `db_config.py` 模块
- 更新 `requirements.txt`
- 测试连接成功

✅ **准备工作2**: 熟悉 finance-web 代码
- React + TypeScript + Vite
- WebSocket 实时通信
- 三栏布局（Sidebar + ChatArea + Workbench）
- 文件上传和任务展示

---

## 🎉 **准备就绪**

现在已经完全了解了：
1. ✅ finance-mcp 代码结构
2. ✅ tally 数据库表结构
3. ✅ finance-web 前端架构
4. ✅ finance-agents AI 后端
5. ✅ 数据库配置已环境变量化

**可以开始改造了！** 🚀

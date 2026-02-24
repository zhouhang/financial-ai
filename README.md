# Financial AI - 金融智能数据整理与对账平台

基于 **LangGraph** 的 AI 驱动金融数据处理系统，提供智能对话、数据整理和自动对账功能。

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     用户层                               │
│              浏览器 (http://localhost:5173)              │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│                  finance-web (前端)                      │
│   React 19 + TypeScript + Vite + WebSocket              │
│   - 实时聊天界面                                          │
│   - 文件上传管理                                          │
│   - 任务进度展示                                          │
│   端口: 5173                                             │
└──────────────────┬──────────────────────────────────────┘
                   │ WebSocket /chat
                   ▼
┌─────────────────────────────────────────────────────────┐
│                data-agent (AI 后端)                      │
│   LangGraph + FastAPI + LangChain                       │
│   - AI 意图识别                                          │
│   - 工作流编排                                            │
│   - MCP 工具调用                                          │
│   端口: 8100                                             │
└──────────────────┬──────────────────────────────────────┘
                   │ MCP Protocol
                   ▼
┌─────────────────────────────────────────────────────────┐
│              finance-mcp (MCP 工具服务器)                │
│   MCP Protocol + Pandas + asyncio                       │
│   - 数据整理工具 (4个)                                    │
│   - 对账工具 (6个)                                        │
│   - 异步任务管理                                          │
│   端口: 3335                                             │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│              PostgreSQL (finflux 数据库)                 │
│   - 对账规则管理                                          │
│   - 任务状态持久化                                        │
│   - 用户权限管理                                          │
└─────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 一键启动所有服务（推荐）

```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
./START_ALL_SERVICES.sh
```

启动脚本会自动：
- ✅ 停止旧服务（端口 3335、8100、5173）
- ✅ 启动 finance-mcp（MCP 工具服务器）
- ✅ 启动 data-agent（AI 后端）
- ✅ 启动 finance-web（前端界面）
- ✅ 验证服务状态
- ✅ 显示访问地址和日志路径

### 一键停止所有服务

```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
./STOP_ALL_SERVICES.sh
```

或使用快捷命令：
```bash
lsof -ti:3335,8100,5173 | xargs kill -9
```

## 📍 服务地址

| 服务 | 端口 | 地址 | 说明 |
|------|------|------|------|
| **finance-web** | 5173 | http://localhost:5173 | 用户界面（React 前端） |
| **data-agent** | 8100 | http://localhost:8100 | AI 后端（LangGraph + FastAPI） |
| **finance-mcp** | 3335 | http://localhost:3335 | MCP 工具服务器（数据整理+对账） |

## 📚 手动启动（三个终端）

如果需要分别查看每个服务的日志，可以手动启动：

**终端 1 - finance-mcp：**
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
cd finance-mcp
python unified_mcp_server.py
```

**终端 2 - data-agent：**
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
cd finance-agents/data-agent
python -m app.server
```

**终端 3 - finance-web：**
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai/finance-web
npm run dev
```

## 📊 查看日志

使用 `START_ALL_SERVICES.sh` 启动时，日志保存在 `logs/` 目录：

```bash
# 实时查看 finance-mcp 日志
tail -f logs/finance-mcp.log

# 实时查看 data-agent 日志
tail -f logs/data-agent.log

# 实时查看 finance-web 日志
tail -f logs/finance-web.log
```

## 💻 项目结构

```
financial-ai/
├── finance-web/                    # 前端 (React + TypeScript + Vite)
│   ├── src/
│   │   ├── App.tsx              # 主应用
│   │   ├── components/          # 组件
│   │   │   ├── Sidebar.tsx      # 会话列表
│   │   │   ├── ChatArea.tsx     # 聊天区
│   │   │   └── Workbench.tsx    # 工作台
│   │   ├── hooks/
│   │   │   └── useWebSocket.ts  # WebSocket 钩子
│   │   └── types.ts             # 类型定义
│   ├── package.json
│   └── vite.config.ts
│
├── finance-agents/                # AI 后端 (LangGraph + FastAPI)
│   └── data-agent/
│       ├── app/
│       │   ├── server.py        # FastAPI 服务器
│       │   ├── config.py        # 配置
│       │   ├── graphs/          # LangGraph 工作流
│       │   │   ├── main_graph.py
│       │   │   ├── reconciliation.py
│       │   │   └── data_preparation.py
│       │   ├── tools/           # MCP 工具客户端
│       │   │   └── mcp_client.py
│       │   └── utils/           # 工具类
│       └── requirements.txt
│
├── finance-mcp/                   # MCP 工具服务器
│   ├── unified_mcp_server.py    # 服务器入口
│   ├── db_config.py             # 数据库配置
│   ├── reconciliation/          # 对账模块
│   │   ├── mcp_server/
│   │   │   ├── tools.py         # 6个 MCP 工具
│   │   │   ├── reconciliation_engine.py
│   │   │   ├── data_cleaner.py
│   │   │   └── task_manager.py
│   │   └── schemas/             # 对账规则配置
│   └── data_preparation/        # 数据整理模块
│       ├── mcp_server/
│       │   ├── tools.py         # 4个 MCP 工具
│       │   ├── processing_engine.py
│       │   └── task_manager.py
│       └── schemas/             # 数据整理配置
│
├── .venv/                         # Python 虚拟环境（所有 Python 服务共用）
├── requirements.txt               # Python 依赖
├── START_ALL_SERVICES.sh          # 一键启动脚本
├── STOP_ALL_SERVICES.sh           # 一键停止脚本
└── README.md                      # 本文件
```

## 🔧 技术栈

### 前端
- **React 19** - UI 框架
- **TypeScript** - 类型安全
- **Vite** - 构建工具
- **Tailwind CSS** - 样式框架
- **WebSocket** - 实时通信

### AI 后端
- **LangGraph** - AI 工作流编排
- **FastAPI** - Web 框架
- **LangChain** - LLM 集成
- **PostgreSQL** - 状态持久化

### MCP 服务
- **MCP Protocol** - 模型上下文协议
- **Starlette** - ASGI Web 框架
- **Pandas** - 数据处理
- **asyncio** - 异步任务管理

### 数据库
- **PostgreSQL (finflux)** - 主数据库
  - 对账规则管理
  - 任务状态持久化
  - 用户权限管理

## 📊 数据流示例

### 场景 1：用户对话 + 数据整理
```
1. 用户输入: "帮我整理货币资金数据"
   ↓
2. finance-web 通过 WebSocket 发送消息
   WebSocket /chat → data-agent
   ↓
3. LangGraph 分析意图 → 数据整理子图
   ↓
4. 调用 MCP 工具
   MCP Protocol → finance-mcp (data_preparation_start)
   ↓
5. finance-mcp 异步执行数据整理任务
   ↓
6. 轮询查询任务状态
   data_preparation_status
   ↓
7. 获取结果并流式返回给用户
   WebSocket stream → finance-web
```

### 场景 2：文件上传 + 对账
```
1. 用户上传两个文件（业务流水 + 财务流水）
   ↓
2. finance-web 调用 data-agent
   POST /upload → data-agent
   ↓
3. data-agent 调用 MCP 工具
   MCP file_upload → finance-mcp
   ↓
4. 文件保存到 finance-mcp/uploads/
   ↓
5. 用户发送对账指令: "对比这两个文件"
   ↓
6. LangGraph 分析意图 → 对账子图
   ↓
7. 调用 MCP 工具
   reconciliation_start → finance-mcp
   ↓
8. finance-mcp 异步执行对账
   ↓
9. 返回对账结果（匹配/差异明细）
   WebSocket stream → finance-web
```

## ✨ 主要功能

### 1. 智能对话
- ✅ 实时 WebSocket 通信
- ✅ 流式输出支持
- ✅ AI 意图识别
- ✅ 多会话管理
- ✅ 中断处理 (Interrupt)

### 2. 数据整理
- ✅ Schema 驱动的数据提取
- ✅ 智能字段映射
- ✅ 数据清洗和转换
- ✅ 自动生成 Excel 报表
- ✅ 任务进度实时显示

### 3. 自动对账
- ✅ 多文件智能匹配
- ✅ 灵活的对账规则
- ✅ 差异自动检测
- ✅ 容差配置支持
- ✅ 详细的对账报告

### 4. 文件管理
- ✅ 拖拽上传
- ✅ 多文件批量处理
- ✅ 文件预览
- ✅ 自动编码检测
- ✅ 上传进度显示

## 🛠️ 环境要求

### Python 服务 (finance-mcp, data-agent)
- Python 3.9+
- PostgreSQL 12+ (数据库)
- 根虚拟环境 `.venv`

### 前端服务 (finance-web)
- Node.js 16+
- npm 或 yarn

### 环境配置
项目根目录需要创建 `.env` 文件：

```bash
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_NAME=finflux
DB_USER=finflux_user
DB_PASSWORD=123456

# MCP 服务器配置
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

## 🔍 常见问题

### Q1: 端口被占用？
```bash
# 查看端口占用
lsof -i:3335  # finance-mcp
lsof -i:8100  # data-agent
lsof -i:5173  # finance-web

# 使用停止脚本清理
./STOP_ALL_SERVICES.sh
```

### Q2: 虚拟环境问题？
```bash
# 检查当前虚拟环境
which python
# 应该输出: /Users/fanyuli/Desktop/workspace/financial-ai/.venv/bin/python

# 如果不是，重新激活
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
```

### Q3: 依赖缺失？
```bash
cd /Users/fanyuli/Desktop/workspace/financial-ai
source .venv/bin/activate
pip install -r requirements.txt

# finance-web 依赖
cd finance-web
npm install
```

### Q4: data-agent 无法调用 finance-mcp？

**检查清单**：
1. ✅ finance-mcp 是否在运行？（端口 3335）
2. ✅ data-agent 是否使用根虚拟环境启动？
3. ✅ 网络连接是否正常？

```bash
# 验证 finance-mcp 连接
curl http://localhost:3335/health

# 查看 data-agent 日志
tail -20 logs/data-agent.log | grep -i "mcp"
```

### Q5: 数据库连接失败？
```bash
# 检查 PostgreSQL 服务
psql -U finflux_user -d finflux -h localhost

# 如果数据库不存在，创建它
creatdb -U finflux_user finflux
```

## 📚 详细文档

- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) - 完整系统架构说明
- [README_SERVICES.md](./README_SERVICES.md) - 服务管理指南
- [QUICK_START.md](./QUICK_START.md) - 快速开始指南
- [启动三个服务-对话记录.md](./%E5%90%AF%E5%8A%A8%E4%B8%89%E4%B8%AA%E6%9C%8D%E5%8A%A1-%E5%AF%B9%E8%AF%9D%E8%AE%B0%E5%BD%95.md) - 服务启动记录

## 🌟 系统特点

### 1. Schema 驱动
- 所有对账和数据整理逻辑通过 JSON Schema 配置
- 无需修改代码即可添加新规则

### 2. 异步任务处理
- 使用 asyncio 处理长时间运行任务
- 不阻塞主线程、实时显示进度

### 3. 实时通信
- WebSocket 实现实时聊天
- 支持流式输出（Streaming）

### 4. AI 驱动
- LangGraph 工作流编排
- 智能意图识别和任务路由

### 5. 安全性
- 路径遍历防护
- 文件类型验证
- 输入验证和清理

### 6. 可扩展性
- MCP 协议标准化工具调用
- LangGraph 灵活的工作流编排
- 数据库持久化状态

## 🚀 部署建议

### 开发环境
使用 `START_ALL_SERVICES.sh` 一键启动所有服务

### 生产环境
1. **数据库**：使用独立的 PostgreSQL 服务器
2. **finance-mcp**：使用 systemd 或 supervisor 管理
3. **data-agent**：使用 gunicorn + uvicorn 部署
4. **finance-web**：使用 nginx 代理，`npm run build` 构建静态文件

## 👥 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

## 📄 License

MIT

## 📞 支持

如有问题，请：
- 查看 [README_SERVICES.md](./README_SERVICES.md) 了解常见问题
- 查看日志文件（`logs/` 目录）
- 提交 Issue 到 GitHub

---

**最后更新**: 2026-02-24  
**版本**: 2.0 (LangGraph 架构)  
**状态**: ✅ 生产就绪

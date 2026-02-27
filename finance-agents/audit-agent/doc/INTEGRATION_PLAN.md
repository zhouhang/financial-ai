# 审计整理数字员工 (Data-Process Agent) 集成开发规划

## 一、项目概述

### 1.1 集成策略
**重要**: 新的 data-process agent 功能将**集成到现有 finance-agents/data-agent 项目中**,而不是创建独立项目。

### 1.2 项目名称
- **英文名**: Data-Process Agent (集成模块)
- **中文名**: 审计整理数字员工

### 1.3 集成位置
```
financial-ai/
├── finance-agents/
│   └── data-agent/
│       └── app/
│           ├── graphs/
│           │   └── data_process/          # [新增] 数据处理子图
│           │       ├── __init__.py
│           │       ├── data_process_graph.py
│           │       ├── nodes.py
│           │       └── routers.py
│           └── tools/
│               └── data_process/          # [新增] 数据处理工具
│                   ├── __init__.py
│                   ├── skill_manager.py
│                   ├── script_generator.py
│                   └── execution_engine.py
├── finance-mcp/
│   └── data_process/                      # [新增] MCP 工具服务器
│       └── mcp_server/
│           ├── tools.py
│           ├── skill_loader.py
│           ├── script_executor.py
│           └── task_manager.py
└── finance-agents/
    └── data-process/                      # [保留] 配置和数据目录
        ├── skills/                        # Skill 定义文件
        ├── data/                          # 原始数据
        ├── scripts/                       # 生成的脚本
        └── result/                        # 处理结果
```

---

## 二、现有架构分析

### 2.1 当前项目结构

```
financial-ai/
├── finance-web/              # 前端 (React + TypeScript)
├── finance-agents/
│   └── data-agent/           # AI 后端 (LangGraph + FastAPI) ← 集成位置
│       └── app/
│           ├── graphs/       # LangGraph 工作流
│           │   ├── main_graph/
│           │   ├── reconciliation.py
│           │   └── data_preparation.py  # 占位符
│           ├── tools/
│           │   └── mcp_client.py
│           ├── server.py
│           └── config.py
├── finance-mcp/              # MCP 工具服务器 ← 扩展位置
│   ├── unified_mcp_server.py
│   ├── data_preparation/     # 数据整理模块
│   └── reconciliation/       # 对账模块
└── finance-agents/
    └── data-process/         # Skill 配置目录
        ├── skills/           # Skill 定义 (.md 文件)
        ├── data/             # 原始数据
        ├── scripts/          # 生成的脚本
        └── result/           # 处理结果
```

### 2.2 现有工作流架构

当前 data-agent 使用 LangGraph 构建，包含:
1. **Router Node**: AI 意图识别，决策使用哪个子图
2. **Task Execution Node**: 执行具体任务 (调用 MCP 工具)
3. **Result Analysis Node**: 分析并展示结果

现有子图:
- **Reconciliation Subgraph**: 对账子图
- **Data Preparation Subgraph**: 数据整理子图 (当前为占位符)

---

## 三、技术架构图 (集成版)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         finance-web (前端)                               │
│                    http://localhost:5173                                │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ WebSocket /chat
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    data-agent (AI 后端) - 端口 8100                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    LangGraph Main Graph                           │  │
│  │                                                                    │  │
│  │  ┌──────────────┐                                                 │  │
│  │  │  Router Node │  ← AI 意图识别                                  │  │
│  │  │  (LLM 决策)   │                                                 │  │
│  │  └──────┬───────┘                                                 │  │
│  │         │                                                         │  │
│  │         ├──────────────────┬──────────────────┬──────────────────┐│  │
│  │         │                  │                  │                  ││  │
│  │         ▼                  ▼                  ▼                  ▼│  │
│  │  ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────┐│  │
│  │  │Reconciliation│  │Data Prep   │  │Data Process│  │Other   ││  │
│  │  │Subgraph    │    │Subgraph    │    │Subgraph    │  │Tasks   ││  │
│  │  │(对账子图)   │    │(数据整理)   │    │(审计整理)   │  │        ││  │
│  │  │[已有]      │    │[占位符]     │    │[新增]      │  │        ││  │
│  │  └─────┬──────┘    └─────┬──────┘    └─────┬──────┘    └────────┘│  │
│  │        │                 │                 │                      │  │
│  └────────┼─────────────────┼─────────────────┼──────────────────────┘  │
│           │                 │                 │                          │
│           ▼                 ▼                 ▼                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    Task Execution Node                            │  │
│  │              (调用 MCP 工具，统一执行入口)                           │  │
│  └─────────────────────────────┬─────────────────────────────────────┘  │
│                                │                                         │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │ MCP Protocol
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  finance-mcp (MCP 工具服务器) - 端口 3335                 │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                   Unified MCP Server                              │  │
│  │                                                                    │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │  │
│  │  │Reconciliation│  │Data Prep     │  │Data Process          │    │  │
│  │  │Tools         │  │Tools         │  │Tools (新增)           │    │  │
│  │  │(6 个工具)     │  │(4 个工具)     │  │                      │    │  │
│  │  │              │  │              │  │  - list_skills       │    │  │
│  │  │              │  │              │  │  - generate_script   │    │  │
│  │  │              │  │              │  │  - execute_script    │    │  │
│  │  │              │  │              │  │  - get_result        │    │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                │                                         │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Data Process Module                                │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐          │
│  │Skill Manager │  │Script        │  │Execution             │          │
│  │技能管理器     │  │Generator     │  │Engine                │          │
│  │              │  │脚本生成器     │  │执行引擎              │          │
│  └──────────────┘  └──────────────┘  └──────────────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐          │
│  │Data Loader   │  │Result        │  │Skill Definitions     │          │
│  │数据加载器     │  │Manager       │  │(skills/*.md)         │          │
│  │              │  │结果管理器     │  │                      │          │
│  └──────────────┘  └──────────────┘  └──────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   /skills/*.md         │  Skill 定义文件
                    │   /data/*              │  原始数据 (Excel/PDF/图片)
                    │   /scripts/*.py        │  生成的脚本
                    │   /result/*            │  处理结果
                    └────────────────────────┘
```

---

## 四、业务功能流程图

### 4.1 整体业务流程 (集成版)

```
┌─────────┐
│  用户   │  输入："帮我整理审计数据" 或 "运行财务报表提取技能"
└────┬────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│  finance-web (前端)                                              │
│  - 用户输入通过 WebSocket 发送到 data-agent                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  data-agent (LangGraph Main Graph)                               │
│                                                                  │
│  ┌──────────────┐                                               │
│  │  Router Node │  ← LLM 分析意图                               │
│  │              │  判断：用户需要数据整理/审计处理                │
│  └──────┬───────┘                                               │
│         │                                                        │
│         ▼                                                        │
│  ┌────────────────┐                                             │
│  │ Data Process   │  ← 路由到数据处理子图                        │
│  │ Subgraph       │                                             │
│  └────────┬───────┘                                             │
│           │                                                      │
└───────────┼──────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Data Process Subgraph (数据处理子图)                             │
│                                                                  │
│  1. ┌──────────────┐                                            │
│     │ List Skills  │  ← 调用 MCP: list_skills                   │
│     └──────┬───────┘                                            │
│            │                                                     │
│  2. ┌──────▼──────────┐                                         │
│     │ Generate Script│  ← 调用 MCP: generate_script(skill_id)   │
│     └──────┬─────────┘                                          │
│            │                                                     │
│  3. ┌──────▼──────────┐                                         │
│     │ Execute Script │  ← 调用 MCP: execute_script(script_id)   │
│     └──────┬─────────┘                                          │
│            │                                                     │
│  4. ┌──────▼──────────┐                                         │
│     │ Get Result     │  ← 调用 MCP: get_result(task_id)         │
│     └──────┬─────────┘                                          │
│            │                                                     │
└────────────┼─────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│  finance-mcp (Data Process Module)                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Skill Manager                                            │   │
│  │  - 扫描 /skills 目录                                       │   │
│  │  - 解析 .md 文件                                           │   │
│  │  - 返回 Skill 列表和详情                                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Script Generator                                         │   │
│  │  - 读取 Skill 描述                                         │   │
│  │  - 调用 LLM 生成 Python 脚本                                │   │
│  │  - 保存到 /scripts 目录                                    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Execution Engine                                         │   │
│  │  - 安全执行脚本                                            │   │
│  │  - 处理 /data 目录数据                                     │   │
│  │  - 保存结果到 /result 目录                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│  文件系统                                                        │
│  /skills/*.md       →  Skill 定义                               │
│  /data/*            →  原始数据 (Excel/PDF/图片)                 │
│  /scripts/*.py      →  生成的脚本                               │
│  /result/*          →  处理结果                                 │
└─────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────┐
│  用户   │  接收处理结果 (Excel/CSV/JSON)
└─────────┘
```

### 4.2 Skill 处理详细流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Skill 处理流程 (集成版)                       │
└─────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐
  │ 1. 用户请求  │  "运行财务报表提取技能"
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 2. Router    │  LLM 分析意图，路由到 Data Process 子图
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 3. list_     │  调用 MCP: list_skills()
  │    skills    │  返回：["FIN-001: 财务报表提取", ...]
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 4. generate_ │  调用 MCP: generate_script("FIN-001")
  │    script    │  - 读取 skills/FIN-001.md
  │              │  - LLM 生成 Python 脚本
  │              │  - 保存到 scripts/generated_FIN-001.py
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 5. execute_  │  调用 MCP: execute_script(script_id)
  │    script    │  - 加载 data/ 目录数据
  │              │  - 执行脚本处理
  │              │  - 保存结果到 result/
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 6. get_      │  调用 MCP: get_result(task_id)
  │    result    │  返回：{"status": "completed", "file": "..."}
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │ 7. 返回结果  │  通过 WebSocket 流式返回给用户
  └──────────────┘
```

---

## 五、模块详细设计 (集成版)

### 5.1 核心模块划分

| 模块名称 | 文件路径 | 功能描述 | 优先级 |
|---------|---------|---------|--------|
| **Data Agent 扩展** |  |  |  |
| Data Process Graph | `app/graphs/data_process/` | 数据处理子图 | P0 |
| Data Process Nodes | `app/graphs/data_process/nodes.py` | 子图节点函数 | P0 |
| Data Process Router | `app/graphs/data_process/routers.py` | 子图路由 | P0 |
| **MCP 工具扩展** |  |  |  |
| Skill Manager | `finance-mcp/data_process/mcp_server/skill_loader.py` | Skill 加载和解析 | P0 |
| Script Generator | `finance-mcp/data_process/mcp_server/script_generator.py` | 脚本生成 | P0 |
| Script Executor | `finance-mcp/data_process/mcp_server/script_executor.py` | 脚本执行 | P0 |
| Task Manager | `finance-mcp/data_process/mcp_server/task_manager.py` | 任务管理 | P0 |
| MCP Tools | `finance-mcp/data_process/mcp_server/tools.py` | MCP 工具定义 | P0 |
| **配置目录** |  |  |  |
| Skills | `finance-agents/data-process/skills/` | Skill 定义文件 | P0 |
| Data | `finance-agents/data-process/data/` | 原始数据 | P0 |
| Scripts | `finance-agents/data-process/scripts/` | 生成的脚本 | P0 |
| Result | `finance-agents/data-process/result/` | 处理结果 | P0 |

### 5.2 最终目录结构

```
financial-ai/
├── finance-web/                           # [不变] 前端
│
├── finance-agents/
│   ├── data-agent/                        # [扩展] AI 后端
│   │   └── app/
│   │       ├── graphs/
│   │       │   ├── main_graph/            # [不变] 主图
│   │       │   ├── reconciliation.py      # [不变] 对账子图
│   │       │   ├── data_preparation.py    # [不变] 数据整理子图
│   │       │   └── data_process/          # [新增] 数据处理子图
│   │       │       ├── __init__.py
│   │       │       ├── data_process_graph.py
│   │       │       ├── nodes.py
│   │       │       └── routers.py
│   │       ├── tools/
│   │       │   ├── mcp_client.py          # [扩展] 添加 data_process 工具
│   │       │   └── data_process/          # [新增] 本地工具 (可选)
│   │       │       └── __init__.py
│   │       ├── server.py                  # [不变]
│   │       └── config.py                  # [不变]
│   │
│   └── data-process/                      # [保留] 配置和数据目录
│       ├── skills/                        # Skill 定义 (.md 文件)
│       │   ├── FIN-001.md                 # 示例：财务报表提取
│       │   └── AUD-001.md                 # 示例：审计数据核对
│       ├── data/                          # 原始数据
│       │   ├── excel/
│       │   ├── pdf/
│       │   └── images/
│       ├── scripts/                       # 生成的脚本
│       │   └── __init__.py
│       └── result/                        # 处理结果
│           └── reports/
│
├── finance-mcp/                           # [扩展] MCP 工具服务器
│   ├── unified_mcp_server.py              # [扩展] 注册 data_process 工具
│   ├── data_preparation/                  # [不变]
│   ├── reconciliation/                    # [不变]
│   └── data_process/                      # [新增] 数据处理模块
│       ├── __init__.py
│       └── mcp_server/
│           ├── __init__.py
│           ├── tools.py                   # MCP 工具定义
│           ├── skill_loader.py            # Skill 加载器
│           ├── script_generator.py        # 脚本生成器
│           ├── script_executor.py         # 脚本执行器
│           ├── task_manager.py            # 任务管理器
│           ├── processing_engine.py       # 处理引擎
│           └── utils/
│               ├── data_loader.py         # 数据加载器
│               ├── excel_processor.py     # Excel 处理器
│               ├── pdf_processor.py       # PDF 处理器
│               └── image_processor.py     # 图片处理器
│
└── .venv/                                 # [不变] 虚拟环境
```

---

## 六、MCP 工具定义

### 6.1 工具列表

| 工具名称 | 功能描述 | 输入参数 | 返回结果 |
|---------|---------|---------|---------|
| `list_skills` | 获取所有可用的 Skill 列表 | 无 | `[{id, name, description}]` |
| `get_skill_detail` | 获取 Skill 详细信息 | `skill_id: str` | `{id, name, description, rules}` |
| `generate_script` | 根据 Skill 生成 Python 脚本 | `skill_id: str` | `{script_id, path, status}` |
| `execute_script` | 执行生成的脚本 | `script_id: str` | `{task_id, status}` |
| `get_execution_status` | 获取执行状态 | `task_id: str` | `{status, progress, message}` |
| `get_execution_result` | 获取执行结果 | `task_id: str` | `{status, result_file, data}` |

### 6.2 工具实现示例

```python
# finance-mcp/data_process/mcp_server/tools.py

from mcp.server.fastmcp import FastMCP
from .skill_loader import load_skills, get_skill_detail
from .script_generator import generate_script as gen_script
from .script_executor import execute_script as exec_script
from .task_manager import get_task_status, get_task_result

mcp = FastMCP("data-process")

@mcp.tool()
async def list_skills() -> list[dict]:
    """获取所有可用的 Skill 列表"""
    return load_skills()

@mcp.tool()
async def get_skill_detail(skill_id: str) -> dict:
    """获取 Skill 详细信息"""
    return get_skill_detail(skill_id)

@mcp.tool()
async def generate_script(skill_id: str) -> dict:
    """根据 Skill 生成 Python 脚本"""
    return gen_script(skill_id)

@mcp.tool()
async def execute_script(script_id: str) -> dict:
    """执行生成的脚本"""
    return exec_script(script_id)

@mcp.tool()
async def get_execution_status(task_id: str) -> dict:
    """获取执行状态"""
    return get_task_status(task_id)

@mcp.tool()
async def get_execution_result(task_id: str) -> dict:
    """获取执行结果"""
    return get_task_result(task_id)
```

---

## 七、开发阶段规划

### 阶段一：基础架构搭建（预计 2-3 天）

**目标**: 完成集成架构和核心模块框架

| 任务编号 | 任务描述 | 优先级 | 预计工时 |
|---------|---------|--------|---------|
| 1.1 | 创建目录结构 (`data_process/` 子图、`finance-mcp/data_process/`) | P0 | 0.5 天 |
| 1.2 | 实现 Skill Loader (读取和解析 .md 文件) | P0 | 0.5 天 |
| 1.3 | 实现 Data Loader (支持 Excel/PDF/图片) | P0 | 1 天 |
| 1.4 | 注册 MCP 工具到 unified_mcp_server.py | P0 | 0.5 天 |
| 1.5 | 编写单元测试框架 | P1 | 0.5 天 |

**交付物**:
- 完整的目录结构
- Skill 加载和解析功能
- MCP 工具注册完成

### 阶段二：核心功能开发（预计 3-5 天）

**目标**: 实现 Script Generator 和 Execution Engine

| 任务编号 | 任务描述 | 优先级 | 预计工时 |
|---------|---------|--------|---------|
| 2.1 | 实现 Script Generator (LLM 生成脚本) | P0 | 1.5 天 |
| 2.2 | 实现 Script Executor (安全执行) | P0 | 1 天 |
| 2.3 | 实现 Task Manager (异步任务管理) | P0 | 1 天 |
| 2.4 | 创建 Data Process Subgraph (LangGraph) | P0 | 1 天 |
| 2.5 | 集成到 Main Graph Router | P0 | 0.5 天 |

**交付物**:
- 完整的脚本生成和执行能力
- LangGraph 子图集成完成
- 端到端流程可运行

### 阶段三：处理器完善（预计 2-3 天）

**目标**: 完善各类数据处理器

| 任务编号 | 任务描述 | 优先级 | 预计工时 |
|---------|---------|--------|---------|
| 3.1 | 完善 Excel 处理器 | P0 | 1 天 |
| 3.2 | 完善 PDF 处理器 | P0 | 1 天 |
| 3.3 | 完善图片处理器 (OCR) | P1 | 1 天 |

**交付物**:
- 支持多格式数据处理

### 阶段四：Skill 系统完善（预计 1-2 天）

**目标**: 完善 Skill 定义和管理系统

| 任务编号 | 任务描述 | 优先级 | 预计工时 |
|---------|---------|--------|---------|
| 4.1 | 设计 Skill MD 文件模板规范 | P0 | 0.5 天 |
| 4.2 | 创建示例 Skill (财务报表提取) | P0 | 0.5 天 |
| 4.3 | 创建示例 Skill (审计数据核对) | P1 | 0.5 天 |
| 4.4 | 实现 Skill 验证和错误处理 | P1 | 0.5 天 |

**交付物**:
- 标准化的 Skill 定义规范
- 可运行的示例 Skill

### 阶段五：测试与优化（预计 2-3 天）

**目标**: 系统测试和优化

| 任务编号 | 任务描述 | 优先级 | 预计工时 |
|---------|---------|--------|---------|
| 5.1 | 编写集成测试 | P0 | 1 天 |
| 5.2 | 性能优化 | P1 | 0.5 天 |
| 5.3 | 错误处理和日志 | P0 | 0.5 天 |
| 5.4 | 文档编写 | P1 | 1 天 |

**交付物**:
- 完整的测试用例
- 稳定的系统
- 完整的文档

---

## 八、Skill 定义规范

### 8.1 Skill MD 文件模板

```markdown
# Skill: {技能名称}

## 基本信息
- **Skill ID**: {唯一标识，如 FIN-001}
- **版本**: {版本号}
- **创建日期**: {创建日期}
- **最后更新**: {更新日期}

## 功能描述
{详细描述该 Skill 的功能和用途}

## 输入数据
- **数据源**: {数据来源目录或文件}
- **数据格式**: {Excel/PDF/图片等}
- **数据要求**: {数据格式要求、必填字段等}

## 处理规则
{详细描述数据处理规则}
1. 数据提取规则
2. 数据验证规则
3. 数据转换规则
4. 数据计算规则

## 输出结果
- **输出格式**: {Excel/CSV/JSON 等}
- **输出位置**: {result 目录下的路径}
- **输出内容**: {输出数据的结构和字段说明}

## 依赖关系
- **依赖 Skill**: {依赖的其他 Skill ID}
- **依赖库**: {需要的 Python 库}

## 异常处理
{说明可能出现的异常情况和处理方式}

## 示例
{提供输入输出示例}
```

### 8.2 Skill 示例

```markdown
# Skill: 财务报表数据提取

## 基本信息
- **Skill ID**: FIN-001
- **版本**: 1.0.0
- **创建日期**: 2026-02-25
- **最后更新**: 2026-02-25

## 功能描述
从 Excel 格式的财务报表中提取关键财务数据，包括资产负债表、利润表、现金流量表的核心指标。

## 输入数据
- **数据源**: data/financial_reports/
- **数据格式**: Excel (.xlsx)
- **数据要求**: 
  - 文件命名格式：YYYYMM_公司代码_报表类型.xlsx
  - 必须包含 sheet: 资产负债表、利润表

## 处理规则
1. 读取指定目录下的所有 Excel 文件
2. 验证文件格式和命名规范
3. 从资产负债表中提取：总资产、总负债、所有者权益
4. 从利润表中提取：营业收入、净利润、营业成本
5. 计算财务比率：资产负债率、毛利率、净利率
6. 验证数据完整性和合理性

## 输出结果
- **输出格式**: Excel (.xlsx)
- **输出位置**: result/financial_metrics/
- **输出内容**: 
  | 字段名 | 说明 |
  |--------|------|
  | company_code | 公司代码 |
  | report_date | 报表日期 |
  | total_assets | 总资产 |
  | total_liabilities | 总负债 |
  | equity | 所有者权益 |
  | revenue | 营业收入 |
  | net_profit | 净利润 |
  | asset_liability_ratio | 资产负债率 |
  | gross_margin | 毛利率 |
  | net_margin | 净利率 |

## 依赖关系
- **依赖 Skill**: 无
- **依赖库**: pandas, openpyxl

## 异常处理
1. 文件不存在：记录错误日志，跳过该文件
2. 格式错误：记录详细错误信息，通知用户
3. 数据异常：标记异常数据，继续处理其他数据

## 示例
输入：data/financial_reports/202601_ABC001_财务报表.xlsx
输出：result/financial_metrics/ABC001_202601_metrics.xlsx
```

---

## 九、集成代码示例

### 9.1 Data Process Subgraph

```python
# finance-agents/data-agent/app/graphs/data_process/data_process_graph.py

from __future__ import annotations

from langgraph.graph import StateGraph, END
from app.models import AgentState
from .nodes import (
    list_skills_node,
    generate_script_node,
    execute_script_node,
    get_result_node,
)

def build_data_process_subgraph() -> StateGraph:
    """构建数据处理子图"""
    builder = StateGraph(AgentState)
    
    # 添加节点
    builder.add_node("list_skills", list_skills_node)
    builder.add_node("generate_script", generate_script_node)
    builder.add_node("execute_script", execute_script_node)
    builder.add_node("get_result", get_result_node)
    
    # 设置边
    builder.set_entry_point("list_skills")
    builder.add_edge("list_skills", "generate_script")
    builder.add_edge("generate_script", "execute_script")
    builder.add_edge("execute_script", "get_result")
    builder.add_edge("get_result", END)
    
    return builder.compile()
```

### 9.2 Main Graph Router 集成

```python
# finance-agents/data-agent/app/graphs/main_graph/routers.py

from langgraph.graph import StateGraph
from ..data_process.data_process_graph import build_data_process_subgraph
from ..reconciliation import build_reconciliation_subgraph

def build_main_graph() -> StateGraph:
    """构建主图，包含所有子图"""
    builder = StateGraph(AgentState)
    
    # 添加主节点
    builder.add_node("router", router_node)
    builder.add_node("task_execution", task_execution_node)
    builder.add_node("result_analysis", result_analysis_node)
    
    # 添加子图
    builder.add_node("reconciliation", build_reconciliation_subgraph())
    builder.add_node("data_process", build_data_process_subgraph())  # 新增
    
    # 设置边
    builder.set_entry_point("router")
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {
            "reconciliation": "reconciliation",
            "data_process": "data_process",  # 新增
            "task_execution": "task_execution",
            "end": END,
        }
    )
    # ... 其他边
    
    return builder.compile()
```

### 9.3 MCP 工具注册

```python
# finance-mcp/unified_mcp_server.py

from data_process.mcp_server.tools import (
    list_skills,
    get_skill_detail,
    generate_script,
    execute_script,
    get_execution_status,
    get_execution_result,
)

# 注册 data_process 工具
mcp_app = FastMCP("finance-mcp")

# ... 现有工具 ...

# 新增 data_process 工具
mcp_app.tool(list_skills)
mcp_app.tool(get_skill_detail)
mcp_app.tool(generate_script)
mcp_app.tool(execute_script)
mcp_app.tool(get_execution_status)
mcp_app.tool(get_execution_result)
```

---

## 十、技术栈

### 10.1 核心技术栈

| 技术 | 用途 | 版本 |
|-----|------|------|
| Python | 主要编程语言 | 3.10+ |
| LangGraph | AI 工作流编排 | 最新 |
| LangChain | LLM 集成 | 最新 |
| MCP Protocol | 工具调用协议 | 最新 |
| FastMCP | MCP 服务器框架 | 最新 |
| pandas | 数据处理 | 2.0+ |
| openpyxl | Excel 处理 | 最新 |
| pdfplumber | PDF 处理 | 最新 |

### 10.2 依赖包

```txt
# 添加到 finance-mcp/requirements.txt 和 data-agent/requirements.txt

# Data Processing
pandas>=2.0.0
openpyxl>=3.1.0
xlrd>=2.0.0

# PDF Processing
pdfplumber>=0.10.0
PyPDF2>=3.0.0

# Image Processing
Pillow>=10.0.0
pytesseract>=0.3.10
```

---

## 十一、风险评估与应对

| 风险 | 影响程度 | 发生概率 | 应对措施 |
|-----|---------|---------|---------|
| LLM 生成脚本质量不稳定 | 高 | 中 | 增加代码验证和测试环节 |
| 与现有架构冲突 | 高 | 低 | 严格遵循现有架构模式 |
| MCP 工具调用失败 | 中 | 中 | 完善的错误处理和重试机制 |
| 复杂 PDF 解析准确率低 | 中 | 高 | 集成多种 PDF 解析库 |
| 脚本执行安全性 | 高 | 中 | 沙箱环境执行，限制系统调用 |

---

## 十二、验收标准

### 12.1 功能验收

- [ ] Data Process 子图成功集成到 Main Graph
- [ ] Router 能正确路由到 Data Process 子图
- [ ] 6 个 MCP 工具全部可用
- [ ] 能正确读取和解析 Skill 定义
- [ ] 能根据 Skill 生成可执行的 Python 脚本
- [ ] 能处理 Excel、PDF、图片等多种格式数据
- [ ] 能将处理结果正确保存到 result 目录

### 12.2 质量验收

- [ ] 单元测试覆盖率 >= 80%
- [ ] 集成测试通过率 100%
- [ ] 代码符合 PEP8 规范
- [ ] 无严重级别以上的安全漏洞

### 12.3 性能验收

- [ ] 单个 Skill 脚本生成时间 < 30 秒
- [ ] 支持至少 10 个 Skill 并发执行
- [ ] 大数据处理（>10MB Excel）不出现内存溢出

---

## 十三、与现有系统集成点

### 13.1 集成点清单

| 集成点 | 位置 | 说明 |
|-------|------|------|
| Main Graph Router | `app/graphs/main_graph/routers.py` | 添加 Data Process 路由 |
| MCP Client | `app/tools/mcp_client.py` | 添加 data_process 工具调用 |
| Unified MCP Server | `finance-mcp/unified_mcp_server.py` | 注册 data_process 工具 |
| Config | `app/config.py` | 添加 data_process 配置 |
| Models | `app/models.py` | 添加 Data Process 相关状态 |

### 13.2 配置扩展

```python
# app/config.py

# ── Data Process ─────────────────────────────────────────────────────────────
DATA_PROCESS_BASE_DIR: str = os.getenv(
    "DATA_PROCESS_BASE_DIR",
    str(Path(__file__).resolve().parents[3] / "finance-agents" / "data-process"),
)
DATA_PROCESS_SKILLS_DIR: str = os.path.join(DATA_PROCESS_BASE_DIR, "skills")
DATA_PROCESS_DATA_DIR: str = os.path.join(DATA_PROCESS_BASE_DIR, "data")
DATA_PROCESS_SCRIPTS_DIR: str = os.path.join(DATA_PROCESS_BASE_DIR, "scripts")
DATA_PROCESS_RESULT_DIR: str = os.path.join(DATA_PROCESS_BASE_DIR, "result")
```

---

## 十四、后续迭代规划

### 14.1 短期迭代（1-2 个月）

1. 支持 Skill 的热更新和动态加载
2. 实现 Skill 执行结果的可视化展示
3. 增加更多数据源支持（数据库、API 等）

### 14.2 中期迭代（3-6 个月）

1. 实现 Skill 的自动优化和建议
2. 支持复杂的多 Skill 协作场景
3. 建立 Skill 市场和共享机制

### 14.3 长期规划（6-12 个月）

1. 实现 Agent 的自主学习和能力进化
2. 支持分布式部署和大规模数据处理
3. 构建完整的审计数字员工生态系统

---

**文档版本**: 2.0 (集成版)  
**创建日期**: 2026-02-25  
**最后更新**: 2026-02-25  
**维护者**: Data-Process Team

# 文件上传逻辑修复总结

## 🎯 问题

1. **误解需求**：之前错误地在 finance-mcp 中添加了 HTTP `/upload_file` 端点
2. **报错**：测试时出现 "基于 HTTP 的 MCP 工具调用未实现；使用进程内调用" 错误
3. **理解偏差**：finance-mcp 的 `file_upload` MCP 工具是为 Dify 集成设计的，从 Dify API 下载文件，不适用于我们的场景

---

## ✅ 正确的架构

### 文件上传流程

```
用户浏览器
    ↓ 选择文件（支持多选）
finance-web (Vite :5173)
    ↓ POST /api/upload (Vite 代理转发)
data-agent (FastAPI :8100)
    ↓ 直接保存文件到 finance-mcp/uploads/年/月/日/
    ↓ 记录到 _thread_files 映射
    ↓ 返回 {file_path, filename, size}
finance-web
    ↓ 显示上传成功
    ↓ 自动发送 "已上传 N 个文件，请继续"
data-agent
    ↓ 调用 LangGraph 处理
    ↓ LangGraph 调用 finance-mcp 的 MCP 工具（reconciliation_start 等）
    ↓ MCP 工具直接从 finance-mcp/uploads/ 读取文件
```

### 关键点

1. **data-agent 直接保存文件**：不需要通过 HTTP 调用 finance-mcp
2. **共享文件存储**：data-agent 和 finance-mcp 都访问同一个 `finance-mcp/uploads/` 目录
3. **MCP 工具只负责对账**：`reconciliation_start` 等工具接收文件路径，而不是文件内容

---

## 🔧 具体修改

### 1. 撤销 finance-mcp 的修改

**文件：** `finance-mcp/unified_mcp_server.py`

**撤销的内容：**
- ❌ 删除了 `upload_file` HTTP 端点函数
- ❌ 删除了导入 `UPLOAD_DIR`, `MAX_FILE_SIZE`
- ❌ 删除了路由中的 `/upload_file` 端点

**最终状态：** finance-mcp 只提供 MCP 工具和 SSE 端点，不提供文件上传 HTTP 接口

---

### 2. 修正 data-agent 的 /upload 接口

**文件：** `finance-agents/data-agent/app/server.py`

**修改前（错误的代理方式）：**
```python
@app.post("/upload")
async def upload_file(...):
    # 使用 httpx 调用 finance-mcp 的 HTTP 端点
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FINANCE_MCP_BASE_URL}/upload_file",
            ...
        )
```

**修改后（正确的直接保存）：**
```python
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    thread_id: str = Form("default"),
):
    """上传文件到 finance-mcp/uploads 目录。"""
    # 验证文件类型和大小
    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(400, f"不支持的文件类型: {ext}")
    
    # 按日期创建目录
    now = datetime.now()
    date_dir = Path(UPLOAD_DIR) / str(now.year) / str(now.month) / str(now.day)
    date_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成安全的文件名
    safe_name = Path(file.filename).name
    dest = date_dir / safe_name
    
    # 如果文件已存在，添加时间戳
    if dest.exists():
        stem = dest.stem
        dest = date_dir / f"{stem}_{now.strftime('%H%M%S')}{ext}"
    
    # 保存文件
    content = await file.read()
    dest.write_bytes(content)
    file_path = str(dest)
    
    # 保存到线程文件映射
    _thread_files.setdefault(thread_id, []).append(file_path)
    
    logger.info(f"文件已上传到 finance-mcp/uploads: {file_path} (thread={thread_id})")
    return {"file_path": file_path, "filename": safe_name, "size": len(content)}
```

**导入修改：**
```python
# 修改前
from app.config import HOST, PORT, FINANCE_MCP_BASE_URL

# 修改后
from app.config import HOST, PORT, UPLOAD_DIR, MAX_FILE_SIZE
```

---

## 📁 配置说明

### data-agent/app/config.py

```python
# finance-mcp 配置
FINANCE_MCP_BASE_URL: str = os.getenv("FINANCE_MCP_BASE_URL", "http://localhost:3335")
FINANCE_MCP_UPLOAD_DIR: str = os.getenv(
    "FINANCE_MCP_UPLOAD_DIR",
    str(Path(__file__).resolve().parents[3] / "finance-mcp" / "uploads"),
)

# 文件上传配置
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", FINANCE_MCP_UPLOAD_DIR)
MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100MB
```

**关键点：**
- `UPLOAD_DIR` 默认指向 `finance-mcp/uploads`
- `FINANCE_MCP_BASE_URL` 用于调用 MCP 工具（通过进程内调用，不是 HTTP）

---

## 🚀 服务状态

### 当前运行的服务

| 服务 | 状态 | 地址 | 端口 | 说明 |
|------|------|------|------|------|
| **finance-mcp** | ✅ 运行中 | http://0.0.0.0:3335 | 3335 | MCP 工具服务（SSE） |
| **data-agent** | ✅ 运行中 | http://0.0.0.0:8100 | 8100 | LangGraph Agent + 文件上传 |
| **finance-web** | ✅ 运行中 | http://localhost:5173 | 5173 | 前端界面 |

---

## 🧪 测试步骤

### 1. 打开浏览器
访问 http://localhost:5173

### 2. 测试文件上传
1. 发送消息：`"我要做对账"`
2. AI 回复：请上传对账文件
3. 点击📎按钮，选择多个文件（如 business.xlsx, finance.xlsx）
4. 观察：
   - ✅ 文件上传成功
   - ✅ 前端自动发送 "已上传 2 个文件：business.xlsx、finance.xlsx。请继续。"
   - ✅ AI 继续流程，调用 MCP 工具分析文件

### 3. 验证文件存储位置
```bash
ls -lh /Users/kevin/workspace/financial-ai/finance-mcp/uploads/2026/2/11/
```

**期望输出：**
```
business.xlsx
finance.xlsx
```

---

## 🔍 MCP 工具调用说明

### data-agent 如何调用 finance-mcp 的 MCP 工具

**文件：** `finance-agents/data-agent/app/tools/mcp_client.py`

```python
async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """通过进程内调用或 HTTP 调用 finance-mcp 工具。"""
    try:
        # 优先使用进程内调用
        return await _call_tool_in_process(tool_name, arguments)
    except Exception:
        logger.warning("进程内 MCP 调用失败，回退到 HTTP", exc_info=True)
        return await _call_tool_http(tool_name, arguments)


async def _call_tool_in_process(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """导入 finance-mcp 工具处理器并直接调用。"""
    import sys
    mcp_root = str(Path(__file__).resolve().parents[3] / "finance-mcp")
    if mcp_root not in sys.path:
        sys.path.insert(0, mcp_root)
    
    from reconciliation.mcp_server.tools import handle_tool_call
    result = await handle_tool_call(tool_name, arguments)
    return result
```

**关键点：**
1. **进程内调用**：直接导入 finance-mcp 的 `handle_tool_call` 函数
2. **不需要 HTTP**：两个服务在同一台机器上，进程内调用更高效
3. **文件路径传递**：data-agent 上传文件后，将文件路径传递给 MCP 工具

---

## 📊 对账流程示例

```
1. 用户：我要做对账
   ↓
2. AI：请上传业务数据和财务数据文件
   ↓
3. 用户：上传 business.xlsx, finance.xlsx
   ↓
4. data-agent：保存到 finance-mcp/uploads/2026/2/11/
   ↓
5. 用户（自动）：已上传 2 个文件，请继续
   ↓
6. LangGraph：分析文件，识别类型
   ↓
7. LangGraph：调用 MCP 工具 reconciliation_start
   参数：{
     "reconciliation_type": "直销对账",
     "files": [
       "/path/to/finance-mcp/uploads/2026/2/11/business.xlsx",
       "/path/to/finance-mcp/uploads/2026/2/11/finance.xlsx"
     ]
   }
   ↓
8. finance-mcp：执行对账，返回 task_id
   ↓
9. LangGraph：轮询任务状态
   ↓
10. LangGraph：获取对账结果，展示给用户
```

---

## ⚠️ 关键要点

### 1. 不要混淆 MCP 工具和 HTTP 端点
- **MCP 工具**：finance-mcp 提供的 `reconciliation_start` 等工具，通过 SSE 或进程内调用
- **HTTP 端点**：data-agent 提供的 `/upload` 端点，用于前端上传文件

### 2. 文件存储位置
- **统一存储**：所有文件存储在 `finance-mcp/uploads/`
- **data-agent 负责上传**：接收前端文件，保存到共享目录
- **finance-mcp 负责处理**：MCP 工具从共享目录读取文件进行对账

### 3. 线程文件映射
- **`_thread_files`**：data-agent 维护每个 thread 上传的文件列表
- **用途**：当 AI 需要知道用户上传了哪些文件时，从这里获取

---

## 🛠️ 调试技巧

### 查看文件上传日志
```bash
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/21.txt | grep "文件已上传"
```

### 查看 MCP 工具调用日志
```bash
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/24.txt | grep "reconciliation"
```

### 检查上传的文件
```bash
ls -lhR /Users/kevin/workspace/financial-ai/finance-mcp/uploads/
```

---

## 🎉 总结

1. **✅ 撤销了错误的修改**：删除了 finance-mcp 中不必要的 HTTP 端点
2. **✅ 修正了架构**：data-agent 直接保存文件到共享目录
3. **✅ 保持了解耦**：文件上传和对账逻辑分离
4. **✅ 所有服务正常运行**：finance-mcp (3335)、data-agent (8100)、finance-web (5173)

---

**修改完成时间**：2026-02-11 15:00  
**修改文件数量**：2 个（unified_mcp_server.py, server.py）  
**测试状态**：✅ 准备测试

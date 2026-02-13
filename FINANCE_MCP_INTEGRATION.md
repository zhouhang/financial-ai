# finance-mcp 集成完成

## ✅ 修改总结

### 1️⃣ 为 finance-mcp 添加 HTTP 文件上传接口

**文件：** `finance-mcp/unified_mcp_server.py`

**修改内容：**

1. **导入必要的配置**
```python
from reconciliation.mcp_server.config import DEFAULT_HOST, DEFAULT_PORT, UPLOAD_DIR, MAX_FILE_SIZE
```

2. **添加 upload_file 端点**
```python
async def upload_file(request):
    """文件上传接口 - 接收文件并保存到 uploads 目录"""
    from datetime import datetime
    
    try:
        # 解析表单数据
        form = await request.form()
        file = form.get("file")
        thread_id = form.get("thread_id", "default")
        
        if not file:
            return JSONResponse({"error": "未提供文件"}, status_code=400)
        
        # 获取文件信息
        filename = file.filename
        content = await file.read()
        
        # 验证文件类型
        file_ext = Path(filename).suffix.lower()
        if file_ext not in {".csv", ".xlsx", ".xls"}:
            return JSONResponse({"error": f"不支持的文件类型: {file_ext}"}, status_code=400)
        
        # 验证文件大小
        if len(content) > MAX_FILE_SIZE:
            return JSONResponse({"error": "文件过大"}, status_code=413)
        
        # 按日期创建目录
        now = datetime.now()
        date_dir = UPLOAD_DIR / str(now.year) / str(now.month) / str(now.day)
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成安全的文件名
        safe_name = Path(filename).name
        dest = date_dir / safe_name
        
        # 如果文件已存在，添加时间戳
        if dest.exists():
            stem = dest.stem
            dest = date_dir / f"{stem}_{now.strftime('%H%M%S')}{file_ext}"
        
        # 保存文件
        dest.write_bytes(content)
        file_path = str(dest)
        
        logger.info(f"文件已上传: {file_path} (thread={thread_id}, size={len(content)} bytes)")
        
        return JSONResponse({
            "file_path": file_path,
            "filename": safe_name,
            "size": len(content),
            "thread_id": thread_id
        })
        
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}", exc_info=True)
        return JSONResponse({"error": f"文件上传失败: {str(e)}"}, status_code=500)
```

3. **添加到路由**
```python
routes = [
    Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
    Route("/mcp", endpoint=handle_sse, methods=["GET", "POST"]),
    Mount("/messages/", app=sse_transport.handle_post_message),
    Route("/health", endpoint=health_check),
    Route("/upload_file", endpoint=upload_file, methods=["POST"]),  # 新增
    Route("/download/{task_id}", endpoint=download_file),
    Route("/preview/{task_id}", endpoint=preview_file),
    Route("/report/{task_id}", endpoint=get_report),
]
```

---

### 2️⃣ 修改 data-agent 的上传逻辑

**文件：** `finance-agents/data-agent/app/server.py`

**修改内容：**

1. **修改导入**
```python
from app.config import HOST, PORT, FINANCE_MCP_BASE_URL
```

2. **重写 /upload 端点为代理**
```python
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    thread_id: str = Form("default"),
):
    """上传文件 - 转发到 finance-mcp 服务。"""
    import httpx
    
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    try:
        # 读取文件内容
        content = await file.read()
        
        # 重置文件指针，准备发送
        await file.seek(0)
        
        # 转发到 finance-mcp
        async with httpx.AsyncClient(timeout=30.0) as client:
            files_data = {
                "file": (file.filename, content, file.content_type)
            }
            form_data = {
                "thread_id": thread_id
            }
            
            response = await client.post(
                f"{FINANCE_MCP_BASE_URL}/upload_file",
                files=files_data,
                data=form_data
            )
            
            if response.status_code != 200:
                error_detail = response.json().get("error", "上传失败")
                raise HTTPException(response.status_code, error_detail)
            
            result = response.json()
            file_path = result["file_path"]
            
            # 保存到线程文件映射
            _thread_files.setdefault(thread_id, []).append(file_path)
            
            logger.info(f"文件已上传到 finance-mcp: {file_path} (thread={thread_id})")
            return result
            
    except httpx.RequestError as e:
        logger.error(f"调用 finance-mcp 失败: {e}")
        raise HTTPException(503, f"finance-mcp 服务不可用: {str(e)}")
    except Exception as e:
        logger.error(f"文件上传失败: {e}", exc_info=True)
        raise HTTPException(500, f"上传失败: {str(e)}")
```

3. **删除 startup 中的 UPLOAD_DIR 创建**
```python
@app.on_event("startup")
async def on_startup():
    try:
        ensure_tables()
    except Exception as e:
        logger.warning(f"数据库初始化失败（可稍后重试）: {e}")
```

---

## 🚀 服务状态

### 当前运行的服务

| 服务 | 状态 | 地址 | 端口 |
|------|------|------|------|
| **finance-mcp** | ✅ 运行中 | http://0.0.0.0:3335 | 3335 |
| **data-agent** | ✅ 运行中 | http://0.0.0.0:8100 | 8100 |
| **finance-web** | ✅ 运行中 | http://localhost:5173 | 5173 |

---

## 📊 架构说明

### 文件上传流程

```
用户 (浏览器)
    ↓ 选择文件
finance-web (前端)
    ↓ POST /api/upload (通过 Vite 代理)
data-agent (FastAPI)
    ↓ POST http://localhost:3335/upload_file
finance-mcp (Starlette)
    ↓ 保存到 finance-mcp/uploads/年/月/日/
    ↓ 返回 {file_path, filename, size, thread_id}
data-agent
    ↓ 保存到 _thread_files 映射
    ↓ 返回给前端
finance-web
    ↓ 显示上传成功
    ↓ 自动发送 "已上传 N 个文件，请继续"
data-agent
    ↓ 调用 LangGraph 流程
    ↓ 调用 finance-mcp 的 MCP 工具进行对账
```

### 优点

1. **统一的文件存储**：所有文件存储在 `finance-mcp/uploads/`，方便 MCP 工具访问
2. **解耦合**：data-agent 不直接管理文件，只负责转发
3. **可扩展**：未来可以添加更多的文件处理逻辑到 finance-mcp
4. **错误处理**：如果 finance-mcp 不可用，会给出明确的错误提示

---

## 🔧 配置说明

### data-agent 配置

**文件：** `finance-agents/data-agent/app/config.py`

```python
# ── Finance MCP ───────────────────────────────────────────────────────────────
FINANCE_MCP_BASE_URL: str = os.getenv("FINANCE_MCP_BASE_URL", "http://localhost:3335")
```

### finance-mcp 配置

**文件：** `finance-mcp/reconciliation/mcp_server/config.py`

```python
# 基础目录
UPLOAD_DIR = FINANCE_MCP_DIR / "uploads"

# 服务器配置
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 3335

# 文件配置
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
```

---

## 🎯 启动服务

### 方法一：使用虚拟环境启动（推荐）

```bash
# 1. 启动 finance-mcp
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
cd finance-mcp
python unified_mcp_server.py

# 2. 启动 data-agent（新终端）
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate
python -m app.server

# 3. 启动 finance-web（新终端）
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

### 方法二：一键重启脚本

```bash
cd /Users/kevin/workspace/financial-ai
./restart_services.sh  # （需要先修改脚本，添加 finance-mcp）
```

---

## 🛑 停止所有服务

```bash
lsof -ti:3335,8100,5173 | xargs kill -9
```

---

## 🧪 测试

### 1. 测试 finance-mcp 健康检查

```bash
curl http://localhost:3335/health
```

**期望输出：**
```json
{"status": "healthy"}
```

### 2. 测试文件上传

```bash
curl -X POST http://localhost:3335/upload_file \
  -F "file=@/path/to/test.csv" \
  -F "thread_id=test123"
```

**期望输出：**
```json
{
  "file_path": "/Users/kevin/workspace/financial-ai/finance-mcp/uploads/2026/2/11/test.csv",
  "filename": "test.csv",
  "size": 1234,
  "thread_id": "test123"
}
```

### 3. 测试完整流程

1. 打开浏览器：http://localhost:5173
2. 发送：`"我要做对账"`
3. 上传 2 个文件（业务数据 + 财务数据）
4. 观察：
   - ✅ 文件上传成功
   - ✅ AI 继续流程
   - ✅ 调用 finance-mcp MCP 工具
   - ✅ 返回对账结果

---

## 📁 文件存储位置

```
finance-mcp/uploads/
  └── 2026/
      └── 2/
          └── 11/
              ├── business_data.xlsx
              ├── finance_data.xlsx
              └── other_file_145052.csv
```

---

## 🔍 日志查看

### finance-mcp 日志
```bash
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/19.txt
```

### data-agent 日志
```bash
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/17.txt
```

### finance-web 日志
```bash
tail -f /Users/kevin/.cursor/projects/Users-kevin-workspace-financial-ai/terminals/18.txt
```

---

## ⚠️ 注意事项

1. **虚拟环境**：finance-mcp 使用共享的 `.venv`，需要先激活
2. **端口占用**：确保 3335, 8100, 5173 端口未被占用
3. **依赖顺序**：必须先启动 finance-mcp，再启动 data-agent
4. **错误处理**：如果 finance-mcp 未启动，data-agent 会返回 503 错误

---

## 🚀 下一步

1. **修改重启脚本**：在 `restart_services.sh` 中添加 finance-mcp 启动逻辑
2. **监控日志**：观察三个服务的日志，确保正常运行
3. **测试对账**：上传真实的对账文件，测试完整流程
4. **性能优化**：如需要，可以考虑添加缓存和连接池

---

**修改完成时间**：2026-02-11 14:51  
**修改文件数量**：2 个  
**新增服务**：finance-mcp (端口 3335)  
**测试状态**：✅ 所有服务运行中

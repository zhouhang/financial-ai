# 服务启动说明与文件上传路径

## 🚀 服务状态

### ✅ data-agent (后端)
- **地址**：http://0.0.0.0:8100
- **状态**：✅ 运行中
- **日志**：WebSocket 连接已建立，LLM (DeepSeek) 调用正常

### ✅ finance-web (前端)
- **地址**：http://localhost:5173
- **状态**：✅ 运行中
- **构建工具**：Vite v7.3.1

---

## 📂 文件上传路径

### `/upload` 接口说明

**文件存储位置：**
```
/Users/kevin/workspace/financial-ai/finance-mcp/uploads/
```

**目录结构（按日期分类）：**
```
uploads/
  └── 2026/
      └── 2/
          └── 11/
              ├── business_data.xlsx
              ├── finance_data.xlsx
              └── other_file_142530.csv  (同名文件自动加时间戳)
```

### 配置源码

**配置文件：** `finance-agents/data-agent/app/config.py`

```python
# 默认上传目录
FINANCE_MCP_UPLOAD_DIR: str = os.getenv(
    "FINANCE_MCP_UPLOAD_DIR",
    str(Path(__file__).resolve().parents[3] / "finance-mcp" / "uploads"),
)

# 实际使用的上传目录（可通过 .env 覆盖）
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", FINANCE_MCP_UPLOAD_DIR)
```

**上传逻辑：** `finance-agents/data-agent/app/server.py`

```python
@app.post("/upload")
async def upload_file(file: UploadFile = File(...), thread_id: str | None = None):
    # 按日期创建子目录
    now = datetime.now()
    date_dir = Path(UPLOAD_DIR) / str(now.year) / str(now.month) / str(now.day)
    date_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存文件
    safe_name = Path(file.filename).name
    dest = date_dir / safe_name
    
    # 如果文件已存在，添加时间戳
    if dest.exists():
        stem = dest.stem
        dest = date_dir / f"{stem}_{now.strftime('%H%M%S')}{ext}"
    
    dest.write_bytes(content)
    file_path = str(dest)  # 返回绝对路径
    
    # 关联到 thread_id
    _thread_files.setdefault(thread_id, []).append(file_path)
    
    return {"file_path": file_path, "filename": safe_name, "size": len(content)}
```

---

## 📋 文件上传特性

### ✅ 已实现功能

1. **多文件上传**
   - 前端支持 `multiple` 属性
   - 并行上传多个文件

2. **自动分类存储**
   - 按年/月/日三级目录存储
   - 便于管理和清理

3. **防重名冲突**
   - 同名文件自动添加时间戳后缀
   - 格式：`filename_HHMMSS.ext`

4. **文件大小限制**
   - 最大 100MB
   - 可通过环境变量 `MAX_FILE_SIZE` 调整

5. **支持的文件类型**
   - `.csv`
   - `.xlsx`
   - `.xls`

6. **会话关联**
   - 每个 `thread_id` 的文件单独跟踪
   - 在 `_thread_files` 字典中维护映射

---

## 🔧 启动命令

### 启动后端 (data-agent)
```bash
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate
python -m app.server
```

### 启动前端 (finance-web)
```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev
```

### 一键启动脚本（可选）
创建 `start_all.sh`：
```bash
#!/bin/bash

# 启动后端
cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
source .venv/bin/activate
python -m app.server > ../../logs/data-agent.log 2>&1 &
echo "data-agent started (PID: $!)"

# 启动前端
cd /Users/kevin/workspace/financial-ai/finance-web
npm run dev > ../logs/finance-web.log 2>&1 &
echo "finance-web started (PID: $!)"

echo "All services started!"
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:8100"
```

---

## 📊 上传流程图

```
用户选择文件
    ↓
前端 ChatArea.tsx
    ↓
handleFileUpload (并行上传)
    ↓
POST /api/upload (Vite 代理到 :8100/upload)
    ↓
data-agent server.py
    ↓
保存到 finance-mcp/uploads/2026/2/11/
    ↓
返回 {file_path, filename, size}
    ↓
前端更新文件列表 + 自动发送消息通知 AI
    ↓
AI 继续流程（文件分析）
```

---

## 🗂️ 查看已上传文件

```bash
# 查看今天上传的文件
ls -lh /Users/kevin/workspace/financial-ai/finance-mcp/uploads/$(date +%Y/%m/%d)

# 查看所有上传文件
tree /Users/kevin/workspace/financial-ai/finance-mcp/uploads

# 清理旧文件（7天前）
find /Users/kevin/workspace/financial-ai/finance-mcp/uploads -type f -mtime +7 -delete
```

---

## ⚙️ 自定义上传路径

如果需要修改上传目录，有两种方式：

### 方式1：环境变量（推荐）
创建 `.env` 文件：
```bash
# finance-agents/data-agent/.env
UPLOAD_DIR=/Users/kevin/custom/upload/path
MAX_FILE_SIZE=209715200  # 200MB
```

### 方式2：修改代码
直接修改 `config.py`：
```python
UPLOAD_DIR: str = "/Users/kevin/custom/upload/path"
```

---

## 🎯 测试上传

在浏览器中：
1. 访问 http://localhost:5173
2. 点击左下角 📎 按钮
3. 选择多个文件（Ctrl/Cmd + 点击）
4. 上传成功后查看右侧"文件" Tab

在终端验证：
```bash
ls -lh /Users/kevin/workspace/financial-ai/finance-mcp/uploads/$(date +%Y/%m/%d)
```

---

**更新时间**：2026-02-11 14:32  
**服务状态**：✅ 全部运行中

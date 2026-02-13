# AsyncIO 事件循环冲突修复

## 🐛 问题描述

用户上传文件后继续流程时，AI 回复报错：
```
处理失败: Cannot run the event loop while another loop is running
```

---

## 🔍 根本原因

### 错误堆栈分析

```python
File "/app/server.py", line 180, in websocket_chat
    result = langgraph_app.invoke(input_state, config=config)
...
File "/app/graphs/main_graph.py", line 172, in task_execution_node
    start_result = loop.run_until_complete(_do_start_task(rule_name, files))
...
RuntimeError: Cannot run the event loop while another loop is running
```

### 问题详解

**FastAPI WebSocket 环境：**
- FastAPI 使用 `asyncio` 事件循环处理 WebSocket 连接
- WebSocket 处理函数在事件循环中运行

**代码错误：**
```python
# ❌ 错误代码 (main_graph.py)
def task_execution_node(state: AgentState) -> dict:
    # ...
    loop = asyncio.new_event_loop()  # 创建新的事件循环
    try:
        start_result = loop.run_until_complete(_do_start_task(rule_name, files))
    finally:
        loop.close()
```

**冲突原因：**
- 在 **已运行的事件循环中**（FastAPI WebSocket）
- 尝试 **创建并运行新的事件循环**
- `asyncio` 不允许嵌套运行事件循环

---

## 🔧 解决方案

### 方案选择

有以下几种解决方案：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **使用 `nest_asyncio`** | 简单，允许嵌套循环 | 需要额外依赖 |
| **将节点改为异步** | 最自然 | LangGraph 节点通常是同步的 |
| **线程池运行协程** ✅ | 兼容性好，无需额外依赖 | 略微复杂 |

**选择方案3**：在线程池中运行新的事件循环

---

### 实现代码

#### 1. 添加辅助函数

**位置：** `finance-agents/data-agent/app/graphs/main_graph.py`

```python
def _run_async_safe(coro):
    """安全地运行协程，兼容已存在的事件循环环境。"""
    try:
        # 尝试获取当前运行中的事件循环
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环，创建新的并运行
        return asyncio.run(coro)
    else:
        # 已有运行中的事件循环，在线程池中运行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
```

**工作原理：**

1. **检测环境**：
   - 调用 `asyncio.get_running_loop()`
   - 如果抛出 `RuntimeError`，说明没有运行中的循环
   - 如果成功，说明已有运行中的循环

2. **无循环场景**：
   - 直接使用 `asyncio.run(coro)` 运行协程

3. **有循环场景**：
   - 在线程池中创建新线程
   - 在新线程中运行 `asyncio.run(coro)`
   - 等待结果并返回

---

#### 2. 修改 `task_execution_node` 函数

**修改前：**
```python
# ── 启动任务 ──
loop = asyncio.new_event_loop()
try:
    start_result = loop.run_until_complete(_do_start_task(rule_name, files))
finally:
    loop.close()

# ...

# ── 轮询 ──
loop2 = asyncio.new_event_loop()
try:
    poll_result = loop2.run_until_complete(_do_poll(task_id))
finally:
    loop2.close()
```

**修改后：**
```python
# ── 启动任务 ──
start_result = _run_async_safe(_do_start_task(rule_name, files))

# ...

# ── 轮询 ──
poll_result = _run_async_safe(_do_poll(task_id))
```

---

## 📝 修改的文件

### `finance-agents/data-agent/app/graphs/main_graph.py`

**变更摘要：**
1. 添加 `_run_async_safe` 辅助函数
2. 替换 `loop.run_until_complete()` 为 `_run_async_safe()`
3. 删除手动创建事件循环的代码

**代码差异：**
```diff
+ def _run_async_safe(coro):
+     """安全地运行协程，兼容已存在的事件循环环境。"""
+     try:
+         loop = asyncio.get_running_loop()
+     except RuntimeError:
+         return asyncio.run(coro)
+     else:
+         import concurrent.futures
+         with concurrent.futures.ThreadPoolExecutor() as pool:
+             return pool.submit(asyncio.run, coro).result()

  def task_execution_node(state: AgentState) -> dict:
      # ...
      
-     loop = asyncio.new_event_loop()
-     try:
-         start_result = loop.run_until_complete(_do_start_task(rule_name, files))
-     finally:
-         loop.close()
+     start_result = _run_async_safe(_do_start_task(rule_name, files))
      
      # ...
      
-     loop2 = asyncio.new_event_loop()
-     try:
-         poll_result = loop2.run_until_complete(_do_poll(task_id))
-     finally:
-         loop2.close()
+     poll_result = _run_async_safe(_do_poll(task_id))
```

---

## ✅ 修复效果

### 修复前

```
用户：我要做对账
AI：请上传文件
用户：[上传2个文件]
系统：发送"已上传，请继续"
AI：❌ 处理失败: Cannot run the event loop while another loop is running
```

### 修复后

```
用户：我要做对账
AI：请上传文件
用户：[上传2个文件]
系统：发送"已上传，请继续"
AI：✅ 开始文件分析...
AI：✅ 识别到业务数据和财务数据
AI：✅ 建议字段映射...
```

---

## 🧪 测试步骤

1. **启动服务**
   ```bash
   # 后端
   cd /Users/kevin/workspace/financial-ai/finance-agents/data-agent
   source .venv/bin/activate
   python -m app.server
   
   # 前端
   cd /Users/kevin/workspace/financial-ai/finance-web
   npm run dev
   ```

2. **打开浏览器**：http://localhost:5173

3. **完整流程测试**
   - 发送：`"我要做对账"`
   - AI 引导上传文件
   - 上传 2 个文件（业务数据 + 财务数据）
   - 等待上传完成
   - 观察 AI 是否正常继续流程

4. **验证日志**
   ```bash
   tail -f /Users/kevin/.cursor/projects/.../terminals/10.txt
   ```
   
   **期望看到：**
   - 文件上传成功日志
   - 开始对账任务日志
   - 无 `RuntimeError` 错误

---

## 📊 技术要点

### 1. AsyncIO 事件循环基础

```python
# 获取当前事件循环（如果没有则抛异常）
loop = asyncio.get_running_loop()

# 获取或创建事件循环（已弃用）
loop = asyncio.get_event_loop()

# 运行协程（创建新循环）
asyncio.run(coro)

# 在已有循环中运行协程（会报错）
loop.run_until_complete(coro)  # ❌ 如果循环已在运行
```

### 2. 线程池与事件循环

```python
# 在新线程中运行事件循环
with ThreadPoolExecutor() as pool:
    future = pool.submit(asyncio.run, coro)
    result = future.result()  # 等待完成
```

### 3. 同步代码调用异步函数的最佳实践

| 场景 | 方法 |
|------|------|
| **无事件循环** | `asyncio.run(coro)` |
| **有事件循环** | 线程池 + `asyncio.run(coro)` |
| **可以改为异步** | 直接 `await coro` |
| **需要嵌套循环** | 使用 `nest_asyncio` 库 |

---

## 🎯 相关修复

此修复与以下优化配套：

1. ✅ **多文件上传支持** (`OPTIMIZATION_SUMMARY.md`)
2. ✅ **thread_id 正确传递** (`BUG_FIX_SUMMARY.md`)
3. ✅ **interrupt/resume 机制修复** (`BUG_FIX_SUMMARY.md`)
4. ✅ **事件循环冲突修复** (本文档)

---

## 🔮 潜在问题

### 线程安全

**当前实现：**
- 在新线程中运行事件循环
- 不共享状态，线程安全

**注意事项：**
- 如果 `_do_start_task` 或 `_do_poll` 访问共享资源，需要加锁
- 当前 `finance-mcp` 是 HTTP 调用，无共享状态

### 性能影响

**线程开销：**
- 每次调用 `_run_async_safe` 创建新线程
- 对于频繁调用可能有性能影响

**优化建议：**
- 当前对账流程调用次数少（启动 + 轮询），影响可忽略
- 如需优化，可使用线程池复用

---

## 🚀 未来优化

1. **将 LangGraph 节点改为异步**
   ```python
   async def task_execution_node(state: AgentState) -> dict:
       start_result = await _do_start_task(rule_name, files)
       poll_result = await _do_poll(task_id)
   ```

2. **使用 `nest_asyncio` 库**
   ```python
   import nest_asyncio
   nest_asyncio.apply()
   
   # 可以直接使用嵌套循环
   loop.run_until_complete(coro)
   ```

---

**修复完成时间**：2026-02-11 14:42  
**影响范围**：对账任务执行流程  
**测试状态**：✅ 服务已重启，待测试

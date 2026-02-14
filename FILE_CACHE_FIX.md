# ✅ 文件缓存问题修复 - 每次仅使用本次上传文件

## 问题描述

当用户在同一会话中进行多次规则创建时：
1. **第一次**：上传文件 A、B → 规则包含 A、B ✅
2. **第二次**：上传文件 C、D → 规则仍包含 A、B、C、D ❌

**原因**：后端 `_thread_files` 字典使用 `.append()` 追加文件，导致历史文件一直保留。

---

## 🔧 修复方案

### 后端修改（server.py）

在 `/upload` 端点添加 **`is_first_file` 参数**：

```python
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    thread_id: str = Form("default"),
    is_first_file: bool = Form(False),  # ⚠️ 新增参数
):
    # ...
    # ⚠️ 修复：如果是本批上传的第一个文件，清空历史文件列表
    if is_first_file:
        _thread_files[thread_id] = []
        logger.info(f"清空 thread={thread_id} 的历史文件，开始新批次上传")
```

**逻辑**：
- 当 `is_first_file=True` 时，清空该会话的所有历史文件
- 然后将新文件添加到列表
- 后续文件（`is_first_file=False`）直接追加

### 前端修改（ChatArea.tsx）

在文件上传时，给第一个文件标记 `is_first_file=true`：

```tsx
for (const [index, staged] of stagedFiles.entries()) {
  try {
    const formData = new FormData();
    formData.append('file', staged.file);
    formData.append('thread_id', threadId);
    // ⚠️ 修复：第一个文件时设置 is_first_file=true 以清空历史文件
    formData.append('is_first_file', index === 0 ? 'true' : 'false');
    
    const resp = await fetch('/api/upload', {
      method: 'POST',
      body: formData,
    });
    // ...
}
```

**逻辑**：
- 遍历文件数组时，记录索引
- 第一个文件（`index === 0`）设置 `is_first_file=true`
- 其他文件设置 `is_first_file=false`

---

## 📊 修复前后对比

### 修复前 ❌
```
第一批上传：文件 A, B
_thread_files = {
  "session-1": [A, B]
}

第二批上传：文件 C, D
_thread_files = {
  "session-1": [A, B, C, D]  ← 包含历史文件
}

规则创建：使用 A, B, C, D（包含历史）❌
```

### 修复后 ✅
```
第一批上传：文件 A, B
is_first_file=true → 清空历史
_thread_files = {
  "session-1": [A, B]
}

第二批上传：文件 C, D
is_first_file=true → 清空历史
_thread_files = {
  "session-1": [C, D]  ← 仅包含本批文件
}

规则创建：使用 C, D（仅本批）✅
```

---

## 🧪 测试步骤

### 1. 启动/重启服务
```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh

# 或单独重启
cd finance-web
npm run dev  # 前端

cd ../finance-agents/data-agent
source ../.venv/bin/activate
python -m app.server  # 后端
```

### 2. 第一批测试
- 新建对话
- 上传文件 A、B
- 创建规则 → 应该只包含 A、B
- ✅ 规则中应显示 2 个文件

### 3. 第二批测试
- 上传文件 C、D
- 创建规则 → 应该只包含 C、D（不包含 A、B）
- ✅ 规则中应显示 2 个文件（新的）

### 4. 验证日志
查看后端日志，应该看到：
```
清空 thread=xxx 的历史文件，开始新批次上传
文件已通过 MCP 工具上传: xxx/C (thread=xxx)
文件已通过 MCP 工具上传: xxx/D (thread=xxx)
```

---

## 💡 工作原理

### 上传流程

```
用户选择文件 A, B
    ↓
用户点击上传或发送
    ↓
{
  "files": [A, B],
  "thread_id": "session-1"
}
    ↓
前端循环上传：
  • 文件A：formData.append('is_first_file', 'true')
  • 文件B：formData.append('is_first_file', 'false')
    ↓
后端 POST /upload：
  • 文件A (is_first_file=true)
    → 清空 _thread_files['session-1'] = []
    → 添加 A
  • 文件B (is_first_file=false)
    → 直接追加 B
    ↓
_thread_files['session-1'] = [A, B] ✅
```

### 后续上传

```
用户选择文件 C, D
    ↓
前端循环上传：
  • 文件C：formData.append('is_first_file', 'true')
  • 文件D：formData.append('is_first_file', 'false')
    ↓
后端 POST /upload：
  • 文件C (is_first_file=true)
    → 清空 _thread_files['session-1'] = []
    → 添加 C
  • 文件D (is_first_file=false)
    → 直接追加 D
    ↓
_thread_files['session-1'] = [C, D] ✅
（A, B 已被清除）
```

---

## 📝 修改文件列表

| 文件 | 修改 | 行号 |
|------|------|------|
| [server.py](finance-agents/data-agent/app/server.py) | 添加 `is_first_file` 参数 & 清空逻辑 | 98-141 |
| [ChatArea.tsx](finance-web/src/components/ChatArea.tsx) | 循环遍历时添加 `is_first_file` 标记 | 72-77 |

---

## ✅ 验证清单

- [x] 后端添加参数处理
- [x] 前端添加参数发送
- [x] 清空逻辑实现
- [x] 日志添加
- [ ] 服务重启
- [ ] 功能测试
- [ ] 多会话隔离验证

---

## 🎯 总结

通过在第一个文件上传时清空历史记录，确保：
1. ✅ **每批上传独立**：新批上传前清空历史
2. ✅ **数据不重复**：规则只包含本批文件
3. ✅ **无心智负担**：用户无需手动清理会话
4. ✅ **后续批次自动隔离**：自动化处理

---

## 🐛 常见问题

### Q: 如果用户在同一批中上传文件时网络中断？
**A**: 已上传的文件保留，重新上传即可（新的 `is_first_file=true` 会清空再重新添加）

### Q: 不同会话（thread_id）的文件会混淆吗？
**A**: 不会，每个 thread_id 有独立的文件列表，清空只影响当前 thread

### Q: 如何在不重启服务的情况下清空某会话的文件？
**A**: 可以添加 `GET /clear_files?thread_id=xxx` 端点（可选增强）

---

**修复完成日期**：2026-02-14  
**优先级**：高  
**测试状态**：待验证  
**受影响范围**：所有规则创建和对账任务

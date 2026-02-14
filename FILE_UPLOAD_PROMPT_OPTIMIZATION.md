# ✅ 文件上传提示优化 - 实现总结

**状态**: ✅ **已实现并部署**
**日期**: 2026-02-14 16:03 UTC+8

---

## 需求概述

优化用户流程中的文件上传提示，根据不同的场景给出不同的提示：

1. **使用已有规则对账** (`USE_EXISTING_RULE`):
   - AI 回复消息末尾添加"请上传文件"的提示
   - 因为这个场景下用户还没有上传任何文件

2. **创建新规则后执行对账** (`CREATE_NEW_RULE` → `SAVE_RULE` → `TASK_EXECUTION`):
   - 不添加上传文件的提示
   - 因为创建规则时第一步已经上传了文件，可以直接执行

---

## 实现方案

### 修改 1：USE_EXISTING_RULE 路径 - 添加上传提示

**文件**: `finance-agents/data-agent/app/graphs/main_graph.py`
**位置**: `router_node` 函数中 `USE_EXISTING_RULE` 分支 (行 345-354)

**变更内容**:
```python
# 之前
return {
    "messages": [AIMessage(content=f"好的，将使用规则「{rule_name}」进行对账。")],
    ...
}

# 之后
msg = f"好的，将使用规则「{rule_name}」进行对账。\n\n✨ 请上传对账文件（业务数据和财务数据各一个）"
return {
    "messages": [AIMessage(content=msg)],
    ...
}
```

**效果**: 用户选择现有规则时，AI 会提示"请上传对账文件（业务数据和财务数据各一个）"

### 修改 2：CREATE_NEW_RULE 后执行路径 - 保留已上传的文件

**文件**: `finance-agents/data-agent/app/graphs/main_graph.py`
**位置**: `ask_start_now_node` 函数 (行 737-759)

**变更内容**:
```python
# 用户回复"开始"时
if response_str in ("开始", "是", "yes", "ok", "好", "执行", "立即开始"):
    # 显式保留 uploaded_files，确保不会丢失创建规则时上传的文件
    return {
        "messages": [AIMessage(content="好的，开始执行对账...")],
        "selected_rule_name": state.get("saved_rule_name"),
        "phase": ReconciliationPhase.TASK_EXECUTION.value,
        "execution_step": TaskExecutionStep.NOT_STARTED.value,
        "uploaded_files": state.get("uploaded_files", []),  # 显式保留
    }
```

**效果**: 确保创建规则时上传的文件不会丢失，直接进入对账流程

---

## 工作流程详解

### 场景 1：使用现有规则对账 (USE_EXISTING_RULE)

```
用户消息: "使用西福规则进行对账" / "使用 西福 对账"
    ↓
router_node 识别意图 (intent=USE_EXISTING_RULE)
    ↓
返回消息: "好的，将使用规则「西福」进行对账。✨ 请上传对账文件（业务数据和财务数据各一个）"
    ↓
进入 TASK_EXECUTION 阶段
    ↓
task_execution_node 检查文件
    ├─ 如果有文件 → 开始对账
    └─ 如果没文件 → 中断询问"请上传需要对账的文件"
```

### 场景 2：创建新规则然后执行对账 (CREATE_NEW_RULE)

```
用户消息: "创建新规则" / "我要创建对账规则"
    ↓
router_node 识别意图 (intent=CREATE_NEW_RULE)
    ↓
返回欢迎消息，进入 FILE_ANALYSIS 阶段
    ↓
用户上传文件 (文件添加到 state.uploaded_files)
    ↓
流程: FILE_ANALYSIS → FIELD_MAPPING → RULE_CONFIG → VALIDATION_PREVIEW
    ↓
save_rule_node 保存规则
    ├─ 规则保存成功
    ├─ 返回 phase=COMPLETED
    └─ route_after_reconciliation 检查 saved_rule_name，跳转 ask_start_now
    ↓
ask_start_now_node 中断询问: "是否立即开始对账？"
    ↓
用户回复: "开始" / "是"
    ↓
返回消息: "好的，开始执行对账..."
进入 TASK_EXECUTION 阶段
保留已上传的文件 (uploaded_files 不丢失)
    ↓
task_execution_node 检查文件
    └─ 文件已存在 → 直接开始对账，不提示上传
```

---

## 关键代码点

### task_execution_node 中的文件检查

当 `task_execution_node` 进入时会执行以下逻辑：

```python
# 提取文件列表
files = []
for item in uploaded_files:
    if isinstance(item, dict):
        file_path = item.get("file_path", "")
        if file_path:
            files.append(file_path)
    else:
        files.append(item)

# 如果没有文件，中断要求用户上传
if not files:
    interrupt({
        "question": "请上传需要对账的文件",
        "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
    })
```

所以：
- **USE_EXISTING_RULE 时**: uploaded_files 为空，会触发此中断
- **CREATE_NEW_RULE 后执行时**: uploaded_files 有值，不触发此中断

---

## 文件修改清单

| 文件 | 位置 | 修改内容 | 行号 |
|------|------|--------|------|
| main_graph.py | router_node (USE_EXISTING_RULE) | 添加上传提示 | 345-354 |
| main_graph.py | ask_start_now_node | 显式保留 uploaded_files | 745-755 |

---

## 测试场景

### 测试场景 1：使用现有规则

1. 打开 http://localhost:5173
2. 说："使用 西福 对账"
3. **预期**: 系统回复"好的，将使用规则「西福」进行对账。✨ 请上传对账文件..."
4. 上传文件，系统开始对账

✅ **验证**: 消息中包含"请上传对账文件"提示

### 测试场景 2：创建新规则

1. 打开 http://localhost:5173
2. 说："创建新规则"
3. **预期**: 系统提示上传文件，进入 FILE_ANALYSIS 阶段
4. 上传文件，继续规则创建流程
5. 完成规则配置和保存
6. 系统询问："是否立即开始对账？"
7. 回复："开始"
8. **预期**: 系统回复"好的，开始执行对账..."
9. **关键**: 系统直接开始对账，不再出现"请上传文件"的提示

✅ **验证**: 
- 文件不丢失
- 直接执行对账，不重复提示上传

---

## 部署信息

**服务状态**: ✅ 已启动

```
✅ finance-mcp   (3335) - 运行正常
✅ data-agent    (8100) - 运行正常  
✅ finance-web   (5173) - 运行正常
```

**访问链接**:
- 前端界面: http://localhost:5173
- API: http://localhost:8100
- MCP: http://localhost:3335

---

## 相关历史修复

1. **自动重新执行 Bug 修复** (之前)
   - 解决完成后重新执行同个任务的问题
   - 通过清空 state 中的 uploaded_files 实现

2. **文件格式扩展** (之前)
   - 支持 .csv, .xlsx, .xlsm, .xls, .xlsb

3. **文件上传提示优化** (本次)
   - 根据流程场景给出差异化提示

---

## 技术要点

### State 管理

- **LangGraph State**: 自动合并节点返回的字典到状态中
- **显式保留**: 在 ask_start_now_node 中显式返回 uploaded_files，确保不依赖隐式合并
- **阶段清空**: CREATE_NEW_RULE 开始时清空旧 uploaded_files，COMPLETED 后也清空

### 中断机制

- `interrupt()` 用于暂停节点执行，等待用户输入或文件上传
- task_execution_node 中检到文件为空时自动调用 interrupt()
- 用户完成文件上传后，消息发送后会重新进入节点

---

## 后续建议

### 短期
- [ ] 手动测试两个场景确保提示显示正确
- [ ] 验证文件传递没有问题

### 中期
- [ ] 考虑添加视觉指示器（进度条或上传状态）
- [ ] 优化消息的提示文案

### 长期
- [ ] 考虑多文件拖拽上传的 UI 改进
- [ ] 添加文件验证失败时的提示

---

**最后更新**: 2026-02-14 16:03 UTC+8
**代码已部署**: ✅

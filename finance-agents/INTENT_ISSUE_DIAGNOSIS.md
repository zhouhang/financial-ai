# 意图识别问题排查报告

## 现象

对账完成后，用户说「我的规则列表」/「我想看看我的规则列表」时：
1. **第一次**：系统回复「请上传对账文件」，误触发对账流程
2. **第二次**：系统直接重新执行了上一次对账任务，展示对账结果

## 根因分析

### 1. 意图识别错误（主要原因）

**流程**：
- Router 的 SYSTEM_PROMPT 原先只有：`use_existing_rule`、`create_new_rule`、`delete_rule`
- **没有**「查看规则列表」的意图
- 用户说「我的规则列表」时，LLM 容易误判为 `use_existing_rule`，并从上下文提取最近使用的规则名（如「腾讯异业」）

**结果**：Router 返回 `phase=TASK_EXECUTION`，展示「请上传对账文件」

### 2. Resume 时未识别用户意图切换（次要原因）

**流程**：
- 第一次误判后，进入 `task_execution`，因无文件触发 `interrupt` 等待上传
- 用户可能误以为需要上传才能看列表，上传了文件
- 用户再次说「我想看看我的规则列表」时，前端发送 `resume=true`
- **Resume 直接恢复 task_execution**，不会重新走 Router
- 若 state 中有 `uploaded_files`（用户刚上传或残留），task_execution 会直接执行对账

**结果**：对账任务被重新执行，展示对账概况和差异分析

### 3. 其他可能因素

- **Server 层**：`phase=COMPLETED` 时会清空 `_thread_files`，逻辑正确
- **State 合并**：resume 时若 `file_infos` 非空会合并到 state，可能带入文件

## 结论

**意图识别是主要原因**：缺少 `list_rules` 意图，导致「规则列表」被误判为「使用规则对账」。

**Resume 未处理意图切换是次要原因**：在 task_execution 的 interrupt 中 resume 时，若用户说「规则列表」等，应识别为取消/切换意图，而不是继续等待文件或执行任务。

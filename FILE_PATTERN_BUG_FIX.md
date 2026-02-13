# file_pattern Bug 修复指南

## 问题描述

在创建对账规则的最后一步（保存规则），保存的 JSON 文件中的 `file_pattern` 总是没有时间戳通配符的文件，例如：
- ❌ 错误：`file_pattern: ["sales_data.csv"]`
- ✅ 正确：`file_pattern: ["sales_data_*.csv"]`

这导致后续调用 `reconciliation_start` 时，传入带有时间戳的文件（如 `sales_data_134019.csv`）无法匹配到规则，从而任务执行结果都是 0 条记录。

---

## 根本原因分析

### 数据流线索：
```
用户上传文件 (sales_data.csv)
    ↓
finance-mcp 的 file_upload 工具添加时间戳
    ↓ (返回: /uploads/2026/2/13/sales_data_134019.csv)
    ↓
data-agent 调用 MCP analyze_files 工具
    ↓ (返回: filename=sales_data_134019.csv, original_filename=sales_data.csv)
    ↓
validation_preview_node 生成 file_pattern
    ↓ ⚠️ 问题可能出现在这里
    ↓
save_rule_node 保存规则
```

### 问题根源：

1. **主要问题**：在 `validation_preview_node` 中，生成 `file_pattern` 的正则表达式可能无法正确识别时间戳：
   - 如果 `filename` 字段返回的是 `sales_data.csv`（不带时间戳）
   - 正则表达式 `_(\d{6})(\.\w+)$` 无法匹配
   - 代码最终生成 `*sales_data.csv*` 而不是 `sales_data_*.csv`

2. **次要问题**：
   - `analyze_files` 返回的 `filename` 可能有问题（应该始终是系统保存的文件名，带时间戳）
   - 中断/恢复过程中，state 中的 `file_analyses` 数据可能不完整

---

## 修复方案

### 修复 1：增强 validation_preview_node 的文件名检查（已实现）

**文件**：`finance-agents/data-agent/app/graphs/reconciliation.py` (第 852-912 行)

**改进内容**：
1. ✅ 检查 `filename` 是否和 `original_filename` 相同（表示有问题）
2. ✅ 如果 `filename` 不包含时间戳后缀，从 `file_path` 中提取系统文件名
3. ✅ 添加详细的日志，记录诊断信息

**样例日志**：
```
✅ validation_preview_node - 处理文件: filename=sales_data_134019.csv, ...
✅ validation_preview_node - 生成的 file_pattern: sales_data_*.csv (是否包含通配符: True, ...)
```

### 修复 2：在 save_rule_node 中验证 file_pattern（已实现）

**文件**：`finance-agents/data-agent/app/graphs/reconciliation.py` (第 1070-1110 行)

**改进内容**：
1. ✅ 保存前检查 `file_pattern` 是否包含通配符
2. ✅ 如果不包含，发出错误日志和用户警告
3. ✅ 防止保存无效的规则

**样例日志**：
```
❌ save_rule_node - 严重问题：business 的 file_pattern 不包含通配符，这会导致无法匹配带时间戳的文件！patterns=['sales_data.csv']
```

### 修复 3：诊断工具（新增）

**文件**：`diagnose_file_pattern.py`

**用法**：
```bash
python diagnose_file_pattern.py "直销对账"
python diagnose_file_pattern.py "nanjing_feihan"
```

**功能**：
- 读取已保存的规则 Schema
- 检查 `file_pattern` 是否包含通配符
- 测试文件匹配逻辑
- 提供诊断结果和修复建议

---

## 如何验证修复

### 步骤 1：检查日志

在创建规则时，观察日志中的以下关键信息：

```bash
# 1. 文件分析阶段
logger.info("analyze_files - 返回数据: filename=sales_data_134019.csv, original_filename=sales_data.csv")

# 2. 规则生成阶段
logger.info("validation_preview_node - 生成的 file_pattern: sales_data_*.csv (是否包含通配符: True)")

# 3. 规则保存阶段
logger.info("save_rule_node - ✅ business 的 file_pattern 有效：['sales_data_*.csv']")
```

### 步骤 2：使用诊断工具

保存规则后，运行诊断工具：
```bash
cd /Users/kevin/workspace/financial-ai
python diagnose_file_pattern.py "你的规则名称"
```

预期输出：
```
✅ 业务数据源 (business):
   file_pattern: ['sales_data_*.csv']
   ✅ 正常：包含通配符

✅ 规则配置正常，可以用于对账
```

### 步骤 3：测试对账

创建规则后，使用包含时间戳的文件进行对账：
```python
result = await call_mcp_tool("reconciliation_start", {
    "reconciliation_type": "你的规则名称",
    "files": ["/uploads/2026/2/13/sales_data_134019.csv", "/uploads/2026/2/13/finance_134019.csv"]
})
```

预期结果：
- ✅ 文件匹配成功
- ✅ 记录数大于 0（不再是全 0）

---

## 常见问题排查

### Q1：运行诊断工具发现 file_pattern 仍然不包含通配符

**原因**：使用的是旧规则（修复前创建的）

**解决**：
1. 删除旧规则
2. 重新创建新规则
3. 确保按照规则创建流程完整操作（不要跳过步骤）

### Q2：规则创建时，第3步（配置参数）或第4步（验证预览）显示警告

**原因**：文件上传可能有问题，或 `analyze_files` 返回的数据不完整

**解决**：
```bash
# 1. 检查文件上传是否成功
ls -la /Users/kevin/workspace/financial-ai/finance-mcp/uploads/

# 2. 查看完整的应用日志
tail -f /Users/kevin/workspace/financial-ai/logs/*.log
```

### Q3：对账执行时仍然显示 0 条匹配记录

**原因**：
1. 规则太旧（修复前创建）
2. 文件名模式与规则不匹配
3. 文件编码问题

**解决**：
```bash
# 1. 运行诊断
python diagnose_file_pattern.py "你的规则名称"

# 2. 检查实际文件名
ls -la /Users/kevin/workspace/financial-ai/finance-mcp/uploads/*/*/*/

# 3. 确认文件是否带时间戳
# 预期：sales_data_134019.csv （包含 _HHMMSS 后缀）
```

---

## 修改清单

### 已修改文件

1. **finance-agents/data-agent/app/graphs/reconciliation.py**
   - `validation_preview_node()` 函数（第 852-912 行）
     - 增强文件名检查逻辑
     - 添加详细的诊断日志
   - `save_rule_node()` 函数（第 1070-1110 行）
     - 添加 file_pattern 验证
     - 添加用户警告机制

2. **新增文件**：`diagnose_file_pattern.py`
   - 规则诊断工具

---

## 验证时间轴

| 步骤 | 时间 | 验证内容 |
|------|------|---------|
| 修复部署 | 2026-02-13 | 代码修改完成 |
| 单条规则测试 | - | 创建一个新规则，检查 file_pattern |
| 诊断工具测试 | - | 运行 diagnose_file_pattern.py |
| 完整流程测试 | - | 创建规则 → 执行对账 → 验证结果 |

---

## 相关文件

- 💾 **规则保存**：`finance-mcp/auth/tools.py` (_handle_save_rule)
- 📋 **规则加载**：`finance-mcp/reconciliation/mcp_server/schema_loader.py`
- 🔍 **文件匹配**：`finance-mcp/reconciliation/mcp_server/file_matcher.py` (_match_pattern)
- 📤 **文件上传**：`finance-mcp/reconciliation/mcp_server/tools.py` (_file_upload)
- 🔬 **文件分析**：`finance-mcp/reconciliation/mcp_server/tools.py` (_analyze_files)

---

## 后续改进建议

1. **添加自动重试机制**：如果 file_pattern 无效，自动纠正
2. **增强验证**：在规则保存时，使用样本文件进行匹配测试
3. **改进日志**：添加日志级别控制，方便调试
4. **文档更新**：在创建规则的教程中强调时间戳的重要性

---

## 测试方案

### 最小化测试

```bash
# 1. 创建规则
# 2. 查看日志中的 file_pattern 是否包含通配符
# 3. 运行诊断工具验证
python diagnose_file_pattern.py "new_rule"
```

### 完整测试

```bash
# 1. 创建新规则
# 2. 上传测试文件（自动添加时间戳）
# 3. 执行对账任务
# 4. 验证结果（应该有记录数，不是 0）
```

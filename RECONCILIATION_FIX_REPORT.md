# 对账结果为0的原因排查与修复报告

## 问题描述

用户使用南京飞翰对账规则上传两个 CSV 文件进行对账，但对账结果显示所有记录都是0（无对账差异）。经过排查，实际问题是**文件未被规则正确匹配**，导致对账引擎没有加载到任何数据。

## 根本原因

### 问题1：file_pattern 不支持所有Excel格式和CSV

**现象**：规则中的 `file_pattern` 只包含 `.xlsx` 格式，不包含 `.xls`, `.xlsm`, `.xlsb`, `.csv` 等其他支持格式。

**根本原因**：在 `save_rule_node` 中保存规则时，没有调用 `_expand_file_patterns()` 函数来扩展 `file_pattern` 为所有支持的格式。

**代码位置**：
- [finance-agents/data-agent/app/graphs/reconciliation.py](finance-agents/data-agent/app/graphs/reconciliation.py#L1133)
- 函数 `save_rule_node` 中，直接保存了 `schema_with_desc` 而没有先扩展 `file_pattern`

### 问题2：file_pattern 模式无法匹配原始文件名

**现象**：生成的 `file_pattern` 是 `1767597466118_*.csv` 等形式，但实际上传的文件是 `1767597466118.csv`（没有时间戳后缀）。两者无法匹配。

**根本原因**：规则生成逻辑在处理不包含时间戳的文件名时，生成了 `*filename_*.ext` 这样的超级通配符模式，但这个模式无法匹配原始的 `filename.ext`。

**代码位置**：
- [finance-agents/data-agent/app/graphs/reconciliation.py](finance-agents/data-agent/app/graphs/reconciliation.py#L930-L945) `validation_preview_node` 中的模式生成逻辑

## 修复方案

### 修复1：保存规则时扩展 file_pattern

**修改位置**：`save_rule_node` 函数

**修改内容**：
```python
# 在保存前扩展 file_pattern 为所有支持的格式
biz_patterns_orig = schema_with_desc.get("data_sources", {}).get("business", {}).get("file_pattern", [])
fin_patterns_orig = schema_with_desc.get("data_sources", {}).get("finance", {}).get("file_pattern", [])

# 扩展 file_pattern 为所有支持的格式（.xlsx/.xls/.xlsm/.xlsb/.csv）
biz_patterns_expanded = []
for pattern in biz_patterns_orig:
    biz_patterns_expanded.extend(_expand_file_patterns(pattern))

fin_patterns_expanded = []
for pattern in fin_patterns_orig:
    fin_patterns_expanded.extend(_expand_file_patterns(pattern))

# 去重并更新 schema
biz_patterns = list(set(biz_patterns_expanded))
fin_patterns = list(set(fin_patterns_expanded))

# 更新 schema 中的 file_pattern
schema_with_desc["data_sources"]["business"]["file_pattern"] = biz_patterns
schema_with_desc["data_sources"]["finance"]["file_pattern"] = fin_patterns
```

### 修复2：生成模式时同时包含原始文件名和时间戳版本

**修改位置**：`validation_preview_node` 函数中的模式生成逻辑

**修改内容**：
```python
# 如果文件名不包含时间戳，生成两个模式：
# 1. 原始文件名（用于匹配上传的文件）
# 2. 带时间戳的通配符版本（用于匹配存储时加上时间戳的文件）
if pattern == filename_with_timestamp:
    # 修复：同时生成原始文件名和带时间戳的文件名模式
    name_parts = filename_with_timestamp.rsplit('.', 1)
    if len(name_parts) == 2:
        patterns_to_add = [
            filename_with_timestamp,  # 原始文件名，例如 1767597466118.csv
            f"{name_parts[0]}_*.{name_parts[1]}"  # 带时间戳的通配符，例如 1767597466118_*.csv
        ]
    else:
        patterns_to_add = [filename_with_timestamp]
else:
    patterns_to_add = [pattern]

# Excel/CSV 格式扩展为所有支持类型
expanded_patterns = []
for p in patterns_to_add:
    expanded_patterns.extend(_expand_file_patterns(p))
```

## 修复后的效果

### 修复前
```
规则: 南京飞翰
file_pattern (business): ['1767597466118_*.xlsx']
file_pattern (finance):  ['ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsx']

文件匹配结果:
❌ 1767597466118.csv -> 不匹配
❌ ads_finance_d_inc_channel_details_20260105152012277_0.csv -> 不匹配
```

### 修复后
```
规则: 南京飞翰
file_pattern (business): ['1767597466118.csv', '1767597466118.xlsx', '1767597466118_*.csv', '1767597466118_*.xlsx', ...]
file_pattern (finance):  ['ads_finance_d_inc_channel_details_20260105152012277_0.csv', 'ads_finance_d_inc_channel_details_20260105152012277_0.xlsx', 'ads_finance_d_inc_channel_details_20260105152012277_0_*.csv', 'ads_finance_d_inc_channel_details_20260105152012277_0_*.xlsx', ...]

文件匹配结果:
✅ 1767597466118.csv -> 匹配模式: 1767597466118.csv
✅ ads_finance_d_inc_channel_details_20260105152012277_0.csv -> 匹配模式: ads_finance_d_inc_channel_details_20260105152012277_0.csv
```

## 受影响的文件

1. **[reconciliation.py](finance-agents/data-agent/app/graphs/reconciliation.py)**
   - `_expand_file_patterns()` 函数（第34行）
   - `validation_preview_node()` 函数（第914-948行）
   - `save_rule_node()` 函数（第1133-1165行）

## 验证步骤

1. ✅ **规则配置验证**：
   ```
   规则已包含所有支持格式！
   business: .csv 格式✓, .xlsx 格式✓
   finance: .csv 格式✓, .xlsx 格式✓
   ```

2. ✅ **文件匹配验证**：
   ```
   业务文件 (CSV): 1767597466118.csv -> 匹配
   业务文件 (XLSX): 1767597466118.xlsx -> 匹配
   财务文件 (CSV): ads_finance_d_inc_channel_details_20260105152012277_0.csv -> 匹配
   财务文件 (XLSX): ads_finance_d_inc_channel_details_20260105152012277_0.xlsx -> 匹配
   ```

3. ✅ **服务启动验证**：
   ```
   finance-mcp   (3335) - 运行正常
   data-agent    (8100) - 运行正常
   finance-web   (5173) - 运行正常
   ```

## 后续建议

1. **建立规则模式验证**：在保存规则时自动验证 `file_pattern` 是否包含所有支持的格式
2. **优化文件上传**：在文件上传时自动添加时间戳后缀，确保不同时间上传的同名文件有区别
3. **添加调试日志**：在对账时记录文件匹配的详细过程，便于后续排查

## 相关代码变更

### 详细代码变更

#### 1. save_rule_node 函数 (第1133-1165行)

**修改前**：
```python
# 更新 schema 的 description 为用户输入的中文名
schema_with_desc = schema.copy()
schema_with_desc["description"] = rule_name_cn

# ⚠️ 关键验证：检查 file_pattern 是否包含通配符
biz_patterns = schema_with_desc.get("data_sources", {}).get("business", {}).get("file_pattern", [])
fin_patterns = schema_with_desc.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
```

**修改后**：
```python
# 更新 schema 的 description 为用户输入的中文名
schema_with_desc = schema.copy()
schema_with_desc["description"] = rule_name_cn

# ✅ 在保存前扩展 file_pattern 为所有支持的格式
biz_patterns_orig = schema_with_desc.get("data_sources", {}).get("business", {}).get("file_pattern", [])
fin_patterns_orig = schema_with_desc.get("data_sources", {}).get("finance", {}).get("file_pattern", [])

# ... 扩展逻辑 ...

biz_patterns = list(set(biz_patterns_expanded))
fin_patterns = list(set(fin_patterns_expanded))

# 更新 schema 中的 file_pattern
schema_with_desc["data_sources"]["business"]["file_pattern"] = biz_patterns
schema_with_desc["data_sources"]["finance"]["file_pattern"] = fin_patterns
```

#### 2. validation_preview_node 函数 (第930-948行)

**修改前**：
```python
# 如果文件名不包含时间戳
if pattern == filename_with_timestamp:
    logger.error(f"validation_preview_node - ❌ 警告：无法从 filename={filename_with_timestamp} 生成时间戳通配符...")
    # 生成过度通配符的模式
    if re.match(r'^\d+\.\w+$', filename_with_timestamp):
        # 纯数字文件名，生成模式：*数字_*.ext（错误！无法匹配原始文件）
        name_parts = filename_with_timestamp.rsplit('.', 1)
        if len(name_parts) == 2:
            pattern = f"*{name_parts[0]}_*.{name_parts[1]}"
```

**修改后**：
```python
# 如果文件名不包含时间戳
if pattern == filename_with_timestamp:
    logger.error(f"validation_preview_node - ❌ 警告：无法从 filename={filename_with_timestamp} 生成时间戳通配符...")
    # 修复：同时生成原始文件名和带时间戳的文件名模式
    name_parts = filename_with_timestamp.rsplit('.', 1)
    if len(name_parts) == 2:
        patterns_to_add = [
            filename_with_timestamp,  # 原始文件名，例如 1767597466118.csv
            f"{name_parts[0]}_*.{name_parts[1]}"  # 带时间戳的通配符，例如 1767597466118_*.csv
        ]
```

## 修复验证日期

- **修复日期**：2026年2月14日
- **验证状态**：✅ 所有检查通过
- **测试文件**：
  - /Users/kevin/Desktop/工作/测试数据/资产对账测试数据/南京飞翰/1767597466118.csv
  - /Users/kevin/Desktop/工作/测试数据/资产对账测试数据/南京飞翰/ads_finance_d_inc_channel_details_20260105152012277_0.csv

# Format Specifier Bug 修复

## 问题描述

错误信息：
```
处理失败: Invalid format specifier '"sum", "date": "first"' for object of type 'str'
```

## 根本原因

在 `finance-agents/data-agent/app/graphs/main_graph.py` 中使用了 `.format()` 方法处理包含 JSON 数据的字符串。当 JSON 内容包含花括号（如 `{"amount": "sum", "date": "first"}`）时，Python 的 `.format()` 方法会尝试将这些花括号解析为格式化占位符，导致 "Invalid format specifier" 错误。

## 修复内容

### 文件：`finance-agents/data-agent/app/graphs/main_graph.py`

#### 1. 第 309 行（router_node 函数）

**修复前：**
```python
system_msg = SYSTEM_PROMPT.format(username=username, available_rules=rules_text)
```

**修复后：**
```python
# 使用 replace 替代 format，避免规则名称/描述中的 {} 被误解析
system_msg = SYSTEM_PROMPT.replace("{username}", username).replace("{available_rules}", rules_text)
```

**原因：** 虽然这个位置不太可能出错，但如果规则名称或描述中包含花括号，也会触发相同问题。使用 `.replace()` 更安全。

#### 2. 第 745 行（result_analysis_node 函数）⚠️ 主要问题

**修复前：**
```python
prompt = RESULT_ANALYSIS_PROMPT.format(result_json=result_json)
```

**修复后：**
```python
# 使用 replace 替代 format，避免 JSON 中的 {} 被误解析为格式化占位符
prompt = RESULT_ANALYSIS_PROMPT.replace("{result_json}", result_json)
```

**原因：** `result_json` 是通过 `json.dumps()` 生成的 JSON 字符串，包含大量花括号（如对账规则中的聚合配置 `{"amount": "sum", "date": "first"}`）。使用 `.format()` 会导致 Python 尝试解析这些花括号，引发错误。

## 解决方案

使用 **`.replace()`** 替代 **`.format()`**：
- `.format()` 会解析字符串中所有的 `{}` 作为占位符
- `.replace()` 只进行简单的字符串替换，不会解析花括号

### 3. 第 884-1012 行（reconciliation.py 中 _parse_rule_config_json_snippet）

**问题：** 用户输入「订单号去掉开头单引号,并截取前21位」时，prompt 中的 `template_json`（来自 direct_sales_schema.json）包含 `{"amount":"sum","date":"first"}` 等聚合配置。若使用 f-string 或 `.format()` 插入，下游某处调用 `.format()` 时会触发 Invalid format specifier。

**修复后：**
```python
# 使用 replace 插入变量，避免 template_json 中的 JSON 花括号被 .format() 误解析
prompt = prompt.replace("<<<TEMPLATE_JSON>>>", template_json, 1)
prompt = prompt.replace("<<<FIELD_MAPPING_DESC>>>", field_mapping_desc, 1)
prompt = prompt.replace("<<<CURRENT_ITEMS_DESC>>>", current_items_desc, 1)
prompt = prompt.replace("<<<USER_INPUT>>>", user_input, 1)
prompt = prompt.replace("<<<JSON_EXAMPLES>>>", json_examples, 1)
```

## 相关文件

类似的安全处理已在其他文件中实现：
- `finance-mcp/reconciliation/mcp_server/reconciliation_engine.py:344`
  - 实现了 `_safe_format_detail()` 方法
  - 使用正则表达式替换，避免 `.format()` 的问题

## 验证

修复后，当对账结果包含 JSON 配置（如聚合规则）时，不再抛出 "Invalid format specifier" 错误。

## 影响范围

- ✅ 修复了对账结果分析失败的问题
- ✅ 修复了可能的规则列表显示问题
- ✅ 提高了系统的健壮性，防止特殊字符导致的崩溃

## 测试建议

1. 创建包含聚合规则的对账配置（如 `{"amount": "sum", "date": "first"}`）
2. 执行对账任务
3. 验证对账结果能正确显示，不会抛出 format specifier 错误

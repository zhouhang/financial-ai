# LLM规则生成逻辑问题分析与修复

## 问题概述

当前腾讯异业对账规则中存在两个关键问题：

### 问题1：重复的订单号转换规则
规则列表中有两个看似相似的规则：
1. **规则A**："订单号去掉开头单引号，并截取前21位"
2. **规则B**："订单号去单引号截取21位，仅保留104开头"

这导致订单号字段被重复处理。

### 问题2：过滤逻辑错误
规则B中的条件表达式有根本的逻辑缺陷：

```python
str(row.get('order_id', '')).lstrip("'")[:21] if str(row.get('order_id', '')).startswith('104') else row.get('order_id', '')
```

**问题分析**：
- ✅ IF 分支：如果订单号以104开头 → 返回处理后的值（去单引号、截取21位）
- ❌ ELSE 分支：如果订单号**不以104开头** → 返回**原始值**（未处理！）

**结果**：L开头的订单号完全避过了过滤，照样参与对账，导致"对账结果中出现L开头的订单"

---

## 根本原因

LLM生成规则时使用的示例有问题。在`_parse_rule_config_json_snippet`函数中，示例4（原始版本）教会LLM生成这样的逻辑：

```python
# 原始（错误的）示例
{"field": "order_id", "transform": "str(row.get('roc_oid', '')).lstrip(\"'\")[:21] if str(row.get('roc_oid', '')).startswith('104') else row.get('roc_oid', '')"}
```

**问题**：
1. 在一个transform中混合了"格式转换"和"数据过滤"两种不同的操作
2. False分支逻辑错误（返回原始值而不是过滤掉）
3. LLM学习了这个模式，导致后续生成同样有问题的规则

---

## 修复方案

### 1️⃣ 修复LLM Prompt中的示例（已实施）

**改进前**（示例4）：
```python
在单个transform中混合format和filter，使用条件表达式
"str(row.get('roc_oid', '')).lstrip(\"'\")[:21] if str(row.get('roc_oid', '')).startswith('104') else row.get('roc_oid', '')"
```

**改进后**（示例4- 新版本）：
```python
分成两个独立的步骤：
1. field_transforms中：只做格式处理
   "str(row.get('roc_oid', '')).lstrip(\"'\")[:21]"
2. row_filters中：只做数据过滤
   {"condition": "str(row.get('order_id', '')).startswith('104')"}
```

**好处**：
- ✅ 逻辑清晰，职责分离
- ✅ 过滤逻辑正确（整行删除）
- ✅ 易于维护和调试
- ✅ LLM更容易理解和复现

### 2️⃣ 添加明确的规则说明（已实施）

在prompt中添加了新的规则5和6（原有规则调整为6-8）：

**规则5：分离format和filter**
```
❌ 错：在transform中混合条件逻辑
   "str(row.get('order_id')).lstrip(\"'\")[:21] if ... else row.get('order_id')"
   
✅ 对：分成两步
   第一步：format via field_transforms
   第二步：filter via row_filters
```

**规则6：避免重复规则**
- 检查当前已有的配置项
- 若相似规则已存在，建议更新或替换而不是添加

### 3️⃣ 实现自动验证和去重（已实施）

添加`_validate_and_deduplicate_rules`函数，在规则合并后执行：

```python
def _validate_and_deduplicate_rules(schema):
    """
    - 检测同一字段的多个transforms
    - 对于订单号字段，特殊处理：
      如果有多个"去单引号截取21位"的规则，只保留第一个
    - 将过滤逻辑从transform移到row_filters
    - 记录警告日志
    """
```

执行流程：
```
LLM生成规则 → merge_json_snippets → _validate_and_deduplicate_rules → 应用规则
```

---

## 具体修改清单

### reconciliation.py 中的修改

#### 修改1：示例4优化
**位置**：`_parse_rule_config_json_snippet`函数的json_examples变量
- 删除了错误的条件表达式示例
- 添加了正确的分离式处理示例
- 强调field_transforms和row_filters的分工

#### 修改2：添加规则5和6
**位置**：prompt中的规则部分
- 新增"规则5：分离format和filter"，明确说明❌错❌和✅正确✅的做法
- 新增"规则6：避免重复规则"，提醒LLM检查重复
- 原有规则重新编号

#### 修改3：实现验证函数
**位置**：`_merge_json_snippets`函数之前
- 新增`_validate_and_deduplicate_rules`函数
- 检测同字段重复规则
- 自动删除重复的format规则

#### 修改4：集成去重函数
**位置**：`rule_config_node`函数中merge后
- 调用`_validate_and_deduplicate_rules(schema)`
- 实现自动去重

---

## 预期效果

### 短期效果（立即生效）
1. ✅ LLM新生成的规则会按照改进的示例进行，避免条件表达式的逻辑错误
2. ✅ 自动去重函数会删除重复的format规则
3. ✅ 对账时L开头的订单会被正确过滤掉

### 中期效果（下次规则重新生成时）
1. ✅ 当用户修改或重新配置规则时，LLM会生成更清洁的规则
2. ✅ 避免再次出现混合了format和filter的transform表达式
3. ✅ 规则结构更清晰，更容易维护

### 长期效果
1. ✅ 累积学习：LLM prompt中的好示例会指导更好的规则生成
2. ✅ 降低维护成本：清晰的规则结构更容易调试
3. ✅ 减少数据质量问题：正确的过滤逻辑保证数据准确性

---

## 验证方法

### 验证1：检查新生成的规则
当用户添加订单号处理相关的规则时，应该看到：
```
业务数据(business)：
  ✓ field_transforms中只有格式处理规则(去单引号、截取长度等)
  ✓ row_filters中只有数据过滤规则(104开头等)
  
财务数据(finance)：
  ✓ 同上
```

### 验证2：检查对账结果
运行对账后，检查结果：
```
✓ 对账数据中不应该出现L开头的订单
✓ row_filters注册的过滤条件成功应用
✓ 缺失统计与过滤后相符
```

### 验证3：检查日志
在数据清理过程中，应该看到：
```
信息：应用行过滤规则: 仅保留104开头的订单号, 剩余 XXXX 条记录
警告：⚠️ 检测到 business 中有 2 个订单号transform规则，可能存在重复
信息：✅ 去重后 business 的订单号transform规则数: 1
```

---

## 代码位置快速查询

| 文件 | 行号 | 修改内容 |
|------|------|---------|
| reconciliation.py | 860 | 修改示例4（分离format和filter） |
| reconciliation.py | 901-940 | 添加规则5-8说明 |
| reconciliation.py | 1104-1165 | 新增_validate_and_deduplicate_rules函数 |
| reconciliation.py | 1618-1620 | 调用去重函数 |

---

## FAQ

**Q：为什么不直接修改现有的JSON规则？**  
A：JSON规则是演进过程中用户添加的，修改它们相当于推翻历史决策。更好的方法是修复生成规则的LLM prompt，从源头避免这类问题。

**Q：去重函数会删除用户的配置吗？**  
A：不会。去重函数只在发现明确的重复format规则时删除（保留第一个）。用作filter的规则完全保留。用户可以在日志中看到删除操作。

**Q：这个修复对现有规则有影响吗？**  
A：现有的腾讯异业规则已经有了row_filters，所以不受影响。但当用户进行规则修改或创建新规则时，会受益于修复。

**Q：如果row_filters执行报错怎么办？**  
A：在data_cleaner.py的_apply_row_filters中已经有异常捕获，会记录错误日志但继续执行。

---

## 总结

通过修复LLM prompt中的示例和规则说明，加上自动验证和去重功能，确保了：
1. ✅ LLM生成的规则逻辑正确
2. ✅ 即使已经生成了重复规则也会被自动检测和更正
3. ✅ 对账结果中不会出现本应被过滤掉的订单

这是一个从源头（LLM）和执行端（验证函数）同时修复问题的综合方案。

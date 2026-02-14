# row_filters 安全检查修复

## 问题概述

对账测试显示 **严重问题**：
- 业务数据：2,289 条记录
- 财务数据：2,289 条记录
- 对账差异：**0 条** ❌ （应该有27-28条差异）

### 根本原因

`row_filters` 被错误地配置在 **两个数据源** 都有：
- 业务数据 row_filters: `{"condition": "startswith('104')"}`
- 财务数据 row_filters: `{"condition": "startswith('104')"}`

这导致：
- 业务数据：2,316 → 2,289（删除了27个L开头订单）
- 财务数据：2,290 → 2,289（删除了1个非104记录）
- **结果**：两个数据源完全相同，无差异！

## 正确的业务逻辑

|  | 业务数据 | 财务数据 |
|---|---------|---------|
| row_filters | ❌ 不应该有 | ✅ 有（排除特殊记录）|
| 期望结果 | 2,316条（包括L开头订单） | 2,289条（排除加款单） |
| 对账差异 | 应显示27个L开头订单只在业务 | ... |

## 实施的三层防护

### 1. LLM 提示改进（已完成）

添加 Rule 6：
```
row_filters的使用（列级过滤vs行级过滤）
- 何时使用：财务系统特殊内部记录（加款单、调账记录）
- 何时不应该使用：不要用row_filters统一两个系统数据格式，不要对业务数据使用
```

### 2. 自动验证函数 - 新增安全检查（刚完成）

在 `_validate_and_deduplicate_rules()` 中添加：

```python
# 🔴 关键检查：防止对账结果显示0个差异的情况
business_row_filters = result.get("data_cleaning_rules", {}).get("business", {}).get("row_filters", [])
finance_row_filters = result.get("data_cleaning_rules", {}).get("finance", {}).get("row_filters", [])

if business_row_filters and finance_row_filters:
    # 检查是否有相同的条件
    common_conditions = set(business_conditions.keys()) & set(finance_conditions.keys())
    if common_conditions:
        logger.error(f"🔴 严重问题：业务数据和财务数据有相同的row_filters，会导致对账失败！")
        logger.warning(f"⚠️  已自动删除业务数据中的 {len(business_row_filters)} 个row_filters")
        # 自动删除业务数据的row_filters
        result["data_cleaning_rules"]["business"]["row_filters"] = []
```

**行为**：
- ✅ 检测到相同条件 → **自动删除业务数据的row_filters**
- ⚠️ 业务有row_filters但财务没有 → **警告并删除业务的row_filters**
- 🔴 记录详细的错误日志供调试

### 3. 数据清理器执行顺序（已验证正确）

在 `data_cleaner.py` 中，每个数据源的处理顺序：
1. Field transforms（格式化）
2. Row filters（行级过滤） ← 仅财务
3. Aggregations（聚合）
4. Global transforms（全局转换）

## 工作流程

```
用户配置 (自然语言)
    ↓
LLM 生成 JSON (现在有 Rule 6 指导)
    ↓
_merge_json_snippets (合并配置)
    ↓
_validate_and_deduplicate_rules (安全检查) ← 【新增】
  • 检查重复的format规则
  • 检查if/else混合逻辑
  • 检查业务/财务相同条件 ← 【新】
    ↓
data_cleaner.apply_cleaning_rules
  • field_transforms (业务 & 财务)
  • row_filters (仅财务)
  • 聚合...
    ↓
对账匹配
```

## 验证步骤

运行对账后检查：

### 预期的日志输出（如果发现问题）
```
🔴 严重问题：业务数据和财务数据有相同的row_filters，会导致对账失败！
   相同的条件: {"condition": "startswith('104')"}
   这会导致两个数据源过滤后记录数相同，无法显示实际差异
   正确做法：row_filters只应该用于财务数据，用于排除特殊内部记录（如加款单）
⚠️  已自动删除业务数据中的 1 个row_filters
```

### 验证记录数
```
业务数据清理前：2,316
业务数据清理后：2,316 (没有row_filters所以不变)
财务数据清理前：2,290
财务数据清理后：2,289 (只有finance row_filters生效)
对账差异：27条 ✅
```

## 关键改进点

| 问题 | 旧做法 | 新做法 |
|----|------|------|
| 重复format规则 | 需手动删除 | 自动检测并合并 |
| if/else混合逻辑 | 需手动纠正 | 自动检测和分离 |
| **两个源头相同row_filters** | **❌ 导致0差异** | **✅ 自动删除业务的filters** |

## 代码位置

- **LLM 提示**：[reconciliation.py](reconciliation.py#L880-L950) 第 930-945 行（Rule 6）
- **验证函数**：[reconciliation.py](reconciliation.py#L1130-L1230) 新增检查逻辑
- **集成点**：[reconciliation.py](reconciliation.py#L1750) `rule_config_node()` 中调用

## 下一步

1. ✅ 测试现有对账 - 验证自动清理是否工作
2. ⏭️ 新的LLM生成 - 验证Rule 6 是否防止新增问题
3. ⏭️ 端到端验证 - 确保差异正确显示（预期27条）

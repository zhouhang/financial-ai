# NaN 订单号处理修复

## 问题现象

对账结果中显示：
- **业务缺失（1 条）** - 订单号显示为 `nan（订单号缺失）`

这说明财务数据中有一条记录的订单号为NaN/空值，但没有被正确删除。

## 根本原因分析

### 执行顺序问题

在 `data_cleaner.py` 中的执行顺序：
1. **field_transforms**（字段转换）
2. **row_filters**（行过滤）
3. **aggregations**（聚合）
4. **global_transforms**（全局转换，包括drop_na）

### 原始的问题流程

```
原始订单号: None/NaN
    ↓
field_transforms 中的: str(row.get('order_id', ''))
    ↓
转换后订单号: "nan"（字符串）
    ↓
global_transforms 中的 drop_na(subset=['order_id', 'amount'])
    ↓
❌ 无法删除（因为"nan"是字符串，不是NaN）
```

### 为什么drop_na无法删除它

- `dropna()` 检查的是pandas NaN（np.nan）
- 字符串 `"nan"` 不被识别为NaN
- 所以订单号为"nan"的记录被保留

## 解决方案

### 1. 修复 field_transforms（schema中）

**位置**：`腾讯异业_schema.json` 的 finance 字段转换

**修改前**：
```json
{
  "field": "order_id",
  "transform": "str(row.get('order_id', ''))",
  "description": "订单号转换为字符串"
}
```

**修改后**：
```json
{
  "field": "order_id",
  "transform": "str(row.get('order_id', '')) if pd.notna(row.get('order_id', '')) and str(row.get('order_id', '')).strip() else None",
  "description": "订单号转换为字符串，保留NaN便于后续drop_na删除空值记录"
}
```

**作用**：
- 如果订单号为NaN、None或空字符串 → 保留为None
- 如果有有效值 → 转换为字符串
- 这样drop_na才能正确删除

### 2. 修复 reconciliation_engine.py（双重保险）

**位置**：`_perform_reconciliation()` 方法

**添加过滤机制**：
```python
# 获取所有订单ID后，立即过滤掉"nan"和空值
business_ids.discard("nan")
finance_ids.discard("nan")
business_ids = {oid for oid in business_ids if oid and str(oid).strip()}
finance_ids = {oid for oid in finance_ids if oid and str(oid).strip()}
```

**作用**：
- 即使有其他原因导致订单号为"nan"，也会在对账时过滤
- 这是双重保险机制

## 修复流程图

```
修复前                          修复后
─────────────────             ─────────────────
订单号: None                   订单号: None
  ↓                             ↓
str()转换→"nan"               条件检查→保留None
  ↓                             ↓
drop_na失败 ❌                 drop_na成功 ✅
  ↓                             ↓
对账结果包含nan    →           对账结果干净 ✅
                      
                            + 双重保险：
                            reconciliation_engine
                            过滤掉任何剩余的"nan"
```

## 数据流验证

### 清洗流程
```
原始财务数据: 2,290 条
    ↓ (field_transforms)
转换后: 2,290 条（订单号为None的记录保留为None）
    ↓ (row_filters)
过滤后: 2,290 条（这一步无过滤规则）
    ↓ (global_transforms: drop_na)
删除后: 2,289 条 ✅（删除了订单号为NaN的1条记录）
    ↓ (聚合、其他转换)
最终: 2,289 条
```

### 对账过程
```
业务订单数: 2,316 条（包括27个L-prefix订单）
财务订单数: 2,289 条（已删除nan和非104订单）
    ↓
获取所有订单ID
    ↓
过滤掉"nan"和空值（双重保险）
    ↓
逐条对账: 2,316条不同订单
    ↓
差异检测:
  - 财务缺失: 27条（L-prefix订单在业务但不在财务）
  - 业务缺失: 0条 ✅（之前的1条nan被删除了）
```

## 关键改进点

| 问题 | 原因 | 修复 | 结果 |
|-----|------|------|------|
| 对账中出现"nan"订单号 | field_transform强制转为字符串 | 保留None、让drop_na删除 | ✅ |
| drop_na无法删除"nan" | "nan"是字符串，不是NaN | 保持原始NaN类型 | ✅ |
| 可能有其他原因 | 数据源来自不同地方 | 对账时再次过滤 | ✅ |

## 测试验证

运行对账后检查：

```
预期结果：
- 业务记录数：2,316 ✅
- 财务记录数：2,289 ✅
- 匹配记录数：2,289 ✅
- 差异:
  财务缺失：27条（都是L开头订单） ✅
  业务缺失：0条（不再显示"nan"） ✅
```

## 代码位置

- **Schema修改**：[腾讯异业_schema.json](腾讯异业_schema.json#L140-L145)
- **对账引擎修改**：[reconciliation_engine.py](reconciliation_engine.py#L115-L125)
- **数据清洗验证**：[data_cleaner.py](data_cleaner.py#L155-L160) (drop_na调用)

## 后续建议

1. ✅ 测试对账结果，确保"nan"订单号消失
2. 可考虑在global_transforms中明确配置drop_na的位置
3. 在LLM生成的field_transforms中，添加类似的NaN检查模式

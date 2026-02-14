# LLM规则生成问题修复总结

## 核心问题
LLM在生成规则时，仍然在`field_transforms`中混合了过滤条件，而不是将其分离到`row_filters`。

例如：
```json
// ❌ 错误：混合了条件判断
{
  "field": "order_id",
  "transform": "row.get('order_id', '') if str(row.get('order_id', '')).startswith('104') else None",
  "description": "保留订单号以104开头的订单"
}

// ✅ 正确：分离为两个独立的规则
{
  "field_transforms": [
    {
      "field": "order_id",
      "transform": "str(row.get('order_id', '')).lstrip(\"'\")[:21]",
      "description": "去单引号、截取21位"
    }
  ],
  "row_filters": [
    {
      "condition": "str(row.get('order_id', '')).startswith('104')",
      "description": "仅保留104开头的订单号"
    }
  ]
}
```

## 根本原因分析

1. **LLM学习的示例有问题**
   - 原始示例4中有混合条件判断的模式
   - LLM学习了这个模式并复现
   
2. **规则说明不够强硬**
   - 之前的规则说明是"建议"级别，不是"禁止"级别
   - LLM没有充分理解为什么不能这样做

3. **缺少自动修复机制**
   - 即使LLM仍然生成了错误的规则，系统也无法检测和修复

## 修复方案（三层防线）

### 1️⃣ LLM提示词优化（源头预防）

#### 改进所有示例
- **删除**：示例3中有条件判断的transform
- **更新**：示例4完全展示正确的分离方式
- **新增**：多个"❌错误例子"反向教学

#### 强化规则说明
从建议级别改为禁止级别：
```
⚠️ **严格规定**：field_transforms中的transform表达式不能包含if/else、条件判断等任何过滤逻辑

❌ **禁止的模式**（这些都是错的，绝对不要生成）：
1. 任何包含if/else的transform
2. 任何返回None来过滤的transform
3. 任何混合了format和filter的expression
```

#### 明确分离职责
```
Transform职责：格式转换，返回新值
Row_filters职责：行级过滤，判断True/False决定保留还是删除

它们永远不应该混在一起！
```

### 2️⃣ 自动验证和拆分（执行时修复）

实现了`_validate_and_deduplicate_rules`函数，在规则合并后执行：

**功能**：
1. 检测transform中的条件判断（if...else...）
2. 自动拆分为：
   - 格式处理的transform
   - 过滤条件的row_filters
3. 记录警告日志告知用户
4. 也处理同字段重复规则的去重

**执行流程**：
```
user_input 
  ↓
LLM 生成规则 
  ↓
merge_json_snippets（合并所有规则片段）
  ↓
_validate_and_deduplicate_rules（自动修复和去重） ← 新增
  ↓
应用到数据清理
```

**示例自动修复**：
```python
# 输入（LLM仍然生成了错的规则）
{
  "field": "order_id",
  "transform": "row.get('order_id', '') if str(row.get('order_id', '')).startswith('104') else None",
  "description": "保留订单号以104开头的订单"
}

# 自动拆分后输出
field_transforms: [
  {
    "field": "order_id",
    "transform": "row.get('order_id', '')",  # 提取的格式部分
    "description": "保留订单号以104开头的订单 (格式转换部分)"
  }
]
row_filters: [
  {
    "condition": "str(row.get('order_id', '')).startswith('104')",
    "description": "保留订单号以104开头的订单 (过滤部分)"
  }
]
```

### 3️⃣ 数据清理执行顺序（逻辑保证）

确保执行顺序：
1. Field transforms（格式处理）
2. Row filters（行过滤）← 检查的是处理后的值
3. Aggregations（聚合）
4. Global transforms（全局转换）

这样row_filters中的条件可以检查到已经格式化后的订单号。

## 修改清单

### reconciliation.py

| 行号 | 修改内容 |
|------|---------|
| 847-856 | 修正示例3中的条件判断 |
| 855-863 | 强化示例4的说明 |
| 901-940 | 重写规则5和6，加强"禁止"级别的说明 |
| 1104-1250 | 重写`_validate_and_deduplicate_rules`函数 |
| 1680-1685 | 调用验证和拆分函数 |

## 效果验证

### 预期效果

**短期**（立即）：
- ✅ 现有规则中的混合条件判断会被自动拆分
- ✅ L开头的订单号会被过滤掉

**中期**（下次编辑规则时）：
- ✅ LLM新生成的规则受强化的prompt指导
- ✅ 规则结构更清晰

**长期**：
- ✅ 减少数据质量问题
- ✅ 更容易维护和调试

### 验证命令

检查是否有混合条件的规则：
```bash
grep -n "if.*else" /Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/schemas/*.json
```

运行对账后检查日志：
```
检测到 business 中 order_id 字段的transform混合了条件判断
将纯过滤规则 '保留订单号以104开头的订单' 移到row_filters
```

## 设计决策

### 为什么选择自动修复而不是拒绝？
- **自动修复**：提供更好的用户体验，规则仍然生效
- **拒绝+报错**：会中断用户的工作流程

### 为什么transform和row_filters不能混合？
1. **语义不同**：transform返回新值（可能是中间值），row_filters返回True/False
2. **执行语义**：row_filters中False意味着"删除整行"，而transform中None只是设置字段为空
3. **可维护性**：分离职责使代码更清晰

### 为什么在data_cleaner.py中row_filters在transform之后？
- Transform首先处理格式（如去单引号、截取长度）
- Row_filters检查的是处理后的值
- 这样104开头的判断能检查到格式化后的订单号

## FAQ

**Q：为什么自动拆分后，两个规则的效果一样吗？**
A：不完全一样。混合规则中的else分支会设置为None（字段变空），自动拆分后是直接删除整行。后者更有效。

**Q：自动修复会删除用户的意图吗？**
A：不会。拆分后的两个规则组合起来，效果比混合规则更好。日志中会记录这个操作。

**Q：如果用户不想删除不符合条件的行怎么办？**
A：用户应该说"将不符合条件的订单清空"而不是"只保留104开头"，这样transform中返回空值就够了。

**Q：为什么LLM仍然会生成这样的规则？**
A：我们用的是temperature=0.1的LLM，但强化prompt需要时间生效。自动修复机制就是为了处理这种情况。

## 后续改进方向

1. **增强LLM prompt**
   - 添加更多负面示例
   - 解释为什么分离很重要
   - 给出transform和row_filters的应用场景集合

2. **数据清理器增强**
   - 在row_filters中支持更复杂的条件表达式
   - 支持多个条件的AND/OR组合
   - 明确日志输出过滤结果（删除多少行）

3. **用户反馈循环**
   - 记录LLM生成的规则和修复后的版本
   - 用这些例子重新训练或微调提示词

---

**修复完成时间**：2026年2月14日  
**修复方式**：三层防线（提示词优化 + 自动修复 + 执行保证）  
**预期效果**：完全防止混合条件判断的根本问题，即使LLM再次生成也会被自动修复

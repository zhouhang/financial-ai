## Context

当前对账流程（来自 `add-rule-recommendation/proposal.md`）：
1. 用户上传文件 → 2. LLM 建议字段映射（现有功能）→ 3. 用户确认字段映射 → 4. 配置规则参数 → 5. 预览并保存

现有 `rule-recommendation` change 已完成设计：
- 使用 `field_mapping_hash` (MD5) 索引实现 O(1) 精确匹配
- 工作流插入 `rule_recommendation` 节点
- 支持规则复制功能

本设计在现有基础上扩展：根据文件表头字段名称，查询规则库中字段名匹配的规则。

## Goals / Non-Goals

**Goals:**
- 在字段映射完成后，根据字段名匹配推荐规则
- 支持订单号、金额、订单时间三个关键字段的匹配
- 高性能查询（3秒内返回结果）
- 用户可直接使用推荐规则对账
- 对账完成后 AI 评估规则适用性，提示保存

**Non-Goals:**
- 不修改现有 `field_mapping_hash` 索引逻辑
- 不实现模糊匹配或语义相似度
- 不改造现有 UI 组件

## Decisions

### 1. 规则推荐时机
**决策**: 在 `field_mapping_node` 确认字段映射后，自动触发规则推荐

**理由**:
- 字段映射已完成，知道文件包含哪些字段
- 用户确认后立即推荐，体验流畅

### 2. 字段匹配策略
**决策**: 根据表头字段名与规则中 `field_roles` 的 key 进行匹配

**匹配逻辑**:
```python
def match_rules_by_field_names(file_columns: dict, rules: list) -> list:
    """
    file_columns: {"business": ["订单号", "金额", "日期"], "finance": ["sup订单号", "发生", "日期"]}
    匹配: 订单号→order_id, 金额→amount, 日期/时间→date
    """
    KEY_FIELD_MAP = {
        "order_id": ["订单号", "订单", "order", "order_id", "订单号"],
        "amount": ["金额", "钱", "amount", "发生", "sum", "total"],
        "date": ["日期", "时间", "date", "time", "datetime", "交易时间", "创建时间"],
    }
    
    matched_rules = []
    for rule in rules:
        score = 0
        matched_fields = []
        
        # 检查规则的关键字段
        for role, aliases in KEY_FIELD_MAP.items():
            rule_field = rule.field_roles.get("business", {}).get(role, "")
            # 检查 file_columns 中是否有匹配的字段名
            for col in file_columns.get("business", []):
                if any(alias in col.lower() for alias in [a.lower() for a in aliases]):
                    score += 1
                    matched_fields.append(f"{role}: {col}")
                    break
        
        if score >= 2:  # 至少匹配2个关键字段
            matched_rules.append((rule, score, matched_fields))
    
    return sorted(matched_rules, key=lambda x: x[1], reverse=True)
```

### 3. 查询优化策略
**决策**: 使用预计算的 `field_mapping_hash` 索引 + 字段名模糊匹配

**理由**:
- 现有 `field_mapping_hash` 已支持精确匹配
- 增加字段名匹配作为补充（哈希相同但字段名略有不同的情况）
- 查询时优先用哈希精确匹配，再用字段名排序

### 4. 推荐结果展示
**决策**: 展示匹配度最高的规则，最多5条

**展示格式**:
```
🔍 **为你推荐以下规则**：

1. ✨ 喜马_官网对账规则 (匹配度: 100%)
   • 业务字段: 订单号 → 第三方订单号, 金额 → 应结算平台金额, 日期 → 下单时间
   • 财务字段: 订单号 → sup订单号, 金额 → 发生
   💡 推荐理由: 关键字段完全匹配

2. 🏅 某公司对账规则 (匹配度: 67%)
   • 业务字段: 订单号 → 订单号, 金额 → 金额
   💡 推荐理由: 订单号和金额字段匹配

请输入数字选择，或输入"创建新规则"继续配置：
```

### 5. 对账结果 AI 评估
**决策**: 对账完成后，调用 LLM 分析规则适用性

**评估因素**:
- 匹配率: 业务数据和财务数据成功匹配的比例
- 差异分析: 未匹配记录的主要原因
- 规则稳定性: 规则配置是否合理

**输出格式**:
```
📊 **对账结果评估**

匹配率: 98.5% (197/200)
未匹配: 3 条 (金额差异超过容差)

💡 **规则适用性评估**: ⭐⭐⭐⭐☆ (推荐使用)
该规则匹配度高，配置合理，建议保存为个人规则以便复用。

[保存为个人规则] [不要保存]
```

### 6. 保存规则交互
**决策**: 使用自然语言处理用户输入

- 用户输入"保存" → 提示输入规则名称 → 复制规则
- 用户输入"不要" → 返回字段映射建议界面

## Risks / Trade-offs

- **[风险]** 字段名匹配可能不准确
  - **缓解**: 使用多 alias 匹配，增加鲁棒性

- **[风险]** 几十万规则查询性能
  - **缓解**: 优先使用 `field_mapping_hash` 精确匹配，结果少时无需字段名排序

- **[权衡]** 精确匹配 vs 模糊匹配
  - 本期只用字段名包含匹配，不做语义相似度

## Open Questions

1. 推荐规则的数量限制？（当前设为5条，是否足够？）
2. 是否需要记录用户选择推荐规则的次数用于排序？
3. AI 评估的 prompt 需要根据实际对账结果调整

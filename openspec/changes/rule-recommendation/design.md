## Context

当前对账规则创建流程：
```
file_analysis → field_mapping → rule_config → validation_preview → save_rule
```

规则数据存储在 `reconciliation_rules` 表，每个规则包含：
- `rule_template` (JSONB): 包含 `data_sources.business/finance.field_roles` 字段映射
- `field_mapping_text`: 人类可读的字段映射描述
- `rule_config_text`: 规则配置描述

现有规则数量预计增长到几万甚至几十万，需要高效的匹配查询机制。

## Goals / Non-Goals

**Goals:**
- 在字段映射完成后，快速找到匹配的现有规则
- 支持几十万规则的高性能查询（O(1) 复杂度）
- 用户可选择使用推荐规则或继续创建新规则
- 对账后可将推荐规则复制为自己的规则

**Non-Goals:**
- 模糊匹配或相似度匹配（本期只做精确匹配）
- 规则推荐的机器学习算法
- 前端 UI 改造（复用现有消息展示）

## Decisions

### 1. 哈希索引策略
**决策**: 在 `reconciliation_rules` 表新增 `field_mapping_hash` 字段，存储字段映射的 MD5 哈希值

**哈希计算逻辑**:
```python
import hashlib
import json

def compute_field_mapping_hash(mappings: dict) -> str:
    """计算字段映射哈希值"""
    # 提取6个关键字段，排序后计算哈希
    fields = []
    for source in ['business', 'finance']:
        for role in ['order_id', 'amount', 'date']:
            value = mappings.get(source, {}).get(role, '')
            # 处理列表类型（如 order_id: ["字段1", "字段2"]）
            if isinstance(value, list):
                value = ','.join(sorted(value))
            fields.append(f"{source}.{role}={value}")
    
    # 排序确保一致性
    fields.sort()
    hash_input = '|'.join(fields)
    return hashlib.md5(hash_input.encode()).hexdigest()
```

**理由**:
- MD5 哈希长度固定（32字符），适合索引
- 哈希碰撞概率极低，可接受
- 支持精确匹配，查询复杂度 O(1)

### 2. 数据库索引
**决策**: 在 `field_mapping_hash` 字段创建 B-tree 索引

```sql
ALTER TABLE reconciliation_rules 
ADD COLUMN field_mapping_hash VARCHAR(32);

CREATE INDEX idx_rules_field_mapping_hash 
ON reconciliation_rules(field_mapping_hash);
```

**理由**:
- B-tree 索引支持精确匹配查询
- VARCHAR(32) 足够存储 MD5 哈希
- 几十万规则查询仍能保持毫秒级响应

### 3. 工作流变更
**决策**: 在 `field_mapping` 之后插入 `rule_recommendation` 节点

**新流程**:
```
file_analysis → field_mapping → rule_recommendation → rule_config → ...
                                      ↓
                            (使用推荐规则) → task_execution → result_analysis
                                      ↓                            ↓
                                                          (保存) → prompt_rule_name → copy_rule
                                                          (不要) → field_mapping
```

**路由逻辑**:
- 如果找到匹配规则 → 显示推荐，等待用户选择
- 用户选择推荐规则 → 直接进入 `task_execution`
- 用户选择创建新规则 → 进入 `rule_config`
- 对账完成后选择保存 → 提示输入名称 → 复制规则
- 对账完成后选择不要 → 回到 `field_mapping`

### 4. 规则复制逻辑
**决策**: 完整复制规则数据，生成新 ID，设置当前用户为 owner

```python
def copy_rule(source_rule_id: str, new_name: str, user_id: str) -> str:
    """复制规则"""
    # 1. 读取源规则
    source = get_rule(source_rule_id)
    
    # 2. 生成新 ID
    new_id = str(uuid.uuid4())
    
    # 3. 复制数据
    new_rule = {
        **source,
        'id': new_id,
        'name': new_name,
        'created_by': user_id,
        'created_at': now(),
        'updated_at': now(),
    }
    
    # 4. 保存
    save_rule(new_rule)
    return new_id
```

### 5. 推荐规则展示格式
**决策**: 展示规则名称 + 字段映射摘要 + 规则配置摘要

**示例输出**:
```
找到 3 个匹配的对账规则：

1. 喜马_官网对账规则
   字段映射: 业务(第三方订单号→订单号, 应结算平台金额→金额) 
            财务(sup订单号→订单号, 发生-→金额)
   规则配置: 订单号截取前21位，相同订单号金额累加

2. 西福商管_对账规则
   ...

请输入数字选择规则，或输入"创建新规则"继续配置：
```

## Risks / Trade-offs

- **[风险]** 哈希碰撞导致错误匹配
  - **缓解**: MD5 碰撞概率极低（1/2^128），可接受；如需更高安全性可换 SHA256

- **[风险]** 字段映射格式变化导致哈希不一致
  - **缓解**: 哈希计算前统一格式化（排序、去空格、小写化等）

- **[风险]** 迁移脚本执行时间过长
  - **缓解**: 分批处理，每批 1000 条规则

- **[权衡]** 精确匹配 vs 模糊匹配
  - 本期只做精确匹配，减少复杂度
  - 后续可扩展相似度匹配（如 Jaccard 相似度）

## Open Questions

1. 是否需要记录规则被推荐/复制的次数用于排序？（可作为"最相关"的依据）
2. 规则复制后是否需要关联原规则（source_rule_id）便于追溯？

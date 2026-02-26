# PostgreSQL 中存储的 JSON 数据说明

本文档描述 tally 数据库中所有 JSONB 列的结构和示例数据。

---

## 1. company.enabled_features

**类型**: `jsonb`，默认 `["reconciliation", "data_prep"]`

**含义**: 公司启用的功能列表

**示例**:
```json
["reconciliation", "data_prep"]
```

---

## 2. departments.settings

**类型**: `jsonb`，默认 `{}`

**含义**: 部门配置，如权限、审批流程等

**示例**:
```json
{}
```

---

## 3. audit_logs.details

**类型**: `jsonb`，可为空

**含义**: 审计日志的详细信息

**示例**:
```json
{"entity": "rule", "action": "create", "rule_name": "西福"}
```

---

## 4. messages.metadata

**类型**: `jsonb`，默认 `{}`

**含义**: 消息的元数据

**示例**:
```json
{}
```

---

## 5. messages.attachments

**类型**: `jsonb`，默认 `[]`

**含义**: 消息附件列表

**格式**:
```json
[
  {"name": "文件名.csv", "path": "/uploads/xxx.csv", "size": 1024}
]
```

---

## 6. reconciliation_rules.rule_template ⭐ 核心

**类型**: `jsonb`，必填

**含义**: 完整的对账规则配置，包含数据源、清洗规则、验证规则等

**完整结构** (参考 `测试6_schema.json`):

```json
{
  "version": "1.0",
  "description": "规则描述",
  "data_sources": {
    "business": {
      "file_pattern": ["1767597466118_*.csv", "..."],
      "field_roles": {
        "order_id": ["sp订单号"],
        "amount": "销售额",
        "date": "订单时间"
      }
    },
    "finance": {
      "file_pattern": ["ads_finance_d_inc_channel_details_*.csv", "..."],
      "field_roles": {
        "order_id": ["sup订单号"],
        "amount": ["发生+", "发生-"],
        "date": "完成时间"
      }
    }
  },
  "key_field_role": "order_id",
  "tolerance": {
    "date_format": "%Y-%m-%d",
    "amount_diff_max": 0.1
  },
  "data_cleaning_rules": {
    "business": {
      "field_transforms": [{"field": "amount", "operation": "round", "decimals": 2, "description": "金额保留2位小数"}],
      "row_filters": [],
      "aggregations": [{"group_by": "order_id", "agg_fields": {"amount": "sum"}, "description": "按订单号合并"}],
      "global_transforms": [{"operation": "drop_na", "subset": ["order_id"]}]
    },
    "finance": { /* 同上结构 */ },
    "global": {
      "global_transforms": [{"operation": "drop_duplicates", "subset": ["order_id"], "keep": "first"}]
    }
  },
  "custom_validations": [
    {"name": "missing_in_business", "condition_expr": "fin_exists and not biz_exists", "detail_template": "..."},
    {"name": "amount_mismatch", "condition_expr": "...", "detail_template": "..."}
  ],
  "field_mapping_text": "业务: 订单号->sp订单号, 金额->销售额\n财务: 订单号->sup订单号, 金额->发生-",
  "rule_config_text": "金额容差 0.1 元\n订单号去除首尾空格"
}
```

**主要字段说明**:
- `data_sources`: 业务/财务数据源，含文件匹配模式、字段角色映射
- `field_roles`: 标准角色(order_id/amount/date/status) → 实际列名
- `data_cleaning_rules`: 字段转换、行过滤、聚合、全局去重
- `custom_validations`: 对账差异类型（缺业务、缺财务、金额不符等）

---

## 7. reconciliation_tasks.finance_files / business_files

**类型**: `jsonb`，可为空

**含义**: 对账任务使用的财务/业务文件路径列表

**示例**:
```json
["/uploads/ads_finance_xxx.csv", "/uploads/1767597466118.csv"]
```

---

## 8. reconciliation_tasks.result_summary

**类型**: `jsonb`，可为空

**含义**: 对账结果汇总

**示例**:
```json
{
  "total_records": 1000,
  "matched": 950,
  "unmatched_finance": 30,
  "unmatched_business": 20,
  "amount_mismatch": 5
}
```

---

## 9. reconciliation_tasks.result_details

**类型**: `jsonb`，可为空

**含义**: 对账结果明细（差异记录等）

---

## 10. rule_versions.rule_template

**类型**: `jsonb`，必填

**含义**: 与 `reconciliation_rules.rule_template` 结构相同，用于规则版本历史

---

## 11. rule_usage_logs.result_summary

**类型**: `jsonb`，可为空

**含义**: 规则使用时的结果摘要

---

## 12. uploaded_files.metadata

**类型**: `jsonb`，可为空

**含义**: 上传文件的元数据（如列数、行数等）

---

## 查询示例

```sql
-- 查看规则名称和 rule_template 的 key 结构
SELECT name, jsonb_object_keys(rule_template) AS keys
FROM reconciliation_rules
LIMIT 5;

-- 提取 field_roles
SELECT name,
  rule_template->'data_sources'->'business'->'field_roles' AS biz_fields,
  rule_template->'data_sources'->'finance'->'field_roles' AS fin_fields
FROM reconciliation_rules
WHERE status = 'active';
```

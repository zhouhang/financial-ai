---
name: generate-file-validation-rule-json
description: 当用户要基于上传文件、截图或字段清单生成文件检查/文件校验 JSON 时使用。输出符合当前 finance-mcp file_validation_rules 风格的规则 JSON。
---

# 生成文件检查规则 JSON

当用户要为财务上传文件生成文件检查规则 JSON 时，使用这个 skill。

典型请求：
- “根据我上传的 5 个文件，生成文件检查规则 json”
- “按这个文件样例写 file 校验规则”
- “做一个文件上传合法性校验 json”

## 目标

生成当前 `file_validation_rules` 风格的 JSON，让文件校验工具可以：
- 识别每一张预期表
- 校验 `required_columns`
- 校验 `file_type`
- 在需要时接受 `column_aliases`

除非用户明确要求解释，否则默认只输出 JSON。

## 当前 JSON 结构

使用下面这个结构：

```json
{
  "file_validation_rules": {
    "validation_config": {
      "ignore_whitespace": true,
      "case_sensitive": false
    },
    "table_schemas": [
      {
        "table_id": "EXAMPLE_SOURCE_TABLE",
        "table_name": "源表A",
        "file_type": ["xls", "xlsx", "xlsm", "xlsb", "csv"],
        "required_columns": ["字段1", "字段2"],
        "column_aliases": {
          "字段1": ["字段一"]
        }
      }
    ]
  }
}
```

## 保留字段与禁用字段

只使用当前代码支持的字段：
- `file_validation_rules`
- `validation_config.ignore_whitespace`
- `validation_config.case_sensitive`
- `table_schemas[].table_id`
- `table_schemas[].table_name`
- `table_schemas[].file_type`
- `table_schemas[].required_columns`
- `table_schemas[].column_aliases`

除非用户明确要求维护历史老规则，否则不要加这些字段：
- `all_columns`
- `optional_columns`
- `description`
- `is_required`
- `max_match_count`

## 工作流

1. 检查用户上传的文件、截图或明确给出的字段清单。
2. 判断一共需要识别几张不同的表。
3. 对每张表提取规范的 `table_name` 和必填表头。
4. 只有在以下情况才加 `column_aliases`：
- 用户明确给了别名表头
- 多个上传样例里出现了稳定的表头变体
5. 对常见表格上传场景，默认 `file_type` 为 `["xls", "xlsx", "xlsm", "xlsb", "csv"]`，除非用户明确缩小范围。
6. 生成稳定的英文大写下划线 `table_id`。

## 命名规则

- `table_name`：如果用户用中文，就保留业务侧中文表名。
- `table_id`：使用简洁的英文大写下划线命名，例如：
  - `AP_INVOICE_DETAIL`
  - `AR_OPENING_BALANCE`
  - `BANK_RECEIPT_DETAIL`

## 字段提取规则

生成 `required_columns` 时：
- 除非明显需要归一化，否则保留源文件中的表头措辞
- 不要发明用户没提供、文件里也没出现的字段
- 如果两个文件只在一两个同义表头上不同，就在 `required_columns` 里保留一个规范字段，把其它写进 `column_aliases`

## 输出规则

- 返回一个完整 JSON 对象。
- 除非用户要求说明，否则不要在 JSON 外再包一层解释性 prose。
- 如果缺少关键字段，只问最小阻塞问题。

## 边界

如果用户需要按内容识别文件、按 sheet 名识别、多级表头、字段值规则、字段类型校验或跨文件约束，要明确说明当前 file rule DSL 不能完整覆盖；只有在仍然有价值时，才输出最接近的可支持 JSON。

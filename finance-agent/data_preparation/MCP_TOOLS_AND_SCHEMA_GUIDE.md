# Data Preparation MCP 工具说明文档

## MCP 工具列表

### 1. data_preparation_start
**名称**: `data_preparation_start`
**描述**: 开始数据整理任务

**输入参数**:
- `data_preparation_type` (string, 必需): 数据整理类型（中文名称，如：审计数据整理、货币资金数据整理）
- `files` (array, 必需): 文件路径列表

**返回**:
```json
{
  "task_id": "proc_20260116_161049_b0f3b0",
  "status": "pending",
  "message": "货币资金数据整理任务已创建，正在处理中"
}
```

**使用示例**:
```json
{
  "data_preparation_type": "货币资金数据整理",
  "files": [
    "/uploads/福擎-科目余额表 本期2025.xlsx",
    "/uploads/福擎-科目余额表 上期2024.xlsx"
  ]
}
```

---

### 2. data_preparation_result
**名称**: `data_preparation_result`
**描述**: 获取数据整理结果

**输入参数**:
- `task_id` (string, 必需): 任务ID

**返回**:
```json
{
  "task_id": "proc_20260116_161049_b0f3b0",
  "status": "success",
  "actions": [
    {
      "action": "download_file",
      "url": "http://localhost:8000/download/proc_20260116_161049_b0f3b0",
      "method": "GET"
    },
    {
      "action": "view_preview",
      "url": "http://localhost:8000/preview/proc_20260116_161049_b0f3b0",
      "method": "GET"
    },
    {
      "action": "get_detailed_report",
      "url": "http://localhost:8000/report/proc_20260116_161049_b0f3b0",
      "method": "GET"
    }
  ],
  "metadata": {
    "project_name": "货币资金数据整理",
    "rule_version": "3.0",
    "execution_time_seconds": 3.82
  }
}
```

---

### 3. data_preparation_status
**名称**: `data_preparation_status`
**描述**: 查询数据整理任务状态

**输入参数**:
- `task_id` (string, 必需): 任务ID

**返回**:
```json
{
  "task_id": "proc_20260116_161049_b0f3b0",
  "status": "processing",
  "progress": 50,
  "message": "正在处理步骤 2/4"
}
```

---

### 4. data_preparation_list_tasks
**名称**: `data_preparation_list_tasks`
**描述**: 列出所有数据整理任务

**输入参数**: 无

**返回**:
```json
{
  "tasks": [
    {
      "task_id": "proc_20260116_161049_b0f3b0",
      "type": "货币资金数据整理",
      "status": "success",
      "created_at": "2026-01-16T16:10:49"
    },
    {
      "task_id": "proc_20260116_155525_2c1580",
      "type": "测试数据整理",
      "status": "success",
      "created_at": "2026-01-16T15:55:25"
    }
  ]
}
```

---

## 步骤化 Schema 结构说明

以 `monetary_funds_schema.json` 为例，详细说明每个 key 的含义。

### 顶层结构

```json
{
  "version": "3.0",
  "schema_type": "step_based",
  "metadata": { ... },
  "template_config": { ... },
  "processing_steps": [ ... ],
  "workflow_controls": { ... }
}
```

#### 1. `version` (string, 必需)
**含义**: Schema 版本号
**值**: `"3.0"` 表示步骤化版本
**示例**: `"3.0"`

#### 2. `schema_type` (string, 必需)
**含义**: Schema 类型，用于区分处理模式
**值**:
- `"step_based"` - 步骤化处理（新版）
- 不设置或其他值 - 传统并行处理（旧版）
**示例**: `"step_based"`

#### 3. `metadata` (object, 必需)
**含义**: 项目元数据信息

```json
{
  "project_name": "货币资金数据整理",
  "author": "审计部",
  "created_at": "2026-01-10",
  "description": "从福擎科目余额表中抽取银行存款数据并填入审计底稿"
}
```

**字段说明**:
- `project_name` (string): 项目名称
- `author` (string): 作者
- `created_at` (string): 创建日期
- `description` (string): 项目描述

---

### 4. `template_config` (object, 必需)
**含义**: 模板文件配置

```json
{
  "template_file": "01 审计底稿-模板.xlsx",
  "output_filename_pattern": "货币资金审计底稿_{timestamp}.xlsx"
}
```

**字段说明**:
- `template_file` (string, 必需): 模板文件名（相对于 templates 目录）
- `output_filename_pattern` (string, 可选): 输出文件名模式
  - `{timestamp}` - 替换为时间戳（格式：YYYYMMDD_HHMMSS）
  - `{YYYY}` - 年份
  - `{MM}` - 月份
  - `{DD}` - 日期

---

### 5. `processing_steps` (array, 必需)
**含义**: 处理步骤列表，按顺序执行

每个步骤是一个对象，包含以下字段：

#### 步骤通用字段

```json
{
  "step_id": "step_1",
  "step_name": "读取本期科目余额表并写入模板",
  "step_type": "extract_and_write",
  "description": "从福擎-科目余额表 本期2025 中提取银行存款数据，写入审计底稿模板",
  "depends_on": [],
  "enabled": true
}
```

**字段说明**:
- `step_id` (string, 必需): 步骤唯一标识符
- `step_name` (string, 必需): 步骤名称（用于显示）
- `step_type` (string, 必需): 步骤类型
  - `"extract_and_write"` - 提取并写入
  - `"read_template_and_match"` - 读取模板并匹配
  - `"transform_and_write"` - 转换并写入
  - `"conditional_write"` - 条件写入
- `description` (string, 可选): 步骤描述
- `depends_on` (array, 必需): 依赖的步骤ID列表（空数组表示无依赖）
- `enabled` (boolean, 可选): 是否启用此步骤（默认 true）

---

#### 5.1 `data_source` (object, 必需)
**含义**: 数据源配置

##### 5.1.1 从上传文件读取

```json
{
  "source_type": "uploaded_file",
  "file_pattern": "*科目余额表*本期*2025*.xlsx",
  "extraction_rules": {
    "multi_index_header": [0, 1],
    "columns_mapping": {
      "科目名称": "account_name",
      "核算项目": "project_item"
    }
  },
  "conditional_extractions": { ... },
  "validation_rules": [ ... ]
}
```

**字段说明**:
- `source_type` (string, 必需): 数据源类型
  - `"uploaded_file"` - 从上传的文件读取
  - `"template_range"` - 从模板读取
  - `"step_output"` - 从之前步骤的输出读取

- `file_pattern` (string, 必需): 文件名匹配模式（支持通配符 `*`）
  - 示例: `"*科目余额表*本期*2025*.xlsx"`

- `extraction_rules` (object, 必需): 提取规则
  - `multi_index_header` (array, 可选): 多级表头行索引
    - 示例: `[0, 1]` 表示第1行和第2行是表头
  - `sheet_name` (string/int, 可选): 工作表名称或索引（默认 0）
  - `skip_rows` (int, 可选): 跳过的行数（默认 0）
  - `columns_mapping` (object, 必需): 列名映射
    - 键: 原列名
    - 值: 新列名
    - 示例: `{"科目名称": "account_name"}`

---

##### 5.1.2 条件提取 `conditional_extractions`

```json
{
  "condition_id": "bank_deposit_current_period",
  "name": "本期银行存款-*筛选",
  "description": "科目名称匹配'银行存款_*'格式且核算项目不为空",
  "condition": {
    "type": "and",
    "conditions": [
      {
        "type": "column_matches",
        "column_header": "account_name",
        "regex_pattern": "^银行存款_[^_]+$",
        "match_type": "regex"
      },
      {
        "type": "column_empty",
        "column_header": "project_item",
        "empty_check": false
      }
    ]
  },
  "extraction": {
    "target_fields": [
      "account_name",
      "project_item",
      {
        "field": "期初余额",
        "sub_field": "借方",
        "output_field": "opening_balance_debit"
      }
    ],
    "output_type": "table"
  }
}
```

**字段说明**:
- `condition_id` (string, 可选): 条件ID
- `name` (string, 可选): 条件名称
- `description` (string, 可选): 条件描述

- `condition` (object, 必需): 条件定义
  - **AND 条件**:
    ```json
    {
      "type": "and",
      "conditions": [ ... ]
    }
    ```

  - **OR 条件**:
    ```json
    {
      "type": "or",
      "conditions": [ ... ]
    }
    ```

  - **正则匹配**:
    ```json
    {
      "type": "column_matches",
      "column_header": "account_name",
      "regex_pattern": "^银行存款_[^_]+$",
      "match_type": "regex"
    }
    ```
    - `column_header`: 列名
    - `regex_pattern`: 正则表达式
    - `match_type`: 匹配类型（`"regex"` 或 `"exact"`）

  - **空值检查**:
    ```json
    {
      "type": "column_empty",
      "column_header": "project_item",
      "empty_check": false
    }
    ```
    - `column_header`: 列名
    - `empty_check`: `true` 检查为空，`false` 检查非空

  - **等值匹配**:
    ```json
    {
      "type": "column_equals",
      "column_header": "status",
      "value": "active"
    }
    ```

- `extraction` (object, 必需): 提取配置
  - `target_fields` (array, 必需): 要提取的字段列表
    - 简单字段: `"account_name"`
    - 多级字段:
      ```json
      {
        "field": "期初余额",
        "sub_field": "借方",
        "output_field": "opening_balance_debit"
      }
      ```
  - `output_type` (string, 必需): 输出类型
    - `"table"` - 表格（DataFrame）
    - `"value"` - 单个值

---

##### 5.1.3 从模板读取

```json
{
  "source_type": "template_range",
  "template_reference": {
    "sheet": "货币资金",
    "range": "A2:H1000",
    "columns_mapping": {
      "A": "customer_id",
      "B": "customer_name",
      "F": "order_amount"
    },
    "read_until_empty": true
  }
}
```

**字段说明**:
- `template_reference` (object, 必需): 模板引用配置
  - `sheet` (string, 必需): 工作表名称
  - `range` (string, 必需): 单元格范围（如 `"A2:H1000"`）
  - `columns_mapping` (object, 必需): 列映射
    - 键: Excel 列字母（如 `"A"`, `"B"`）
    - 值: 字段名
  - `read_until_empty` (boolean, 可选): 是否读取到空行为止（默认 false）

---

##### 5.1.4 模板匹配

```json
{
  "conditional_extractions": {
    "match_with_template": {
      "template_fields": ["account_name", "project_item"],
      "data_fields": ["account_name", "project_item"],
      "match_type": "inner_join"
    }
  }
}
```

**字段说明**:
- `match_with_template` (object, 可选): 与模板数据匹配
  - `template_fields` (array, 必需): 模板中的匹配字段
  - `data_fields` (array, 必需): 数据中的匹配字段
  - `match_type` (string, 必需): 匹配类型
    - `"inner_join"` - 内连接（只保留匹配的）
    - `"left_join"` - 左连接（保留所有数据）

---

#### 5.2 `template_reference` (object, 可选)
**含义**: 模板引用（用于 `read_template_and_match` 类型）

```json
{
  "sheet": "货币资金",
  "range": "B9:C100",
  "columns_mapping": {
    "B": "account_name",
    "C": "project_item"
  },
  "read_until_empty": true
}
```

**用途**: 在 `read_template_and_match` 步骤中，先读取模板数据，然后用作匹配条件

---

#### 5.3 `template_action` (object, 必需)
**含义**: 模板操作（如何写入数据到模板）

##### 5.3.1 写入表格 `write_table`

```json
{
  "action_type": "write_table",
  "target": {
    "sheet": "货币资金",
    "start_cell": "B9",
    "header_mapping": {
      "account_name": "B",
      "project_item": "C",
      "opening_balance_debit": "D",
      "current_period_debit": "E",
      "current_period_credit": "F"
    }
  }
}
```

**字段说明**:
- `action_type`: `"write_table"`
- `target` (object, 必需):
  - `sheet` (string, 必需): 工作表名称
  - `start_cell` (string, 必需): 起始单元格（如 `"B9"`）
  - `header_mapping` (object, 必需): 字段到列的映射
    - 键: 字段名
    - 值: Excel 列字母
  - `write_mode` (string, 可选): 写入模式
    - `"overwrite"` - 覆盖（默认）
    - `"append"` - 追加

---

##### 5.3.2 匹配写入 `write_matched`

```json
{
  "action_type": "write_matched",
  "target": {
    "sheet": "货币资金",
    "match_by": {
      "template_columns": ["B", "C"],
      "data_fields": ["account_name", "project_item"]
    },
    "write_columns": {
      "prior_period_credit": "H"
    },
    "aggregation": {
      "prior_period_credit": "sum"
    }
  }
}
```

**字段说明**:
- `action_type`: `"write_matched"`
- `target` (object, 必需):
  - `sheet` (string, 必需): 工作表名称
  - `match_by` (object, 必需): 匹配规则
    - `template_columns` (array, 必需): 模板中的匹配列（Excel 列字母）
    - `data_fields` (array, 必需): 数据中的匹配字段
  - `write_columns` (object, 必需): 要写入的列
    - 键: 字段名
    - 值: Excel 列字母
  - `aggregation` (object, 可选): 聚合函数
    - 键: 字段名
    - 值: 聚合函数（`"sum"`, `"count"`, `"mean"`, `"first"`）

---

##### 5.3.3 写入列 `write_column`

```json
{
  "action_type": "write_column",
  "target": {
    "sheet": "汇总表",
    "start_cell": "I2",
    "field": "net_income"
  }
}
```

**字段说明**:
- `action_type`: `"write_column"`
- `target` (object, 必需):
  - `sheet` (string, 必需): 工作表名称
  - `start_cell` (string, 必需): 起始单元格
  - `field` (string, 必需): 要写入的字段名

---

##### 5.3.4 写入单值 `write_value`

```json
{
  "action_type": "write_value",
  "target": {
    "sheet": "汇总表",
    "cell": "A1",
    "value_source": "total_amount"
  }
}
```

**字段说明**:
- `action_type`: `"write_value"`
- `target` (object, 必需):
  - `sheet` (string, 必需): 工作表名称
  - `cell` (string, 必需): 单元格位置
  - `value_source` (string, 必需): 值来源字段

---

#### 5.4 `transformations` (array, 可选)
**含义**: 数据转换操作（用于 `transform_and_write` 类型）

```json
[
  {
    "operation": "calculate",
    "formula": "{{payment_amount}} - {{return_amount}}",
    "output_field": "net_income",
    "default_value": 0
  }
]
```

**字段说明**:
- `operation` (string, 必需): 操作类型
  - `"calculate"` - 计算
  - `"aggregate"` - 聚合
  - `"copy"` - 复制
- `formula` (string, 必需): 计算公式（用 `{{field_name}}` 引用字段）
- `output_field` (string, 必需): 输出字段名
- `default_value` (number, 可选): 默认值（用于 NaN）

---

#### 5.5 `output_variables` (object, 可选)
**含义**: 输出变量（供后续步骤使用）

```json
{
  "current_period_data": {
    "description": "本期银行存款数据，供上期数据匹配使用",
    "fields": ["account_name", "project_item"]
  }
}
```

**字段说明**:
- 键: 变量名
- 值: 变量配置
  - `description` (string, 可选): 描述
  - `fields` (array, 可选): 包含的字段列表

---

### 6. `workflow_controls` (object, 可选)
**含义**: 工作流控制配置

```json
{
  "execution_order": "sequential",
  "error_handling": {
    "on_extraction_error": "skip_and_log",
    "on_calculation_error": "use_default:0",
    "max_errors": 10
  },
  "logging": {
    "level": "INFO",
    "output_file": "monetary_funds_processing_log_{timestamp}.txt"
  }
}
```

**字段说明**:
- `execution_order` (string, 可选): 执行顺序
  - `"sequential"` - 顺序执行（步骤化默认）
  - `"parallel"` - 并行执行（传统模式）

- `error_handling` (object, 可选): 错误处理
  - `on_extraction_error` (string): 提取错误时的处理
    - `"skip_and_log"` - 跳过并记录
    - `"raise"` - 抛出异常
  - `on_calculation_error` (string): 计算错误时的处理
    - `"use_default:0"` - 使用默认值 0
    - `"raise"` - 抛出异常
  - `max_errors` (int): 最大错误数

- `logging` (object, 可选): 日志配置
  - `level` (string): 日志级别（`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`）
  - `output_file` (string): 日志文件名模式

---

## 完整示例

参见 `schemas/monetary_funds_schema.json` 获取完整的步骤化 schema 示例。

## 测试

运行测试脚本验证 schema:
```bash
cd finance-agent/data_preparation
../../.venv/bin/python run_monetary_funds_test.py
```

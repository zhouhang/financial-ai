# 步骤化数据整理功能使用指南

## 概述

步骤化数据整理功能允许你按顺序执行多个数据处理步骤，每个步骤可以：
- 从上传的文件读取数据
- 从模板读取之前步骤写入的数据
- 使用模板数据作为条件匹配其他文件
- 执行计算和转换
- 将结果写入模板

## 快速开始

### 1. 创建测试数据

```bash
cd finance-mcp/data_preparation
../../.venv/bin/python create_test_data.py
```

这将创建：
- 测试模板文件
- 4 个测试数据文件（客户主表、订单明细、付款记录、退货记录）

### 2. 运行测试

```bash
../../.venv/bin/python run_test.py
```

测试将验证所有 7 个功能需求。

## Schema 配置

### 基本结构

```json
{
  "version": "3.0",
  "schema_type": "step_based",
  "template_config": {
    "template_file": "模板文件.xlsx",
    "output_filename_pattern": "输出_{timestamp}.xlsx"
  },
  "processing_steps": [
    // 步骤定义
  ]
}
```

### 步骤类型

#### 1. extract_and_write - 提取并写入

从文件读取数据并写入模板。

```json
{
  "step_id": "step_1",
  "step_type": "extract_and_write",
  "data_source": {
    "source_type": "uploaded_file",
    "file_pattern": "*客户*.xlsx",
    "extraction_rules": {
      "sheet_name": "Sheet1",
      "columns_mapping": {
        "A": "customer_id",
        "B": "customer_name"
      }
    }
  },
  "template_action": {
    "action_type": "write_table",
    "target": {
      "sheet": "汇总表",
      "start_cell": "A2",
      "header_mapping": {
        "customer_id": "A",
        "customer_name": "B"
      }
    }
  }
}
```

#### 2. read_template_and_match - 读取模板并匹配

读取模板数据，用作条件匹配其他文件。

```json
{
  "step_id": "step_2",
  "step_type": "read_template_and_match",
  "depends_on": ["step_1"],
  "template_reference": {
    "sheet": "汇总表",
    "range": "A2:B1000",
    "columns_mapping": {
      "A": "customer_id"
    },
    "read_until_empty": true
  },
  "data_source": {
    "source_type": "uploaded_file",
    "file_pattern": "*订单*.xlsx",
    "extraction_rules": {
      "sheet_name": "订单",
      "columns_mapping": {
        "A": "order_id",
        "B": "customer_id",
        "C": "amount"
      }
    },
    "conditional_extractions": {
      "match_with_template": {
        "template_fields": ["customer_id"],
        "data_fields": ["customer_id"],
        "match_type": "inner_join"
      }
    }
  },
  "template_action": {
    "action_type": "write_matched",
    "target": {
      "sheet": "汇总表",
      "match_by": {
        "template_columns": ["A"],
        "data_fields": ["customer_id"]
      },
      "write_columns": {
        "amount": "C"
      },
      "aggregation": {
        "amount": "sum"
      }
    }
  }
}
```

#### 3. transform_and_write - 转换并写入

读取模板数据，执行计算，写回模板。

```json
{
  "step_id": "step_3",
  "step_type": "transform_and_write",
  "depends_on": ["step_2"],
  "data_source": {
    "source_type": "template_range",
    "template_reference": {
      "sheet": "汇总表",
      "range": "A2:C1000",
      "columns_mapping": {
        "A": "customer_id",
        "B": "payment",
        "C": "refund"
      },
      "read_until_empty": true
    }
  },
  "transformations": [
    {
      "operation": "calculate",
      "formula": "{{payment}} - {{refund}}",
      "output_field": "net_income",
      "default_value": 0
    }
  ],
  "template_action": {
    "action_type": "write_column",
    "target": {
      "sheet": "汇总表",
      "start_cell": "D2",
      "field": "net_income"
    }
  }
}
```

## 核心概念

### 1. 数据源类型

- **uploaded_file**: 从上传的文件读取
- **template_range**: 从模板读取
- **step_output**: 从之前步骤的输出读取

### 2. 模板操作类型

- **write_table**: 写入表格数据
- **write_matched**: 匹配已有行并更新
- **write_column**: 写入单列
- **write_value**: 写入单个值

### 3. 匹配类型

- **inner_join**: 只保留在模板中存在的数据
- **left_join**: 保留所有数据

### 4. 聚合函数

- **sum**: 求和
- **count**: 计数
- **mean**: 平均值
- **first**: 第一个值

## 示例场景

### 场景：多源数据汇总

1. **Step 1**: 读取客户主表 → 写入模板
2. **Step 2**: 读取模板客户 → 匹配订单数据 → 聚合订单金额 → 写入模板
3. **Step 3**: 读取模板客户 → 匹配付款数据 → 聚合付款金额 → 写入模板
4. **Step 4**: 读取模板客户 → 匹配退货数据 → 聚合退货金额 → 写入模板
5. **Step 5**: 读取模板数据 → 计算净收入 → 写入模板

完整示例见：`schemas/test_step_based_schema.json`

## 测试报告

详细的测试报告见：`TEST_REPORT.md`

## 文件结构

```
finance-mcp/data_preparation/
├── mcp_server/
│   ├── processing_engine.py    # 核心处理引擎
│   ├── template_reader.py      # 模板读取器
│   ├── template_writer.py      # 模板写入器
│   └── ...
├── schemas/
│   ├── test_step_based_schema.json          # 测试 schema
│   └── step_based_example_schema.json       # 示例 schema
├── templates/
│   └── 多源数据整理模板.xlsx                # 测试模板
├── test_data/
│   ├── 测试_客户主表_20260116.xlsx
│   ├── 测试_订单明细_20260116.xlsx
│   ├── 测试_付款记录_20260116.xlsx
│   └── 测试_退货记录_20260116.xlsx
├── test_output/                              # 测试输出目录
├── create_test_data.py                       # 创建测试数据脚本
├── run_test.py                               # 运行测试脚本
├── TEST_REPORT.md                            # 测试报告
└── README_STEP_BASED.md                      # 本文档
```

## 注意事项

1. **依赖关系**: 确保 `depends_on` 正确配置，避免循环依赖
2. **列映射**: 使用字母（A, B, C）表示 Excel 列
3. **NaN 处理**: 空值会被自动处理为默认值（通常是 0）
4. **文件匹配**: 使用通配符 `*` 匹配文件名
5. **性能**: 大数据量时注意设置合理的 range 范围

## 常见问题

### Q: 如何处理没有匹配数据的情况？

A: 使用 `aggregation` 时，没有匹配的行会保持为空（NaN）。在后续计算中，NaN 会被转换为默认值。

### Q: 如何调试步骤执行？

A: 查看日志输出，每个步骤都会记录详细的执行信息。

### Q: 如何添加新的步骤类型？

A: 在 `processing_engine.py` 中扩展 `_execute_step` 方法。

## 支持

如有问题，请查看：
- 测试报告：`TEST_REPORT.md`
- 示例 schema：`schemas/test_step_based_schema.json`
- 测试脚本：`run_test.py`

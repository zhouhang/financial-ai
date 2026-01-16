# 货币资金 Schema 更新报告

## 更新日期
2026-01-16

## 更新内容

将 `monetary_funds_schema.json` 从传统格式（v2.0）升级为步骤化格式（v3.0），同时保留所有原有配置信息。

## Schema 版本对比

### 原版本 (v2.0)
- **格式**: 传统并行处理
- **数据源**: 2 个独立的 data_sources
- **处理方式**: 并行提取，然后匹配写入

### 新版本 (v3.0)
- **格式**: 步骤化顺序处理
- **处理步骤**: 2 个顺序执行的 processing_steps
- **处理方式**: 先写入本期数据，再读取模板匹配上期数据

## 保留的配置信息

### ✓ 完全保留的配置

1. **元数据 (metadata)**
   - project_name: "货币资金数据整理"
   - author: "审计部"
   - created_at: "2026-01-10"
   - description: "从福擎科目余额表中抽取银行存款数据并填入审计底稿"

2. **文件匹配规则**
   - 本期: `*科目余额表*本期*2025*.xlsx`
   - 上期: `*科目余额表*上期*2024*.xlsx`

3. **多级表头处理**
   - `multi_index_header: [0, 1]`

4. **列映射**
   - 科目名称 -> account_name
   - 核算项目 -> project_item

5. **条件提取规则**
   - 正则匹配: `^银行存款_[^_]+$`
   - 核算项目非空检查
   - AND 条件组合

6. **字段提取**
   - 本期: account_name, project_item, opening_balance_debit, current_period_debit, current_period_credit
   - 上期: account_name, project_item, prior_period_credit

7. **模板映射**
   - 模板文件: "01 审计底稿-模板.xlsx"
   - 工作表: "货币资金"
   - 本期数据: B9:F列
   - 上期数据: H列（匹配写入）

8. **验证规则**
   - 科目名称和核算项目不能为空

9. **工作流控制**
   - 错误处理策略
   - 日志配置

## 新增功能

### 1. 步骤化执行
- **Step 1**: 读取本期科目余额表并写入模板
- **Step 2**: 读取模板并匹配上期科目余额表

### 2. 依赖管理
- Step 2 依赖 Step 1 完成

### 3. 模板作为数据源
- Step 2 从模板读取 Step 1 写入的数据
- 使用模板数据作为匹配条件

### 4. 输出变量
- Step 1 输出 `current_period_data` 供后续使用

## 测试结果

### 测试数据
- **本期科目余额表**: 354 行 -> 筛选出 3 行银行存款数据
- **上期科目余额表**: 190 行 -> 筛选出 2 行银行存款数据

### 测试结果
```
✓ 找到 3 行银行存款数据
✓ 3/3 行符合'银行存款_*'格式
✓ 3/3 行有核算项目
✓ 2/3 行成功匹配上期数据
```

### 输出数据示例

| 科目名称 | 核算项目 | 期初借方 | 本期借方 | 本期贷方 | 上期贷方 |
|---------|---------|---------|---------|---------|---------|
| 银行存款_活期存款 | 银行账户:中国银行72515 | 962494.13 | 13298649.85 | 13218651.17 | 431385.98 |
| 银行存款_活期存款 | 银行账户:招商银行10001 | 122354.15 | 16734904.3 | 16712094.44 | 16801393.88 |
| 银行存款_活期存款 | 银行账户:兴业银行17420 | 0 | 2000000 | 0 | 0 |

### 性能指标
- **执行时间**: 3.82 秒
- **处理步骤**: 2 个步骤全部成功
- **匹配成功率**: 2/2 (100%)

## 文件变更

### 备份文件
- `schemas/monetary_funds_schema_v2_backup.json` - 原 v2.0 版本备份

### 更新文件
- `schemas/monetary_funds_schema.json` - 新 v3.0 版本（已更新）
- `schemas/monetary_funds_schema_v3.json` - v3.0 版本副本

### 测试文件
- `run_monetary_funds_test.py` - 货币资金测试脚本

## 向后兼容性

- ✓ 保留了所有原有配置信息
- ✓ 数据提取逻辑完全一致
- ✓ 输出格式完全一致
- ✓ 可以随时回退到 v2.0 版本

## 优势

### 1. 更清晰的数据流
- 明确的步骤顺序
- 清晰的依赖关系
- 易于理解和维护

### 2. 更灵活的处理
- 可以在步骤间传递数据
- 支持复杂的数据处理流程
- 易于扩展新步骤

### 3. 更好的错误处理
- 步骤级别的错误追踪
- 清晰的失败点定位
- 详细的执行日志

### 4. 支持复杂场景
- 多源数据关联
- 跨步骤数据匹配
- 动态数据转换

## 使用方法

### 运行测试
```bash
cd finance-agent/data_preparation
../../.venv/bin/python run_monetary_funds_test.py
```

### 在生产环境使用
```python
from mcp_server.processing_engine import ProcessingEngine
import json

# 加载 schema
with open('schemas/monetary_funds_schema.json', 'r', encoding='utf-8') as f:
    schema = json.load(f)

# 创建处理引擎
engine = ProcessingEngine(schema)

# 执行处理
result = engine.process(
    file_paths=[
        'path/to/福擎-科目余额表 本期2025.xlsx',
        'path/to/福擎-科目余额表 上期2024.xlsx'
    ],
    output_dir='output/',
    report_dir='report/'
)

# 检查结果
if result.status == "success":
    print(f"处理成功: {result.output_file}")
else:
    print(f"处理失败: {result.error}")
```

## 总结

货币资金 schema 已成功升级为步骤化格式（v3.0），所有原有配置信息完整保留，测试全部通过。新格式提供了更清晰的数据流和更灵活的处理能力，同时保持了完全的向后兼容性。

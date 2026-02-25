---
name: intelligent-file-analyzer
description: 智能分析复杂文件场景（多sheet/非标准格式/多文件配对），自适应选择最佳处理策略
license: MIT
metadata:
  author: tally
  version: "1.0"
---

# 智能文件分析器

## 概述
处理用户上传的复杂文件场景，包括：
- 单个Excel包含多个sheet
- 非标准格式（合并单元格、注释行、多级表头）
- 单文件单sheet需要拆分
- 多个文件需要智能配对

## 输入参数
- `files`: 上传的文件列表（包含file_path, original_filename等）
- `complexity_info`: 复杂度信息对象
  - `multi_sheet`: boolean - 是否有多sheet文件
  - `file_count`: int - 文件数量
  - `non_standard`: boolean - 是否可能有非标准格式

## 执行步骤

### 1. 多Sheet识别与分类

**触发条件**: complexity_info.multi_sheet == true

**步骤**:
```
对于每个Excel文件：
a) 调用MCP工具读取所有sheet名称和数据
   mcp_tool: read_excel_sheets
   参数: {file_path: "...", sample_rows: 5}

b) 分析每个sheet的特征：
   - 列名列表
   - 前5行样本数据
   - 行数统计

c) 使用LLM判断每个sheet的数据类型：
   提示词模板：
   """
   你是财务数据分析专家。分析以下Excel的所有sheet，判断每个sheet的数据类型。

   Sheet信息：
   {sheet_info}

   类型定义：
   - business: 业务数据（订单、销售、交易等）
   - finance: 财务数据（账单、流水、发票等）
   - summary: 汇总表（统计、总结类）
   - other: 其他（说明、模板等）

   返回JSON格式：
   {
     "results": [
       {"sheet_name": "...", "type": "business", "confidence": 0.85, "reason": "..."},
       ...
     ]
   }
   """

d) 输出识别结果并请求用户确认
```

### 2. 非标准格式处理

**触发条件**: complexity_info.non_standard == true 或检测到格式问题

**处理策略**:
```
a) 注释行检测：
   - 扫描前10行
   - 识别模式：全空行、标题行、说明文本
   - 标记真实数据起始行

b) 表头识别：
   - 检测是否有多级表头（跨行合并）
   - 如果有多级，取最后一行作为列名
   - 处理空列名（用前一列名填充）

c) 合并单元格处理：
   - 检测空值模式
   - 向下填充（forward fill）
   - 记录原始结构供参考

d) 数据区域提取：
   - 从真实表头行开始
   - 到最后一个非空行结束
   - 生成规范的DataFrame
```

### 3. 单文件数据拆分

**触发条件**: file_count == 1 且只有1个有效sheet

**拆分策略**:
```
a) 横向拆分检测：
   - 寻找连续的空列（作为分隔符）
   - 检查左右两侧列名是否有business/finance特征
   - 计算左右数据的相关性

b) 纵向拆分检测：
   - 寻找数据中间的连续空行
   - 检查上下部分的列名是否不同
   - 判断是否是两个独立数据集

c) 列名分组拆分：
   - 分析列名，识别明显的分组（如：订单相关、财务相关）
   - 基于列名相似度聚类
   - 尝试按组拆分

d) 如果无法拆分：
   - 使用LLM识别该数据类型（business或finance）
   - 返回提示："检测到{type}数据，请上传对应的{opposite_type}数据文件"
```

### 4. 多文件智能配对

**触发条件**: file_count > 2

**配对策略**:
```
a) 特征提取：
   对每个文件/sheet提取：
   - 列名列表
   - 关键字段（订单号、金额、日期的列名）
   - 数据行数
   - 数据类型（business/finance）

b) 相似度计算：
   构建相似度矩阵：
   similarity_score = (
     列名重叠度 * 0.4 +
     关键字段匹配度 * 0.4 +
     行数接近度 * 0.2
   )

c) 配对推荐：
   - 找出所有 business-finance 类型的配对
   - 按相似度排序
   - 选择最高分的配对作为推荐
   - 如果有多个高分配对，列出所有选项

d) 输出格式：
   {
     "recommended": {
       "business_file": "...",
       "finance_file": "...",
       "confidence": 0.92,
       "reason": "列名重叠度85%，包含订单号和金额字段"
     },
     "alternatives": [...]
   }
```

### 5. 生成标准化输出

**统一输出格式**:
```json
{
  "success": true,
  "analyses": [
    {
      "filename": "销售数据.xlsx",
      "original_filename": "销售数据.xlsx",
      "sheet_name": "Sheet1",  // 如果是多sheet
      "file_path": "...",
      "columns": ["订单号", "金额", ...],
      "row_count": 1000,
      "sample_data": [...],
      "guessed_source": "business",
      "confidence": 0.85,
      "processing_notes": "检测到2行注释，已跳过"
    },
    ...
  ],
  "recommendations": {
    "pairing": {
      "business": "销售数据.xlsx",
      "finance": "财务账单.xlsx",
      "confidence": 0.90
    },
    "warnings": [
      "文件A包含3个sheet，已自动选择'明细表'"
    ]
  }
}
```

## 错误处理

**常见问题处理**:

1. **无法读取Excel**: 返回友好错误，建议检查文件格式
2. **列名全为空**: 尝试用第一行数据作为列名
3. **数据全为空**: 提示用户文件可能损坏
4. **无法判断类型**: 标记为unknown，让用户手动指定
5. **配对失败**: 提示无法自动配对，建议用户分开上传

## 输出展示

**向用户展示分析结果**:

```
🔍 智能文件分析完成

📊 分析结果：
✅ 销售订单.xlsx (业务数据) - 1,234行
   └─ 包含字段：订单号、商品名称、金额、日期

✅ 财务账单.xlsx (财务数据) - 1,198行
   └─ 包含字段：交易流水号、收入金额、账期

💡 推荐配对：
销售订单.xlsx ↔ 财务账单.xlsx (匹配度: 90%)
理由：两个文件的订单号字段可关联，金额字段类型匹配

请确认是否使用此配对进行对账？
```

## 调试和日志

记录关键决策点：
- 复杂度检测结果
- Sheet识别过程
- 格式处理步骤
- 配对推荐逻辑
- LLM调用次数和响应时间

## 性能优化

- 缓存文件读取结果（同一文件避免重复读取）
- 限制LLM调用次数（批量分析多个sheet）
- 大文件只读取前N行样本（默认100行）
- 超时保护（单个文件分析不超过30秒）

# 修复：Integer exceeds 64-bit range

## 问题描述
用户上传4个文件进行智能分析时，系统提示 "处理失败: Integer exceeds 64-bit range"

## 根本原因
在读取Excel文件时，pandas将大整数（如长订单号 1234567890123456789）识别为 `int64` 或 `numpy.int64` 类型。当LangGraph尝试将状态数据序列化到checkpoint时，msgpack无法处理超过64位范围的整数，导致序列化失败。

## 修复内容

### 文件：`finance-mcp/reconciliation/mcp_server/tools.py`

#### 修复1：`_read_excel_sheets` 函数 (line 1075-1083)

**修复前**：
```python
sheet_info = {
    "sheet_name": sheet_name,
    "columns": list(df.columns),
    "row_count": len(df),
    "sample_data": df.fillna("").to_dict(orient="records")
}
```

**修复后**：
```python
# 提取样本数据，确保所有值都转换为字符串（避免大整数序列化问题）
sample = df.head(sample_rows).fillna("").to_dict(orient="records")
safe_sample = []
for row in sample:
    safe_sample.append({k: str(v) for k, v in row.items()})

sheet_info = {
    "sheet_name": sheet_name,
    "columns": [str(col) for col in df.columns],  # 确保列名也是字符串
    "row_count": int(len(df)),  # 确保是标准int
    "sample_data": safe_sample
}
```

#### 修复2：`_analyze_files` 函数 (line 880-883)

**已有保护**（无需修改）：
```python
sample = df.head(5).fillna("").to_dict(orient="records")
safe_sample = []
for row in sample:
    safe_sample.append({k: str(v) for k, v in row.items()})
```

## 修复原理

1. **数值转字符串**：将所有数据值通过 `str(v)` 转换为字符串
   - `1234567890123456789` (int64) → `"1234567890123456789"` (str)
   - 字符串可以安全地通过msgpack序列化

2. **列名标准化**：`[str(col) for col in df.columns]`
   - 防止pandas特殊列名类型导致的问题

3. **行数类型安全**：`int(len(df))`
   - 确保是Python标准int，而不是numpy.int64

## 测试验证

### 测试场景
- ✅ 上传包含大整数的Excel文件（订单号 > 10^18）
- ✅ 多sheet文件智能识别
- ✅ 4个文件智能配对
- ✅ LangGraph状态序列化

### 预期结果
- ✅ 不再出现 "Integer exceeds 64-bit range" 错误
- ✅ 智能分析正常完成
- ✅ 文件配对推荐正常显示

## 相关文件
- `finance-mcp/reconciliation/mcp_server/tools.py` - MCP工具层修复
- `finance-agents/data-agent/app/graphs/reconciliation/helpers.py` - 使用修复后的工具
- `finance-agents/data-agent/app/graphs/reconciliation/nodes.py` - file_analysis_node调用

## 版本信息
- 修复日期：2026-02-25
- 修复版本：v1.0.1
- 影响范围：智能文件分析功能

## 回归风险
- ✅ 低风险：只改变了数据类型（int→str），不影响业务逻辑
- ✅ 向后兼容：字符串类型的数值在后续处理中可以正常使用
- ✅ 性能影响：微乎其微（仅样本数据转换，通常<100行）

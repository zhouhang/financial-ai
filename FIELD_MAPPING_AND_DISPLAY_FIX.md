# 字段映射和显示优化修复

## 问题 1: 用户明确指定文件被忽略

### 问题描述
用户说"文件2的product_price除以100"，但系统识别成了"文件1的product_price除以100"。

原因：LLM 根据字段名判断数据源，而不是根据用户明确指定的文件。product_price 在业务数据(文件1)中，所以系统自动归到 business，忽略了用户的"文件2"指定。

### 修复方案
修改了 `_parse_rule_config_json_snippet` 中的 LLM prompt，**提升用户明确指定的优先级**：

**新的规则优先级**（从高到低）：
1. **🔴 规则1（最高优先级）**：用户明确指定文件
   - 用户说"文件1"或"业务" → 必须配置到 business，**无论字段名如何**
   - 用户说"文件2"或"财务" → 必须配置到 finance，**无论字段名如何**
   - **用户的明确指定永远优先于字段名判断**

2. **规则2（次优先级）**：根据字段名判断数据源  
   - 仅当**用户没有明确指定文件**时，才使用字段名判断
   - 如果字段在业务数据 → business
   - 如果字段在财务数据 → finance

3. **规则3**：两文件都配置情况
   - 仅当用户说"两个都"或"同时"时

### 修改的地方
📝 文件：`finance-agents/data-agent/app/graphs/reconciliation.py`
📍 行：~850 - `_parse_rule_config_json_snippet` 函数的 LLM prompt

### 示例修复
```
用户输入：文件2的product_price除以100
新规则识别：
  ✓ 用户明确说"文件2" → 配置到 finance
  ✓ 忽略字段名，不根据product_price在业务数据中自动改为business

结果：✅ 正确配置到 finance
```

---

## 问题 2: 显示"文件1"和"文件2"而不是真实文件名

### 问题描述
系统显示"📁 业务文件(文件1)"和"📁 财务文件(文件2)"，而用户上传的实际文件名可能是"business_2024.csv"和"finance_2024.csv"。

### 修复方案
修改了格式化函数以支持传入**实际文件名**：

#### 修改 1：`_analyze_config_target` 函数
添加了 `file_names` 参数：
```python
def _analyze_config_target(json_snippet: dict, file_names: dict[str, str] | None = None) -> str:
    """
    Args:
        file_names: 文件名映射，格式 {"business": "业务文件名", "finance": "财务文件名"}
    """
```

**改进**：
- 如果提供了文件名，显示真实文件名（如"sales.csv"）而不是"文件1"
- 如果没有提供，使用默认值"业务文件(文件1)"

#### 修改 2：`_format_operations_summary` 函数
添加了 `file_names` 参数，显示字段映射操作时使用真实文件名：

```
之前：✏️ 文件1（业务数据）修改 order_id: 新列名
之后：✏️ sales.csv 修改 order_id: 新列名  (如果用户上传的文件名是 sales.csv)
```

#### 修改 3：`_format_rule_config_items` 函数
添加了 `file_names` 参数，显示规则配置时使用真实文件名：

```
之前：
  1. 📁 业务文件(文件1) product_price除以100
  2. 📁 财务文件(文件2) 发生-除以100

之后：
  1. 📁 sales_order.csv product_price除以100
  2. 📁 finance_detail.xlsx 发生-除以100
```

#### 修改 4：`rule_config_node` 函数
在显示配置前构建**文件名映射**：

```python
# 构建文件名映射（从 file_analyses 中获取实际文件名）
file_names = {}
file_analyses = state.get("file_analyses", [])
for analysis in file_analyses:
    source = analysis.get("guessed_source", "")
    filename = analysis.get("filename", "")
    if source == "business" and filename:
        file_names["business"] = filename
    elif source == "finance" and filename:
        file_names["finance"] = filename
```

然后将 `file_names` 传给所有格式化函数：
```python
config_display = _format_rule_config_items(config_items, file_names)
updated_config_display = _format_rule_config_items(new_config_items, file_names)
```

### 修改的地方
📝 文件：`finance-agents/data-agent/app/graphs/reconciliation.py`

📍 行 260：`_format_operations_summary` 函数
📍 行 1021：`_analyze_config_target` 函数  
📍 行 1057：`_format_rule_config_items` 函数
📍 行 1137：`rule_config_node` 函数（构建文件名映射）
📍 行 1160、1267、1349、1366：传入 `file_names` 参数的调用

### 示例修复
```
用户上传文件：sales_2024.csv 和 finance_2024.csv

之前显示：
  1. 📁 业务文件(文件1) product_price除以100转换
  2. 📁 财务文件(文件2) 发生-除以100转换

之后显示：
  1. 📁 sales_2024.csv product_price除以100转换
  2. 📁 finance_2024.csv 发生-除以100转换
```

---

## 额外修复：列别名删除功能

### 新的操作类型 `delete_column`

当用户想删除字段中的某个列别名（而不是整个字段）时：

**新操作格式**：
```json
{
  "action": "delete_column",  # 新操作类型
  "target": "business",       # 数据源
  "role": "amount",           # 字段名（保留）
  "column": "pay_amt",        # 要删除的列别名
  "description": "删除pay_amt列别名"
}
```

**例子**：
```
当前映射：
  amount: ["pay_amt", "金额"]

用户说：去掉pay_amt

执行后：
  amount: ["金额"]  ✓ 保留了"金额"列别名
```

### 修改的地方
📝 文件：`finance-agents/data-agent/app/graphs/reconciliation.py`

📍 行 172：`_apply_field_mapping_operations` 函数
  - 添加了 `elif action == "delete_column":` 分支
  - 处理列表中的删除：`updated_list = [col for col in existing if col != column]`
  - 如果列表删除后为空，删除整个字段
  - 如果是字符串，检查后删除

📍 行 260：`_format_operations_summary` 函数
  - 添加了对 `delete_column` 操作的格式化支持
  - 显示：`🚫 {文件名} 从 {role} 中移除列别名: {column}`

📍 行 325：LLM prompt 中的示例和规则
  - 新增示例：
    ```json
    - {"action": "delete_column", "target": "business", "role": "amount", "column": "pay_amt", "description": "仅删除文件1的amount字段中的pay_amt列别名，保留其他列"}
    ```
  - 新增规则说明区分"删除字段"和"删除列别名"

---

## 测试清单

- [ ] 用户明确指定文件时是否被正确识别
  - [ ] "文件2的product_price" → finance（即使product_price在business中）
  - [ ] "财务数据的amount" → finance
  - [ ] "业务的order_id" → business

- [ ] 文件名显示是否使用真实文件名
  - [ ] 上传 sales.csv + finance.xlsx
  - [ ] 查看配置显示 "sales.csv" 而不是 "文件1"

- [ ] 列别名删除功能
  - [ ] 删除列表中的一个别名（保留其他）
  - [ ] 删除唯一的列别名（删除整个字段）

- [ ] 优先级验证
  - [ ] 用户明确指定 > 字段名自动判断
  - [ ] "文件2的product_price" 优先级最高

---

## 部署步骤

1. ✅ 代码修改完成
2. ✅ 语法检查通过
3. ⏳ 服务部署中...
4. ⏳ 测试验证中...

---

## 快速参考

### 修改的函数签名

```python
# 之前
def _format_operations_summary(operations: list[dict[str, Any]]) -> str:

# 现在
def _format_operations_summary(operations: list[dict[str, Any]], 
                              file_names: dict[str, str] | None = None) -> str:

---

# 之前
def _analyze_config_target(json_snippet: dict) -> str:

# 现在  
def _analyze_config_target(json_snippet: dict, 
                          file_names: dict[str, str] | None = None) -> str:

---

# 之前
def _format_rule_config_items(config_items: list[dict] = None) -> str:

# 现在
def _format_rule_config_items(config_items: list[dict] = None,
                             file_names: dict[str, str] | None = None) -> str:
```

### 文件名映射构建

```python
file_names = {}
for analysis in state.get("file_analyses", []):
    source = analysis.get("guessed_source", "")
    filename = analysis.get("filename", "")
    if source == "business" and filename:
        file_names["business"] = filename
    elif source == "finance" and filename:
        file_names["finance"] = filename
```

### 新的 LLM 规则（优先级）

| 优先级 | 规则 | 说明 |
|--------|------|------|
| 🔴 最高 | 用户明确指定文件 | 用户说"文件2"就配到finance，忽略字段名 |
| 🟡 次高 | 根据字段名判断 | 仅当用户未明确指定时 |
| 🟢 最低 | 为两个文件都配置 | 仅当用户说"两个都" |

---

## 版本信息

- **修复版本**：v2.1
- **涉及文件**：`finance-agents/data-agent/app/graphs/reconciliation.py`
- **修改行数**：~80 行代码修改
- **新增操作类型**：1 个 (`delete_column`)
- **改进的函数**：4 个（`_format_operations_summary`, `_analyze_config_target`, `_format_rule_config_items`, `rule_config_node`）


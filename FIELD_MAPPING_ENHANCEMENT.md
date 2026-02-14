# 字段映射增强功能文档

## 概述

字段映射阶段（第2步）已增强，现在支持更灵活的字段操作：
- ✅ **添加新字段映射** (add)
- ✅ **修改现有字段映射** (update)  
- ✅ **删除字段映射** (delete)
- ✅ **同时操作两个文件** 或 **单个文件操作**

## 核心改进

### 1. 操作类型支持

系统现在可以理解并执行以下操作：

```json
{
  "action": "add|update|delete",
  "target": "business|finance",           // 文件1或文件2
  "role": "order_id|amount|date|status",  // 字段角色
  "column": "列名或[列名1, 列名2]"         // 映射的列名
}
```

### 2. 用户指令示例

#### 示例1：只修改一个文件的字段
```
文件1的订单号改为"订单ID"
```
**预期操作**：
- 更新 business 文件的 order_id 映射为 "订单ID"

#### 示例2：添加新字段到一个文件
```
文件2添加status字段，对应"订单状态"列
```
**预期操作**：
- 在 finance 文件添加 status 映射为 "订单状态"

#### 示例3：删除字段映射
```
删除文件1的status字段映射
```
**预期操作**：
- 从 business 文件删除 status 字段

#### 示例4：同时操作两个文件
```
两个文件都添加status字段。文件1对应"订单状态"，文件2对应"status"
```
**预期操作**：
- 在 business 文件添加 status = "订单状态"
- 在 finance 文件添加 status = "status"

#### 示例5：混合操作多个文件
```
文件1: 订单号改为"orderId"，删除status。文件2: 添加status对应"order_status"
```
**预期操作**：
- 更新 business 的 order_id
- 删除 business 的 status
- 添加 finance 的 status

## 技术架构

### 新增函数

#### `_apply_field_mapping_operations(current_mappings, operations)`
**功能**：根据操作列表执行字段映射调整
**参数**：
- `current_mappings`: 当前的字段映射字典
- `operations`: 操作列表

**返回**：调整后的映射字典

#### `_format_operations_summary(operations)`
**功能**：将操作列表格式化为用户友好的文本摘要
**输出样例**：
```
  ➕ 文件1（业务数据） 添加 status: 订单状态
  ✏️ 文件2（财务数据） 修改 order_id: 新列名
  ❌ 文件1（业务数据） 删除 status
```

#### `_adjust_field_mappings_with_llm()` 改进
**功能**：使用LLM解析用户指令生成结构化操作
**返回值**：`(调整后的映射, 操作列表)`

### LLM Prompt 增强

新prompt包含：
- ✅ 对操作类型（add/update/delete）的明确指示
- ✅ 对目标文件（business/finance）的部分（"文件1" vs "文件2"）识别
- ✅ 对规则的严格约束（不删除必需字段）
- ✅ 结构化操作列表返回格式

## 使用流程

### 用户交互流程

1. **上传文件** → 系统自动分析并推荐字段映射

2. **第2步：确认字段映射**
   - 显示各字段对应关系
   - 提示用户操作选项

3. **用户选择**：
   - ✅ 输入"确认" → 进入下一步
   - 📝 输入调整指令 → 系统处理

4. **系统处理调整指令**
   ```
   用户输入 
     ↓
   LLM解析生成操作列表
     ↓  
   应用操作修改映射
     ↓
   显示操作摘要
     ↓
   重新展示更新后的映射
   ```

5. **用户再次确认** → 继续或继续调整

## 操作规则

### ✅ 允许的操作

| 操作 | 适用字段 | 说明 |
|------|--------|------|
| add | order_id, amount, date, status | 添加新的字段映射 |
| update | 所有 | 修改现有字段的列名映射 |
| delete | status 仅 | 删除可选字段（only status） |

### ❌ 不允许的操作

- ❌ 删除 `order_id`, `amount`, `date`（必需字段）
- ❌ 添加无效的字段角色（仅支持 order_id, amount, date, status）
- ❌ 为不存在的文件执行操作

## 错误处理

### 场景1：LLM 无法理解用户指令
```
系统响应：
⚠️ 已记录你的调整意见，但未能自动解析。请详细描述需要修改的地方：
```
→ 用户需要用更清晰的表述重新输入

### 场景2：尝试删除必需字段  
```
LLM prompt中明确禁止：
"不要生成删除order_id、amount、date的操作（这些是必需的）"
```

### 场景3：指定的列名不存在
```
系统记录警告，操作跳过：
⚠️ 字段 {role} 不存在于 {target} 中，跳过 {action}
```

## 集成示例

### 与规则配置的关联

调整完字段映射后，系统进入第3步（规则配置）。
在该阶段，LLM 已知道：
- ✅ 每个data source的确切字段映射
- ✅ 通过`field_mappings`参数传递
- ✅ 可以防止错误的跨源转换

参考：[FIELD_TRANSFORMATION_FIX.md](./FIELD_TRANSFORMATION_FIX.md)

## 测试场景

### 测试1：简单的字段更新
```
输入：文件1的订单号改为"order_num"
预期：business.order_id = "order_num"
```

### 测试2：添加status字段
```
输入：两个文件都添加status字段。文件1对应"state"，文件2对应"status"
预期：
- business.status = "state"
- finance.status = "status"
```

### 测试3：删除可选字段
```
输入：删除文件1的status
预期：business字典中删除status键
```

### 测试4：复杂混合操作（实际使用场景）
```
输入：
文件1（Tencent业务）: 订单号改为"order_id"，金额改为"amount_in_cents"
文件2（财务报表）: 金额改为"income_amount"
```
**预期操作**：
- ✏️ 更新 business.order_id = "order_id"
- ✏️ 更新 business.amount = "amount_in_cents"  
- ✏️ 更新 finance.amount = "income_amount"

## 性能说明

- ⚡ 每次调整触发一次LLM调用
- ⚡ LLM温度设置为0.1（低温度=更确定性的输出）
- 📊 操作应用时间 < 100ms
- 📊 完整调整周期 < 5s（包括LLM延迟）

## 未来扩展

- [ ] 支持条件性字段映射（如"如果X为空，使用Y"）
- [ ] 支持字段转换规则在映射阶段
- [ ] 支持字段别名（多个列名映射到同一个role）
- [ ] UI中支持图形化字段拖拽编辑

---

## 相关文档

- [ARCHITECTURE_FIX_REPORT.md](./ARCHITECTURE_FIX_REPORT.md) - 早期的字段映射实现
- [FINAL_ARCHITECTURE.md](./FINAL_ARCHITECTURE.md) - 系统整体架构
- [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) - 详细架构说明

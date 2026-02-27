# Skill: 审计数据整理 (Audit Data Organizer)

## 基本信息

- **Skill ID**: `AUDIT-DATA-ORGANIZER-001`
- **版本**: 3.0
- **创建日期**: 2026-02-26
- **最后更新**: 2026-02-27
- **作者**: 数据整理数字员工团队
- **状态**: ✅ 已启用
- **所属 Agent**: 数据整理数字员工 (Data-Process Agent)

---

## 一、功能描述

本 Skill 是**数据整理数字员工**的一个专业技能，专门用于处理审计部门的数据整理业务。通过意图识别自动调用对应的业务规则文件，处理不同的财务数据整理业务。

**核心能力**:
1. **意图识别**: 根据用户请求自动识别业务类型（货币资金、流水分析、应收账款等）
2. **规则加载**: 从 `references/` 目录加载对应的业务规则文件
3. **脚本执行**: 调用或生成 Python 脚本执行数据处理
4. **结果输出**: 生成标准化的 Excel 和 Markdown 格式结果

**支持的业务类型**:

| 意图编码 | 业务名称 | 规则文件 | 脚本文件 |
|----------|----------|----------|----------|
| `cash_funds` | 货币资金 | `references/cash_funds_rule.md` | `scripts/cash_funds_rule.py` |
| `transaction_analysis` | 流水分析 | `references/transaction_analysis_rule.md` | `scripts/transaction_analysis_rule.py` |
| `accounts_receivable` | 应收账款 | `references/accounts_receivable_analysis_rule.md` | `scripts/accounts_receivable_rule.py` |
| `inventory_analysis` | 库存商品 | `references/inventory_analysis_rule.md` | `scripts/inventory_analysis_rule.py` |
| `bank_account_check` | 开户清单核对 | `references/bank_account_check_rule.md` | `scripts/bank_account_check_rule.py` |

---

## 二、在 Agent 中的位置

```
数据整理数字员工 (Data-Process Agent)
├── 核心框架
│   ├── Skill Manager (技能管理器)
│   ├── Script Generator (脚本生成器)
│   └── Execution Engine (执行引擎)
├── Skills (技能集合)
│   ├── audit/ (审计数据整理 Skill) ← 本 Skill
│   │   ├── SKILL.md (技能定义)
│   │   ├── references/ (规则文件)
│   │   └── scripts/ (处理脚本)
│   └── [其他业务 Skill] (待扩展)
└── 公共目录
    ├── data/ (原始数据)
    └── result/ (处理结果)
```

---

## 三、输入数据

### 3.1 数据源

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `user_request` | str | ✅ | 用户的自然语言请求描述 |
| `files` | list[str] | ✅ | 上传的文件路径列表 |
| `output_dir` | str | ❌ | 输出目录，默认为 `result/` |

### 3.2 数据格式

| 格式类型 | 支持扩展名 | 说明 |
|----------|-----------|------|
| Excel | `.xlsx`, `.xls` | 科目余额表、银行对账单、流水明细等 |
| PDF | `.pdf` | 银行回单、对账单（需 OCR） |
| 图片 | `.png`, `.jpg` | 扫描件（需 OCR） |

### 3.3 数据要求

| 要求项 | 说明 |
|--------|------|
| 文件编码 | UTF-8 或 GBK |
| 表头要求 | 第一行为列名，支持中文列名 |
| 数据完整性 | 不允许空行，关键列不允许空值 |
| 金额格式 | 支持千位分隔符，支持负数括号表示 |

---

## 四、处理规则

### 4.1 意图识别规则

根据用户请求中的关键词匹配业务类型：

| 意图编码 | 关键词列表 |
|----------|-----------|
| `cash_funds` | 货币资金、现金、银行存款、资金明细、资金核对 |
| `transaction_analysis` | 流水、交易明细、银行流水、流水分析、交易分析 |
| `accounts_receivable` | 应收、账款、客户往来、应收账款、应收分析 |
| `inventory_analysis` | 库存、存货、商品、仓储、库存分析、存货分析 |
| `bank_account_check` | 开户、清单、核对、账户清单、开户清单 |

**识别算法**:
```python
def identify_intent(user_request: str) -> str:
    """
    根据用户请求识别业务意图

    参数:
        user_request: 用户的请求描述

    返回:
        意图类型编码（如 'cash_funds'）

    规则:
        1. 提取请求中的关键词
        2. 计算每个意图的匹配分数
        3. 返回匹配分数最高的意图
        4. 如果无匹配，返回默认意图 'cash_funds'
    """
```

### 4.2 规则文件加载规则

**规则文件路径映射**:

```python
RULE_FILE_MAPPING = {
    'cash_funds': 'references/cash_funds_rule.md',
    'transaction_analysis': 'references/transaction_analysis_rule.md',
    'accounts_receivable': 'references/accounts_receivable_analysis_rule.md',
    'inventory_analysis': 'references/inventory_analysis_rule.md',
    'bank_account_check': 'references/bank_account_check_rule.md'
}
```

**加载规则**:
1. 根据意图类型查找对应的规则文件路径
2. 检查规则文件是否存在
3. 读取并解析规则文件内容
4. 提取规则中的关键信息（数据源、输出字段、处理规则等）

### 4.3 脚本执行规则

**脚本文件路径映射**:

```python
SCRIPT_FILE_MAPPING = {
    'cash_funds': 'scripts/cash_funds_rule.py',
    'transaction_analysis': 'scripts/transaction_analysis_rule.py',
    'accounts_receivable': 'scripts/accounts_receivable_rule.py',
    'inventory_analysis': 'scripts/inventory_analysis_rule.py',
    'bank_account_check': 'scripts/bank_account_check_rule.py'
}
```

**执行优先级**:
1. **优先调用现有脚本**: 如果 `scripts/{intent}_rule.py` 存在，直接执行
2. **自动生成脚本**: 如果脚本不存在但规则文件存在，根据规则自动生成
3. **错误处理**: 如果规则和脚本都不存在，返回错误提示

**脚本执行参数**:
```bash
python scripts/{intent}_rule.py --input <文件路径> --output-dir <输出目录>
```

### 4.4 数据处理流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据处理流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 接收用户请求                                                 │
│     ↓                                                           │
│  2. 意图识别 → 确定业务类型                                      │
│     ↓                                                           │
│  3. 检查脚本是否存在                                             │
│     ├── 存在 → 直接执行脚本                                      │
│     └── 不存在 → 检查规则文件                                     │
│         ├── 存在 → 自动生成脚本 → 执行                            │
│         └── 不存在 → 返回错误提示                                 │
│     ↓                                                           │
│  4. 执行数据处理                                                 │
│     ├── 读取输入文件                                             │
│     ├── 识别数据源                                               │
│     ├── 应用处理规则                                             │
│     └── 生成输出结果                                             │
│     ↓                                                           │
│  5. 返回处理结果                                                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、输出结果

### 5.1 输出格式

| 格式 | 说明 | 文件扩展名 |
|------|------|-----------|
| Excel | 结构化数据，支持多 Sheet | `.xlsx` |
| Markdown | 可读性好的文本格式 | `.md` |
| JSON | 机器可读的结构化数据 | `.json` |

### 5.2 输出位置

- **默认输出目录**: `result/`
- **输出文件命名**: `{业务类型}_{timestamp}.{ext}`
- **示例**: `result/cash_funds_20260226_100000.xlsx`

### 5.3 输出数据结构

**标准输出结构**:

```json
{
    "skill_id": "AUDIT-DATA-ORGANIZER-001",
    "intent_type": "cash_funds",
    "rule_file": "references/cash_funds_rule.md",
    "status": "success",
    "data": {
        "sheet_name": "货币资金明细表",
        "headers": ["序号", "科目名称", "核算项目", "期初金额", "本期借方", "本期贷方", "期末金额", "银行对账单金额", "差异", "账户性质", "备注"],
        "rows": [...],
        "summary": {...}
    },
    "metadata": {
        "processed_at": "2026-02-26T10:00:00Z",
        "source_files": ["科目余额表.xlsx", "银行对账单.xlsx"],
        "record_count": 10,
        "script_path": "scripts/cash_funds_rule.py"
    }
}
```

**错误输出结构**:

```json
{
    "skill_id": "AUDIT-DATA-ORGANIZER-001",
    "intent_type": "cash_funds",
    "rule_file": "references/cash_funds_rule.md",
    "status": "error",
    "error": {
        "code": "DATA_SOURCE_NOT_FOUND",
        "message": "未找到科目余额表数据源",
        "suggestion": "请上传包含'科目余额表'的文件"
    }
}
```

---

## 六、依赖关系

### 6.1 依赖 Agent

| 依赖项 | 说明 |
|--------|------|
| **数据整理数字员工** | 本 Skill 运行在数据整理数字员工平台上，依赖其核心框架提供的环境 |

### 6.2 依赖库

| 库名 | 版本 | 用途 |
|------|------|------|
| `pandas` | >=2.0 | 数据处理 |
| `openpyxl` | >=3.0 | Excel 文件读写 |
| `markdown` | >=3.0 | Markdown 格式输出 |
| `pathlib` | 内置 | 路径处理 |
| `subprocess` | 内置 | 脚本执行 |
| `re` | 内置 | 正则表达式匹配 |

### 6.3 依赖文件

| 文件类型 | 路径 | 说明 |
|----------|------|------|
| 规则文件 | `references/{业务类型}_rule.md` | 业务规则定义 |
| 脚本文件 | `scripts/{业务类型}_rule.py` | Python 处理脚本 |

---

## 七、异常处理

### 7.1 异常类型及处理

| 异常代码 | 异常名称 | 触发条件 | 处理方式 |
|----------|----------|----------|----------|
| `INTENT_NOT_RECOGNIZED` | 意图识别失败 | 用户请求无法匹配任何已知意图 | 使用默认意图或提示用户澄清 |
| `RULE_FILE_NOT_FOUND` | 规则文件缺失 | 意图对应的规则文件不存在 | 返回错误提示，建议联系管理员 |
| `SCRIPT_EXECUTION_FAILED` | 脚本执行失败 | Python 脚本执行出错 | 捕获错误日志，返回错误详情 |
| `SCRIPT_TIMEOUT` | 脚本执行超时 | 脚本执行超过 5 分钟 | 终止执行，返回超时提示 |
| `DATA_SOURCE_NOT_FOUND` | 数据源缺失 | 未找到所需的数据文件 | 提示用户上传对应文件 |
| `DATA_FORMAT_ERROR` | 数据格式错误 | 文件格式不符合要求 | 提示用户检查文件格式 |
| `OUTPUT_DIR_NOT_WRITABLE` | 输出目录不可写 | 无法写入输出目录 | 创建目录或返回权限错误 |

---

## 八、示例

### 8.1 货币资金处理示例

**用户请求**:
```
请帮我整理货币资金明细表，我有科目余额表和银行对账单
```

**处理流程**:
1. 识别意图：`cash_funds`（匹配关键词"货币资金"）
2. 检查脚本：`scripts/cash_funds_rule.py` 存在 ✅
3. 执行脚本处理
4. 返回结果

**输入文件**:
- `data/科目余额表.xlsx`
- `data/银行对账单.xlsx`

**输出结果**:
- `result/cash_funds_20260226_100000.xlsx`
- `result/cash_funds_20260226_100000.md`

---

### 8.2 流水分析示例

**用户请求**:
```
帮我分析一下银行流水，看看有没有异常交易
```

**处理流程**:
1. 识别意图：`transaction_analysis`（匹配关键词"流水"、"分析"）
2. 加载规则：`references/transaction_analysis_rule.md`
3. 执行数据处理
4. 返回流水分析报告

**输入文件**:
- `data/银行流水.xlsx`

**输出结果**:
- `result/transaction_analysis_20260226_100000.xlsx`

---

## 九、LangGraph 集成说明

### 9.1 作为 Agent 的 Skill

本 Skill 是数据整理数字员工的一个子模块，通过 LangGraph 子图实现：

```python
# proc-agent/skills/audit/skill_graph.py

from langgraph.graph import StateGraph, END

def build_audit_skill_subgraph() -> StateGraph:
    """构建审计数据整理 Skill 子图"""
    builder = StateGraph(AuditSkillState)
    
    # 添加节点
    builder.add_node("intent_identification", intent_identification_node)
    builder.add_node("rule_loading", rule_loading_node)
    builder.add_node("script_execution", script_execution_node)
    
    # 设置流程
    builder.set_entry_point("intent_identification")
    builder.add_edge("intent_identification", "rule_loading")
    builder.add_edge("rule_loading", "script_execution")
    builder.add_edge("script_execution", END)
    
    return builder
```

### 9.2 在 Agent 中的调用

```python
# proc-agent/main_graph.py

from skills.audit.skill_graph import build_audit_skill_subgraph

def build_main_graph() -> StateGraph:
    """构建数据整理数字员工主图"""
    builder = StateGraph(AgentState)
    
    # 添加审计 Skill 子图
    builder.add_node("audit_skill", build_audit_skill_subgraph().compile())
    
    # 添加路由逻辑
    builder.add_conditional_edges(
        "router",
        route_to_skill,
        {
            "audit": "audit_skill",
            # 其他 skill...
        }
    )
    
    return builder
```

---

## 十、相关文件

| 文件类型 | 路径 | 说明 |
|----------|------|------|
| Skill 定义 | `skills/audit/SKILL.md` | 本技能定义文件 |
| 规则文件 | `skills/audit/references/cash_funds_rule.md` | 货币资金业务规则 |
| 脚本文件 | `skills/audit/scripts/cash_funds_rule.py` | 货币资金处理脚本 |
| Agent 主目录 | `../../` | 数据整理数字员工根目录 |

---

**文档版本**: 3.0  
**创建日期**: 2026-02-26  
**最后更新**: 2026-02-27  
**维护者**: 数据整理数字员工团队

---
name: recognition-report-filler
description: 将手工凭证 Excel 中的数据提取并填充到 BI 报表中。触发关键词：手工凭证、BI费用明细、BI费用、BI损益、损益毛利、核算报表、核算明细、毛利分析、供应商毛利、代运营毛利、费用归集。输入文件：手工凭证.xlsx（必填）+ 可选的BI费用明细表.xlsx + 可选的BI损益毛利明细表.xlsx。输出：生成或填充后的 BI费用明细表.xlsx 和 BI损益毛利明细表.xlsx。
metadata:
  author: 数据整理数字员工团队
  version: "3.0"
allowed-tools: read_file, write_file, execute_python
---

# Skill: 核算报表填充 (Recognition Report Filler)

## 基本信息

- **Skill ID**: `RECOGNITION-REPORT-FILL-001`
- **版本**: 3.0
- **创建日期**: 2026-03-02
- **最后更新**: 2026-03-08
- **作者**: 数据整理数字员工团队
- **状态**: ✅ 已启用
- **所属 Agent**: 数据整理数字员工 (Data-Process Agent)

---

## 一、功能描述

本 Skill 是**数据整理数字员工**的一个专业技能，专门用于将**手工凭证 Excel** 中的数据提取并填充到 BI 报表中。

**两种运行模式**:

| 模式 | 触发条件 | 行为 |
|------|----------|------|
| **自动生成模式** | 仅上传手工凭证（未上传 BI 表） | 根据数据规则自动生成完整的 BI费用明细表 和 BI损益毛利明细表 |
| **追加同步模式** | 上传手工凭证 + 任意一个或两个 BI 表 | 将自动生成的数据同步追加到用户已有的 BI 表末尾，保留原有数据 |

**脚本优先策略**:
- 若 `scripts/recognition_rule.py` 文件存在，**直接调用**该脚本进行业务处理
- 若脚本不存在，根据规则文件重新生成脚本后再执行

**输入文件**:
1. 手工凭证 Excel（**必填**）——数据提取源
2. BI费用明细表 Excel（**可选**）——已有数据，若提供则追加同步；若未提供则自动生成
3. BI损益毛利明细表 Excel（**可选**）——已有数据，若提供则追加同步；若未提供则自动生成

**核心能力**:
1. **文件自动识别**: 自动判断上传的文件分别是哪种类型（凭证/费用表/毛利表）
2. **凭证数据解析**: 从手工凭证 Excel 中提取会计分录数据，识别借贷方科目、金额、摘要等信息
3. **BI 费用明细表处理**: 按费用科目过滤与字段映射，生成或追加费用数据
4. **BI 损益毛利明细表处理**: 按收入/成本科目过滤与销售商维度汇总，生成或追加毛利行
5. **格式保留**: 若用户提供已有表，列名/样式/单元格格式均完整保留，仅新增数据行
6. **文件下载**: 将处理后的完整 Excel 存放到当前用户的 result 目录，返回可下载 URL

**支持的输出报表**:

| 报表名称 | 输出文件名 | 说明 |
|----------|------------|------|
| BI 费用明细表 | `BI费用明细表.xlsx` | 自动生成 或 已有表 + 手工凭证费用数据追加后的完整表 |
| BI 损益毛利明细表 | `BI损益毛利明细表.xlsx` | 自动生成 或 已有表 + 手工凭证毛利汇总数据追加后的完整表 |

---

## 二、在 Agent 中的位置

```
数据整理数字员工 (Data-Process Agent)
├── 核心框架
│   ├── Skill Manager (技能管理器)
│   ├── Script Generator (脚本生成器)
│   └── Execution Engine (执行引擎)
├── Skills (技能集合)
│   ├── audit/ (审计数据整理 Skill)
│   └── recognition/ (核算报表填充 Skill) ← 本 Skill
│       ├── SKILL.md (技能定义)
│       ├── references/ (规则文件)
│       │   └── recognition_rule.md (处理规则)
│       ├── scripts/ (处理脚本)
│       │   └── recognition_rule.py (数据处理脚本)
│       └── data/ (参考模板)
│           ├── AI自动化逻辑20260103.xlsx (逻辑规则参考模板)
│           ├── 手工凭证原表.xlsx (凭证数据示例)
│           ├── BI费用明细表.xlsx (费用表字段格式参考)
│           └── 供应商&代运营毛利表原表.xlsx (毛利表字段格式参考)
└── 公共目录
    ├── data/ (原始数据)
    └── result/ (处理结果)
```

---

## 三、触发条件

### 3.1 意图触发关键词

用户请求包含以下任意关键词时，触发本 Skill：

| 关键词组 | 优先级 | 说明 |
|----------|--------|------|
| `手工凭证` | 高 | 用户明确提到手工凭证文件 |
| `BI费用` / `BI费用明细` | 高 | 需要填充 BI 费用相关报表 |
| `BI损益` / `损益毛利` | 高 | 需要填充损益毛利报表 |
| `核算报表` / `核算明细` | 高 | 请求处理核算相关报表 |
| `凭证填充报表` / `凭证补充数据` | 高 | 从凭证数据填充报表 |
| `毛利明细` / `毛利分析` | 中 | 需要毛利数据分析 |
| `费用明细` + `凭证` | 中 | 费用明细与凭证相关联 |
| `供应商毛利` / `代运营毛利` | 中 | 供应商或代运营毛利分析 |

## 3.2 文件触发条件

用户上传包含手工凭证文件时触发（BI 两个表为可选）：

| 文件类型 | 识别特征 | 必填 |
|----------|----------|------|
| 手工凭证 | 文件名含"手工凭证"或"凭证" | ✅ 必填 |
| BI 费用明细表 | 文件名含"BI费用明细"或"费用明细表" | ❌ 可选 |
| BI 损益毛利明细表 | 文件名含"BI损益"、"损益毛利"或"供应商" | ❌ 可选 |

### 3.3 触发逻辑

```
触发条件 = (
    用户请求包含高优先级关键词
    AND 用户上传了含"凭证"的 Excel 文件
) OR (
    用户请求包含中优先级关键词 AND 用户上传了 Excel 文件
) OR (
    用户请求提到"填充报表"/"核算" AND 文件名含"凭证"
)

注意：BI 费用明细表和 BI 损益毛利明细表为可选，未上传时自动生成。
```

---

## 四、输入数据

### 4.1 数据源

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `user_request` | str | ✅ | 用户的自然语言请求描述 |
| `files` | list[str] | ✅ | 上传的文件路径列表（必须包含手工凭证，BI 两个表可选） |
| `output_dir` | str | ❌ | 输出目录，默认为 `result/{chat_id}/` |
| `chat_id` | str | ❌ | 用户会话 ID，用于隔离输出目录 |

### 4.2 文件要求

| 文件类型 | 文件名模式 | 必填 | 未提供时的行为 |
|----------|-----------|------|----------------|
| 手工凭证 Excel | `*手工凭证*.xlsx` / `*凭证*.xlsx` | ✅ **必填** | 无法处理，提示用户上传 |
| BI 费用明细表 Excel | `*BI费用明细*.xlsx` / `*费用明细表*.xlsx` | ❌ 可选 | 根据数据规则自动生成 |
| BI 损益毛利明细表 Excel | `*BI损益*.xlsx` / `*损益毛利*.xlsx` / `*供应商*.xlsx` | ❌ 可选 | 根据数据规则自动生成 |

### 4.3 数据格式

| 格式类型 | 支持扩展名 | 说明 |
|----------|-----------|------|
| Excel | `.xlsx`, `.xls` | 主要数据格式 |

---

## 五、处理规则

### 5.1 脚本执行策略（优先级最高）

```
1. 检查 scripts/recognition_rule.py 是否存在
   ├── 存在 → 直接调用该脚本（跳过脚本生成步骤）
   └── 不存在 → 根据 references/recognition_rule.md 规则重新生成脚本后执行
```

### 5.2 运行模式判断

```python
# 根据用户上传的文件数量自动判断运行模式
if bi_expense_file and bi_profit_file:
    mode = "sync"       # 追加同步模式：两个 BI 表均已提供
elif bi_expense_file or bi_profit_file:
    mode = "partial"    # 部分同步模式：仅提供其中一个 BI 表
else:
    mode = "generate"   # 自动生成模式：仅提供手工凭证
```

### 5.3 意图识别规则

```python
RECOGNITION_KEYWORDS = {
    "recognition_report": [
        "手工凭证", "BI费用", "BI费用明细", "BI损益", "损益毛利",
        "核算报表", "核算明细", "凭证填充报表", "毛利明细", "毛利分析",
        "供应商毛利", "代运营毛利", "费用归集",
        "凭证报表", "BI报表填充"
    ]
}
```

#### 5.4 处理流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     核算报表填充处理流程                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 接收用户请求 + 上传文件                                       │
│     ↓                                                           │
│  2. 检查 scripts/recognition_rule.py 是否存在                    │
│     ├── 存在 → 直接进入步骤 4（跳过脚本生成）                      │
│     └── 不存在 → 步骤 3：根据规则生成脚本                          │
│     ↓                                                           │
│  3. [仅脚本不存在时] 根据 recognition_rule.md 生成 py 脚本         │
│     ↓                                                           │
│  4. 文件自动识别（通过文件名/内容特征）                             │
│     ├── 识别手工凭证文件（voucher）—— 必填，不存在则报错             │
│     ├── 识别 BI 费用明细表（bi_expense）—— 可选                    │
│     └── 识别 BI 损益毛利明细表（bi_profit）—— 可选                 │
│     ↓                                                           │
│  5. 判断运行模式                                                  │
│     ├── 自动生成模式（无 BI 表）→ 从凭证全量生成两张 BI 表           │
│     ├── 追加同步模式（有 BI 表）→ 将新数据追加到已有表末尾            │
│     └── 部分同步模式（仅有1个 BI 表）→ 有表的追加，缺表的自动生成    │
│     ↓                                                           │
│  6. 读取手工凭证数据                                              │
│     ├── 自动识别 Sheet 和表头行                                   │
│     └── 数据清洗和规范化                                          │
│     ↓                                                           │
│  7. 处理 BI 费用明细表                                            │
│     ├── 过滤费用类科目（销售费用/管理费用/财务费用等）              │
│     ├── 字段映射（科目拆分、金额计算、日期转换等）                  │
│     ├── [追加模式] 使用 openpyxl 读取已有表，追加数据行             │
│     ├── [生成模式] 按标准字段格式从头生成完整表                     │
│     └── 保存为 BI费用明细表.xlsx                                  │
│     ↓                                                           │
│  8. 处理 BI 损益毛利明细表                                        │
│     ├── 过滤收入/成本类科目（主营业务收入/主营业务成本等）           │
│     ├── 按月份+供应商+公司+商品大类汇总毛利数据                    │
│     ├── [追加模式] 在合计行前插入新数据，重新计算合计行              │
│     ├── [生成模式] 按标准字段格式从头生成完整表                     │
│     └── 保存为 BI损益毛利明细表.xlsx                              │
│     ↓                                                           │
│  9. 保存到用户结果目录                                            │
│     └── result/{chat_id}/                                       │
│     ↓                                                           │
│  10. 返回处理后文件的下载 URL                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.5 脚本文件路径

```python
SCRIPT_FILE_MAPPING = {
    "recognition_report": "scripts/recognition_rule.py"
}

RULE_FILE_MAPPING = {
    "recognition_report": "references/recognition_rule.md"
}
```

---

## 六、输出结果

### 6.1 输出文件

| 文件名 | 格式 | 说明 |
|--------|------|------|
| `BI费用明细表.xlsx` | Excel | 用户上传的已有表 + 手工凭证费用数据填充后的完整版本 |
| `BI损益毛利明细表.xlsx` | Excel | 用户上传的已有表 + 手工凭证毛利汇总数据填充后的完整版本 |

### 6.2 输出位置

- **输出目录**: `result/{chat_id}/`
- **示例路径**: `result/abc123/BI费用明细表.xlsx`
- **下载 URL**: `http://{host}:{port}/result/{chat_id}/BI费用明细表.xlsx`

### 6.3 标准返回结构

```json
{
    "skill_id": "RECOGNITION-REPORT-FILL-001",
    "intent_type": "recognition_report",
    "status": "success",
    "result_files": [
        "result/abc123/BI费用明细表.xlsx",
        "result/abc123/BI损益毛利明细表.xlsx"
    ],
    "download_urls": [
        "http://localhost:8100/result/abc123/BI费用明细表.xlsx",
        "http://localhost:8100/result/abc123/BI损益毛利明细表.xlsx"
    ],
    "metadata": {
        "processed_at": "2026-03-04T10:00:00Z",
        "source_file": "手工凭证原表.xlsx",
        "bi_expense_file": "BI费用明细表.xlsx",
        "bi_profit_file": "BI损益毛利明细表.xlsx",
        "record_count": 100,
        "expense_appended_count": 45,
        "profit_appended_count": 12
    }
}
```

### 6.4 错误返回结构

```json
{
    "skill_id": "RECOGNITION-REPORT-FILL-001",
    "intent_type": "recognition_report",
    "status": "error",
    "error": {
        "code": "REQUIRED_FILE_MISSING",
        "message": "缺少必要文件: 手工凭证文件",
        "suggestion": "请上传手工凭证 Excel 文件（文件名应含「手工凭证」或「凭证」）。\nBI费用明细表和BI损益毛利明细表为可选文件，未上传时将根据凭证数据自动生成。"
    }
}
```

---

## 七、依赖关系

### 7.1 依赖库

| 库名 | 版本 | 用途 |
|------|------|------|
| `pandas` | >=2.0 | 数据处理和转换 |
| `openpyxl` | >=3.0 | Excel 文件读写（保留格式追加行） |
| `pathlib` | 内置 | 路径处理 |
| `json` | 内置 | 结构化输出 |
| `argparse` | 内置 | 命令行参数解析 |

### 7.2 依赖文件

| 文件类型 | 路径 | 说明 |
|----------|------|------|
| 规则文件 | `references/recognition_rule.md` | 业务处理规则定义 |
| 费用表字段参考 | `data/BI费用明细表.xlsx` | BI 费用明细表字段格式参考 |
| 毛利表字段参考 | `data/供应商&代运营毛利表原表.xlsx` | BI 损益毛利明细表字段格式参考 |

---

## 八、异常处理

| 异常代码 | 异常名称 | 触发条件 | 处理方式 |
|----------|----------|----------|-----------|
| `VOUCHER_FILE_MISSING` | 手工凭证缺失 | 未上传任何手工凭证文件 | 提示用户上传手工凭证，BI 表为可选 |
| `VOUCHER_FORMAT_ERROR` | 凭证格式错误 | 凭证文件不符合预期格式 | 提示检查文件格式 |
| `OUTPUT_GEN_FAILED` | 输出生成失败 | 生成/写入 Excel 文件时出错 | 返回错误详情，建议重试 |
| `OUTPUT_DIR_ERROR` | 输出目录错误 | 无法创建/写入结果目录 | 尝试备用目录 |
| `SCRIPT_GEN_FAILED` | 脚本生成失败 | 脚本不存在且根据规则生成失败 | 返回错误详情，提示联系管理员 |

---

## 九、示例

#### 9.1 标准使用示例（仅传手工凭证，自动生成模式）

**用户请求**:
```
根据上传的手工凭证生成BI报表
```

**上传文件**:
- `手工凭证原表202507月.xlsx`

**处理流程**:
1. 检查 `scripts/recognition_rule.py` → 存在，直接调用
2. 识别文件：手工凭证 ✅，BI费用明细表 ❌（未传），BI损益毛利明细表 ❌（未传）
3. 运行模式：**自动生成模式**
4. 从手工凭证提取全量数据，按规则生成完整的两张 BI 表
5. 返回生成文件下载链接

**输出结果**:
```
已成功生成以下报表，请点击下载：
- BI费用明细表: http://localhost:8100/result/{chat_id}/BI费用明细表.xlsx
- BI损益毛利明细表: http://localhost:8100/result/{chat_id}/BI损益毛利明细表.xlsx
```

### 9.2 追加同步示例（传手工凭证 + 两个 BI 表）

**用户请求**:
```
请将上传的凭证数据填充到 BI 费用明细表和 BI 损益毛利明细表中
```

**上传文件**:
- `手工凭证原表.xlsx`
- `BI费用明细表.xlsx`（已有数据不全的表）
- `BI损益毛利明细表.xlsx`（已有数据不全的表）

**处理流程**:
1. 检查 `scripts/recognition_rule.py` → 存在，直接调用
2. 识别文件：手工凭证 ✅，BI费用明细表 ✅，BI损益毛利明细表 ✅
3. 运行模式：**追加同步模式**
4. 读取手工凭证数据，将新数据追加到已有两张 BI 表末尾
5. 返回填充后文件下载链接

**输出结果**:
```
已成功填充以下报表，请点击下载：
- BI费用明细表: http://localhost:8100/result/{chat_id}/BI费用明细表.xlsx
- BI损益毛利明细表: http://localhost:8100/result/{chat_id}/BI损益毛利明细表.xlsx
```

### 9.3 缺少手工凭证时的错误提示

**用户请求**:
```
帮我生成BI报表
```

**未上传任何文件**

**返回错误提示**:
```
缺少必要文件：手工凭证文件
请上传手工凭证 Excel 文件（文件名应含「手工凭证」或「凭证」）
BI费用明细表和BI损益毛利明细表为可选文件，不传时将根据凭证数据自动生成。
```

---

## 十、LangGraph 集成说明

```python
# proc-agent/skills/recognition/skill_graph.py

from langgraph.graph import StateGraph, END

def build_recognition_skill_subgraph() -> StateGraph:
    """构建核算报表填充 Skill 子图"""
    builder = StateGraph(RecognitionSkillState)
    
    # 添加节点
    builder.add_node("file_recognition", file_recognition_node)
    builder.add_node("data_extraction", data_extraction_node)
    builder.add_node("expense_fill", expense_fill_node)
    builder.add_node("profit_fill", profit_fill_node)
    
    # 设置流程
    builder.set_entry_point("file_recognition")
    builder.add_edge("file_recognition", "data_extraction")
    builder.add_edge("data_extraction", "expense_fill")
    builder.add_edge("expense_fill", "profit_fill")
    builder.add_edge("profit_fill", END)
    
    return builder
```

---

## 十一、相关文件

| 文件类型 | 路径 | 说明 |
|----------|------|------|
| Skill 定义 | `skills/recognition/SKILL.md` | 本技能定义文件 |
| 规则文件 | `skills/recognition/references/recognition_rule.md` | 业务处理规则 |
| 脚本文件 | `skills/recognition/scripts/recognition_rule.py` | 数据处理脚本 |
| 逻辑模板 | `skills/recognition/data/AI自动化逻辑20260103.xlsx` | AI 逻辑规则参考 |
| 毛利格式 | `skills/recognition/data/供应商&代运营毛利表原表.xlsx` | 毛利表输出格式 |
| BI 费用模板 | `skills/recognition/data/BI费用明细表.xlsx` | BI 费用明细表字段格式参考 |

---

**文档版本**: 3.0
**创建日期**: 2026-03-02
**最后更新**: 2026-03-08
**维护者**: 数据整理数字员工团队

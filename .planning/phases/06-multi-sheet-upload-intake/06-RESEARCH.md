# Phase 06: Multi-Sheet Upload Intake - Research

**Researched:** 2026-04-22
**Domain:** file-based proc/recon multi-sheet workbook intake in existing FastAPI + MCP stack
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- 多 sheet 兼容必须落在上传输入层，不改 `proc DSL` / `recon DSL`。
- CSV 和单 sheet 文件保持原行为，多 sheet 工作簿拆成逻辑文件后再进入正式 `file_check`。
- 预筛选只过滤明显无效 sheet，不能代替正式 schema 匹配，更不能抢做唯一映射。
- 正式歧义继续由现有 `validate_files` 判定，并把 `candidate_mappings` 向上层透传。
- 逻辑文件命名必须唯一、稳定、可追溯到原工作簿和 sheet。
- `proc` 与 `recon` 必须共享同一套逻辑文件映射，不能形成两套 intake 行为。

### the agent's Discretion
- 共享工具模块的位置和拆分文件的具体落盘目录可以调整，但必须复用现有 `/uploads/...` 协议。
- 失败消息里是详细展示所有被过滤 sheet，还是只展示摘要，可在实现时决定。

### Deferred Ideas (OUT OF SCOPE)
- 在规则层增加 sheet 名约束
- 基于语义或 LLM 的说明页识别
- 前端人工勾选 sheet

</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 工作簿拆 sheet 和逻辑文件落盘 | API/Backend (`data-agent`) | MCP storage contract | 上传后的输入整理由共享 graph 入口接管最合适 |
| 正式 schema 匹配和唯一映射 | MCP (`file_validate_tool`) | API/Backend | 现有 `validate_files` 已是权威实现，不应复制第二套 |
| `proc` / `recon` 运行时按 `file_path` 读文件 | MCP runtime | API/Backend | 运行时并不关心文件来源，只关心映射是否正确 |
| 歧义和过滤结果对用户可解释展示 | API/Backend | Frontend/chat layer | 上层消息需要基于候选映射和保留/过滤摘要生成 |

</architectural_responsibility_map>

<research_summary>
## Summary

代码现状说明这次改造的关键不是 `proc` / `recon` DSL，也不是 `recon_tool.py` 或 `steps_runtime.py` 的执行核心，而是共享 file_check 入口的输入展开方式。现在 `public_nodes._read_header()` 对 Excel 只读取 `wb.active`，导致工作簿天然被简化成“只存在一个 sheet 的文件”。与此同时，`file_validate_tool.validate_files_against_rules()` 在真正接收到多个候选“文件”时，已经具备足够强的 schema 匹配与歧义检测能力。

因此最稳妥的方案是：
1. 在 `data-agent` 侧把多 sheet 工作簿拆成多个逻辑文件。
2. 用低风险预筛选先剔除明显不可能命中的 sheet，避免旧数量门槛和唯一映射被噪音污染。
3. 把保留下来的逻辑文件交回现有 `validate_files` 做权威匹配。
4. 让 `proc` / `recon` 后续都从同一份“逻辑上传文件列表”解析 `file_path`。

**Primary recommendation:** 在 `finance-agents/data-agent/utils/` 增加共享 intake 模块，统一处理“原始上传文件 -> 逻辑上传文件 -> 命名/映射/摘要”，然后在 `public_nodes.check_file_node()` 前后插入 split/prefilter 和错误摘要增强；不要把多 sheet 逻辑散落到 `proc` 和 `recon` 各自的节点中。

</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openpyxl | existing | 读取工作簿、遍历 sheet、写回拆分后的 `.xlsx` | 当前项目已经在 file_check 和导出里使用 |
| pandas | existing | `proc` / `recon` 运行时继续读取逻辑文件 | 现有 runtime 已稳定依赖 |
| FastAPI + LangGraph graphs | existing | 共享 file_check orchestration | 当前 `proc` / `recon` 都通过这里接入 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `finance-mcp/tools/file_validate_tool.py` | existing | 正式 schema 匹配和唯一映射 | 预筛选完成后必须继续走这里 |
| `finance-mcp/security_utils.py` | existing | `/uploads/...` 路径解析 | 逻辑文件落盘后供下游统一读取 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 输入层 split + prefilter | 修改 `proc` / `recon` DSL 支持 sheet | 会把底层规则、存量 rule_detail 和运行时全部扩散性改动 |
| 轻量结构化预筛选 | 基于文件名或 sheet 名硬匹配 schema | 风险高，且现有规则本来就主要靠表头而不是文件名 |
| 共享逻辑文件列表 | `proc` / `recon` 各自再拆一遍 workbook | 会导致行为漂移和后续排障困难 |

**Installation:**
```bash
# No new dependency is required for this phase.
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### System Architecture Diagram

```text
raw uploaded files
  ↓
normalize upload entries
  ↓
expand workbook sheets into logical upload files
  ↓
sheet-level prefilter
  ├─ drop obvious invalid sheets
  └─ keep candidate logical files
  ↓
existing validate_files_against_rules()
  ↓
matched_results + candidate_mappings
  ↓
shared logical file map in ctx
  ├─ proc uses table_name -> file_path
  └─ recon uses table_name -> file_path
```

### Recommended Project Structure
```text
finance-agents/data-agent/utils/
└── file_intake.py                     # logical upload file split / prefilter / naming / maps

finance-agents/data-agent/graphs/main_graph/
└── public_nodes.py                    # consume logical upload files before validate_files

finance-agents/data-agent/graphs/proc/
└── nodes.py                           # prefer ctx logical uploads when executing proc

finance-agents/data-agent/graphs/recon/
└── execution_service.py               # prefer ctx logical uploads when building recon_inputs
```

### Pattern 1: Keep a single authoritative matcher
**What:** 预筛选只判断“明显不可能命中任何 schema”，正式匹配仍交给 `validate_files_against_rules()`.
**When to use:** 已有成熟 schema 匹配器，新增输入形态只需要降低噪音时。
**Example:**
```python
if not could_match_any_schema(sheet_header, table_schemas):
    drop_sheet(reason="no_schema_candidate")
else:
    keep_for_validate_files()
```

### Pattern 2: Model split sheets as real logical upload files
**What:** 每个保留下来的 sheet 都有自己的 `file_path`、显示名和溯源元数据。
**When to use:** 下游运行时只接受文件路径，而不是 workbook + sheet 组合描述时。
**Example:**
```python
{
    "file_path": "/uploads/2026/4/22/demo__s02__risk_asset.xlsx",
    "original_filename": "demo.xlsx",
    "display_name": "demo__s02__risk_asset.xlsx",
    "sheet_name": "风险资产",
    "sheet_index": 2,
}
```

### Pattern 3: Prefer ctx-resolved logical files over raw state uploads
**What:** `check_file_node()` 之后把逻辑文件列表放入共享 ctx，`proc` / `recon` 执行都从这里取。
**When to use:** 上游 intake 已经重新解释过用户上传内容时。
**Example:**
```python
logical_uploaded_files = ctx.get("logical_uploaded_files") or state.get("uploaded_files") or []
file_path_map, _ = build_upload_name_maps(logical_uploaded_files)
```

### Anti-Patterns to Avoid
- **把所有拆出的 sheet 都直接算上传文件数量:** 说明页会先把旧数量门槛撑爆。
- **让预筛选去猜“这张 sheet 属于哪个 table_name”:** 会绕开正式唯一映射，制造静默错配。
- **继续依赖原始上传文件名反查路径:** 一旦 `matched_results.file_name` 变成逻辑文件名，下游就会找不到真实拆分文件。

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 正式 schema 匹配 | 新的独立匹配器 | `validate_files_against_rules()` | 现有工具已包含别名归一化和唯一映射 |
| 新文件协议 | workbook + sheet 的自定义执行协议 | 继续使用 `/uploads/...` + `file_path` | 现有 `proc` / `recon` 运行时已稳定支持 |
| 语义化文件名识别 | 让规则依赖 sheet 名或文件名包含关系 | 仍以表头和 schema 为主 | 现有规则本来就不是文件名驱动，硬绑文件名只会更脆弱 |

**Key insight:** 这次改造最值钱的是“把多 sheet 先还原成多个像普通文件一样的输入对象”，而不是让运行时理解更复杂的 workbook 结构。
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: 预筛选和正式匹配逻辑不一致
**What goes wrong:** 某个 sheet 在预筛选阶段被判掉，但正式匹配本来是能命中的。
**Why it happens:** 预筛选没有复用 required columns / alias 的同一归一化标准。
**How to avoid:** 预筛选只做“不能命中任何 schema”的保守判断，并使用与 `validate_files` 一致的列名标准化规则。

### Pitfall 2: 只改了 file_check，没有改执行期映射
**What goes wrong:** file_check 成功，但 `proc` / `recon` 执行时根据逻辑文件名找不到 `file_path`。
**Why it happens:** 下游仍然只从原始 `state.uploaded_files` 建映射。
**How to avoid:** 为 `proc` / `recon` 共用一套逻辑文件 map，并在 ctx 中贯穿。

### Pitfall 3: 文件显示名冲突
**What goes wrong:** 两个不同工作簿拆出的 sheet 生成同名显示名，后一个覆盖前一个映射。
**Why it happens:** 只使用 sheet 名或原工作簿名做显示名。
**How to avoid:** 显示名中加入稳定的 workbook identity 和 sheet index，并保留合法扩展名。

### Pitfall 4: 歧义信息在上层丢失
**What goes wrong:** `validate_files` 已经返回 `candidate_mappings`，但用户只看到“请重新上传更符合要求的文件”。
**Why it happens:** `public_nodes` 只消费 `error` 文本，没有展开候选映射。
**How to avoid:** 把候选 table 列表渲染进失败消息，并附带预筛选摘要。

</common_pitfalls>

<code_examples>
## Code Examples

Verified patterns from the current codebase:

### Excel header currently reads only active sheet
```python
# Source: finance-agents/data-agent/graphs/main_graph/public_nodes.py
wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
ws = wb.active
header = [str(cell.value or "").strip() for cell in next(ws.iter_rows(max_row=1))]
```

### Existing ambiguity support already exists in MCP validator
```python
# Source: finance-mcp/tools/file_validate_tool.py
return {
    "success": False,
    "error": assignment_error,
    "unmatched_files": unmatched_files,
    "candidate_mappings": {
        file_name: [
            {"table_id": item["table_id"], "table_name": item["table_name"]}
            for item in matched_tables
        ]
        for file_name, matched_tables in file_to_tables_map.items()
    },
}
```

### Proc execution only needs table_name -> file_path
```python
# Source: finance-agents/data-agent/graphs/proc/nodes.py
sync_uploaded_files.append({
    "file_name": file_name,
    "file_path": file_path,
    "table_id": table_id,
    "table_name": table_name,
})
```
</code_examples>

---
*Phase: 06-multi-sheet-upload-intake*
*Research completed: 2026-04-22*

# Phase 6: Multi-Sheet Upload Intake - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

为文件型 `proc` / `recon` 增加单个 Excel 多 sheet 工作簿的共享输入层能力。这个阶段的目标不是修改 `proc DSL` / `recon DSL`，也不是让规则显式声明 sheet 名称，而是在正式 `file_check` 之前把工作簿拆成 sheet 级逻辑文件，做安全的预筛选，并把结果继续接回现有 `table_name -> file_path` 执行链路。

这个阶段只覆盖文件上传后的 intake、schema 预筛选、正式 file_check 接入、命名和回归验证。不在这里重做规则 DSL，不改变 `validate_files` 的权威地位，也不扩展前端方案创建 UI。

</domain>

<decisions>
## Implementation Decisions

### Intake Boundary
- **D-01:** 多 sheet 兼容必须落在上传输入层，在调用正式 `validate_files` 之前完成；现有 `proc DSL` / `recon DSL` 不改。
- **D-02:** CSV 和单 sheet 文件继续按当前逻辑直通，不为兼容多 sheet 而改变既有单文件行为。
- **D-03:** 多 sheet 工作簿拆出的结果必须是“逻辑上传文件”对象，而不是只存在于内存中的 header 摘要；后续 `proc` / `recon` 都要能拿到真实 `file_path`。

### Sheet Split And Prefilter
- **D-04:** 预筛选发生在 sheet 拆分之后、正式 `validate_files` 之前；只有通过预筛选的逻辑文件才参与正式 schema 唯一映射和后续执行。
- **D-05:** 预筛选只允许过滤“明显无效”的 sheet：空表头、无数据行、或在别名归一化后不可能满足任何 schema `required_columns` 的 sheet。
- **D-06:** 预筛选不能替代正式 schema 匹配，更不能在多个 schema 候选之间擅自做唯一选择。真正的歧义仍由现有 `validate_files` 的唯一映射逻辑判定。

### Naming And Traceability
- **D-07:** 逻辑文件命名必须唯一、稳定，并保留原工作簿和 sheet 可追溯信息；命名不能依赖“sheet 名刚好等于 table_name”这类脆弱约定。
- **D-08:** 用户可见名称必须继续保留合法扩展名，避免现有 file_type 判断因为文件名格式变化而失效。
- **D-09:** 日志、报错和候选映射提示都应优先展示“原工作簿名 + sheet 名”的可理解信息，而不是只展示服务器存储名。

### Shared Proc / Recon Path
- **D-10:** `proc` 与 `recon` 必须共享同一套逻辑上传文件映射，不能一边用原始 `uploaded_files`，另一边用拆分后的逻辑文件。
- **D-11:** 下游执行映射应优先从 `ctx` 中读取逻辑上传文件列表；`state.uploaded_files` 保持兼容，不作为多 sheet 场景的唯一真相来源。
- **D-12:** `validate_files` 现有返回的 `candidate_mappings` 必须继续向上层透传；多 sheet 场景下这不是异常噪音，而是关键可解释性信息。

### the agent's Discretion
- 共享 intake 工具最终放在 `finance-agents/data-agent/utils/` 还是其他复用模块，可在实施时决定；但必须被 `public_nodes`、`proc`、`recon` 共同复用。
- 拆分出的物理文件可以采用 `.xlsx` 作为统一格式，只要 `resolve_upload_file_path()` 和现有 dataframe 读取逻辑无需改协议即可消费。
- 过滤掉的 sheet 是否全部回显给用户，还是只在失败时摘要展示，可以在实施时决定；但被过滤和保留的理由必须能在日志中定位。

</decisions>

<specifics>
## Specific Ideas

- 现有 `check_file_node` 读取 Excel 表头时只看活动 sheet，所以单个多 sheet 工作簿天然丢信息。
- 如果把拆出的所有 sheet 直接当成“上传文件”送进 `validate_files`，宽松规则会先被旧数量门槛误杀，后续唯一映射也会被说明页干扰。
- 这次要保留“正式匹配器只有一个”，也就是 `finance-mcp/tools/file_validate_tool.py` 仍然是 schema 匹配权威；预筛选只做低风险剔除。
- 文件名本身不是现有规则匹配主依据；关键是表头和 `table_name -> file_path`。因此命名设计的核心是唯一性和可追溯，不是语义匹配。

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` — 多 sheet 上传需求已被加入 Active / Constraints / Key Decisions
- `.planning/REQUIREMENTS.md` — FILE-01 ~ FILE-04 的范围、边界和 phase 追踪
- `.planning/ROADMAP.md` — Phase 6 目标、成功标准和三段实施计划
- `.planning/STATE.md` — 当前项目状态与新增 Phase 6 的路线演化说明

### Repo Constraints
- `AGENTS.md` — 仓库级命令、测试方式、编辑约束和服务重启要求

### Current File Intake Path
- `finance-agents/data-agent/graphs/main_graph/public_nodes.py` — 共享 `check_file_node`、上传文件路径归一化、表头读取入口
- `finance-agents/data-agent/graphs/proc/nodes.py` — `proc` 执行前如何把匹配结果回填成 `uploaded_files`
- `finance-agents/data-agent/graphs/recon/nodes.py` — `recon` 如何复用公共 `check_file_node`
- `finance-agents/data-agent/graphs/recon/execution_service.py` — `recon` 执行时如何从文件匹配结果构造 `recon_inputs`

### Validation And Runtime
- `finance-mcp/tools/file_validate_tool.py` — 正式 schema 匹配、唯一映射和 `candidate_mappings` 返回逻辑
- `finance-mcp/proc/mcp_server/steps_runtime.py` — `proc` 运行时如何从 `file_path` 读取 DataFrame
- `finance-mcp/recon/mcp_server/recon_tool.py` — `recon` 运行时如何按 `table_name` 识别输入对象

### Upload Storage
- `finance-mcp/tools/file_upload_tool.py` — 原始上传文件如何落盘到 `/uploads/...`
- `finance-mcp/security_utils.py` — 上传路径解析与安全约束

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `public_nodes.check_file_node()` 已经是 `proc` / `recon` 共用的 file_check 入口，是插入 split + prefilter 的最佳位置。
- `file_validate_tool.validate_files_against_rules()` 已经具备列名归一化、别名映射、唯一赋值和 `candidate_mappings` 输出，不需要重造第二套 schema 匹配器。
- `proc` 运行时和 `recon` 运行时都只要求最终能拿到 `file_path`；它们不关心这个文件是否来自原始上传，还是来自拆分后的 sheet。
- `resolve_upload_file_path()` 已经统一支持 `/uploads/...` 引用，只要逻辑文件也落在上传目录协议内，下游无需改读文件协议。

### Established Patterns
- `state.uploaded_files` 允许是字符串路径或 `{file_path, original_filename}` 字典；多 sheet 改造要继续兼容这两种形态。
- `recon` 通过适配 `proc_ctx` 复用 `check_file_node()`，所以新增的逻辑文件字段应尽量挂在共享 ctx 上，而不是散落到两个子图各自实现。
- 现有 `build_upload_name_maps()` / `_build_upload_name_maps()` 在 `proc` 和 `recon` 侧存在重复实现，这正好说明应当抽一层共享逻辑上传文件映射工具。

### Integration Points
- `finance-agents/data-agent/graphs/main_graph/public_nodes.py:124` 的 `_read_header()` 目前只读 Excel `wb.active`，这是多 sheet 丢失的直接原因。
- `finance-agents/data-agent/graphs/main_graph/public_nodes.py:406` 在 file_check 时直接按原始上传文件列表构造 `files_with_columns`，这是 prefilter 需要接管的关键点。
- `finance-agents/data-agent/graphs/proc/nodes.py:160` 和 `finance-agents/data-agent/graphs/recon/execution_service.py:759` 都依赖文件名映射回 `file_path`，所以逻辑文件命名冲突会直接导致运行时错配。
- `finance-mcp/tools/file_validate_tool.py:382` 已经把歧义候选放进 `candidate_mappings`，但上层提示还没有完整消费。

### Risks To Control
- 预筛选过宽：说明页、封面页、空白页进入正式 file_check，导致旧数量门槛误报或唯一映射歧义被放大。
- 预筛选过窄：真实业务 sheet 被提前过滤，导致“缺少规则要求的文件”类误报。
- 命名冲突：不同工作簿拆出的逻辑文件显示名重复，覆盖映射表。
- 只改 file_check 不改下游映射：`validate_files` 成功，但 `proc` / `recon` 执行时找不到对应 `file_path`。

</code_context>

<deferred>
## Deferred Ideas

- 在规则层显式声明“只吃哪个 sheet”或“sheet 名正则” —— 本阶段不扩展 DSL。
- 对说明页做更重的语义识别或 LLM 判断 —— 本阶段只做低风险、基于结构和表头的预筛选。
- 为前端上传界面增加 sheet 预览和人工勾选 —— 当前阶段以后端 intake 自动兼容为主。

</deferred>

---
*Phase: 06-multi-sheet-upload-intake*
*Context gathered: 2026-04-22*

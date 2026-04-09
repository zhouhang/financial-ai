# PRD: Proc 草稿叙事细化 + 规则/数据源运行时兼容性校验

## 1. Introduction / 概述

在 Recon 方案向导第二步 "AI 生成数据整理配置" 中，当前存在两类问题：

1. **叙事文本过于模糊**：前端 `ReconWorkspace.tsx` 的 `summarizeProcDraft` 生成的步骤描述
   仅输出 "步骤 1：将当前选择的数据集整理后写入左侧整理结果表" 等通用句子，没有指明
   具体是哪个数据集、哪些字段、经过哪些操作后形成 `left_recon_ready` /
   `right_recon_ready`，用户很难确认 AI 是否理解了自己的业务。

2. **proc JSON 不符合 DSL 规范**：LLM 偶尔会把字段映射写成 `{"from": "...", "to": "..."}`
   这种不合法形态，绕过了 `ProcStepsRuleSetModel` 定义的 `target_field` + `value.type`
   结构，导致后续执行失败，但前端并未在生成阶段拦截。

3. **缺少运行时数据-规则兼容性校验**：proc / recon 规则本身只是纯规则，不保存历史绑定
   数据集。当前向导没有校验"当前选中的左/右原始数据源字段"是否满足"所选 proc 规则的
   输入契约"，也没有校验"proc 输出（经整理后的 `left_recon_ready` / `right_recon_ready`）
   是否满足"所选 recon 规则的输入契约"，用户只能在真正运行时才暴露问题。

本 PRD 的目标是同时治理以上三类问题。

## 2. Goals / 目标

- G1：让第二步生成的叙事文本能准确陈述 **"哪个数据集的哪个字段 → 经过哪些编号步骤 → 形成
  左/右整理结果表"**，并按左、右分组展示。
- G2：保证 AI 生成的 proc JSON **100% 通过 `ProcStepsRuleSetModel` 的结构校验**，
  否则不允许进入后续流程。
- G3：在用户 **选择规则 + 选择数据源** 时，提供字段级兼容性校验（proc 输入契约 vs 原始
  数据源，recon 输入契约 vs proc 输出表），选择时黄色警告、运行前红色阻塞。
- G4：校验逻辑 **单一事实来源** —— data-agent 不再通过 `importlib` 直接加载
  finance-mcp 的 `rule_schema.py`，改为走 MCP 工具调用。

## 3. User Stories / 用户故事

### US-001：后端 —— 为每个 proc step 生成可读的 description 字段

**Description:** 作为 AI 方案设计器，我需要在生成 proc 草稿时为每个 step 写入一段具体的
`description` 文本，明确描述"哪个数据集的哪些字段做了什么操作"，让前端可以原样渲染而无需
回拼。

**Acceptance Criteria:**
- [ ] 修改 `finance-agents/data-agent/graphs/recon/scheme_design/executor.py` 的
  `_build_proc_prompt`，新增一条 LLM 要求："每个 step 必须输出 `description` 字段，
  说明输入数据集名、涉及字段、执行的操作（过滤 / 聚合 / 映射 / 写入等）、目标表"。
- [ ] 提示词中给出正面示例，例如 `"description": "将支付流水 pay_flow 的 order_id
  写入 biz_key，amount 求和后写入 amount，过滤条件 status='paid'，upsert 到
  left_recon_ready。"`
- [ ] `description` 允许缺省但 `_normalize_proc_draft` 会用 fallback 拼接空值
  （不抛错），保证旧 LLM 输出仍可用。
- [ ] `_build_proc_draft` 的本地 fallback 也需要为每个 step 写入最简 description
  （例如 "write_dataset 步骤：将 <table> 写入 <target>"）。
- [ ] 单元测试：给定一个含 description 的合法草稿，`_normalize_proc_draft` 原样返回；
  给定不含 description 的草稿，返回结果中每个 step 都有 description 字段。

### US-002：后端 —— proc 草稿结构校验失败自动重试一次

**Description:** 作为 AI 方案设计器，当 LLM 生成的 proc JSON 不通过
`ProcStepsRuleSetModel` 时，我需要自动把 schema 错误拼回提示词再调用 LLM 一次，
仍失败才向上抛错。

**Acceptance Criteria:**
- [ ] `scheme_design/executor.py` 中调用 LLM 的流程改为：
  1. 首次生成 → 调用 MCP `rule_validate` 工具（见 US-004）
  2. 若失败，读取 `validation_errors[0].path / message`，拼成一段中文修复提示附加到原
     提示词末尾，重新调用 LLM 一次
  3. 仍失败则抛出 `ValueError`，错误信息包含首条 validation_error 的 `path` 和 `message`
- [ ] 自动重试只执行一次，防止无限循环。
- [ ] 重试使用的提示词包含原始输入 + 上一次返回 JSON（截断至 8KB）+ 错误列表。
- [ ] 单元测试：mock LLM 首次返回带 `from`/`to` 的 mapping，第二次返回合法 JSON ——
  executor 最终应返回合法 JSON 且调用 LLM 两次。
- [ ] 单元测试：mock LLM 两次都返回非法 JSON —— executor 应抛出异常，异常信息包含
  "mappings" 字样。
- [ ] Typecheck / lint 通过。

### US-003：finance-mcp —— 将 `validate_rule_record` 暴露为 MCP 工具 `rule_validate`

**Description:** 作为规则体系维护者，我需要在 finance-mcp 中新增一个 `rule_validate`
工具，作为校验规则 JSON 的唯一入口，替代当前 data-agent 用 `importlib` 从磁盘直接加载
`rule_schema.py` 的脆弱做法。

**Acceptance Criteria:**
- [ ] 在 `finance-mcp/tools/rules.py`（或新建 `finance-mcp/tools/rule_validate_tool.py`）
  注册一个 MCP 工具：
  - `name`: `rule_validate`
  - `input_schema`: `{ rule_code: str?, rule: object, expected_kind:
    "proc_steps"|"recon"|"proc"|"merge"|"file_validation"|"proc_entry" }`
  - 内部委托给现有 `validate_rule_record`
  - 返回体透传 `success / validation_errors / rule / rule_type`
- [ ] 在 `finance-mcp/unified_mcp_server.py` 的工具注册列表中挂载该工具。
- [ ] 修改 `finance-agents/data-agent/graphs/recon/scheme_design/executor.py`：
  - 删除 `_load_finance_mcp_rule_schema_module` 和它的 `importlib.util.spec_from_file_location`
  - `_normalize_proc_draft` / `_normalize_recon_draft` 改为通过 `tools/mcp_client.py`
    调用 `rule_validate` MCP 工具
  - 校验失败的行为保持 US-002 约定
- [ ] 集成测试：启动 finance-mcp，用 mcp_client 调用 `rule_validate`，分别传入：
  - 合法 proc_steps JSON → `success=True`
  - 含 `from`/`to` 的 mappings → `success=False` 且错误 path 指向 `steps.*.mappings`
  - 合法 recon JSON → `success=True`
- [ ] 老的 `importlib` 动态加载路径完全删除（grep 不到）。

### US-004：后端 —— 规则输入契约抽取器

**Description:** 作为兼容性校验模块，我需要一个纯函数 `extract_rule_input_contract(rule,
kind)`，从已发布的 proc / recon 规则中静态扫描出"每个输入位置需要的字段集合"。

**Acceptance Criteria:**
- [ ] 新建 `finance-mcp/tools/rule_contract.py`（或置于 `rule_schema.py` 同目录）：
  ```python
  def extract_rule_input_contract(rule: dict, kind: str) -> dict:
      """
      Returns:
        {
          "kind": "proc_steps"|"recon",
          "inputs": [
            { "role": "left_source_1", "table": "<hint>",
              "required_fields": ["order_id","amount","status"] },
            ...
          ]
        }
      """
  ```
- [ ] proc_steps 抽取规则：
  - 扫描所有 `write_dataset` step 的 `sources[]` 列表，为每个 `alias` 建立一条 input
  - 该 alias 的 `required_fields` = 该 step 中 `mappings[].value.source.field`（当
    `value.type == "source"` 且 `source.alias == alias`）∪ `match.sources[*].keys[].field`
    （同 alias）∪ `aggregate[*].group_fields`（同 source_alias）
  - `table` 从对应 `sources[i].table` 取
- [ ] recon 抽取规则：
  - 固定输入为 `left_recon_ready` 和 `right_recon_ready`
  - left 的 `required_fields` = `rules[*].recon.key_columns.mappings[].source_field`
    ∪ `rules[*].recon.compare_columns.columns[].source_column`
    ∪ `rules[*].recon.aggregation.group_by[].source_field`
    ∪ `rules[*].recon.aggregation.aggregations[].source_field`
  - right 的 `required_fields` = 对应的 `*.target_field` / `*.target_column`
- [ ] 字段抽取严格按源字段名（不做大小写折叠），以便 US-006 可以直接做字符串相等比较。
- [ ] 单元测试：
  - 给定一个含 2 个 sources、3 个 mappings 的 proc 草稿，正确聚合出 2 个 input 的字段集合
  - 给定一个含聚合 + 比对列的 recon 规则，left / right 字段集合正确
  - 给定空 `steps`/空 `rules` 返回 `{ "inputs": [] }` 不抛错

### US-005：finance-mcp —— 暴露 `rule_contract_extract` MCP 工具

**Description:** 作为方案向导后端，我需要能通过 MCP 拿到某条已发布规则的输入契约，
无需在前端或 data-agent 里重复实现字段扫描逻辑。

**Acceptance Criteria:**
- [ ] 在 `finance-mcp/tools/rules.py` 新增 MCP 工具：
  - `name`: `rule_contract_extract`
  - `input_schema`: `{ rule_code: str, expected_kind: str }`
  - 行为：先调用 `load_and_validate_rule(rule_code, expected_kind)`，若合法则调用
    US-004 的 `extract_rule_input_contract` 并返回结果；若不合法则返回 `success=False`
    + `validation_errors`
- [ ] 挂载到 `unified_mcp_server.py` 工具列表。
- [ ] 集成测试：
  - 对数据库中一条真实 proc_steps 规则调用，返回结构正确
  - 对不存在的 rule_code 返回 `RULE_NOT_FOUND`

### US-006：后端 —— 运行时兼容性校验 API

**Description:** 作为方案向导前端，我需要一个 HTTP 接口（或 data-agent 工具）接受"所选
规则 + 所选数据源"，返回字段兼容性检查结果，让前端可以显示警告或阻塞运行。

**Acceptance Criteria:**
- [ ] 在 `finance-agents/data-agent/graphs/recon/scheme_design/api.py` 新增接口
  `POST /scheme_design/compatibility_check`，入参：
  ```json
  {
    "kind": "proc_steps" | "recon",
    "rule_code": "PROC_XXX",
    "bindings": [
      {
        "role": "left_source_1",
        "source_type": "dataset" | "derived",
        "source_id": "ds_abc",
        "fields": ["order_id","amount","biz_date","status"]
      }
    ]
  }
  ```
  - 当 `kind == "recon"` 时，`bindings` 的 `role` 固定为 `left_recon_ready` /
    `right_recon_ready`，`fields` 由前端从对应 proc 输出 schema 读取。
- [ ] 后端逻辑：
  1. 调 MCP `rule_contract_extract` 拿到规则契约
  2. 逐个 `role` 比对：`missing_fields = required_fields - provided_fields`
  3. **严格名字匹配**（不做大小写折叠、不做同义词映射），有任何 missing 即视为失败
  4. 返回体：
     ```json
     {
       "status": "passed" | "failed",
       "details": [
         {
           "role": "left_source_1",
           "required_fields": [...],
           "provided_fields": [...],
           "missing_fields": ["status"],
           "message": "所选数据源缺少字段：status"
         }
       ]
     }
     ```
- [ ] 当 `rule_contract_extract` 返回非 success 时，整体 status 为 `failed`，`details`
  带规则校验错误。
- [ ] 单元测试：
  - 所有字段齐全 → passed
  - 缺一个字段 → failed，missing_fields 命中
  - 大小写不一致（例如提供 `Status` 而规则要 `status`）→ failed（严格匹配）
  - 未知 rule_code → failed，details 中带 RULE_NOT_FOUND
- [ ] Typecheck 通过，FastAPI 接口带 pydantic 入参校验。

### US-007：前端 —— 重写 summarizeProcDraft 为左/右分组叙事

**Description:** 作为用户，我希望在第二步看到的叙事文本按"左侧数据整理 / 右侧数据整理"
分组，每组下有编号子步骤，每一步都写明具体数据集和字段的操作。

**Acceptance Criteria:**
- [ ] 重写 `finance-web/src/components/ReconWorkspace.tsx` 中的 `summarizeProcDraft`：
  1. 先按 step 的 `target_table` 前缀把 steps 分到 `left` / `right` / `other` 三组
     （`left_*` → 左，`right_*` → 右，其余归 other 单独列出）
  2. 渲染顺序：左侧标题 + 左侧子步骤（1.1 / 1.2 / ...）→ 右侧标题 + 右侧子步骤
     （2.1 / 2.2 / ...）→ other（如有）
  3. 每个子步骤文字的首选来源是 LLM 输出的 `step.description`；若该字段为空，才回退
     到从结构化 JSON（sources / mappings / aggregate / filter）拼接
- [ ] 结构化回退文案必须体现"X 数据集的 Y 字段 → 经过 Z 操作 → 写入 target 的 A 字段"的
  叙事骨架，不能再出现 "当前选择的数据集" 这种占位词。
- [ ] 标题固定为 `## 左侧数据整理` / `## 右侧数据整理`，与现有 Markdown 渲染兼容。
- [ ] 当 `steps` 为空时显示 "尚未生成整理步骤" 而不是空白。
- [ ] 单元测试（Vitest）：
  - 给定一个包含 `left_create_schema` + `left_write_dataset` + `right_create_schema`
    + `right_write_dataset` 的 proc JSON，输出文本满足：
    - 含 "左侧数据整理" 和 "右侧数据整理" 两个一级标题
    - 左侧下有 "步骤 1.1" "步骤 1.2" 编号
    - 右侧下有 "步骤 2.1" "步骤 2.2" 编号
    - 每个 write_dataset 子步骤的文本中出现对应 `source.table` 的名字
  - 给定 step 含 `description` 字段 → 输出文本中能找到该 description 原文
  - 给定 step 不含 `description` → 输出文本不含 "当前选择的数据集" 字样
- [ ] Typecheck / lint 通过。
- [ ] 在浏览器中使用 dev-browser skill 验证 ReconWorkspace 第二步的渲染效果（两个样本
  数据集，左右各一份）。

### US-008：前端 —— 选择规则/数据源时显示黄色兼容性警告

**Description:** 作为用户，在方案向导第二步、第三步切换"选择已有规则"模式并选定规则后，
我希望立刻看到字段缺失的黄色提示（可继续编辑），不必等到点"运行"。

**Acceptance Criteria:**
- [ ] 在 `ReconWorkspace.tsx` 中：
  - 当 proc `configMode === 'existing'` 且用户完成（`selectedProcConfigId` 变更 或
    `leftSourceIds` / `rightSourceIds` 变更）时，防抖 400ms 调用 US-006 接口
  - 当 recon `configMode === 'existing'` 且 proc 输出 schema 已知 + 用户选定 recon
    规则时，同理防抖调用
  - 结果写入已有的 `procCompatibility` / `reconCompatibility` state
- [ ] `CompatibilityCheckResult` 类型补充：
  ```ts
  status: 'idle' | 'checking' | 'passed' | 'warning' | 'failed';
  details: Array<{
    role: string;
    missingFields: string[];
    message: string;
  }>;
  ```
  - 选择时：failed 结果以 `status='warning'` 呈现（黄色 UI），不阻塞编辑
  - 运行时（US-009）：同样的 failed 结果以 `status='failed'` 呈现（红色 UI）
- [ ] `SchemeWizardTargetProcStep.tsx` 和 `SchemeWizardReconStep.tsx` 展示区域：
  - warning：黄色 banner，图标 `AlertTriangle`，文案
    "所选数据源缺少字段：<role>.<field>，仍可继续但运行时会被阻塞"
  - passed：绿色 banner，文案 "字段兼容性检查通过"
- [ ] 单元测试（Vitest + MSW 或 mock fetch）：
  - 返回 missing_fields → state 变成 warning，banner DOM 包含 "缺少字段"
  - 返回 passed → state 变成 passed
  - rule_code 为空时不触发请求
- [ ] Typecheck / lint 通过。
- [ ] 在浏览器中使用 dev-browser skill 验证黄色 banner 渲染。

### US-009：前端 —— 运行前做红色阻塞式兼容性校验

**Description:** 作为用户，当我点击第二步 / 第三步的"试运行"或"提交方案"按钮时，若字段
不兼容，我希望被红色弹窗 / 禁用按钮阻止，避免浪费执行资源。

**Acceptance Criteria:**
- [ ] 在提交方案前、点试运行前的 handler 中，同步再调一次 US-006 接口（使用最新的
  数据源 / 规则 / proc 输出 schema）。
- [ ] 若返回 failed：
  - proc 阶段：阻止 `试运行` 和 `下一步` 按钮；顶部显示红色 banner，列出 missing_fields；
    聚焦到受影响的选择框
  - recon 阶段：同上，阻止 `提交方案`
- [ ] 若返回 passed：继续原有流程。
- [ ] `trialDisabled` prop 的计算在原有条件基础上追加
  `proc/reconCompatibility.status === 'failed'`。
- [ ] 不能因为接口暂时不可达就永久阻塞：若请求异常，banner 显示 "兼容性检查失败，已跳过
  校验继续执行"（warning 级），不阻塞运行。
- [ ] 单元测试：
  - mock 校验返回 failed → 点击按钮后按钮仍被禁用或弹出红色提示
  - mock 校验返回 passed → 继续调用原有的 `onTrialRecon` / `onGenerateRecon`
- [ ] Typecheck / lint 通过。
- [ ] 在浏览器中使用 dev-browser skill 验证红色阻塞效果。

### US-010：集成测试 —— 坏 LLM 输出 fixture 端到端回归

**Description:** 作为维护者，我需要一批"典型坏 LLM 输出"的 fixture 文件，对
`executor → rule_validate → retry → summarize` 的全链路做端到端回归。

**Acceptance Criteria:**
- [ ] 在 `finance-agents/data-agent/tests/recon/scheme_design/fixtures/` 下建立：
  - `llm_output_from_to_mapping.json`（用 from/to）
  - `llm_output_missing_step_id.json`
  - `llm_output_wrong_value_type.json`（value.type 使用 `calc`）
  - `llm_output_valid.json`（正样本）
- [ ] 集成测试 `test_proc_draft_pipeline.py`：
  - 对每个坏 fixture，mock LLM 第一次返回该 fixture、第二次返回 `llm_output_valid.json`，
    断言 executor 最终返回的 draft 通过 `rule_validate` 且 LLM 调用次数为 2
  - 对 `llm_output_valid.json` fixture，LLM 只被调用 1 次
  - 对 `llm_output_valid.json`，前端 `summarizeProcDraft` snapshot 测试（Vitest
    快照）—— 正文同时出现 "左侧数据整理" / "右侧数据整理" 两个标题
- [ ] 集成测试 `test_compatibility_check_api.py`：
  - 使用内存中的规则 fixture + 模拟 MCP 客户端，调用
    `/scheme_design/compatibility_check`，覆盖"字段齐全"、"缺字段"、"规则不存在"
    三种场景
- [ ] 所有测试可在 CI 中自动运行（`pytest finance-agents/data-agent/tests/recon/scheme_design`
  与 `pnpm -C finance-web test`）。

## 4. Functional Requirements / 功能需求

- FR-1：LLM 生成的 proc_steps JSON 中 **每个 step 都必须有 `description` 字段**；
  描述需要提到 1) 输入数据集名；2) 参与的字段；3) 执行的操作；4) 写入的目标表。
- FR-2：`_build_proc_prompt` 必须在提示词中给出一个正面示例 step，示例内 mapping 使用
  `target_field + value.type=source + source.alias/field` 的合法格式。
- FR-3：proc 草稿在返回前必须通过 `rule_validate` MCP 工具（`expected_kind=proc_steps`）
  的校验；校验失败时自动重试一次，仍失败则抛错。
- FR-4：recon 草稿同样必须通过 `rule_validate`（`expected_kind=recon`）。
- FR-5：`finance-agents/data-agent/graphs/recon/scheme_design/executor.py` 中不得再有
  `importlib.util.spec_from_file_location` 动态加载 finance-mcp 模块的代码。
- FR-6：`finance-mcp` 必须新增 MCP 工具 `rule_validate` 和 `rule_contract_extract`，
  复用现有 `validate_rule_record` 和新写的 `extract_rule_input_contract`。
- FR-7：`extract_rule_input_contract` 对 proc_steps 必须聚合每个 `sources[].alias`
  在 mappings / match / aggregate 里被引用的字段。
- FR-8：`extract_rule_input_contract` 对 recon 必须抽取 `left_recon_ready` /
  `right_recon_ready` 的 required_fields（分别来自 source_* 和 target_* 字段）。
- FR-9：`/scheme_design/compatibility_check` 接口 **必须做严格字段名字符串相等**，
  不做大小写折叠、不做同义词映射。
- FR-10：前端第二步的 `summarizeProcDraft` 输出必须按"左侧数据整理 / 右侧数据整理"
  分组，每组内子步骤使用 `组号.序号` 编号（例如 1.1 / 1.2 / 2.1）。
- FR-11：前端在"选择已有规则"模式下必须在选中规则或数据源变化后 400ms 内自动发起一次
  兼容性校验（防抖），失败时显示黄色 warning。
- FR-12：前端在点击"试运行 / 下一步 / 提交方案"前必须同步再做一次兼容性校验，失败时
  禁用按钮 + 红色提示。
- FR-13：兼容性校验接口临时不可达时，前端必须 **允许继续操作**（只显示 warning 级提示），
  不得永久阻塞。

## 5. Non-Goals / 不做的事

- NG-1：不做规则输入字段名与数据源字段名之间的自动映射 / 同义词匹配（本期答案选 8A
  严格匹配）。若未来要做，留到后续 PRD。
- NG-2：不做数据类型兼容性校验（只校验字段名是否存在），decimal 精度、date 格式等不在
  本期范围。
- NG-3：不做数据内容抽样校验（例如采样 10 行看字段是否真的非空），只做结构级校验。
- NG-4：不涉及 `ProcRuleSetModel`（旧 proc）和 `merge` 类型规则，本期只覆盖
  `proc_steps` 和 `recon`。
- NG-5：不修改 `auto_scheme_run` / `manual_scheme_run` 的运行时执行逻辑，只在方案
  设计阶段做校验。
- NG-6：不做 LLM 输出的多轮自我修复（最多只自动重试 1 次）。

## 6. Design Considerations / 设计说明

- 前端叙事改造优先使用 LLM 的 `description`，而不是在前端做复杂结构拼接。前端的结构化
  fallback 只是兜底，以免完全依赖 LLM 稳定性。
- `CompatibilityCheckResult` 已经存在于 `SchemeWizardReconStep.tsx` 中，但类型需要扩
  展出 `checking` 和 `warning` 状态，以及带 `missingFields` 的 `details` 数组。
- 黄色 / 红色视觉差异沿用 `finance-web` 现有的 `AlertTriangle` / `XCircle` 风格。
- MCP 工具命名遵循现有风格：动词_对象（参考 `rule_query` / `rule_create` / `rule_update`），
  故使用 `rule_validate`、`rule_contract_extract`。

## 7. Technical Considerations / 技术约束

- 必须删除 `scheme_design/executor.py` 里的 `_load_finance_mcp_rule_schema_module`
  动态加载路径。这是本期的硬性要求之一（G4）。
- `rule_validate` MCP 工具的返回体必须透传 `validation_errors`（包含 `path` /
  `message` / `type`），否则自动重试无法构造错误提示。
- 兼容性校验接口需要知道"数据源已有字段"。第二步的字段来自现有
  `availableSources[].fields` state；第三步的字段需要从最近一次 proc 试运行结果或
  `left_recon_ready` / `right_recon_ready` 的 schema 读取 —— 若没有 proc 试运行结
  果，前端应 skip 校验并在 banner 里提示 "请先试运行 proc 以便检查 recon 兼容性"。
- 提示词加长后要注意 `_summarize_dataset_inputs` 的总长度，必要时对 `sample_rows`
  再裁剪（当前已裁到 3 行）。
- 自动重试会额外消耗 LLM 调用。要在 executor 层加 metric / log（`proc_draft_retry_total`）
  以便观察比例。

## 8. Success Metrics / 成功指标

- 第二步生成的 proc 草稿 **首次就通过 rule_validate 的比例 ≥ 95%**（加入自动重试后
  整体通过率 ≥ 99%）。
- 第二步叙事文本中 **不再出现 "当前选择的数据集"** 占位词（日志采样 0 命中）。
- 当选择字段不兼容时，**100% 的用户在点击运行前就能看到黄色 warning**（前端集成测试
  覆盖）。
- 运行时因 "字段缺失" 导致的失败次数相比改造前下降 80% 以上。

## 9. Open Questions / 待确认

- Q1：recon 阶段的兼容性校验需要 "proc 输出字段列表"。若用户选择 "沿用已有 proc 规则"
  但还没做 proc 试运行，前端应怎么获取目标表字段？候选：a) 从 proc 规则的
  `create_schema.columns` 静态读取；b) 强制要求先试运行一次 proc。本 PRD 暂定走 a，
  作为 FR-11 的补充 —— 若 proc 规则没有 `create_schema` step，则显示 warning 跳过校验。
- Q2：`rule_validate` 是否需要支持 `rule_code` 缺省？目前 `validate_rule_record`
  接受空 rule_code，此处保持一致即可，但要确认 MCP 工具 input_schema 是否允许 optional。
- Q3：自动重试的提示词追加文本是否需要英文版本？目前所有提示词都是中文，统一使用中文即可。
- Q4：dev-browser 手工验收需要走哪条登录流？由实施者在开始 US-007 / US-008 / US-009
  前确认一下 seed 数据和登录账号。

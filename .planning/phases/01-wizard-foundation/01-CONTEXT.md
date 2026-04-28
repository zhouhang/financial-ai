# Phase 1: Wizard Foundation - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

建立“新建对账方案”的 4 步向导骨架、步骤边界、草稿状态模型和基础交互约束。这个阶段只收口流程框架与状态权责，不在这里实现第二步的完整字段编辑器、第三步的完整对账规则编辑器，也不重做 `proc` / `recon` 引擎。

</domain>

<decisions>
## Implementation Decisions

### Step Structure
- **D-01:** Phase 1 只固定新的 4 步业务化结构，不新增额外能力，不改变底层执行模型。
- **D-02:** Step 1 只承载 `方案名称` 和 `对账目的`，不再放左右数据集选择，也不再放左/右口径描述。
- **D-03:** Step 2 调整为“数据准备”，承载左右数据集选择、筛选数据 / 行数据操作占位、左右输出表字段配置，以及后续 `proc` 试跑入口。
- **D-04:** Step 3 调整为“对账规则”，输入来源是 Step 2 的整理后输出结构，而不是原始数据集。
- **D-05:** Step 4 是确认与保存页，只展示方案摘要、试跑状态和保存门禁，不再成为第二个可编辑主界面。
- **D-06:** 推荐采用更业务化的步骤标题：`方案目标`、`数据准备`、`对账规则`、`确认保存`。

### Draft Authority And Invalidation
- **D-07:** 新向导的长期状态模型不再继续扩张当前扁平 `schemeDraft`，而是按步骤拆成至少 4 个语义切片：`intent`、`preparation`、`reconciliation`、`confirmation`。
- **D-08:** 用户可编辑的业务配置是权威数据；生成的 JSON、兼容性检查结果、试跑结果和样例预览都属于派生工件，必须挂靠到某个明确版本的业务配置上。
- **D-09:** 上游步骤一旦改动，必须显式失效下游派生工件与通过状态。最低规则：
  Step 1 改动会失效 Step 2-4 的派生工件；
  Step 2 改动会失效 `proc` / `recon` JSON、两步试跑状态和下游样例；
  Step 3 改动只失效 `recon` JSON、`recon` 试跑状态和结果样例。
- **D-10:** Phase 1 的状态模型要预留“陈旧但可参考”的工件能力，支持后续阶段把旧试跑结果显示为“仅供参考”，但绝不能与当前权威配置混用。
- **D-11:** 不引入 `instruction_text` / `rendered_summary` 这类双权威文本面。只要存在可编辑文本面，用户编辑的文本就必须是当前可见且被系统认为权威的文本。

### UI Shell And User Language
- **D-12:** Phase 1 复用现有 `ReconWorkspace` 里的创建方案弹窗，不迁移到独立页面，也不拆成新的右侧工作台。
- **D-13:** 文案和字段命名优先面向财务用户，默认界面避免暴露 JSON、DSL、validator 等技术术语。
- **D-14:** JSON 仅保留为高级查看能力，不作为默认编辑路径。
- **D-15:** 第四步展示的是确认摘要，不做第二套复杂配置控件，避免所见即所得被破坏。

### API And Backend Boundary
- **D-16:** Phase 1 继续沿用现有设计会话接口 `/recon/schemes/design/*` 和最终保存接口 `/recon/schemes`，不为向导重构单独发明一套新协议。
- **D-17:** 新前端草稿模型通过前端适配层编译到现有 `target`、`generate`、`trial`、`scheme_meta_json` 载荷，不要求在 Phase 1 先改后端保存模型。
- **D-18:** 现有 `proc DSL` / `recon DSL` 与保存前试跑门禁保持不变。向导重构必须围绕当前 guardrails 与 save-time validation 展开，而不是规避它们。

### the agent's Discretion
- 前端最终采用 `useReducer`、拆分 hooks，还是保留父组件 helper + 子组件 props 的方式，可以在 planning 阶段决定；但必须把“权威配置”和“派生工件”明确分层。
- Step badge、摘要卡片、空状态和过渡动画的视觉表现可沿用现有 `ReconWorkspace` 设计语言，不需要在 Phase 1 另起一套视觉系统。

</decisions>

<specifics>
## Specific Ideas

- 主要用户是财务人员，目标是让他们通过业务配置而不是 JSON 来完成自动化对账方案创建。
- AI 的角色是“先给一版建议”，不是黑盒替代人；财务需要能看样例、改配置、再试跑。
- 不接受把用户编辑文本和系统展示文本拆成两套不同权威面板，这会破坏所见即所得。
- 新流程必须让后续 Phase 2 和 Phase 3 能自然落到现有 `proc json` 与 `recon json`，而不是引入新的抽象层替换底层 DSL。

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope
- `.planning/PROJECT.md` — 本次重构的核心价值、边界和关键决策
- `.planning/REQUIREMENTS.md` — v1 范围、保存门禁和试跑要求
- `.planning/ROADMAP.md` — Phase 1 的目标、计划拆分与成功标准

### Repo Constraints
- `AGENTS.md` — 仓库级工程约束、启动方式、测试命令和修改边界

### DSL Guardrails
- `finance-agents/data-agent/skills/proc-config/references/proc-dsl-guardrails.md` — 当前 `proc` steps DSL 的硬约束，证明向导不能脱离现有输出模型
- `finance-agents/data-agent/skills/recon-config/references/recon-dsl-guardrails.md` — 当前 `recon` DSL 的硬约束，证明第三步必须产出兼容现有引擎的规则

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `finance-web/src/components/ReconWorkspace.tsx`：当前创建方案弹窗、步骤切换、保存按钮、AI 生成与试跑 orchestration 都集中在这里，是 Phase 1 的主改造入口。
- `finance-web/src/components/recon/SchemeWizardTargetProcStep.tsx`：当前 Step 1/2 合并视图、样例表格、状态提示和数据源选择 UI 可直接复用其基础组件与展示块。
- `finance-web/src/components/recon/SchemeWizardReconStep.tsx`：当前 Step 3 的 AI 生成、试跑结果与高级 JSON 入口已有现成模式，可保留为后续阶段的壳。
- `finance-web/src/components/recon/autoApi.ts`：已统一封装 `/api/recon/*` 的 REST/SSE 调用，适合作为继续复用的前端 API 边界。
- `finance-agents/data-agent/graphs/recon/scheme_design/api.py`：现有设计会话 start / target / generate / use-existing / trial 接口都在这里。
- `finance-agents/data-agent/graphs/recon/auto_run_api.py`：最终方案保存和保存前试跑门禁在这里生效。

### Established Patterns
- 现有向导状态由 `ReconWorkspace.tsx` 父组件持有，再以窄 props 下发到步骤子组件；后续重构应优先顺着这个边界演进，而不是一次性重写整个工作区。
- 现有实现已经存在“上游变更时手动清空下游状态”的模式；Phase 1 需要把它系统化成明确的失效规则，而不是继续散落在各个 callback 里。
- 最终保存仍依赖 `scheme_meta_json`、`dataset_bindings_json`、`proc_rule_json`、`recon_rule_json` 和试跑状态；这意味着前端新模型必须能被编译回这套结构。

### Integration Points
- `renderSchemeWizardContent()`：当前步骤切换与内容分发总入口。
- `handleCreateScheme()`：当前最终保存编译层，把前端状态转成 `/schemes` API 载荷。
- `ensureDesignSession()` / `syncDesignTarget()` / `consumeRuleGenerationStream()`：当前 AI 生成和试跑前的设计会话编排边界。

</code_context>

<deferred>
## Deferred Ideas

- 真正可执行的“筛选数据 / 行数据操作”可视化编辑器 —— 属于后续 Phase 2+，当前只保留结构占位。
- 更深度的整理规则 / 对账逻辑模板复用能力 —— 属于后续阶段，不在 Phase 1 的框架收口内解决。

</deferred>

---
*Phase: 01-wizard-foundation*
*Context gathered: 2026-04-22*

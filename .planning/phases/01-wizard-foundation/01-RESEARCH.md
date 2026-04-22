# Phase 01: Wizard Foundation - Research

**Researched:** 2026-04-22
**Domain:** reconciliation scheme wizard shell refactor in existing React + FastAPI product
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Phase 1 只固定新的 4 步业务化结构，不新增额外能力，不改变底层执行模型。
- Step 1 只承载 `方案名称` 和 `对账目的`，不再放左右数据集选择，也不再放左/右口径描述。
- Step 2 调整为“数据准备”，承载左右数据集选择、筛选数据 / 行数据操作占位、左右输出表字段配置，以及后续 `proc` 试跑入口。
- Step 3 调整为“对账规则”，输入来源是 Step 2 的整理后输出结构，而不是原始数据集。
- Step 4 是确认与保存页，只展示方案摘要、试跑状态和保存门禁，不再成为第二个可编辑主界面。
- 新向导的长期状态模型不再继续扩张当前扁平 `schemeDraft`，而是按步骤拆成至少 4 个语义切片：`intent`、`preparation`、`reconciliation`、`confirmation`。
- 用户可编辑的业务配置是权威数据；生成的 JSON、兼容性检查结果、试跑结果和样例预览都属于派生工件，必须挂靠到某个明确版本的业务配置上。
- 上游步骤一旦改动，必须显式失效下游派生工件与通过状态。
- 不引入 `instruction_text` / `rendered_summary` 这类双权威文本面。
- Phase 1 复用现有 `ReconWorkspace` 里的创建方案弹窗，不迁移到独立页面。
- 文案和字段命名优先面向财务用户，默认界面避免暴露 JSON、DSL、validator 等技术术语。
- JSON 仅保留为高级查看能力，不作为默认编辑路径。
- Phase 1 继续沿用现有设计会话接口 `/recon/schemes/design/*` 和最终保存接口 `/recon/schemes`。
- 现有 `proc DSL` / `recon DSL` 与保存前试跑门禁保持不变。

### the agent's Discretion
- 前端最终采用 `useReducer`、拆分 hooks，还是保留父组件 helper + 子组件 props 的方式，可以在 planning 阶段决定；但必须把“权威配置”和“派生工件”明确分层。
- Step badge、摘要卡片、空状态和过渡动画的视觉表现可沿用现有 `ReconWorkspace` 设计语言，不需要在 Phase 1 另起一套视觉系统。

### Deferred Ideas (OUT OF SCOPE)
- 真正可执行的“筛选数据 / 行数据操作”可视化编辑器
- 更深度的整理规则 / 对账逻辑模板复用能力

</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 4 步向导外壳与步骤导航 | Browser/Client | Frontend Server | 完全属于前端交互壳和局部状态展示 |
| 草稿权威模型与失效规则 | Browser/Client | API/Backend | 权威业务配置和派生工件版本管理先在前端落地，再编译到后端接口 |
| AI 设计会话调用编排 | Browser/Client | API/Backend | 前端负责触发和消费 `/schemes/design/*`，后端继续拥有生成与试跑能力 |
| 最终方案保存载荷编译 | Browser/Client | API/Backend | 前端把草稿切片编译成现有 `scheme_meta_json` / `dataset_bindings_json` 契约 |
| 保存前试跑门禁 | API/Backend | Browser/Client | 后端已校验 `proc_trial_status` / `recon_trial_status`，前端只负责更清晰地表达门禁 |

</architectural_responsibility_map>

<research_summary>
## Summary

这一 phase 不需要为“新建对账方案”引入新的框架或新的页面体系。现有仓库已经具备可用的前端 modal 壳、设计会话接口、保存接口、JSON 高级视图和试跑门禁，因此 Phase 1 的正确研究结论是“重构状态权责和步骤边界”，而不是“补更多能力”或“重起一个前端架构层”。

从代码现状看，`ReconWorkspace.tsx` 已经承担了创建方案的完整 orchestration，但 `schemeDraft` 扁平且同时承载了业务输入、生成结果、兼容性提示和试跑输出，导致任何上游编辑都只能靠 scattered callback 手动清空。对于这一类按钮驱动、跨步骤有明确失效关系的 wizard，标准做法不是引入状态机库，而是先把权威数据和派生工件拆开，再把每一步的 invalidation 规则系统化。

**Primary recommendation:** 保持现有 modal + API 边界，先把前端 wizard 重构成“步骤切片状态 + 派生工件 + 显式失效规则”的结构，然后再在后续 phase 往 Step 2 和 Step 3 注入更重的业务配置能力。
</research_summary>

<standard_stack>
## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 19.2.0 | Step shell, controlled inputs, local orchestration | 现有前端已基于 React 19 构建，Phase 1 无需引入额外状态框架 |
| TypeScript | 5.9.x | Wizard state typing, payload adapters, invalidation helpers | 当前项目已启用严格 TS，适合把状态切片与派生工件模型类型化 |
| Tailwind CSS | 4.1.x | Wizard layout, cards, banners, state badges | 现有组件视觉全部基于 Tailwind utility class，复用成本最低 |
| lucide-react | 0.563.x | Step icons, status icons | 当前工作区已统一使用 lucide-react |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| FastAPI routes in `scheme_design/api.py` | existing | 设计会话 start / target / generate / trial 边界 | 继续复用现有 `/recon/schemes/design/*` 流程时使用 |
| `fetchReconAutoApi` + SSE consumer | existing | 统一 REST / SSE 调用与降级路径 | 所有 wizard 生成、试跑调用都应继续从这里走 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 现有 local state + typed helpers | XState / Zustand | 对当前 phase 过重，会把“收口模型”问题变成“迁移状态库”问题 |
| 保留扁平 `schemeDraft` | 分层草稿模型 | 保留扁平对象短期改得快，但会继续放大失效和派生工件混用问题 |
| 复用当前 modal | 新独立页面 | 独立页面可更干净，但会把 Phase 1 从“框架收口”扩大成“入口迁移” |

**Installation:**
```bash
# No new package is required for Phase 1 research conclusion.
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### System Architecture Diagram

```text
User input
  ↓
Wizard step shell in ReconWorkspace
  ↓
Step-specific draft slice (intent / preparation / reconciliation / confirmation)
  ↓
Derived artifact layer
  ├─ generated proc/recon JSON
  ├─ compatibility state
  ├─ trial preview
  └─ stale/reference markers
  ↓
Adapter functions
  ├─ /recon/schemes/design/* for generate / trial
  └─ /recon/schemes for final save
  ↓
Existing backend save / validation gates
```

### Recommended Project Structure
```text
finance-web/src/components/recon/
├── SchemeWizardTargetProcStep.tsx      # Step 1/2 presentation shell (to be narrowed)
├── SchemeWizardReconStep.tsx           # Step 3 presentation shell
├── SchemeWizardSummaryStep.tsx         # New Step 4 summary shell
├── schemeWizardState.ts                # Draft slices, invalidation helpers, adapters
└── autoApi.ts                          # Existing REST/SSE boundary
```

### Pattern 1: Split authoritative draft from derived artifacts
**What:** Keep editable business data separate from generated JSON, compatibility hints and trial previews.
**When to use:** Multi-step forms where upstream edits invalidate downstream generated artifacts.
**Example:**
```ts
type WizardDraft = {
  intent: {
    name: string
    businessGoal: string
  }
  preparation: {
    leftDatasets: SchemeSourceOption[]
    rightDatasets: SchemeSourceOption[]
    leftDescription: string
    rightDescription: string
  }
  derived: {
    proc: {
      draftText: string
      ruleJson: Record<string, unknown> | null
      status: 'idle' | 'stale' | 'passed' | 'needs_adjustment'
    }
  }
}
```

### Pattern 2: Centralize invalidation rules in helper functions
**What:** Use explicit reset/invalidate helpers instead of scattering partial resets across callbacks.
**When to use:** Upstream field changes must deterministically clear or mark stale multiple downstream artifacts.
**Example:**
```ts
function invalidateFromIntent(prev: WizardDraft): WizardDraft {
  return {
    ...prev,
    preparation: emptyPreparationDraft(),
    reconciliation: emptyReconciliationDraft(),
    derived: emptyDerivedDraft(),
  }
}
```

### Pattern 3: Keep backend contract compilation at the edge
**What:** UI state uses business-friendly types; compile to `scheme_meta_json` only at save/generate/trial boundaries.
**When to use:** Existing backend API is stable but user-facing UI needs a cleaner model.
**Example:**
```ts
function buildSchemePayload(draft: WizardDraft) {
  return {
    scheme_name: draft.intent.name.trim(),
    description: draft.intent.businessGoal.trim(),
    scheme_meta_json: compileSchemeMeta(draft),
  }
}
```

### Anti-Patterns to Avoid
- **继续扩张扁平 `schemeDraft`:** 会让业务输入、生成产物和试跑结果继续互相污染，后续 phase 只会更难收口。
- **用两个文本面表示一个配置:** 一个给用户编辑，一个给系统展示，会直接破坏所见即所得。
- **把 invalidation 隐藏成“默默清空”:** 财务用户会误以为系统丢数据；必须显式标记 stale 或 reference 状态。
</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| REST/SSE transport | 新的请求层或第二套 polling/SSE 工具 | `fetchReconAutoApi` + `consumeRuleGenerationStream` | 现有路径已兼容 `/api/recon` fallback 和流式消息解析 |
| Theme management | 向导私有主题切换逻辑 | `finance-web/src/theme.ts` + existing CSS tokens | dark mode 已有统一入口，局部另造会导致视觉撕裂 |
| Save-time validation | 前端复制后端保存门禁逻辑一整套 | 以前端提示 + 后端 `/schemes` gate 为准 | 后端已经拥有最终校验权，前端只需要更清晰表达状态 |

**Key insight:** 这一步最容易误入“造一层新架构”，但现有仓库已经有 transport、theme、save gate 和 workspace shell，真正需要重做的是状态语义和步骤边界。
</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Upstream edits silently invalidate downstream state
**What goes wrong:** 用户改了方案目标或数据准备，`proc` / `recon` 结果被部分保留、部分清空，用户无法判断当前样例是不是最新的。
**Why it happens:** 业务草稿、派生 JSON、试跑样例和状态提示都混在一个对象里。
**How to avoid:** 给每一步建立独立 draft slice，并用统一 invalidation helper 管理派生工件。
**Warning signs:** 多个 callback 都在写 `procTrialStatus = 'idle'`、`reconRuleJson = null` 一类散落逻辑。

### Pitfall 2: UI shell phase scope失控
**What goes wrong:** 本来只该收口 wizard shell，却顺手开始实现完整字段编辑器、完整规则编辑器或新页面入口，导致 phase 目标飘移。
**Why it happens:** “反正要改”时把 Phase 2/3 的内容提前带进来。
**How to avoid:** Phase 1 只做步骤框架、状态语义和摘要页，不交付完整 Step 2/3 能力。
**Warning signs:** Plan 任务开始新增复杂字段配置器、公式 builder、rule editor schema。

### Pitfall 3: UI wording仍然技术导向
**What goes wrong:** 财务用户仍然看到 `proc`、`recon`、`JSON validator` 等术语，虽然壳变了，但理解成本没降。
**Why it happens:** 直接沿用当前工程命名做标题和提示语。
**How to avoid:** 业务标题、摘要文案和状态提示统一使用财务语境；技术名词只保留在高级视图或错误详情。
**Warning signs:** Step title、primary CTA、summary card 里直接出现 DSL/JSON 术语。
</common_pitfalls>

<code_examples>
## Code Examples

Verified patterns from the current codebase:

### Existing save-gate edge compilation
```ts
// Source: finance-web/src/components/ReconWorkspace.tsx
if (schemeDraft.procTrialStatus !== 'passed' || schemeDraft.reconTrialStatus !== 'passed') {
  setModalError('请先完成数据整理和对账逻辑的试跑验证，再保存方案。')
  return
}
```

### Existing design-session transport boundary
```ts
// Source: finance-web/src/components/recon/autoApi.ts
export async function fetchReconAutoApi(path: string, init?: RequestInit): Promise<Response> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const candidates = [`/api/recon${normalizedPath}`, `/api/api/recon${normalizedPath}`];
  ...
}
```

### Existing theme token source of truth
```css
/* Source: finance-web/src/index.css */
:root {
  --color-surface: #ffffff;
  --color-surface-secondary: #f5f7fb;
  --color-text-primary: #0f172a;
}

html[data-theme='dark'] {
  --color-surface: #132033;
  --color-surface-secondary: #091321;
  --color-text-primary: #eef4fb;
}
```
</code_examples>

<sota_updates>
## State of the Art (2024-2025)

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 单一巨大组件直接存全部流程状态 | 分 slice + derived artifact 的 wizard state | React app complexity growth over the last few years | 对多步 AI-assisted forms 更稳定，便于失效和回放 |
| 单纯“禁用下一步”作为流程控制 | 明确 step readiness + stale/reference messaging | 现代 workflow-heavy UIs | 对用户更可解释，尤其适合 AI 生成后需人工修正的场景 |

**New tools/patterns to consider:**
- 本 phase 不需要引入新库；重点是把已有 React/TS 边界用得更清楚。
- 以 helper module 抽出 draft adapter / invalidation rules，比直接扩展父组件更利于后续 Step 2/3 演进。

**Deprecated/outdated:**
- 让用户在 UI 中同时面对两套文本权威面板
- 在顶层 notice 中提示错误，但当前操作区域没有局部反馈
</sota_updates>

<validation_architecture>
## Validation Architecture

- Phase 1 以前端组件测试、类型/构建检查和局部交互回归为主，不依赖新测试框架。
- Quick feedback 以 `vitest` 单测或小范围组件测试为主。
- Wave 完成后至少跑 `eslint` 和 `build`，确保向导壳和类型没有被重构破坏。
- 人工校验只保留“步骤流是否符合财务认知”“stale/reference 提示是否清晰”这类自动化难完全覆盖的交互。

</validation_architecture>

<open_questions>
## Open Questions

1. **状态容器最终采用 reducer 还是 helper module**
   - What we know: 当前 phase 不需要引入新库，但必须拆开权威草稿与派生工件。
   - What's unclear: 最终是 `useReducer` 还是 `useState + helper` 更贴合现有文件结构。
   - Recommendation: 规划时基于改动面大小决定；优先最小入侵但要保证 invalidation 规则集中。

2. **Step 4 是否独立成新组件文件**
   - What we know: 现有 Step 4 基本还是在 `ReconWorkspace.tsx` 内联摘要。
   - What's unclear: 是先保留 inline rendering，还是抽成 `SchemeWizardSummaryStep.tsx`。
   - Recommendation: 如果 Phase 1 要大改摘要结构，就直接抽组件，避免 `ReconWorkspace.tsx` 继续膨胀。
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)
- `finance-web/src/components/ReconWorkspace.tsx` — 当前 wizard 状态模型、试跑门禁、保存载荷编译
- `finance-web/src/components/recon/SchemeWizardTargetProcStep.tsx` — 当前 Step 1/2 展示与文案结构
- `finance-web/src/components/recon/SchemeWizardReconStep.tsx` — 当前 Step 3 展示、试跑结果与 JSON 入口
- `finance-web/src/components/recon/autoApi.ts` — 现有 REST / SSE transport 边界
- `finance-agents/data-agent/graphs/recon/scheme_design/api.py` — 设计会话后端接口
- `finance-agents/data-agent/graphs/recon/auto_run_api.py` — 保存方案与门禁校验
- `finance-web/src/index.css` — 主题 token 与 dark mode 基线

### Secondary (MEDIUM confidence)
- `.planning/phases/01-wizard-foundation/01-CONTEXT.md` — 用户锁定的业务决策与 phase 边界
- `AGENTS.md` — 仓库级测试、构建和协作约束

### Tertiary (LOW confidence - needs validation)
- none
</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: React wizard shell refactor on existing app
- Ecosystem: existing repo stack only
- Patterns: draft slicing, derived artifacts, invalidation, adapter compilation
- Pitfalls: state pollution, hidden stale results, scope drift

**Confidence breakdown:**
- Standard stack: HIGH - no new stack needed, repo is already opinionated
- Architecture: HIGH - driven by existing code hotspots and locked context
- Pitfalls: HIGH - already reflected in current user feedback and code shape
- Code examples: HIGH - all examples come from local source files

**Research date:** 2026-04-22
**Valid until:** 2026-05-22
</metadata>

---

*Phase: 01-wizard-foundation*
*Research completed: 2026-04-22*
*Ready for planning: yes*

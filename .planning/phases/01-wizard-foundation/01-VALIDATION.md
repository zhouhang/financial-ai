---
phase: 01
slug: wizard-foundation
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-22
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for wizard-shell refactor execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest + eslint + TypeScript/Vite build |
| **Config file** | `finance-web/vitest.config.ts` |
| **Quick run command** | `cd finance-web && npx vitest run tests/components/recon-fallback-warning.spec.tsx` |
| **Full suite command** | `cd finance-web && npm run test:components && npm run lint && npm run build` |
| **Estimated runtime** | ~120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd finance-web && npx vitest run tests/components/recon-fallback-warning.spec.tsx`
- **After every plan wave:** Run `cd finance-web && npm run test:components && npm run lint`
- **Before `$gsd-verify-work`:** `cd finance-web && npm run build` must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | FLOW-01 | T-01-01 | 草稿状态不会因局部重构丢失或串写 | unit/type | `cd finance-web && npx vitest run tests/components/recon-fallback-warning.spec.tsx` | ✅ | ⬜ pending |
| 01-02-01 | 02 | 2 | FLOW-01 | T-01-02 | Step 1 只暴露业务意图，未提前暴露数据准备能力 | component | `cd finance-web && npm run test:components` | ✅ | ⬜ pending |
| 01-03-01 | 03 | 3 | FLOW-01 | T-01-03 | Step 4 只显示摘要和保存门禁，不泄漏未通过状态 | build/integration | `cd finance-web && npm run lint && npm run build` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 财务视角下的步骤认知是否自然 | FLOW-01 | 自动化难以判断文案与步骤心智是否足够业务化 | 打开新增方案弹窗，确认 Step 1 只包含方案名称和对账目的，步骤标题不出现 `proc` / `recon` 技术术语 |
| stale/reference 提示是否易理解 | FLOW-01 | 自动化难以完整判断引用态提示是否可感知 | 在上游步骤修改后，确认下游样例和状态被明确标记为待重新生成或仅供参考，而不是静默覆盖 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 120s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-22

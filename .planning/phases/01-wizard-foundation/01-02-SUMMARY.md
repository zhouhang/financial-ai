---
phase: 01-wizard-foundation
plan: 02
subsystem: ui
tags: [react, wizard, ux]
requires:
  - phase: 01-wizard-foundation
    provides: state slices and invalidation helpers
provides:
  - finance-facing step shell
  - dedicated intent step
affects: [scheme-wizard]
tech-stack:
  added: []
  patterns: [business-first step copy]
key-files:
  created: [/Users/kevin/workspace/financial-ai/finance-web/src/components/recon/SchemeWizardIntentStep.tsx]
  modified: [/Users/kevin/workspace/financial-ai/finance-web/src/components/ReconWorkspace.tsx, /Users/kevin/workspace/financial-ai/finance-web/src/components/recon/SchemeWizardTargetProcStep.tsx]
key-decisions:
  - "第一步只保留方案名称和对账目的。"
patterns-established:
  - "数据集选择从第一步移到第二步，主流程不暴露 JSON。"
requirements-completed: [FLOW-01]
duration: 0min
completed: 2026-04-22
---

# Phase 1 Plan 02 Summary

**向导外壳改成财务可理解的四步流，第一步只讲业务目标，不再混入数据准备动作。**

## Accomplishments
- 增加独立的 `SchemeWizardIntentStep`，承载方案名称和对账目的。
- `ReconWorkspace` 明确区分 `方案目标 / 数据准备 / 对账规则 / 确认保存` 四步。
- 第二步改成真正的数据准备页，保留后续能力区而不提前暴露技术配置。

## Verification
- `finance-web` 构建通过

## Issues Encountered
- 无

## Next Phase Readiness
- 第二步可以直接接入左右数据集选择和输出字段编辑器。

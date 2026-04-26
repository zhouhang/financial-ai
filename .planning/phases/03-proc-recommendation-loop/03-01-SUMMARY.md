---
phase: 03-proc-recommendation-loop
plan: 01
subsystem: ui
tags: [react, proc, ai]
requires:
  - phase: 02-dataset-output-editor
    provides: output field editor and dataset selections
provides:
  - AI proc recommendation loop
  - reference preview handling after edits
  - proc output-field round-trip
affects: [scheme-wizard, proc-trial]
tech-stack:
  added: []
  patterns: [stale preview marked as reference]
key-files:
  created: []
  modified: [/Users/kevin/workspace/financial-ai/finance-web/src/components/ReconWorkspace.tsx, /Users/kevin/workspace/financial-ai/finance-web/src/components/recon/SchemeWizardTargetProcStep.tsx, /Users/kevin/workspace/financial-ai/finance-web/src/components/recon/schemeWizardState.ts]
key-decisions:
  - "人工修改后的字段配置始终是权威版本，AI 结果只能回填不能覆盖手工调整。"
patterns-established:
  - "旧试跑结果允许保留，但必须标成“仅供参考”。"
requirements-completed: [PROC-01, PROC-02, PROC-03, PROC-04]
duration: 0min
completed: 2026-04-22
---

# Phase 3 Plan 01 Summary

**第二步已经形成 AI 整理建议、人工修正与 `proc` 试跑互相校正的闭环。**

## Accomplishments
- AI 生成整理配置后可直接回填第二步字段编辑器。
- `proc` 试跑结果展示原始样例和整理后样例，编辑后旧结果保留为参考态。
- `proc rule json` 可以反向恢复为左右输出字段，保证已有规则与新编辑器互通。

## Verification
- `cd /Users/kevin/workspace/financial-ai/finance-web && npx vitest run tests/components/scheme-wizard-state.spec.ts`

## Issues Encountered
- 无

## Next Phase Readiness
- 第三步可以直接消费第二步输出结构，生成结构化对账规则。

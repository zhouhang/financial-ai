---
status: partial
phase: 05-save-gate-and-hardening
source:
  - 05-01-SUMMARY.md
started: 2026-04-22T21:35:00Z
updated: 2026-04-22T21:35:00Z
---

## Current Test

[testing paused — 3 items outstanding]

## Tests

### 1. 时间口径在已有规则 / AI 生成 / 保存之间保持一致
expected: 选择已有对账逻辑或重新 AI 生成后，左右时间字段不会丢失；保存后的方案详情和新增运行计划也能看到相同时间口径。
result: pass

### 2. 第四步保存门禁与试跑状态一致
expected: 只有当数据整理试跑和对账试跑都通过后，第四步保存按钮才可点击；否则摘要区明确提示阻塞原因。
result: pending

### 3. 高级 JSON 视图能查看最新 proc / recon JSON
expected: 在第二步和第三步点击 JSON 后，弹层展示的是当前最新生成结果，而不是旧版本。
result: pending

### 4. 第二步输出字段和第三步结构化字段在重新打开方案后仍可还原
expected: 保存后的方案再次打开时，左右输出字段、匹配字段、金额字段和时间字段都能从 scheme meta 还原。
result: pending

## Summary

total: 4
passed: 1
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

[]

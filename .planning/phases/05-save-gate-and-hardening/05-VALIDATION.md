---
phase: 05
slug: save-gate-and-hardening
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-22
---

# Phase 05 — Validation Strategy

## Automated Checks

| Command | Purpose |
|---------|---------|
| `cd /Users/kevin/workspace/financial-ai/finance-web && npx tsc --noEmit --pretty false` | 校验 wizard 状态与组件类型一致性 |
| `cd /Users/kevin/workspace/financial-ai/finance-web && npx vitest run tests/components/scheme-wizard-state.spec.ts tests/components/recon-fallback-warning.spec.tsx` | 校验状态回填、fallback 提示和时间口径持久化 |
| `cd /Users/kevin/workspace/financial-ai/finance-web && npm run build` | 校验完整前端构建链路 |

## Manual Checks

| Behavior | Why Manual |
|----------|------------|
| 第四步保存门禁与试跑状态一致 | 需要真实点击流程确认按钮禁用/启用时机 |
| 第二步 / 第三步 JSON 弹层展示的是最新结果 | 需要结合 UI 操作确认不是旧缓存 |
| 保存后重新打开方案能恢复左右输出字段与时间口径 | 需要通过真实保存后再打开验证 |

## Current Outcome

- 自动化检查已完成并通过。
- 人工 UAT 已写入 `05-UAT.md`，当前仍有 3 项待人工确认。

---
phase: 06
slug: multi-sheet-upload-intake
status: completed
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-22
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for multi-sheet upload intake execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Primary targets** | `finance-agents/data-agent/tests/` and `finance-mcp/tests/` |
| **Quick run command** | `cd /Users/kevin/workspace/financial-ai && source .venv/bin/activate && pytest finance-agents/data-agent/tests/test_file_intake.py -q` |
| **Cross-path command** | `cd /Users/kevin/workspace/financial-ai && source .venv/bin/activate && pytest finance-agents/data-agent/tests/test_file_intake.py finance-mcp/tests/test_file_validate_tool.py -q` |
| **Full phase command** | `cd /Users/kevin/workspace/financial-ai && source .venv/bin/activate && pytest finance-agents/data-agent/tests/test_file_intake.py finance-agents/data-agent/tests/recon/test_execution_service.py finance-mcp/tests/test_file_validate_tool.py -q` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After plan 06-01:** Run the `test_file_intake.py` subset covering split and path mapping.
- **After plan 06-02:** Run `test_file_intake.py` plus `test_file_validate_tool.py` to verify prefilter and ambiguity surfacing.
- **After plan 06-03:** Run the full phase command above.
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | FILE-01, FILE-04 | T-06-01, T-06-02 | 多 sheet 工作簿能展开为逻辑文件且命名/路径可追溯 | unit | `pytest finance-agents/data-agent/tests/test_file_intake.py -q` | ✅ | green |
| 06-02-01 | 02 | 2 | FILE-02, FILE-03 | T-06-03, T-06-04 | 预筛选只过滤明显无效 sheet，真实歧义继续上抛 | unit/integration | `pytest finance-agents/data-agent/tests/test_file_intake.py finance-mcp/tests/test_file_validate_tool.py -q` | ✅ | green |
| 06-03-01 | 03 | 3 | FILE-01, FILE-02, FILE-03, FILE-04 | T-06-05 | `proc` / `recon` 都能从逻辑文件匹配结果走通执行映射 | integration | `pytest finance-agents/data-agent/tests/test_file_intake.py finance-agents/data-agent/tests/recon/test_execution_service.py finance-mcp/tests/test_file_validate_tool.py -q` | ✅ | green |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

Existing pytest infrastructure is sufficient. This phase only needs new targeted tests; no new test framework is required.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 额外说明页不会再触发“文件数量超过限制” | FILE-02 | 需要端到端观察预筛选和正式 file_check 的组合表现 | 上传一个包含业务 sheet + 说明页 + 空白页的工作簿，确认说明页被过滤且正式 file_check 仍只看到业务 sheet |
| 模糊命中仍然给出候选映射提示 | FILE-03 | 自动化只能校验返回结构，难以判断提示文案是否足够可理解 | 上传两个都能命中同一宽松 schema 的 sheet，确认失败消息里展示候选 table 列表 |
| 拆分文件命名可回溯 | FILE-04 | 需要人工审视日志/输出文件名可读性 | 查看拆分后逻辑文件名、错误提示和日志，确认都能定位到原工作簿与 sheet |

---

## Validation Sign-Off

- [x] All plans have automated verification targets
- [x] Sampling continuity: each plan has at least one executable pytest command
- [x] No watch-mode or long-running command required
- [x] `nyquist_compliant: true` set in frontmatter
- [x] 2026-04-23 reran targeted phase tests: `pytest finance-agents/data-agent/tests/test_file_intake.py finance-agents/data-agent/tests/test_public_nodes_file_intake.py finance-agents/data-agent/tests/recon/test_execution_service.py finance-mcp/tests/test_file_validate_tool.py -q` (`8 passed`)

**Approval:** approved 2026-04-22

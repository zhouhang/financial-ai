# Recon Explosion Exception Sampling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent high-volume reconciliation runs from creating and notifying every exception while preserving full run-level counts and showing a clear sampled-list indicator.

**Architecture:** The data-agent keeps full `anomaly_items` and full run summary counts, but `create_exception_tasks_node` samples before calling `execution_run_exception_create` when the configured threshold is exceeded. Sampling metadata is merged into `execution_runs.artifacts_json.runtime_summary.exception_sampling`; frontend runtime summary view models expose that metadata so the internal and public exception lists can label sampled displays.

**Tech Stack:** Python 3.12, pytest, async node tests with monkeypatch, React 19, TypeScript, Vitest, Testing Library.

---

## File Structure

- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
  - Owns notify policy parsing, anomaly sampling, sampled exception creation, and runtime summary metadata persistence.
- Modify: `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`
  - Extends existing node tests for policy parsing, sampling, and runtime summary artifacts.
- Modify: `finance-web/src/components/recon/runRuntimeSummary.ts`
  - Parses `runtime_summary.exception_sampling` into a typed frontend view model.
- Modify: `finance-web/src/components/ReconWorkspace.tsx`
  - Shows a sampled-list badge in the internal exception board without changing list behavior.
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
  - Shows the same sampled-list badge on the public exception page.
- Modify: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`
  - Covers public sampled display text.
- Modify: `finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx`
  - Covers internal sampled display text.

Do not modify MCP CRUD in `finance-mcp/auth/db.py` or `finance-mcp/tools/execution_runs.py` for this first implementation.

---

### Task 1: Backend Policy Parsing And Sampling Helpers

**Files:**
- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
- Test: `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`

- [ ] **Step 1: Write failing tests for policy parsing and sampling**

Append these tests near `test_create_exception_tasks_node_creates_all_anomalies` in `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`:

```python
def test_resolve_notify_policy_prefers_notify_policy_sample_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", "9")

    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "reminder_policy_json": {
                    "explosion_threshold": 50,
                    "explosion_sample_limit": 10,
                },
                "notify_policy": {
                    "explosion_threshold": 1000,
                    "sample_exception_limit": 200,
                },
            }
        }
    )

    assert policy == {
        "explosion_threshold": 1000,
        "sample_exception_limit": 200,
        "explosion_sample_limit": 200,
    }


def test_resolve_notify_policy_keeps_legacy_reminder_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT", raising=False)

    policy = nodes._resolve_notify_policy(
        {
            "plan_meta_json": {
                "reminder_policy": {
                    "explosion_threshold": 300,
                    "explosion_sample_limit": 40,
                }
            }
        }
    )

    assert policy["explosion_threshold"] == 300
    assert policy["sample_exception_limit"] == 40
    assert policy["explosion_sample_limit"] == 40


def test_sample_anomalies_for_exception_creation_stratifies_by_type_and_owner() -> None:
    anomalies = [
        {"item_id": "a1", "anomaly_type": "source_only", "_exception_owner_identifier": "owner-a"},
        {"item_id": "a2", "anomaly_type": "source_only", "_exception_owner_identifier": "owner-a"},
        {"item_id": "b1", "anomaly_type": "target_only", "_exception_owner_identifier": "owner-b"},
        {"item_id": "b2", "anomaly_type": "target_only", "_exception_owner_identifier": "owner-b"},
        {"item_id": "c1", "anomaly_type": "matched_with_diff", "_exception_owner_identifier": "owner-a"},
        {"item_id": "c2", "anomaly_type": "matched_with_diff", "_exception_owner_identifier": "owner-a"},
    ]

    sampled, metadata = nodes._sample_anomalies_for_exception_creation(
        anomalies,
        sample_limit=4,
    )

    assert [item["item_id"] for item in sampled[:3]] == ["a1", "b1", "c1"]
    assert len(sampled) == 4
    assert metadata["enabled"] is True
    assert metadata["sample_count"] == 4
    assert metadata["total_count"] == 6
    assert metadata["strategy"] == "stratified_by_anomaly_type_owner"
    assert metadata["fallback_used"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_resolve_notify_policy_prefers_notify_policy_sample_limit finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_resolve_notify_policy_keeps_legacy_reminder_policy finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_sample_anomalies_for_exception_creation_stratifies_by_type_and_owner -v
```

Expected: tests fail because `_resolve_notify_policy` does not return `sample_exception_limit` and `_sample_anomalies_for_exception_creation` does not exist.

- [ ] **Step 3: Implement policy parsing constants and helper functions**

In `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`, replace the current `_DEFAULT_NOTIFY_EXPLOSION_LIMIT = 50` constant with:

```python
_DEFAULT_NOTIFY_EXPLOSION_LIMIT = 1000
_DEFAULT_EXCEPTION_SAMPLE_LIMIT = 200
_EXCEPTION_SAMPLING_STRATEGY = "stratified_by_anomaly_type_owner"
```

Replace `_resolve_notify_policy` with:

```python
def _resolve_notify_policy(run_plan: dict[str, Any]) -> dict[str, int]:
    meta = _safe_dict(run_plan.get("plan_meta_json") or run_plan.get("plan_meta") or run_plan.get("meta"))
    legacy_policy = _safe_dict(meta.get("reminder_policy_json") or meta.get("reminder_policy"))
    notify_policy = _safe_dict(meta.get("notify_policy"))
    policy = {**legacy_policy, **notify_policy}
    threshold = _safe_int(
        policy.get("explosion_threshold")
        or policy.get("max_detail_reminders")
        or os.getenv("RECON_AUTO_NOTIFY_EXPLOSION_LIMIT"),
        _DEFAULT_NOTIFY_EXPLOSION_LIMIT,
    )
    sample_limit = _safe_int(
        policy.get("sample_exception_limit")
        or policy.get("explosion_sample_limit")
        or os.getenv("RECON_EXCEPTION_SAMPLE_LIMIT"),
        _DEFAULT_EXCEPTION_SAMPLE_LIMIT,
    )
    threshold = max(1, threshold)
    sample_limit = max(1, sample_limit)
    return {
        "explosion_threshold": threshold,
        "sample_exception_limit": sample_limit,
        "explosion_sample_limit": sample_limit,
    }
```

Add these helpers below `_resolve_notify_policy`:

```python
def _anomaly_sampling_owner_identifier(item: dict[str, Any]) -> str:
    return str(
        item.get("_exception_owner_identifier")
        or item.get("owner_identifier")
        or item.get("owner")
        or ""
    ).strip()


def _sampling_group_key(item: dict[str, Any]) -> tuple[str, str]:
    anomaly_type = str(item.get("anomaly_type") or "unknown").strip() or "unknown"
    return anomaly_type, _anomaly_sampling_owner_identifier(item)


def _sample_anomalies_for_exception_creation(
    anomalies: list[dict[str, Any]],
    *,
    sample_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total_count = len(anomalies)
    safe_limit = max(1, int(sample_limit or _DEFAULT_EXCEPTION_SAMPLE_LIMIT))
    metadata = {
        "enabled": True,
        "reason": "explosion_threshold_exceeded",
        "sample_limit": safe_limit,
        "total_count": total_count,
        "sample_count": 0,
        "created_count": 0,
        "create_failed_count": 0,
        "strategy": _EXCEPTION_SAMPLING_STRATEGY,
        "fallback_used": False,
    }
    if total_count <= safe_limit:
        metadata["sample_count"] = total_count
        return list(anomalies), metadata

    try:
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        group_order: list[tuple[str, str]] = []
        for item in anomalies:
            key = _sampling_group_key(item)
            if key not in groups:
                groups[key] = []
                group_order.append(key)
            groups[key].append(item)

        sampled: list[dict[str, Any]] = []
        selected_by_key: dict[tuple[str, str], int] = {}
        for key in group_order:
            if len(sampled) >= safe_limit:
                break
            sampled.append(groups[key][0])
            selected_by_key[key] = 1

        remaining_slots = safe_limit - len(sampled)
        remaining_total = sum(max(0, len(groups[key]) - selected_by_key.get(key, 0)) for key in group_order)
        if remaining_slots > 0 and remaining_total > 0:
            fractional_allocations: list[tuple[float, tuple[str, str], int]] = []
            for key in group_order:
                remaining_in_group = max(0, len(groups[key]) - selected_by_key.get(key, 0))
                if remaining_in_group <= 0:
                    continue
                raw_share = remaining_slots * (remaining_in_group / remaining_total)
                whole_share = min(remaining_in_group, int(raw_share))
                if whole_share:
                    sampled.extend(groups[key][selected_by_key.get(key, 0):selected_by_key.get(key, 0) + whole_share])
                    selected_by_key[key] = selected_by_key.get(key, 0) + whole_share
                fractional_allocations.append((raw_share - whole_share, key, remaining_in_group))

            leftover_slots = safe_limit - len(sampled)
            for _, key, _ in sorted(fractional_allocations, key=lambda item: (-item[0], group_order.index(item[1]))):
                if leftover_slots <= 0:
                    break
                cursor = selected_by_key.get(key, 0)
                if cursor >= len(groups[key]):
                    continue
                sampled.append(groups[key][cursor])
                selected_by_key[key] = cursor + 1
                leftover_slots -= 1

        sampled = sampled[:safe_limit]
        metadata["sample_count"] = len(sampled)
        return sampled, metadata
    except Exception as exc:
        logger.error("[recon][exception_sampling] 分层抽样失败，回退为前 %s 条: %s", safe_limit, exc)
        fallback = list(anomalies[:safe_limit])
        metadata["sample_count"] = len(fallback)
        metadata["fallback_used"] = True
        metadata["fallback_error"] = str(exc)
        return fallback, metadata
```

- [ ] **Step 4: Run helper tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_resolve_notify_policy_prefers_notify_policy_sample_limit finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_resolve_notify_policy_keeps_legacy_reminder_policy finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_sample_anomalies_for_exception_creation_stratifies_by_type_and_owner -v
```

Expected: PASS.

- [ ] **Step 5: Commit backend helper work**

Run:

```bash
git add finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py
git commit -m "feat(recon): add exception sampling helpers"
```

Expected: commit succeeds.

---

### Task 2: Backend Node Sampling And Runtime Metadata

**Files:**
- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
- Test: `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`

- [ ] **Step 1: Update existing exploding test expectations**

In `finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py`, rename `test_create_exception_tasks_node_creates_all_anomalies` to:

```python
def test_create_exception_tasks_node_samples_exploding_anomalies(monkeypatch: pytest.MonkeyPatch) -> None:
```

In that renamed test, add an update payload collector next to `created_payloads`:

```python
    update_payloads: list[dict[str, object]] = []
```

Replace the existing `fake_call_mcp_tool` with:

```python
    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_create":
            created_payloads.append(payload)
            index = len(created_payloads)
            return {
                "success": True,
                "exception": {
                    "id": f"exception-{index}",
                    "run_id": payload["run_id"],
                    "owner_identifier": payload["owner_identifier"],
                    "feedback_json": {},
                },
            }
        if name == "execution_run_update":
            update_payloads.append(payload)
            return {
                "success": True,
                "run": {
                    "id": payload["run_id"],
                    "artifacts_json": payload["artifacts_json"],
                },
            }
        raise AssertionError(f"unexpected MCP tool: {name}")
```

In that test's `plan_meta_json.notify_policy`, change:

```python
"explosion_sample_limit": 3,
```

to:

```python
"sample_exception_limit": 3,
```

Replace the final assertions with:

```python
    assert len(created_payloads) == 3
    assert recon_ctx["exception_created_count"] == 3
    assert recon_ctx["exception_creation_limited"] is True
    assert recon_ctx["exception_total_count"] == len(anomalies)
    assert recon_ctx["exception_created_sample_count"] == 3
    assert recon_ctx["auto_notify_policy"]["explosion"] is True
    assert recon_ctx["auto_notify_policy"]["created_exception_sample_limit"] == 3
    assert recon_ctx["exception_sampling"]["enabled"] is True
    assert recon_ctx["exception_sampling"]["threshold"] == 10
    assert recon_ctx["exception_sampling"]["sample_limit"] == 3
    assert recon_ctx["exception_sampling"]["total_count"] == len(anomalies)
    assert recon_ctx["exception_sampling"]["sample_count"] == 3
    assert len(update_payloads) == 1
```

- [ ] **Step 2: Add runtime artifact persistence test**

Append this test after the renamed test:

```python
def test_create_exception_tasks_node_persists_exception_sampling_runtime_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_payloads: list[dict[str, object]] = []
    create_payloads: list[dict[str, object]] = []

    async def fake_call_mcp_tool(name: str, payload: dict[str, object]) -> dict[str, object]:
        if name == "execution_run_exception_create":
            create_payloads.append(payload)
            return {
                "success": True,
                "exception": {
                    "id": f"exception-{len(create_payloads)}",
                    "run_id": payload["run_id"],
                    "owner_identifier": payload["owner_identifier"],
                    "feedback_json": {},
                },
            }
        if name == "execution_run_update":
            update_payloads.append(payload)
            return {
                "success": True,
                "run": {
                    "id": payload["run_id"],
                    "artifacts_json": payload["artifacts_json"],
                },
            }
        raise AssertionError(f"unexpected MCP tool: {name}")

    monkeypatch.setattr(nodes, "call_mcp_tool", fake_call_mcp_tool)

    anomalies = [
        {"item_id": f"anomaly-{index}", "anomaly_type": "source_only"}
        for index in range(1, 8)
    ]
    state = {
        "auth_token": "token",
        "recon_ctx": {
            "execution_run_record": {
                "id": "run-001",
                "artifacts_json": {
                    "runtime_summary": {
                        "queue": {"job_id": "queue-001"},
                        "summary_notification": {"status": "sent"},
                    }
                },
            },
            "scheme_code": "scheme-001",
            "run_plan": {
                "owner_mapping_json": {
                    "default_owner": {"name": "周行", "identifier": "ding-user-001"}
                },
                "plan_meta_json": {
                    "notify_policy": {
                        "explosion_threshold": 3,
                        "sample_exception_limit": 2,
                    }
                },
            },
            "anomaly_items": anomalies,
        },
    }

    result = asyncio.run(nodes.create_exception_tasks_node(state))

    assert len(create_payloads) == 2
    assert len(update_payloads) == 1
    artifacts = update_payloads[0]["artifacts_json"]
    runtime_summary = artifacts["runtime_summary"]
    assert runtime_summary["queue"] == {"job_id": "queue-001"}
    assert runtime_summary["summary_notification"] == {"status": "sent"}
    assert runtime_summary["exception_sampling"]["enabled"] is True
    assert runtime_summary["exception_sampling"]["total_count"] == 7
    assert runtime_summary["exception_sampling"]["sample_count"] == 2
    assert result["recon_ctx"]["execution_run_record"]["artifacts_json"] == artifacts
```

- [ ] **Step 3: Run node tests to verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_create_exception_tasks_node_samples_exploding_anomalies finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_create_exception_tasks_node_persists_exception_sampling_runtime_summary -v
```

Expected: FAIL because `create_exception_tasks_node` still creates all anomalies and does not persist `exception_sampling`.

- [ ] **Step 4: Add runtime summary merge helper**

In `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`, add below `_merge_runtime_summary_notification`:

```python
def _merge_runtime_exception_sampling(
    artifacts: dict[str, Any],
    sampling: dict[str, Any],
) -> dict[str, Any]:
    patched = dict(artifacts or {})
    runtime_summary = _safe_dict(patched.get("runtime_summary"))
    runtime_summary["exception_sampling"] = _safe_dict(sampling)
    patched["runtime_summary"] = runtime_summary
    return patched


async def _persist_runtime_exception_sampling(
    *,
    auth_token: str,
    ctx: dict[str, Any],
    sampling: dict[str, Any],
) -> None:
    run = _safe_dict(ctx.get("execution_run_record"))
    run_id = str(run.get("id") or "").strip()
    if not auth_token or not run_id or not sampling:
        return
    artifacts = _merge_runtime_exception_sampling(
        _safe_dict(run.get("artifacts_json")),
        sampling,
    )
    update_result = await call_mcp_tool(
        "execution_run_update",
        {"auth_token": auth_token, "run_id": run_id, "artifacts_json": artifacts},
    )
    if bool(update_result.get("success")):
        ctx["execution_run_record"] = _safe_dict(update_result.get("run")) or {
            **run,
            "artifacts_json": artifacts,
        }
```

- [ ] **Step 5: Update `create_exception_tasks_node` to sample before creation**

In `create_exception_tasks_node`, replace:

```python
    explosion_sample_limit = int(notify_policy["explosion_sample_limit"])
    total_anomaly_count = len(anomalies)
    notify_explosion = total_anomaly_count > explosion_threshold
    ctx["auto_notify_policy"] = {
        **notify_policy,
        "anomaly_count": total_anomaly_count,
        "explosion": notify_explosion,
        "created_exception_sample_limit": total_anomaly_count,
    }
```

with:

```python
    sample_limit = int(notify_policy["sample_exception_limit"])
    total_anomaly_count = len(anomalies)
    notify_explosion = total_anomaly_count > explosion_threshold
    sampled_anomalies = anomalies
    sampling_metadata: dict[str, Any] = {
        "enabled": False,
        "threshold": explosion_threshold,
        "sample_limit": sample_limit,
        "total_count": total_anomaly_count,
        "sample_count": total_anomaly_count,
        "created_count": 0,
        "create_failed_count": 0,
        "strategy": _EXCEPTION_SAMPLING_STRATEGY,
        "fallback_used": False,
    }
    if notify_explosion:
        sampled_anomalies, sampling_metadata = _sample_anomalies_for_exception_creation(
            anomalies,
            sample_limit=sample_limit,
        )
        sampling_metadata["threshold"] = explosion_threshold
    ctx["auto_notify_policy"] = {
        **notify_policy,
        "anomaly_count": total_anomaly_count,
        "explosion": notify_explosion,
        "created_exception_sample_limit": len(sampled_anomalies),
    }
```

Then replace the creation loop header:

```python
    for idx, item in enumerate(anomalies, start=1):
```

with:

```python
    for idx, item in enumerate(sampled_anomalies, start=1):
```

After the loop, replace:

```python
    ctx["exception_created_count"] = created
    ctx["created_exceptions"] = created_exceptions
    ctx["exception_creation_limited"] = False
    ctx["exception_total_count"] = total_anomaly_count
    ctx["exception_created_sample_count"] = created
    return {"recon_ctx": ctx}
```

with:

```python
    sampling_metadata["created_count"] = created
    sampling_metadata["create_failed_count"] = max(0, len(sampled_anomalies) - created)
    ctx["exception_created_count"] = created
    ctx["created_exceptions"] = created_exceptions
    ctx["exception_creation_limited"] = notify_explosion
    ctx["exception_total_count"] = total_anomaly_count
    ctx["exception_created_sample_count"] = len(sampled_anomalies)
    ctx["exception_sampling"] = sampling_metadata
    if notify_explosion:
        await _persist_runtime_exception_sampling(
            auth_token=auth_token,
            ctx=ctx,
            sampling=sampling_metadata,
        )
    return {"recon_ctx": ctx}
```

- [ ] **Step 6: Run backend node tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_create_exception_tasks_node_samples_exploding_anomalies finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_create_exception_tasks_node_persists_exception_sampling_runtime_summary -v
```

Expected: PASS.

- [ ] **Step 7: Run related backend regression tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_maybe_auto_notify_node_groups_exceptions_by_owner finance-agents/data-agent/tests/recon/test_summary_notification_recipient_name.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit backend node sampling**

Run:

```bash
git add finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py
git commit -m "feat(recon): sample exploding exception creation"
```

Expected: commit succeeds.

---

### Task 3: Frontend Runtime Summary Sampling View Model

**Files:**
- Modify: `finance-web/src/components/recon/runRuntimeSummary.ts`
- Test: `finance-web/tests/components/run-runtime-summary.test.ts`

- [ ] **Step 1: Create failing view-model tests**

Create `finance-web/tests/components/run-runtime-summary.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { buildRuntimeSummaryView } from '../../src/components/recon/runRuntimeSummary';

describe('buildRuntimeSummaryView exception sampling', () => {
  it('normalizes exception sampling metadata from runtime summary', () => {
    const view = buildRuntimeSummaryView({
      raw: {
        artifacts_json: {
          runtime_summary: {
            exception_sampling: {
              enabled: true,
              total_count: 35665,
              sample_count: 200,
              sample_limit: 200,
              threshold: 1000,
              strategy: 'stratified_by_anomaly_type_owner',
              fallback_used: false,
            },
          },
        },
      },
    });

    expect(view.exceptionSampling.enabled).toBe(true);
    expect(view.exceptionSampling.totalCount).toBe(35665);
    expect(view.exceptionSampling.sampleCount).toBe(200);
    expect(view.exceptionSampling.sampleLimit).toBe(200);
    expect(view.exceptionSampling.threshold).toBe(1000);
    expect(view.exceptionSampling.strategy).toBe('stratified_by_anomaly_type_owner');
    expect(view.exceptionSampling.fallbackUsed).toBe(false);
  });

  it('falls back to disabled exception sampling when metadata is absent', () => {
    const view = buildRuntimeSummaryView({ raw: { artifacts_json: {} } });

    expect(view.exceptionSampling).toEqual({
      enabled: false,
      totalCount: null,
      sampleCount: null,
      sampleLimit: null,
      threshold: null,
      strategy: '',
      fallbackUsed: false,
    });
  });
});
```

- [ ] **Step 2: Run frontend view-model tests to verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/run-runtime-summary.test.ts
```

Expected: FAIL because `exceptionSampling` does not exist on the view model.

- [ ] **Step 3: Add sampling type and normalizer**

In `finance-web/src/components/recon/runRuntimeSummary.ts`, add this interface after `RuntimeNotificationView`:

```typescript
export interface RuntimeExceptionSamplingView {
  enabled: boolean;
  totalCount: number | null;
  sampleCount: number | null;
  sampleLimit: number | null;
  threshold: number | null;
  strategy: string;
  fallbackUsed: boolean;
}
```

Add this field to `RuntimeSummaryViewModel`:

```typescript
  exceptionSampling: RuntimeExceptionSamplingView;
```

Add this function after `normalizeNotification`:

```typescript
function normalizeExceptionSampling(value: unknown): RuntimeExceptionSamplingView {
  const item = asRecord(value);
  return {
    enabled: item.enabled === true,
    totalCount: toOptionalInt(item.total_count ?? item.totalCount),
    sampleCount: toOptionalInt(item.sample_count ?? item.sampleCount),
    sampleLimit: toOptionalInt(item.sample_limit ?? item.sampleLimit),
    threshold: toOptionalInt(item.threshold),
    strategy: toText(item.strategy).trim(),
    fallbackUsed: item.fallback_used === true || item.fallbackUsed === true,
  };
}
```

In `buildRuntimeSummaryView`, add this return property:

```typescript
    exceptionSampling: normalizeExceptionSampling(runtimeSummary.exception_sampling ?? runtimeSummary.exceptionSampling),
```

- [ ] **Step 4: Run frontend view-model tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/run-runtime-summary.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit frontend view-model work**

Run:

```bash
git add finance-web/src/components/recon/runRuntimeSummary.ts finance-web/tests/components/run-runtime-summary.test.ts
git commit -m "feat(recon-web): expose exception sampling summary"
```

Expected: commit succeeds.

---

### Task 4: Frontend Sampled Difference Labels

**Files:**
- Modify: `finance-web/src/components/ReconWorkspace.tsx`
- Modify: `finance-web/src/components/PublicReconRunExceptionsPage.tsx`
- Modify: `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`
- Modify: `finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx`

- [ ] **Step 1: Add public page failing test assertion**

In `finance-web/tests/components/public-recon-run-exceptions-page.test.tsx`, in the first test's mocked `runtime_summary`, add:

```typescript
            exception_sampling: {
              enabled: true,
              total_count: 35665,
              sample_count: 200,
              sample_limit: 200,
              threshold: 1000,
              strategy: 'stratified_by_anomaly_type_owner',
            },
```

Place it next to `summary_notification`.

In the same test, replace:

```typescript
    expect(screen.getByText((_, element) => element?.textContent === '待处理差异 60 条')).toBeInTheDocument();
```

with:

```typescript
    expect(screen.getByText((_, element) => element?.textContent === '全量差异 35,665 条，当前抽样展示 200 条')).toBeInTheDocument();
```

- [ ] **Step 2: Add internal workspace failing test assertion**

In `finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx`, in the `/api/recon/runs` mocked run, add:

```typescript
              artifacts_json: {
                runtime_summary: {
                  exception_sampling: {
                    enabled: true,
                    total_count: 35665,
                    sample_count: 200,
                    sample_limit: 200,
                    threshold: 1000,
                    strategy: 'stratified_by_anomaly_type_owner',
                  },
                },
              },
```

Then after the dialog loads, add:

```typescript
    expect(within(dialog).getByText((_, element) => element?.textContent === '全量差异 35,665 条，当前抽样展示 200 条')).toBeInTheDocument();
```

- [ ] **Step 3: Run frontend component tests to verify they fail**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/public-recon-run-exceptions-page.test.tsx tests/components/recon-workspace-run-exceptions-panel.test.tsx
```

Expected: FAIL because pages still render `待处理差异 ... 条`.

- [ ] **Step 4: Update public page label**

In `finance-web/src/components/PublicReconRunExceptionsPage.tsx`, find the difference list header span:

```tsx
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
              待处理差异 {formatCount(pendingDifferenceTotal)} 条
            </span>
```

Replace it with:

```tsx
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
              {runtimeSummary.exceptionSampling.enabled
                ? `全量差异 ${formatCount(runtimeSummary.exceptionSampling.totalCount ?? pendingDifferenceTotal)} 条，当前抽样展示 ${formatCount(runtimeSummary.exceptionSampling.sampleCount ?? filteredExceptions.length)} 条`
                : `待处理差异 ${formatCount(pendingDifferenceTotal)} 条`}
            </span>
```

- [ ] **Step 5: Update internal workspace label**

In `finance-web/src/components/ReconWorkspace.tsx`, find the internal exception board header span:

```tsx
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
              待处理差异 {formatCount(run.anomalyCount)} 条
            </span>
```

Replace it with:

```tsx
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-sm font-medium text-amber-700">
              {runtimeSummary.exceptionSampling.enabled
                ? `全量差异 ${formatCount(runtimeSummary.exceptionSampling.totalCount ?? run.anomalyCount)} 条，当前抽样展示 ${formatCount(runtimeSummary.exceptionSampling.sampleCount ?? modalExceptions.length)} 条`
                : `待处理差异 ${formatCount(run.anomalyCount)} 条`}
            </span>
```

- [ ] **Step 6: Run frontend component tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/run-runtime-summary.test.ts tests/components/public-recon-run-exceptions-page.test.tsx tests/components/recon-workspace-run-exceptions-panel.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit frontend sampled labels**

Run:

```bash
git add finance-web/src/components/PublicReconRunExceptionsPage.tsx finance-web/src/components/ReconWorkspace.tsx finance-web/tests/components/public-recon-run-exceptions-page.test.tsx finance-web/tests/components/recon-workspace-run-exceptions-panel.test.tsx
git commit -m "feat(recon-web): label sampled exception lists"
```

Expected: commit succeeds.

---

### Task 5: Final Verification

**Files:**
- Verify only; no planned edits.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_resolve_notify_policy_prefers_notify_policy_sample_limit finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_resolve_notify_policy_keeps_legacy_reminder_policy finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_sample_anomalies_for_exception_creation_stratifies_by_type_and_owner finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_create_exception_tasks_node_samples_exploding_anomalies finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_create_exception_tasks_node_persists_exception_sampling_runtime_summary finance-agents/data-agent/tests/recon/test_auto_schedule_collection.py::test_maybe_auto_notify_node_groups_exceptions_by_owner -v
```

Expected: PASS.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test:components -- tests/components/run-runtime-summary.test.ts tests/components/public-recon-run-exceptions-page.test.tsx tests/components/recon-workspace-run-exceptions-panel.test.tsx
```

Expected: PASS.

- [ ] **Step 3: Run type check/build for frontend**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run build
```

Expected: PASS.

- [ ] **Step 4: Restart services**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, and finance-mcp restart successfully.

- [ ] **Step 5: Verify service health**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
curl http://localhost:8100/health
curl http://localhost:3335/health
```

Expected: both services return healthy responses.

- [ ] **Step 6: Confirm no unexpected verification edits**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
git status --short
```

Expected: only unrelated pre-existing changes, or no output. No commit is needed for this verification-only task.

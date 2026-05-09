# Auto Recon Platform Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make automatic reconciliation and rerun collection route through dataset-specific collection drivers for database, Taobao/Tmall, and Alipay platform authorization sources.

**Architecture:** Keep the run graph channel-agnostic: it triggers dataset collection, waits for a sync job, and builds `dataset_ref`. Put source-specific decisions in the data source collection layer using `source_kind`, `provider_code`, dataset storage, and `collection_driver`. Preserve existing Taobao/Tmall `platform_order_lines` behavior while allowing Alipay's separately-developed downloader/parser to plug in without duplicating it.

**Tech Stack:** Python FastAPI/MCP tools, PostgreSQL-backed auth/data source tables, pandas dataset loaders, React/TypeScript run plan binding helpers, pytest.

---

## File Structure

- Modify `finance-mcp/tools/data_sources.py`
  - Add collection driver resolution helpers.
  - Route dataset collection through a small driver switch.
  - Add an Alipay driver adapter that delegates to an injectable function and does not implement file download/parsing itself.
  - Return driver information in collection job results and collection attempts.
- Modify `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
  - Preserve dataset `collection_driver` / `dataset_source_type` metadata while hydrating plan bindings.
  - Include driver/source context in collection attempt output and validation errors.
- Modify `finance-web/src/components/recon/runPlanBindings.ts`
  - Resolve `dataset_source_type` from explicit dataset metadata so Alipay can use its registered structured-table loader instead of being forced to `collection_records`.
- Add/modify tests:
  - `finance-mcp/tests/test_platform_collection_driver_routing.py`
  - `finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py`
  - `finance-web/tests/components/run-plan-bindings.test.ts`

Do not implement Alipay raw file download or parser logic. That work belongs to the parallel Alipay implementation. This plan only delegates to a registered/importable Alipay collection function when present.

---

### Task 1: Add Collection Driver Resolution

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_platform_collection_driver_routing.py`

- [ ] **Step 1: Write failing tests for driver resolution**

Create `finance-mcp/tests/test_platform_collection_driver_routing.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def test_resolve_collection_driver_prefers_explicit_collection_config() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "alipay"}
    dataset = {
        "extract_config": {"collection_driver": "wrong_driver"},
        "meta": {
            "catalog_profile": {
                "collection_config": {
                    "collection_driver": "alipay_bill_download_import",
                },
            }
        },
    }

    assert data_sources._resolve_collection_driver(source, dataset) == "alipay_bill_download_import"


def test_resolve_collection_driver_keeps_taobao_platform_order_lines_compatibility() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "taobao"}
    dataset = {
        "extract_config": {
            "storage": "platform_order_lines",
            "platform_code": "taobao",
        },
    }

    assert data_sources._resolve_collection_driver(source, dataset) == "taobao_order_api"


def test_resolve_collection_driver_defaults_database_to_db_query() -> None:
    source = {"source_kind": "database", "provider_code": "postgres"}
    dataset = {"extract_config": {"storage": "dataset_collection_records"}}

    assert data_sources._resolve_collection_driver(source, dataset) == "db_query"


def test_resolve_collection_driver_defaults_alipay_platform_oauth() -> None:
    source = {"source_kind": "platform_oauth", "provider_code": "alipay"}
    dataset = {"extract_config": {"storage": "alipay_bill_lines"}}

    assert data_sources._resolve_collection_driver(source, dataset) == "alipay_bill_download_import"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_collection_driver_routing.py -q
```

Expected: FAIL with `AttributeError: module 'tools.data_sources' has no attribute '_resolve_collection_driver'`.

- [ ] **Step 3: Implement driver resolution helpers**

In `finance-mcp/tools/data_sources.py`, add near `_dataset_uses_platform_order_lines`:

```python
COLLECTION_DRIVER_DB_QUERY = "db_query"
COLLECTION_DRIVER_TAOBAO_ORDER_API = "taobao_order_api"
COLLECTION_DRIVER_ALIPAY_BILL_DOWNLOAD_IMPORT = "alipay_bill_download_import"


def _collection_config_value(dataset_row: dict[str, Any] | None, *keys: str) -> str:
    dataset = dataset_row if isinstance(dataset_row, dict) else {}
    containers: list[dict[str, Any]] = []
    collection_config = _dataset_collection_config(dataset)
    if collection_config:
        containers.append(collection_config)
    for container_key in ("extract_config", "schema_summary", "meta", "sync_strategy"):
        value = dataset.get(container_key)
        if isinstance(value, dict):
            containers.append(value)

    for container in containers:
        for key in keys:
            text = _safe_text(container.get(key))
            if text:
                return text
    return ""


def _resolve_collection_driver(source_row: dict[str, Any] | None, dataset_row: dict[str, Any] | None) -> str:
    source = source_row if isinstance(source_row, dict) else {}
    dataset = dataset_row if isinstance(dataset_row, dict) else {}
    explicit = _collection_config_value(
        dataset,
        "collection_driver",
        "driver",
        "collector",
        "collection_type",
    ).lower()
    if explicit:
        return explicit

    storage = _dataset_storage_value(dataset)
    if storage == "platform_order_lines":
        return COLLECTION_DRIVER_TAOBAO_ORDER_API

    source_kind = _safe_text(source.get("source_kind") or dataset.get("source_kind")).lower()
    provider_code = _safe_text(source.get("provider_code") or dataset.get("provider_code")).lower()
    if source_kind == "database":
        return COLLECTION_DRIVER_DB_QUERY
    if source_kind == "platform_oauth" and provider_code in {"taobao", "tmall"}:
        return COLLECTION_DRIVER_TAOBAO_ORDER_API
    if source_kind == "platform_oauth" and provider_code == "alipay":
        return COLLECTION_DRIVER_ALIPAY_BILL_DOWNLOAD_IMPORT
    return ""
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_collection_driver_routing.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_platform_collection_driver_routing.py
git commit -m "feat: resolve dataset collection drivers"
```

---

### Task 2: Route Dataset Collection Through Drivers

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_platform_collection_driver_routing.py`

- [ ] **Step 1: Add failing tests for driver routing**

Append to `finance-mcp/tests/test_platform_collection_driver_routing.py`:

```python
import pytest


@pytest.mark.anyio
async def test_execute_sync_job_routes_alipay_to_registered_driver(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda **kwargs: {
            "id": "dataset-alipay-1",
            "dataset_code": "alipay_bill_lines",
            "resource_key": "alipay_bill_lines:merchant-1",
            "extract_config": {
                "storage": "alipay_bill_lines",
                "collection_driver": "alipay_bill_download_import",
                "key_fields": ["trade_no"],
                "date_field": "bill_date",
            },
            "sync_strategy": {},
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt_update", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: {"id": kwargs["sync_job_id"], "job_status": kwargs["job_status"]},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "create_unified_data_source_event",
        lambda **kwargs: calls.setdefault("event", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_health",
        lambda **kwargs: calls.setdefault("source_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources,
        "_update_dataset_health_by_resource",
        lambda **kwargs: calls.setdefault("dataset_health", kwargs),
    )

    def fake_driver(**kwargs):
        calls["driver"] = kwargs
        return {
            "success": True,
            "healthy": True,
            "rows": [],
            "collection_summary": {"upserted_count": 1, "storage": "alipay_bill_lines"},
            "message": "支付宝账单采集成功",
        }

    monkeypatch.setattr(data_sources, "_run_alipay_bill_download_import", fake_driver)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill_lines:merchant-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "resource_key": "alipay_bill_lines:merchant-1",
            "params": {"biz_date": "2026-05-06"},
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert result["collection_driver"] == "alipay_bill_download_import"
    driver_call = calls["driver"]
    assert driver_call["company_id"] == "company-1"
    assert driver_call["source_id"] == "source-alipay-1"
    assert driver_call["dataset_id"] == "dataset-alipay-1"
    assert driver_call["resource_key"] == "alipay_bill_lines:merchant-1"
    assert calls["event"]["event_payload"]["collection_driver"] == "alipay_bill_download_import"


@pytest.mark.anyio
async def test_execute_sync_job_reports_unavailable_alipay_driver(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        data_sources,
        "_resolve_dataset_row",
        lambda **kwargs: {
            "id": "dataset-alipay-1",
            "dataset_code": "alipay_bill_lines",
            "resource_key": "alipay_bill_lines:merchant-1",
            "extract_config": {
                "collection_driver": "alipay_bill_download_import",
                "key_fields": ["trade_no"],
            },
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt_update", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_status",
        lambda **kwargs: calls.setdefault("job_update", kwargs),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_data_source_health",
        lambda **kwargs: calls.setdefault("source_health", kwargs),
    )
    monkeypatch.setattr(
        data_sources,
        "_update_dataset_health_by_resource",
        lambda **kwargs: calls.setdefault("dataset_health", kwargs),
    )

    def missing_driver(**kwargs):
        raise NotImplementedError("支付宝采集器尚未注册")

    monkeypatch.setattr(data_sources, "_run_alipay_bill_download_import", missing_driver)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill_lines:merchant-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "resource_key": "alipay_bill_lines:merchant-1",
            "params": {"biz_date": "2026-05-06"},
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is False
    assert "支付宝采集器尚未注册" in result["error"]
    assert calls["job_update"]["job_status"] == "failed"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_collection_driver_routing.py -q
```

Expected: FAIL because `_run_alipay_bill_download_import` and driver routing are not implemented.

- [ ] **Step 3: Add driver adapter and sync execution routing**

In `finance-mcp/tools/data_sources.py`, add this adapter near `_run_platform_order_collection`:

```python
def _run_alipay_bill_download_import(
    *,
    company_id: str,
    source_id: str,
    dataset_id: str,
    dataset_code: str,
    resource_key: str,
    collection_config: dict[str, Any],
    params: dict[str, Any],
    checkpoint_before: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Delegate to the Alipay collector implemented by the platform auth workstream."""
    try:
        from platforms.connectors.alipay import run_alipay_bill_download_import
    except Exception as exc:  # noqa: BLE001
        raise NotImplementedError("支付宝采集器尚未注册") from exc

    return run_alipay_bill_download_import(
        company_id=company_id,
        source_id=source_id,
        dataset_id=dataset_id,
        dataset_code=dataset_code,
        resource_key=resource_key,
        collection_config=collection_config,
        params=params,
        checkpoint_before=dict(checkpoint_before or {}),
    )
```

Then in `_execute_sync_job`, replace the current `uses_platform_order_lines` branch with driver-based routing:

```python
dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
collection_driver = _resolve_collection_driver(runtime_source, dataset_row)
uses_platform_order_lines = collection_driver == COLLECTION_DRIVER_TAOBAO_ORDER_API
if collection_driver == COLLECTION_DRIVER_TAOBAO_ORDER_API:
    params.setdefault("collection_config", _dataset_collection_config(dataset_row))
    params.setdefault("dataset_id", _safe_text((dataset_row or {}).get("id")))
    params.setdefault("dataset_code", _safe_text((dataset_row or {}).get("dataset_code")))
    if not isinstance(params.get("platform_order_collection"), dict):
        params["platform_order_collection"] = _resolve_taobao_collection_window(
            dataset_row=dataset_row or {},
            params=params,
            checkpoint_before=checkpoint_before,
        )
    result = _run_platform_order_collection(
        company_id=company_id,
        source_id=source_id,
        dataset_id=_safe_text(params.get("dataset_id")),
        dataset_code=_safe_text(params.get("dataset_code")),
        resource_key=resource_key,
        collection_config=dict(params.get("collection_config") or {}),
        params=params,
        checkpoint_before=checkpoint_before,
    )
elif collection_driver == COLLECTION_DRIVER_ALIPAY_BILL_DOWNLOAD_IMPORT:
    params.setdefault("collection_config", _dataset_collection_config(dataset_row))
    params.setdefault("dataset_id", _safe_text((dataset_row or {}).get("id")))
    params.setdefault("dataset_code", _safe_text((dataset_row or {}).get("dataset_code")))
    result = _run_alipay_bill_download_import(
        company_id=company_id,
        source_id=source_id,
        dataset_id=_safe_text(params.get("dataset_id")),
        dataset_code=_safe_text(params.get("dataset_code")),
        resource_key=resource_key,
        collection_config=dict(params.get("collection_config") or {}),
        params=params,
        checkpoint_before=checkpoint_before,
    )
else:
    result = await _run_connector_sync(runtime_source, arguments)
```

Add a flag immediately after `collection_driver`:

```python
uses_driver_managed_storage = collection_driver in {
    COLLECTION_DRIVER_TAOBAO_ORDER_API,
    COLLECTION_DRIVER_ALIPAY_BILL_DOWNLOAD_IMPORT,
}
```

Use `uses_driver_managed_storage` instead of `uses_platform_order_lines` when deciding whether generic `dataset_collection_records` upsert should run:

```python
if uses_driver_managed_storage:
    collection_summary = dict(result.get("collection_summary") or {})
elif collection_context:
    collection_records, collection_validation = _build_collection_records(
        rows=rows,
        key_fields=list(collection_context.get("key_fields") or []),
    )
```

and:

```python
if collection_context and not uses_driver_managed_storage:
    collection_summary = auth_db.upsert_dataset_collection_records(...)
```

Also add `collection_driver` to success/failure return payloads and event payloads in `_execute_sync_job`:

```python
"collection_driver": collection_driver,
```

In `_trigger_dataset_collection_resolved`, after resolving `config`, compute:

```python
source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id) or {}
collection_driver = _resolve_collection_driver(source_row, dataset_row)
params["collection_driver"] = collection_driver
```

Return it from `_trigger_dataset_collection_resolved`:

```python
"collection_driver": collection_driver,
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_collection_driver_routing.py -q
```

Expected: PASS.

- [ ] **Step 5: Run existing collection regression tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py finance-mcp/tests/test_scheduler_collection_plans.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_platform_collection_driver_routing.py
git commit -m "feat: route dataset collection by driver"
```

---

### Task 3: Preserve Dataset Source Type and Driver in Auto Scheme Runs

**Files:**
- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`
- Test: `finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py`

- [ ] **Step 1: Write failing tests for binding hydration and recon input construction**

Create `finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_AGENT_ROOT = Path(__file__).resolve().parents[2]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

from graphs.recon.auto_scheme_run import nodes


@pytest.mark.anyio
async def test_hydrate_binding_preserves_dataset_source_type_from_dataset(monkeypatch) -> None:
    async def fake_get_dataset(*args, **kwargs):
        return {
            "success": True,
            "dataset": {
                "id": "dataset-alipay-1",
                "dataset_code": "alipay_bill_lines",
                "business_name": "支付宝账单明细",
                "source_kind": "platform_oauth",
                "provider_code": "alipay",
                "extract_config": {
                    "collection_driver": "alipay_bill_download_import",
                    "dataset_source_type": "alipay_bill_lines",
                    "storage": "alipay_bill_lines",
                },
                "collection_config": {
                    "collection_driver": "alipay_bill_download_import",
                    "dataset_source_type": "alipay_bill_lines",
                },
            },
        }

    monkeypatch.setattr(nodes, "data_source_get_dataset", fake_get_dataset)

    hydrated = await nodes._hydrate_binding_source_meta(
        auth_token="token",
        binding={
            "data_source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "resource_key": "alipay_bill_lines:merchant-1",
            "table_name": "alipay_bill_lines",
            "dataset_source_type": "collection_records",
        },
    )

    assert hydrated["dataset_source_type"] == "alipay_bill_lines"
    assert hydrated["collection_driver"] == "alipay_bill_download_import"
    assert hydrated["source_kind"] == "platform_oauth"
    assert hydrated["provider_code"] == "alipay"


def test_build_recon_inputs_uses_hydrated_dataset_source_type() -> None:
    inputs = nodes._build_recon_inputs_from_ready_collections(
        [
            {
                "binding": {
                    "data_source_id": "source-alipay-1",
                    "dataset_id": "dataset-alipay-1",
                    "resource_key": "alipay_bill_lines:merchant-1",
                    "table_name": "alipay_bill_lines",
                    "dataset_source_type": "alipay_bill_lines",
                    "query": {"date_field": "bill_date"},
                },
                "collection_records": {
                    "dataset_id": "dataset-alipay-1",
                    "resource_key": "alipay_bill_lines:merchant-1",
                    "record_count": 1,
                },
            }
        ],
        biz_date="2026-05-06",
    )

    dataset_ref = inputs[0]["payload"]["dataset_ref"]
    assert dataset_ref["source_type"] == "alipay_bill_lines"
    assert dataset_ref["source_key"] == "source-alipay-1"
    assert dataset_ref["query"]["biz_date"] == "2026-05-06"
    assert dataset_ref["query"]["date_field"] == "bill_date"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py -q
```

Expected: FAIL because hydration does not derive `dataset_source_type` or `collection_driver` from dataset metadata.

- [ ] **Step 3: Add metadata extraction helpers**

In `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`, add near `_safe_dict` helpers:

```python
def _first_text_from_dicts(dicts: list[dict[str, Any]], *keys: str) -> str:
    for item in dicts:
        for key in keys:
            value = str(item.get(key) or "").strip()
            if value:
                return value
    return ""


def _dataset_meta_containers(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    for key in ("collection_config", "extract_config", "schema_summary", "metadata", "meta"):
        value = dataset.get(key)
        if isinstance(value, dict):
            containers.append(dict(value))
    catalog = _safe_dict(_safe_dict(dataset.get("metadata")).get("catalog_profile"))
    collection_config = _safe_dict(catalog.get("collection_config"))
    if collection_config:
        containers.insert(0, collection_config)
    return containers


def _dataset_source_type_from_meta(dataset: dict[str, Any], fallback: str) -> str:
    containers = _dataset_meta_containers(dataset)
    explicit = _first_text_from_dicts(containers, "dataset_source_type", "source_type", "loader")
    if explicit:
        return explicit
    storage = _first_text_from_dicts(containers, "storage", "physical_storage", "source").lower()
    if storage == "platform_order_lines":
        return "platform_order_lines"
    if storage and storage not in {"dataset_collection_records", "collection_records"}:
        return storage
    return fallback or "collection_records"


def _collection_driver_from_meta(dataset: dict[str, Any]) -> str:
    return _first_text_from_dicts(
        _dataset_meta_containers(dataset),
        "collection_driver",
        "driver",
        "collector",
        "collection_type",
    )
```

- [ ] **Step 4: Update binding hydration**

Inside `_hydrate_binding_source_meta`, in the `if bool(dataset_result.get("success")) and dataset:` block, add:

```python
fallback_source_type = str(hydrated.get("dataset_source_type") or "collection_records").strip() or "collection_records"
hydrated["dataset_source_type"] = _dataset_source_type_from_meta(dataset, fallback_source_type)
collection_driver = _collection_driver_from_meta(dataset)
if collection_driver:
    hydrated["collection_driver"] = collection_driver
```

Keep the existing `dataset_extract_config`, `dataset_collection_config`, and source/provider assignments.

- [ ] **Step 5: Include driver context in collection attempts**

In `check_dataset_ready_node`, when appending `collection_attempts`, change the attempt payload to include:

```python
"collection_driver": str(collect_result.get("collection_driver") or binding.get("collection_driver") or ""),
"dataset_source_type": str(binding.get("dataset_source_type") or ""),
```

When a collection fails, include the same details in the missing binding:

```python
missing_bindings.append(
    {
        **binding,
        "collection_driver": str(collect_result.get("collection_driver") or binding.get("collection_driver") or ""),
        "error": f"先同步失败：{collection_error}",
    }
)
```

- [ ] **Step 6: Run tests**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py -q
```

Expected: PASS.

- [ ] **Step 7: Run existing auto scheme tests if present**

Run:

```bash
source .venv/bin/activate
pytest finance-agents/data-agent/tests/recon -q
```

Expected: PASS. If unrelated tests fail because the current workspace has parallel Alipay/Taobao edits, capture the failing test names and error messages before continuing.

- [ ] **Step 8: Commit**

```bash
git add finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py
git commit -m "feat: preserve collection metadata in auto recon runs"
```

---

### Task 4: Preserve Dataset Source Type in Run Plan Bindings

**Files:**
- Modify: `finance-web/src/components/recon/runPlanBindings.ts`
- Test: `finance-web/tests/components/run-plan-bindings.test.ts`

- [ ] **Step 1: Add failing frontend unit tests**

Create or extend `finance-web/tests/components/run-plan-bindings.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';
import { resolveDatasetSourceType } from '../../src/components/recon/runPlanBindings';

describe('resolveDatasetSourceType', () => {
  it('keeps platform_order_lines compatibility', () => {
    expect(resolveDatasetSourceType({
      extractConfig: { storage: 'platform_order_lines' },
      schemaSummary: {},
    })).toBe('platform_order_lines');
  });

  it('uses explicit dataset_source_type for alipay parsed tables', () => {
    expect(resolveDatasetSourceType({
      extractConfig: {
        collection_driver: 'alipay_bill_download_import',
        dataset_source_type: 'alipay_bill_lines',
        storage: 'alipay_bill_lines',
      },
      schemaSummary: {},
    })).toBe('alipay_bill_lines');
  });

  it('defaults database-like datasets to collection_records', () => {
    expect(resolveDatasetSourceType({
      extractConfig: { storage: 'dataset_collection_records' },
      schemaSummary: {},
    })).toBe('collection_records');
  });
});
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
cd finance-web
npm test -- run-plan-bindings.test.ts
```

Expected: FAIL because the return type currently only allows `platform_order_lines | collection_records`.

- [ ] **Step 3: Update `resolveDatasetSourceType`**

In `finance-web/src/components/recon/runPlanBindings.ts`, change the return type:

```typescript
export function resolveDatasetSourceType(source: {
  extractConfig?: Record<string, unknown>;
  schemaSummary?: Record<string, unknown>;
}): string {
```

Then replace the function body with:

```typescript
  const extractConfig = asRecord(source.extractConfig);
  const schemaSummary = asRecord(source.schemaSummary);
  const explicit = firstText(
    extractConfig.dataset_source_type,
    extractConfig.source_type,
    extractConfig.loader,
    schemaSummary.dataset_source_type,
    schemaSummary.source_type,
    schemaSummary.loader,
  ).toLowerCase();
  if (explicit) return explicit;

  const storage = firstText(
    extractConfig.storage,
    extractConfig.physical_storage,
    schemaSummary.storage,
    schemaSummary.physical_storage,
    schemaSummary.source,
  ).toLowerCase();
  if (storage === 'platform_order_lines') return 'platform_order_lines';
  if (storage && storage !== 'dataset_collection_records' && storage !== 'collection_records') {
    return storage;
  }
  return 'collection_records';
```

- [ ] **Step 4: Ensure binding metadata carries the source type**

In `buildRunPlanBinding`, keep:

```typescript
dataset_source_type: datasetSourceType,
mapping_config: {
  dataset_source_type: datasetSourceType,
},
```

No additional frontend fields are required for Alipay; it remains `sourceKind='platform_oauth'` and `providerCode='alipay'`.

- [ ] **Step 5: Run tests**

Run:

```bash
cd finance-web
npm test -- run-plan-bindings.test.ts
```

Expected: PASS.

- [ ] **Step 6: Run TypeScript check**

Run:

```bash
cd finance-web
npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-web/src/components/recon/runPlanBindings.ts finance-web/tests/components/run-plan-bindings.test.ts
git commit -m "feat: preserve dataset source type in run plans"
```

---

### Task 5: Register or Document Alipay Dataset Loader Contract

**Files:**
- Modify if needed: `finance-mcp/recon/mcp_server/dataset_loader.py`
- Test: `finance-mcp/tests/test_platform_order_dataset_loader.py` or a new `finance-mcp/tests/test_alipay_dataset_loader_contract.py`

- [ ] **Step 1: Check the parallel Alipay implementation**

Run:

```bash
rg -n "alipay_bill|register_dataset_loader|dataset_source_type|source_type" finance-mcp -S
```

Expected: identify whether the other workstream already registers a loader such as `alipay_bill_lines`.

- [ ] **Step 2A: If Alipay loader already exists, add a contract test only**

Create `finance-mcp/tests/test_alipay_dataset_loader_contract.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_alipay_bill_lines_loader_is_registered() -> None:
    assert "alipay_bill_lines" in dataset_loader._DATASET_LOADERS
```

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_alipay_dataset_loader_contract.py -q
```

Expected: PASS.

- [ ] **Step 2B: If Alipay loader does not exist yet, add a skipped contract test**

Create `finance-mcp/tests/test_alipay_dataset_loader_contract.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_alipay_bill_lines_loader_contract() -> None:
    if "alipay_bill_lines" not in dataset_loader._DATASET_LOADERS:
        pytest.skip("Alipay parsed-table loader is owned by the parallel Alipay implementation")
    assert "alipay_bill_lines" in dataset_loader._DATASET_LOADERS
```

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_alipay_dataset_loader_contract.py -q
```

Expected: SKIPPED until the Alipay implementation lands, then PASS.

- [ ] **Step 3: Commit**

```bash
git add finance-mcp/tests/test_alipay_dataset_loader_contract.py
git commit -m "test: document alipay dataset loader contract"
```

---

### Task 6: Integration Verification and Service Restart

**Files:**
- No code changes unless verification exposes a defect.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
source .venv/bin/activate
pytest \
  finance-mcp/tests/test_platform_collection_driver_routing.py \
  finance-mcp/tests/test_platform_order_collection.py \
  finance-mcp/tests/test_platform_order_dataset_loader.py \
  finance-mcp/tests/test_scheduler_collection_plans.py \
  finance-agents/data-agent/tests/recon/test_auto_scheme_collection_routing.py \
  -q
```

Expected: PASS, except the Alipay loader contract may SKIP if the parallel implementation has not landed.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd finance-web
npm test -- run-plan-bindings.test.ts
npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 3: Restart services after code changes**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, and finance-mcp restart successfully.

- [ ] **Step 4: Health check**

Run:

```bash
curl -s http://localhost:8100/health
curl -s http://localhost:3335/health
```

Expected: both return healthy service responses.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git log --oneline -6
```

Expected: only pre-existing unrelated workspace changes remain unstaged; this plan's commits are visible in the recent log.

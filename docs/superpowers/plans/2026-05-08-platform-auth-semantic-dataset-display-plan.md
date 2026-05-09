# 平台授权语义数据集展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 淘宝/天猫、支付宝授权成功并完成初始化采集后，店铺详情能展示真实语义字段结构和 20 条真实数据，并且运行中状态不会暴露重复初始化或刷新语义动作。

**Architecture:** 后端继续把语义写入 `data_source_datasets.meta.semantic_profile`，新增平台样本加载、字段来源标记和店铺数据集聚合响应，不改 raw 明细表。data-agent 只做 FastAPI 路由与 MCP client 转发，前端在平台店铺详情行内打开数据集详情区，复用现有语义发布侧栏和采集详情能力。

**Tech Stack:** Python FastAPI, PostgreSQL auth_db helpers, pytest, React + TypeScript, Vite, existing MCP tool routing.

---

## File Map

- Modify `finance-mcp/tools/data_sources.py`: add platform sample loader, platform semantic presets, semantic field grouping metadata, and optional dataset collection status fields in collection detail response.
- Modify `finance-mcp/tests/test_platform_order_collection.py`: add backend tests for Taobao semantic sampling, Alipay raw-field expansion, collection detail status, and running-job action state.
- Modify `finance-agents/data-agent/tools/mcp_client.py`: expose `semantic_status`, `collection_status`, `field_groups`, `sample_limit`, and 20-row responses from MCP collection detail.
- Modify `finance-agents/data-agent/graphs/data_source/api.py`: extend `DataSourceDatasetCollectionDetailResponse`, default `sample_limit` to 20 for shop detail use, and keep existing endpoint path stable.
- Modify `finance-web/src/components/DataConnectionsPanel.tsx`: add shop dataset detail state, resolve each fixed platform dataset from existing source datasets by `resource_key`, render field groups and 20-row preview, hide duplicate actions while jobs run, and route manage-publish to the existing semantic side panel.
- No database migration is required because semantic metadata remains in `data_source_datasets.meta.semantic_profile` and sample rows already live in `platform_order_lines` / `platform_alipay_bill_lines`.

## Data Contract

`GET /api/data-sources/{source_id}/datasets/{dataset_id}/collection-detail?sample_limit=20` should return this compatible extension:

```json
{
  "success": true,
  "dataset": {
    "id": "dataset-alipay-trade-1",
    "resource_key": "alipay_bill:trade:shop-1",
    "semantic_status": "generated_with_samples",
    "semantic_fields": []
  },
  "collection_status": {
    "status": "succeeded",
    "message": "已采集真实样本",
    "can_initialize": false,
    "can_retry_initialize": false,
    "latest_job": {}
  },
  "semantic_status": {
    "status": "succeeded",
    "message": "已生成语义结构",
    "can_refresh": true,
    "can_retry": false
  },
  "field_groups": [
    { "key": "normalized", "label": "标准字段", "default_open": true, "fields": [] },
    { "key": "raw_bill", "label": "原始账单字段", "default_open": true, "fields": [] },
    { "key": "system", "label": "系统字段", "default_open": false, "fields": [] }
  ],
  "rows": [],
  "sample_limit": 20
}
```

The existing keys `collection_stats`, `jobs`, `rows`, `count`, and `row_count` must remain unchanged for existing consumers.

### Task 1: Backend Platform Semantic Sampling And Presets

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_platform_order_collection.py`

- [ ] **Step 1: Add failing tests for platform semantic refresh**

Append these tests to `finance-mcp/tests/test_platform_order_collection.py` near the existing platform collection detail tests:

```python
@pytest.mark.anyio
async def test_refresh_semantic_profile_reads_platform_order_lines(monkeypatch) -> None:
    calls: dict[str, Any] = {}
    persisted: dict[str, Any] = {}

    dataset = _platform_order_dataset()
    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "淘宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "taobao",
        },
    )

    def fake_list_platform_order_lines(**kwargs: Any) -> list[dict[str, Any]]:
        calls["list_platform_order_lines"] = kwargs
        return [
            {
                "payload": {
                    "tid": "T1001",
                    "oid": "O1001",
                    "biz_date": "2026-05-07",
                    "pay_time": "2026-05-07 10:02:03",
                    "payment": "88.00",
                    "order_payment": "88.00",
                    "title": "测试商品",
                }
            }
        ]

    monkeypatch.setattr(data_sources.auth_db, "list_platform_order_lines", fake_list_platform_order_lines)
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        persisted["payload"] = payload
        next_dataset = dict(dataset)
        next_dataset["meta"] = payload["meta"]
        return next_dataset

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset", fake_update_dataset)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-1", "sample_limit": 20}
    )

    assert result["success"] is True
    assert result["sample_source"] == "platform_order_lines"
    assert calls["list_platform_order_lines"]["dataset_id"] == "dataset-1"
    assert calls["list_platform_order_lines"]["resource_key"] == "taobao_order_lines:shop-1"
    profile = persisted["payload"]["meta"]["semantic_profile"]
    assert profile["generated_from"]["sample_source"] == "platform_order_lines"
    assert profile["field_label_map"]["tid"] == "主订单号"
    assert profile["field_label_map"]["order_payment"] == "子订单实付金额"
    assert profile["key_fields"] == ["tid", "oid"]
```

```python
@pytest.mark.anyio
async def test_refresh_semantic_profile_expands_alipay_raw_bill_fields(monkeypatch) -> None:
    persisted: dict[str, Any] = {}
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: dataset,
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {
            "id": data_source_id,
            "name": "支付宝授权连接",
            "source_kind": "platform_oauth",
            "provider_code": "alipay",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "source_row_key": "row-1",
                    "bill_type": "trade",
                    "bill_date": "2026-05-07",
                    "alipay_trade_no": "202605070001",
                    "merchant_order_no": "M1001",
                    "income_amount": "88.00",
                    "raw": {
                        "支付宝交易号": "202605070001",
                        "商户订单号": "M1001",
                        "收入": "88.00",
                        "入账时间": "2026-05-07 10:03:04",
                    },
                }
            }
        ],
    )
    monkeypatch.setattr(
        data_sources,
        "_load_dataset_sample_rows_from_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic records")),
    )

    def fake_update_dataset(dataset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        persisted["payload"] = payload
        next_dataset = dict(dataset)
        next_dataset["meta"] = payload["meta"]
        return next_dataset

    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_dataset", fake_update_dataset)
    monkeypatch.setattr(data_sources.auth_db, "create_unified_data_source_event", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_get_semantic_llm_config", lambda: None)

    result = await data_sources._handle_data_source_refresh_dataset_semantic_profile(
        {"auth_token": "token", "dataset_id": "dataset-alipay-1", "sample_limit": 20}
    )

    assert result["success"] is True
    assert result["sample_source"] == "platform_alipay_bill_lines"
    profile = persisted["payload"]["meta"]["semantic_profile"]
    assert profile["field_label_map"]["alipay_trade_no"] == "支付宝交易号"
    assert profile["field_label_map"]["raw.支付宝交易号"] == "支付宝交易号"
    assert profile["field_label_map"]["raw.收入"] == "收入"
    raw_field = next(item for item in profile["fields"] if item["raw_name"] == "raw.收入")
    assert raw_field["field_source"] == "raw_bill"
    assert raw_field["source"] == "platform_preset"
    assert profile["key_fields"] == ["source_row_key"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_refresh_semantic_profile_reads_platform_order_lines finance-mcp/tests/test_platform_order_collection.py::test_refresh_semantic_profile_expands_alipay_raw_bill_fields -v
```

Expected: both tests fail because `_handle_data_source_refresh_dataset_semantic_profile` still reads only generic `dataset_collection_records`, does not report `platform_order_lines` / `platform_alipay_bill_lines` as `sample_source`, and does not expand `raw.*` fields.

- [ ] **Step 3: Add platform sample loader and raw flattening**

In `finance-mcp/tools/data_sources.py`, add these helpers before `_refresh_dataset_semantic_profile`:

```python
def _flatten_platform_sample_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    raw = payload.get("raw")
    if isinstance(raw, dict):
        for key, value in raw.items():
            raw_name = f"raw.{_safe_text(key)}"
            if raw_name.strip() and raw_name not in payload:
                payload[raw_name] = value
    return payload


def _load_dataset_semantic_sample_rows(
    *,
    company_id: str,
    data_source_id: str,
    dataset_row: dict[str, Any],
    resource_key: str,
    limit: int,
) -> tuple[list[dict[str, Any]], str]:
    dataset_id = _safe_text(dataset_row.get("id")) or None
    dataset_code = _safe_text(dataset_row.get("dataset_code")) or None

    if _dataset_uses_platform_order_lines(dataset_row):
        records = auth_db.list_platform_order_lines(
            company_id=company_id,
            data_source_id=data_source_id,
            dataset_id=dataset_id,
            resource_key=resource_key,
            limit=limit,
            offset=0,
        )
        rows = [
            _flatten_platform_sample_payload(dict(item.get("payload") or {}))
            for item in records
            if isinstance(item, dict) and isinstance(item.get("payload"), dict)
        ]
        return rows, "platform_order_lines" if rows else "none"

    if _dataset_uses_platform_alipay_bill_lines(dataset_row):
        records = auth_db.list_platform_alipay_bill_lines(
            company_id=company_id,
            data_source_id=data_source_id,
            dataset_id=dataset_id,
            resource_key=resource_key,
            limit=limit,
            offset=0,
        )
        rows = [
            _flatten_platform_sample_payload(dict(item.get("payload") or {}))
            for item in records
            if isinstance(item, dict) and isinstance(item.get("payload"), dict)
        ]
        return rows, "platform_alipay_bill_lines" if rows else "none"

    rows = _load_dataset_sample_rows_from_collection_records(
        company_id=company_id,
        data_source_id=data_source_id,
        dataset_id=_safe_text(dataset_row.get("id")),
        dataset_code=dataset_code or "",
        resource_key=resource_key,
        limit=limit,
    )
    return rows, "collection_records" if rows else "none"
```

- [ ] **Step 4: Add platform semantic presets**

In `finance-mcp/tools/data_sources.py`, add these constants near the semantic helper constants:

```python
PLATFORM_SEMANTIC_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "platform_order_lines": {
        "tid": {"display_name": "主订单号", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.98},
        "oid": {"display_name": "子订单号", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.98},
        "biz_date": {"display_name": "业务日期", "semantic_type": "date", "business_role": "time", "confidence": 0.98},
        "pay_time": {"display_name": "付款时间", "semantic_type": "datetime", "business_role": "time", "confidence": 0.98},
        "modified": {"display_name": "更新时间", "semantic_type": "datetime", "business_role": "time", "confidence": 0.96},
        "trade_status": {"display_name": "主订单状态", "semantic_type": "status", "business_role": "status", "confidence": 0.96},
        "order_status": {"display_name": "子订单状态", "semantic_type": "status", "business_role": "status", "confidence": 0.96},
        "refund_status": {"display_name": "退款状态", "semantic_type": "status", "business_role": "status", "confidence": 0.96},
        "payment": {"display_name": "主订单实付金额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.98},
        "order_payment": {"display_name": "子订单实付金额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.98},
        "total_fee": {"display_name": "主订单商品总额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.96},
        "order_total_fee": {"display_name": "子订单商品总额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.96},
        "alipay_no": {"display_name": "支付宝交易号", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.96},
        "title": {"display_name": "商品标题", "semantic_type": "text", "business_role": "name", "confidence": 0.96},
        "quantity": {"display_name": "购买数量", "semantic_type": "number", "business_role": "quantity", "confidence": 0.96},
    },
    "platform_alipay_bill_lines": {
        "source_row_key": {"display_name": "账单行唯一键", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.98},
        "bill_type": {"display_name": "账单类型", "semantic_type": "category", "business_role": "category", "confidence": 0.96},
        "bill_date": {"display_name": "账单日期", "semantic_type": "date", "business_role": "time", "confidence": 0.98},
        "alipay_trade_no": {"display_name": "支付宝交易号", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.98},
        "merchant_order_no": {"display_name": "商户订单号", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.98},
        "business_order_no": {"display_name": "业务订单号", "semantic_type": "identifier", "business_role": "identifier", "confidence": 0.96},
        "amount": {"display_name": "发生金额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.96},
        "income_amount": {"display_name": "收入金额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.98},
        "expense_amount": {"display_name": "支出金额", "semantic_type": "amount", "business_role": "amount", "confidence": 0.98},
        "trade_time": {"display_name": "交易时间", "semantic_type": "datetime", "business_role": "time", "confidence": 0.96},
    },
}

PLATFORM_SYSTEM_FIELDS = {
    "source_row_key",
    "source_file_name",
    "source_row_number",
    "data_source_id",
    "dataset_id",
    "shop_connection_id",
    "resource_key",
    "created_at",
    "updated_at",
}
```

Then add this helper before `_build_semantic_profile`:

```python
def _platform_semantic_storage_key(dataset_row: dict[str, Any]) -> str:
    if _dataset_uses_platform_order_lines(dataset_row):
        return "platform_order_lines"
    if _dataset_uses_platform_alipay_bill_lines(dataset_row):
        return "platform_alipay_bill_lines"
    return ""


def _apply_platform_semantic_preset(
    *,
    dataset_row: dict[str, Any],
    field_item: dict[str, Any],
) -> dict[str, Any]:
    raw_name = _safe_text(field_item.get("raw_name"))
    storage = _platform_semantic_storage_key(dataset_row)
    preset = dict((PLATFORM_SEMANTIC_PRESETS.get(storage) or {}).get(raw_name) or {})

    if raw_name.startswith("raw."):
        raw_label = raw_name.split(".", 1)[1]
        preset = {
            "display_name": raw_label,
            "semantic_type": "unknown",
            "business_role": "normal",
            "confidence": 0.92,
            **preset,
        }
        field_source = "raw_bill"
    elif raw_name in PLATFORM_SYSTEM_FIELDS:
        field_source = "system"
    else:
        field_source = "normalized"

    if not preset and not storage:
        return field_item

    next_item = {
        **field_item,
        **{key: value for key, value in preset.items() if value not in ("", None)},
        "raw_name": raw_name,
        "field_source": field_source,
        "source": "platform_preset" if preset or storage else field_item.get("source"),
    }
    if not _safe_text(next_item.get("description")):
        next_item["description"] = f"{next_item.get('display_name') or raw_name}字段。"
    return next_item
```

Inside `_build_semantic_profile`, after `field_item` is assembled and before appending it to `field_items`, apply the preset:

```python
        field_item = _apply_platform_semantic_preset(
            dataset_row=dataset_row,
            field_item=field_item,
        )
```

Also set platform key fields after the identifier-based key field loop:

```python
    storage = _platform_semantic_storage_key(dataset_row)
    if storage == "platform_order_lines":
        key_fields = [field for field in ["tid", "oid"] if field in field_label_map]
    elif storage == "platform_alipay_bill_lines" and "source_row_key" in field_label_map:
        key_fields = ["source_row_key"]
```

- [ ] **Step 5: Wire platform sample loading into semantic refresh**

Replace the first sample loading block in `_handle_data_source_refresh_dataset_semantic_profile` with:

```python
    sample_rows, sample_source = _load_dataset_semantic_sample_rows(
        company_id=company_id,
        data_source_id=source_id,
        dataset_row=dataset_row,
        resource_key=resource_key,
        limit=sample_limit,
    )
```

Keep the existing connector preview fallback, but only allow it when `sample_source == "none"` and the dataset is not one of the two platform storages:

```python
    if (
        not sample_rows
        and not _dataset_uses_platform_order_lines(dataset_row)
        and not _dataset_uses_platform_alipay_bill_lines(dataset_row)
        and str(source_row.get("source_kind") or "") not in AGENT_ASSISTED_KINDS
    ):
```

Inside `_build_semantic_profile`, extend `generated_from` with a default marker:

```python
        "sample_source": "semantic_refresh",
```

Add a `sample_source` parameter to `_refresh_dataset_semantic_profile` and persist it before merging existing manual overrides:

```python
def _refresh_dataset_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    source_row: dict[str, Any] | None,
    sample_rows: list[dict[str, Any]] | None = None,
    status: str = "",
    sample_source: str = "",
    allow_llm: bool = False,
) -> dict[str, Any] | None:
    rows = [row for row in (sample_rows or []) if isinstance(row, dict)]
    semantic_profile = _build_semantic_profile(
        dataset_row=dataset_row,
        source_row=source_row,
        sample_rows=rows,
        status=status or ("generated_with_samples" if rows else "generated_basic"),
        allow_llm=allow_llm,
    )
    if sample_source:
        semantic_profile.setdefault("generated_from", {})["sample_source"] = sample_source
    semantic_profile = _merge_existing_semantic_profile(
        generated_profile=semantic_profile,
        existing_profile=_extract_semantic_profile(dataset_row),
    )
    updated = _persist_dataset_semantic_profile(
        dataset_row=dataset_row,
        semantic_profile=semantic_profile,
    )
    return updated or dataset_row
```

Then pass the actual source from `_handle_data_source_refresh_dataset_semantic_profile`:

```python
    refreshed = _refresh_dataset_semantic_profile(
        dataset_row=dataset_row,
        source_row=source_row,
        sample_rows=sample_rows,
        status="generated_with_samples" if sample_rows else "generated_basic",
        sample_source=sample_source,
        allow_llm=True,
    )
```

- [ ] **Step 6: Run backend semantic tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_refresh_semantic_profile_reads_platform_order_lines finance-mcp/tests/test_platform_order_collection.py::test_refresh_semantic_profile_expands_alipay_raw_bill_fields -v
```

Expected: both tests pass.

- [ ] **Step 7: Commit backend semantic sampling**

Run:

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_platform_order_collection.py
git commit -m "feat: add platform semantic sampling"
```

### Task 2: Backend Collection Detail Status And Field Groups

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_platform_order_collection.py`

- [ ] **Step 1: Add failing tests for detail status and groups**

Append these tests to `finance-mcp/tests/test_platform_order_collection.py`:

```python
@pytest.mark.anyio
async def test_collection_detail_returns_platform_field_groups_and_twenty_rows(monkeypatch) -> None:
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")
    dataset["meta"] = {
        "semantic_profile": {
            "status": "generated_with_samples",
            "field_label_map": {
                "alipay_trade_no": "支付宝交易号",
                "raw.收入": "收入",
                "source_row_key": "账单行唯一键",
            },
            "fields": [
                {"raw_name": "alipay_trade_no", "display_name": "支付宝交易号", "field_source": "normalized"},
                {"raw_name": "raw.收入", "display_name": "收入", "field_source": "raw_bill"},
                {"raw_name": "source_row_key", "display_name": "账单行唯一键", "field_source": "system"},
            ],
            "generated_from": {"has_sample_rows": True},
        }
    }

    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: _alipay_platform_source(id=data_source_id),
    )
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_dataset_by_id", lambda company_id, dataset_id: dataset)
    monkeypatch.setattr(data_sources.auth_db, "list_unified_sync_jobs", lambda **kwargs: [])
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(data_sources.auth_db, "get_platform_alipay_bill_line_stats", lambda **kwargs: {"total_count": 21})
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [
            {
                "payload": {
                    "alipay_trade_no": f"T{index:02d}",
                    "source_row_key": f"row-{index}",
                    "raw": {"收入": str(index)},
                }
            }
            for index in range(20)
        ],
    )

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "sample_limit": 20,
        }
    )

    assert result["success"] is True
    assert result["sample_limit"] == 20
    assert result["row_count"] == 20
    assert result["collection_status"]["status"] == "succeeded"
    assert result["collection_status"]["can_initialize"] is False
    assert result["semantic_status"]["status"] == "succeeded"
    assert result["semantic_status"]["can_refresh"] is True
    groups = {group["key"]: group for group in result["field_groups"]}
    assert [field["raw_name"] for field in groups["normalized"]["fields"]] == ["alipay_trade_no"]
    assert [field["raw_name"] for field in groups["raw_bill"]["fields"]] == ["raw.收入"]
    assert [field["raw_name"] for field in groups["system"]["fields"]] == ["source_row_key"]
    assert result["rows"][0]["raw.收入"] == "0"
```

```python
@pytest.mark.anyio
async def test_collection_detail_marks_running_job_as_non_actionable(monkeypatch) -> None:
    dataset = _platform_order_dataset()
    monkeypatch.setattr(data_sources, "_require_user", lambda token: {"company_id": "company-1"})
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda company_id, data_source_id: {"id": data_source_id, "source_kind": "platform_oauth", "provider_code": "taobao"},
    )
    monkeypatch.setattr(data_sources.auth_db, "get_unified_data_source_dataset_by_id", lambda company_id, dataset_id: dataset)
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_sync_jobs",
        lambda **kwargs: [
            {
                "id": "job-running",
                "resource_key": "taobao_order_lines:shop-1",
                "status": "running",
                "trigger_mode": "initial",
                "created_at": "2026-05-08T01:00:00Z",
            }
        ],
    )
    monkeypatch.setattr(data_sources, "_enrich_jobs_with_latest_attempts", lambda company_id, jobs: jobs)
    monkeypatch.setattr(data_sources.auth_db, "get_platform_order_line_stats", lambda **kwargs: {"total_count": 0})
    monkeypatch.setattr(data_sources.auth_db, "list_platform_order_lines", lambda **kwargs: [])

    result = await data_sources._handle_data_source_get_dataset_collection_detail(
        {"auth_token": "token", "source_id": "source-1", "dataset_id": "dataset-1", "sample_limit": 20}
    )

    assert result["collection_status"]["status"] == "running"
    assert result["collection_status"]["message"] == "初始化中"
    assert result["collection_status"]["can_initialize"] is False
    assert result["semantic_status"]["status"] == "waiting_for_samples"
    assert result["semantic_status"]["can_refresh"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_collection_detail_returns_platform_field_groups_and_twenty_rows finance-mcp/tests/test_platform_order_collection.py::test_collection_detail_marks_running_job_as_non_actionable -v
```

Expected: both tests fail because `collection_status`, `semantic_status`, `field_groups`, `sample_limit`, and flattened `raw.*` preview fields are not returned.

- [ ] **Step 3: Add status derivation helpers**

In `finance-mcp/tools/data_sources.py`, add these helpers before `_handle_data_source_get_dataset_collection_detail`:

```python
def _normalize_job_status_for_detail(job: dict[str, Any] | None) -> str:
    status = _safe_text((job or {}).get("status")).lower()
    if status in {"queued", "pending", "scheduled"}:
        return "queued"
    if status in {"running", "processing", "in_progress"}:
        return "running"
    if status in {"failed", "error"}:
        return "failed"
    if status in {"succeeded", "success", "completed", "done"}:
        return "succeeded"
    return ""


def _build_collection_status_detail(
    *,
    jobs: list[dict[str, Any]],
    stats: dict[str, Any],
    row_count: int,
) -> dict[str, Any]:
    latest_job = jobs[0] if jobs else {}
    job_status = _normalize_job_status_for_detail(latest_job)
    total_count = int(stats.get("total_count") or stats.get("record_count") or row_count or 0)
    if job_status == "queued":
        status, message = "queued", "等待初始化"
    elif job_status == "running":
        status, message = "running", "初始化中"
    elif total_count > 0 or row_count > 0:
        status, message = "succeeded", "已采集真实样本"
    elif job_status == "failed":
        status, message = "failed", _safe_text(latest_job.get("last_error_message") or latest_job.get("error_message")) or "初始化失败"
    else:
        status, message = "not_started", "尚未初始化"

    return {
        "status": status,
        "message": message,
        "latest_job": latest_job,
        "stats": stats,
        "can_initialize": status == "not_started",
        "can_retry_initialize": status == "failed",
        "is_running": status in {"queued", "running"},
    }


def _build_semantic_status_detail(
    *,
    dataset_row: dict[str, Any] | None,
    has_sample_rows: bool,
    collection_running: bool,
) -> dict[str, Any]:
    profile = _extract_semantic_profile(dataset_row or {})
    flat = _flatten_semantic_profile(dataset_row or {})
    raw_status = _safe_text(flat.get("semantic_status"))
    if collection_running:
        return {"status": "waiting_for_samples", "message": "等待真实样本", "can_refresh": False, "can_retry": False}
    if not has_sample_rows:
        return {"status": "waiting_for_samples", "message": "等待真实样本", "can_refresh": False, "can_retry": False}
    if raw_status in {"generated_with_samples", "llm_generated", "manual_updated", "published"} or profile:
        return {"status": "succeeded", "message": "已生成语义结构", "can_refresh": True, "can_retry": False}
    if raw_status == "failed":
        return {"status": "failed", "message": "语义生成失败", "can_refresh": False, "can_retry": True}
    return {"status": "waiting_for_generation", "message": "等待语义生成", "can_refresh": True, "can_retry": False}
```

- [ ] **Step 4: Add field group helper**

In `finance-mcp/tools/data_sources.py`, add:

```python
def _build_dataset_semantic_field_groups(dataset_row: dict[str, Any] | None) -> list[dict[str, Any]]:
    flat = _flatten_semantic_profile(dataset_row or {})
    groups = {
        "normalized": {"key": "normalized", "label": "标准字段", "default_open": True, "fields": []},
        "raw_bill": {"key": "raw_bill", "label": "原始账单字段", "default_open": True, "fields": []},
        "system": {"key": "system", "label": "系统字段", "default_open": False, "fields": []},
    }
    for item in flat.get("semantic_fields") or []:
        if not isinstance(item, dict):
            continue
        raw_name = _safe_text(item.get("raw_name") or item.get("name"))
        if not raw_name:
            continue
        field_source = _safe_text(item.get("field_source"))
        if not field_source:
            if raw_name.startswith("raw."):
                field_source = "raw_bill"
            elif raw_name in PLATFORM_SYSTEM_FIELDS:
                field_source = "system"
            else:
                field_source = "normalized"
        groups.setdefault(
            field_source,
            {"key": field_source, "label": field_source, "default_open": field_source != "system", "fields": []},
        )
        groups[field_source]["fields"].append(
            {
                **dict(item),
                "raw_name": raw_name,
                "display_name": _safe_text(item.get("display_name") or item.get("display_name_zh"))
                or dict(flat.get("field_label_map") or {}).get(raw_name)
                or raw_name,
                "field_source": field_source,
            }
        )
    return [groups["normalized"], groups["raw_bill"], groups["system"]] + [
        value for key, value in groups.items() if key not in {"normalized", "raw_bill", "system"}
    ]
```

- [ ] **Step 5: Extend collection detail response**

In `_handle_data_source_get_dataset_collection_detail`, change the platform sample row mapping to flatten raw fields:

```python
    sample_rows = [
        _flatten_platform_sample_payload(dict(item.get("payload") or {}))
        for item in collection_records
        if isinstance(item, dict) and isinstance(item.get("payload"), dict)
    ]
```

Before the return, compute:

```python
    collection_status = _build_collection_status_detail(
        jobs=jobs,
        stats=stats if isinstance(stats, dict) else {},
        row_count=len(sample_rows),
    )
    semantic_status = _build_semantic_status_detail(
        dataset_row=dataset_row,
        has_sample_rows=len(sample_rows) > 0 or int((stats or {}).get("total_count") or 0) > 0,
        collection_running=bool(collection_status.get("is_running")),
    )
```

Add these keys to the return object:

```python
        "collection_status": collection_status,
        "semantic_status": semantic_status,
        "field_groups": _build_dataset_semantic_field_groups(dataset_row),
        "sample_limit": sample_limit,
```

- [ ] **Step 6: Run collection detail tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_collection_detail_returns_platform_field_groups_and_twenty_rows finance-mcp/tests/test_platform_order_collection.py::test_collection_detail_marks_running_job_as_non_actionable -v
```

Expected: both tests pass.

- [ ] **Step 7: Run existing platform collection suite**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py -v
```

Expected: all tests in `test_platform_order_collection.py` pass.

- [ ] **Step 8: Commit backend detail extensions**

Run:

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_platform_order_collection.py
git commit -m "feat: expose platform dataset detail status"
```

### Task 3: data-agent API Contract Pass-Through

**Files:**
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
- Modify: `finance-agents/data-agent/graphs/data_source/api.py`

- [ ] **Step 1: Extend response model**

In `finance-agents/data-agent/graphs/data_source/api.py`, update `DataSourceDatasetCollectionDetailResponse`:

```python
class DataSourceDatasetCollectionDetailResponse(BaseModel):
    success: bool
    mode: str = "mock"
    source_id: str = ""
    resource_key: str = ""
    dataset: dict[str, Any] | None = None
    collection_stats: dict[str, Any] = Field(default_factory=dict)
    collection_status: dict[str, Any] = Field(default_factory=dict)
    semantic_status: dict[str, Any] = Field(default_factory=dict)
    field_groups: list[dict[str, Any]] = Field(default_factory=list)
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    row_count: int = 0
    sample_limit: int = 20
    message: str = ""
```

- [ ] **Step 2: Default collection detail sample limit to 20**

In `get_dataset_collection_detail(...)`, change the query default:

```python
sample_limit: int = Query(20, ge=1, le=50, description="最新样本行数量"),
```

And include new fields in the response:

```python
    return DataSourceDatasetCollectionDetailResponse(
        success=True,
        mode=str(result.get("mode") or mode or "mock"),
        source_id=str(result.get("source_id") or source_id),
        resource_key=str(result.get("resource_key") or resource_key or ""),
        dataset=result.get("dataset"),
        collection_stats=result.get("collection_stats") or {},
        collection_status=result.get("collection_status") or {},
        semantic_status=result.get("semantic_status") or {},
        field_groups=result.get("field_groups") or [],
        jobs=result.get("jobs") or [],
        rows=result.get("rows") or [],
        count=int(result.get("count") or len(result.get("jobs") or [])),
        row_count=int(result.get("row_count") or len(result.get("rows") or [])),
        sample_limit=int(result.get("sample_limit") or sample_limit),
        message=str(result.get("message") or ""),
    )
```

- [ ] **Step 3: Preserve unknown-tool fallback shape**

In `finance-agents/data-agent/tools/mcp_client.py`, update the unknown tool fallback in `data_source_get_dataset_collection_detail`:

```python
        return {
            "success": True,
            "source_id": source_id,
            "resource_key": resource_key,
            "collection_status": {"status": "not_started", "message": "当前环境尚未接入采集详情", "can_initialize": False},
            "semantic_status": {"status": "waiting_for_samples", "message": "等待真实样本", "can_refresh": False},
            "field_groups": [],
            "jobs": [],
            "rows": [],
            "count": 0,
            "row_count": 0,
            "sample_limit": max(1, min(sample_limit, 50)),
            "message": "当前环境尚未接入采集详情",
        }
```

- [ ] **Step 4: Run API import check**

Run:

```bash
source .venv/bin/activate
python -m compileall finance-agents/data-agent/graphs/data_source/api.py finance-agents/data-agent/tools/mcp_client.py
```

Expected: command exits with status 0 and prints successful compilation lines for both files.

- [ ] **Step 5: Commit data-agent pass-through**

Run:

```bash
git add finance-agents/data-agent/graphs/data_source/api.py finance-agents/data-agent/tools/mcp_client.py
git commit -m "feat: pass through platform dataset detail metadata"
```

### Task 4: Frontend Shop Dataset Detail State And Rendering

**Files:**
- Modify: `finance-web/src/components/DataConnectionsPanel.tsx`

- [ ] **Step 1: Add frontend local types**

Change the React import at the top of `finance-web/src/components/DataConnectionsPanel.tsx` so fragments can be keyed inside `shops.map`:

```typescript
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
```

In the `lucide-react` import at the top of `finance-web/src/components/DataConnectionsPanel.tsx`, add `Sparkles` between `ShieldCheck` and `Store`:

```typescript
  ShieldCheck,
  Sparkles,
  Store,
```

In `finance-web/src/components/DataConnectionsPanel.tsx`, add these interfaces after `DatasetCollectionDetailDialogState`:

```typescript
interface PlatformDatasetFieldGroup {
  key: string;
  label: string;
  default_open?: boolean;
  fields: Array<Record<string, unknown>>;
}

interface PlatformDatasetCollectionStatus {
  status: string;
  message: string;
  can_initialize?: boolean;
  can_retry_initialize?: boolean;
  is_running?: boolean;
  latest_job?: Record<string, unknown>;
  stats?: Record<string, unknown>;
}

interface PlatformDatasetSemanticStatus {
  status: string;
  message: string;
  can_refresh?: boolean;
  can_retry?: boolean;
}

interface PlatformShopDatasetDetail {
  sourceId: string;
  source: DataSourceListItem;
  dataset: DataSourceDatasetSummary;
  collectionStatus: PlatformDatasetCollectionStatus;
  semanticStatus: PlatformDatasetSemanticStatus;
  fieldGroups: PlatformDatasetFieldGroup[];
  rows: Array<Record<string, unknown>>;
  loading: boolean;
  error: string;
  loadedAt: string;
}
```

- [ ] **Step 2: Add detail state**

Near the existing platform state declarations around `shops`, add:

```typescript
const [expandedShopDatasetId, setExpandedShopDatasetId] = useState<string>('');
const [shopDatasetDetails, setShopDatasetDetails] = useState<Record<string, PlatformShopDatasetDetail[]>>({});
const [shopDatasetActionError, setShopDatasetActionError] = useState<Record<string, string>>({});
```

- [ ] **Step 3: Add response normalizers**

Add these helpers near `normalizeDataset`:

```typescript
function normalizePlatformFieldGroups(raw: unknown): PlatformDatasetFieldGroup[] {
  const groups = Array.isArray(raw) ? raw : [];
  return groups
    .map((item) => {
      const value = asRecord(item);
      if (!value) return null;
      return {
        key: asString(value.key) ?? asString(value.name) ?? 'fields',
        label: asString(value.label) ?? asString(value.name) ?? '字段',
        default_open: asBoolean(value.default_open),
        fields: Array.isArray(value.fields)
          ? value.fields.filter((field): field is Record<string, unknown> => Boolean(asRecord(field)))
          : [],
      };
    })
    .filter(Boolean) as PlatformDatasetFieldGroup[];
}

function normalizePlatformDatasetDetail(
  raw: unknown,
  source: DataSourceListItem,
  fallbackDataset: DataSourceDatasetSummary,
): PlatformShopDatasetDetail {
  const value = asRecord(raw) ?? {};
  const dataset = normalizeDataset(value.dataset) ?? fallbackDataset;
  const collectionStatus = asRecord(value.collection_status) ?? {};
  const semanticStatus = asRecord(value.semantic_status) ?? {};
  const rows = Array.isArray(value.rows)
    ? value.rows.filter((row): row is Record<string, unknown> => Boolean(asRecord(row)))
    : [];

  return {
    sourceId: source.id,
    source,
    dataset,
    collectionStatus: {
      status: asString(collectionStatus.status) ?? 'not_started',
      message: asString(collectionStatus.message) ?? '尚未初始化',
      can_initialize: asBoolean(collectionStatus.can_initialize),
      can_retry_initialize: asBoolean(collectionStatus.can_retry_initialize),
      is_running: asBoolean(collectionStatus.is_running),
      latest_job: asRecord(collectionStatus.latest_job) ?? undefined,
      stats: asRecord(collectionStatus.stats) ?? undefined,
    },
    semanticStatus: {
      status: asString(semanticStatus.status) ?? 'waiting_for_samples',
      message: asString(semanticStatus.message) ?? '等待真实样本',
      can_refresh: asBoolean(semanticStatus.can_refresh),
      can_retry: asBoolean(semanticStatus.can_retry),
    },
    fieldGroups: normalizePlatformFieldGroups(value.field_groups),
    rows,
    loading: false,
    error: '',
    loadedAt: new Date().toISOString(),
  };
}
```

- [ ] **Step 4: Add dataset lookup and loader**

Add these callbacks near `fetchShops` / platform handlers:

```typescript
const findPlatformShopDatasets = useCallback(
  (shop: ShopConnection): Array<{ source: DataSourceListItem; dataset: DataSourceDatasetSummary }> => {
    const shopId = shop.id;
    const platformCode = (selectedPlatform?.platform_code ?? '').toLowerCase();
    const matches: Array<{ source: DataSourceListItem; dataset: DataSourceDatasetSummary }> = [];
    remoteSources.forEach((source) => {
      (source.datasets ?? []).forEach((dataset) => {
        const resourceKey = dataset.resource_key || dataset.dataset_code;
        const matched =
          platformCode === 'taobao'
            ? resourceKey === `taobao_order_lines:${shopId}`
            : platformCode === 'alipay'
              ? resourceKey.startsWith('alipay_bill:') && resourceKey.endsWith(`:${shopId}`)
              : false;
        if (matched) matches.push({ source, dataset });
      });
    });
    return matches;
  },
  [remoteSources, selectedPlatform?.platform_code],
);

const loadPlatformShopDatasetDetails = useCallback(
  async (shop: ShopConnection) => {
    const shopKey = shop.id;
    setExpandedShopDatasetId((current) => (current === shopKey ? '' : shopKey));
    setShopDatasetActionError((prev) => ({ ...prev, [shopKey]: '' }));
    const datasetRefs = findPlatformShopDatasets(shop);
    if (!authToken) {
      setShopDatasetDetails((prev) => ({
        ...prev,
        [shopKey]: datasetRefs.map(({ source, dataset }) => ({
          sourceId: source.id,
          source,
          dataset,
          collectionStatus: { status: 'not_started', message: '当前环境未连接后端采集详情。' },
          semanticStatus: { status: 'waiting_for_samples', message: '等待真实样本' },
          fieldGroups: [],
          rows: [],
          loading: false,
          error: '当前环境未连接后端采集详情。',
          loadedAt: '',
        })),
      }));
      return;
    }

    setShopDatasetDetails((prev) => ({
      ...prev,
      [shopKey]: datasetRefs.map(({ source, dataset }) => ({
        sourceId: source.id,
        source,
        dataset,
        collectionStatus: { status: 'not_started', message: '加载中' },
        semanticStatus: { status: 'waiting_for_samples', message: '加载中' },
        fieldGroups: [],
        rows: [],
        loading: true,
        error: '',
        loadedAt: '',
      })),
    }));

    const details = await Promise.all(
      datasetRefs.map(async ({ source, dataset }) => {
        if (draftSourceIdSet.has(source.id)) {
          return {
            sourceId: source.id,
            source,
            dataset,
            collectionStatus: { status: 'not_started', message: '当前环境未连接后端采集详情。' },
            semanticStatus: { status: 'waiting_for_samples', message: '等待真实样本' },
            fieldGroups: [],
            rows: [],
            loading: false,
            error: '当前环境未连接后端采集详情。',
            loadedAt: '',
          };
        }
        try {
          const params = new URLSearchParams({
            resource_key: dataset.resource_key || dataset.dataset_code,
            limit: '10',
            sample_limit: '20',
          });
          const response = await fetch(
            `/api/data-sources/${source.id}/datasets/${encodeURIComponent(dataset.id)}/collection-detail?${params.toString()}`,
            { headers: authHeaders },
          );
          const data = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(String(data?.detail || data?.message || '获取数据集详情失败'));
          }
          return normalizePlatformDatasetDetail(data, source, dataset);
        } catch (error) {
          return {
            sourceId: source.id,
            source,
            dataset,
            collectionStatus: { status: 'not_started', message: '加载失败' },
            semanticStatus: { status: 'waiting_for_samples', message: '等待真实样本' },
            fieldGroups: [],
            rows: [],
            loading: false,
            error: error instanceof Error ? error.message : '获取数据集详情失败',
            loadedAt: '',
          };
        }
      }),
    );

    setShopDatasetDetails((prev) => ({ ...prev, [shopKey]: details }));
  },
  [authHeaders, authToken, draftSourceIdSet, findPlatformShopDatasets],
);
```

- [ ] **Step 5: Add action handlers with running-state guard**

Add:

```typescript
const refreshPlatformDatasetSemantic = useCallback(
  async (shop: ShopConnection, detail: PlatformShopDatasetDetail) => {
    if (detail.collectionStatus.is_running || !detail.semanticStatus.can_refresh) return;
    setShopDatasetActionError((prev) => ({ ...prev, [shop.id]: '' }));
    const updated = await refreshDatasetSemanticSuggestions(detail.source, detail.dataset);
    if (updated) {
      await loadPlatformShopDatasetDetails(shop);
    }
  },
  [loadPlatformShopDatasetDetails, refreshDatasetSemanticSuggestions],
);

const retryPlatformDatasetCollection = useCallback(
  async (shop: ShopConnection, detail: PlatformShopDatasetDetail) => {
    if (detail.collectionStatus.is_running) return;
    setShopDatasetActionError((prev) => ({ ...prev, [shop.id]: '' }));
    try {
      const response = await fetch(
        `/api/data-sources/${detail.sourceId}/datasets/${encodeURIComponent(detail.dataset.id)}/collection`,
        {
          method: 'POST',
          headers: authHeaders,
          body: JSON.stringify({
            resource_key: detail.dataset.resource_key || detail.dataset.dataset_code,
            background: true,
            params: {
              dataset_id: detail.dataset.id,
              resource_key: detail.dataset.resource_key || detail.dataset.dataset_code,
            },
          }),
        },
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(String(data?.detail || data?.message || '初始化采集失败'));
      }
      await loadPlatformShopDatasetDetails(shop);
    } catch (error) {
      setShopDatasetActionError((prev) => ({
        ...prev,
        [shop.id]: error instanceof Error ? error.message : '初始化采集失败',
      }));
    }
  },
  [authHeaders, loadPlatformShopDatasetDetails],
);
```

- [ ] **Step 6: Add render helpers**

Add these helpers before `renderPlatformDetails`:

```typescript
function platformDatasetStatusClass(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'succeeded' || normalized === 'succeeded_with_samples') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (normalized === 'running' || normalized === 'queued') return 'bg-blue-50 text-blue-700 border-blue-200';
  if (normalized === 'failed') return 'bg-red-50 text-red-700 border-red-200';
  return 'bg-surface-secondary text-text-secondary border-border';
}

function displayFieldName(field: Record<string, unknown>): string {
  return asString(field.display_name) ?? asString(field.display_name_zh) ?? asString(field.raw_name) ?? asString(field.name) ?? '-';
}

function rawFieldName(field: Record<string, unknown>): string {
  return asString(field.raw_name) ?? asString(field.name) ?? '';
}

function formatPreviewCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}
```

Add a `renderPlatformDatasetDetail` function:

```typescript
const renderPlatformDatasetDetail = (shop: ShopConnection) => {
  const details = shopDatasetDetails[shop.id] ?? [];
  const actionError = shopDatasetActionError[shop.id] || '';
  if (expandedShopDatasetId !== shop.id) return null;

  return (
    <tr className="border-t border-border-subtle bg-surface-secondary/60">
      <td colSpan={6} className="px-4 py-4">
        {actionError && (
          <div className="mb-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            {actionError}
          </div>
        )}
        {details.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-surface px-4 py-6 text-sm text-text-secondary">
            未找到该店铺的数据集目录。授权初始化完成后会自动生成固定数据集。
          </div>
        ) : (
          <div className="space-y-3">
            {details.map((detail) => {
              const allPreviewFields = detail.fieldGroups
                .filter((group) => group.key !== 'system')
                .flatMap((group) => group.fields)
                .map((field) => rawFieldName(field))
                .filter(Boolean)
                .slice(0, 8);
              const previewFields = allPreviewFields.length > 0
                ? allPreviewFields
                : Object.keys(detail.rows[0] ?? {}).filter((key) => key !== 'raw').slice(0, 8);
              return (
                <div key={detail.dataset.id} className="rounded-xl border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-text-primary">
                        {detail.dataset.business_name || detail.dataset.dataset_name}
                      </p>
                      <p className="mt-1 text-xs text-text-muted">{detail.dataset.resource_key || detail.dataset.dataset_code}</p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${platformDatasetStatusClass(detail.collectionStatus.status)}`}>
                        {detail.collectionStatus.message}
                      </span>
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${platformDatasetStatusClass(detail.semanticStatus.status)}`}>
                        {detail.semanticStatus.message}
                      </span>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {(detail.collectionStatus.can_initialize || detail.collectionStatus.can_retry_initialize) && !detail.collectionStatus.is_running && (
                      <button
                        type="button"
                        onClick={() => void retryPlatformDatasetCollection(shop, detail)}
                        className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        {detail.collectionStatus.can_retry_initialize ? '重新初始化' : '立即初始化'}
                      </button>
                    )}
                    {detail.semanticStatus.can_refresh && !detail.collectionStatus.is_running && (
                      <button
                        type="button"
                        onClick={() => void refreshPlatformDatasetSemantic(shop, detail)}
                        className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary transition-colors hover:bg-surface-tertiary"
                      >
                        <Sparkles className="h-3.5 w-3.5" />
                        {detail.semanticStatus.can_retry ? '重新生成语义' : '刷新语义'}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        void startEditDatasetSemantic(detail.source, detail.dataset);
                      }}
                      className="inline-flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs text-blue-700 transition-colors hover:bg-blue-100"
                    >
                      管理发布
                    </button>
                  </div>

                  {detail.loading ? (
                    <div className="mt-3 flex items-center rounded-lg border border-border bg-surface-secondary px-3 py-4 text-sm text-text-secondary">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      正在加载数据集详情
                    </div>
                  ) : detail.error ? (
                    <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
                      {detail.error}
                    </div>
                  ) : (
                    <>
                      <div className="mt-4 grid gap-3 md:grid-cols-3">
                        {detail.fieldGroups.map((group) => (
                          <div key={group.key} className="rounded-lg border border-border bg-surface-secondary p-3">
                            <p className="text-xs font-semibold text-text-primary">{group.label}</p>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {group.fields.slice(0, group.key === 'system' ? 6 : 16).map((field) => (
                                <span
                                  key={`${detail.dataset.id}-${group.key}-${rawFieldName(field)}`}
                                  className="inline-flex rounded-full border border-border bg-surface px-2 py-0.5 text-[11px] text-text-secondary"
                                  title={rawFieldName(field)}
                                >
                                  {displayFieldName(field)}
                                </span>
                              ))}
                              {group.fields.length === 0 && <span className="text-xs text-text-muted">无字段</span>}
                            </div>
                          </div>
                        ))}
                      </div>

                      <div className="mt-4 overflow-x-auto rounded-lg border border-border">
                        <table className="min-w-[720px] w-full text-xs">
                          <thead className="bg-surface-secondary text-left text-text-secondary">
                            <tr>
                              {previewFields.map((field) => (
                                <th key={`${detail.dataset.id}-head-${field}`} className="px-3 py-2 font-medium" title={field}>
                                  {detail.dataset.field_label_map?.[field] || field.replace(/^raw\./, '')}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {detail.rows.slice(0, 20).map((row, rowIndex) => (
                              <tr key={`${detail.dataset.id}-row-${rowIndex}`} className="border-t border-border-subtle">
                                {previewFields.map((field) => (
                                  <td key={`${detail.dataset.id}-${rowIndex}-${field}`} className="max-w-[220px] truncate px-3 py-2 text-text-primary" title={formatPreviewCell(row[field])}>
                                    {formatPreviewCell(row[field])}
                                  </td>
                                ))}
                              </tr>
                            ))}
                            {detail.rows.length === 0 && (
                              <tr>
                                <td colSpan={Math.max(previewFields.length, 1)} className="px-3 py-5 text-center text-text-secondary">
                                  暂无真实样本数据
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </td>
    </tr>
  );
};
```

- [ ] **Step 7: Add shop row action**

In `renderPlatformDetails`, inside each shop action group before “重授权”, add:

```tsx
<button
  type="button"
  onClick={() => void loadPlatformShopDatasetDetails(shop)}
  className="inline-flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs text-blue-700 hover:bg-blue-100 transition-colors"
>
  <Database className="h-3.5 w-3.5" />
  数据集
</button>
```

Then change the `shops.map` rendering from a single `<tr>` to a keyed `Fragment`:

```tsx
<Fragment key={shop.id}>
  <tr className="border-t border-border-subtle text-text-primary">
    <td className="px-4 py-3">{shop.external_shop_name}</td>
    <td className="px-4 py-3 text-text-secondary">{shop.external_shop_id}</td>
    <td className="px-4 py-3">
      <span className="inline-flex rounded-full bg-surface-accent px-2.5 py-1 text-xs font-medium text-blue-600">
        {getStatusLabel(shop.auth_status)}
      </span>
    </td>
    <td className="px-4 py-3 text-text-secondary">{formatTime(shop.token_expires_at)}</td>
    <td className="px-4 py-3 text-text-secondary">{formatTime(shop.last_sync_at)}</td>
    <td className="px-4 py-3">
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={() => void loadPlatformShopDatasetDetails(shop)}
          className="inline-flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-2.5 py-1.5 text-xs text-blue-700 hover:bg-blue-100 transition-colors"
        >
          <Database className="h-3.5 w-3.5" />
          数据集
        </button>
        <button
          type="button"
          onClick={() => void handleReauthorize(shop)}
          disabled={actioningShopId === shop.id}
          className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs text-text-primary hover:bg-surface-tertiary disabled:opacity-60 transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          重授权
        </button>
        <button
          type="button"
          onClick={() => void handleDisable(shop)}
          disabled={actioningShopId === shop.id}
          className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-60 transition-colors"
        >
          <Ban className="h-3.5 w-3.5" />
          停用
        </button>
      </div>
    </td>
  </tr>
  {renderPlatformDatasetDetail(shop)}
</Fragment>
```

- [ ] **Step 8: Run frontend type check**

Run:

```bash
cd finance-web
npx tsc --noEmit
```

Expected: TypeScript exits with status 0.

- [ ] **Step 9: Commit frontend shop detail UI**

Run:

```bash
git add finance-web/src/components/DataConnectionsPanel.tsx
git commit -m "feat: show platform shop semantic datasets"
```

### Task 5: Reconciliation Dataset Selection Guard Verification

**Files:**
- Test: `finance-mcp/tests/test_platform_order_collection.py`

- [ ] **Step 1: Verify only published semantic datasets remain selectable**

Run:

```bash
rg -n "only_published|publish_status|isDatasetAvailable|readDatasetPublishStatus|semantic_status" finance-web/src/components/recon finance-web/src/components/DataConnectionsPanel.tsx finance-mcp/tools/data_sources.py
```

Expected: dataset candidates and available dataset rendering still filter by `publish_status == published` or `only_published`, and no new shop detail state is used as a reconciliation eligibility source.

- [ ] **Step 2: Add a backend regression test**

Append this test to `finance-mcp/tests/test_platform_order_collection.py`:

```python
def test_platform_shop_detail_does_not_publish_dataset_by_itself() -> None:
    dataset = _alipay_bill_dataset(id="dataset-alipay-1")
    dataset["publish_status"] = "unpublished"
    dataset["meta"] = {
        "semantic_profile": {
            "status": "generated_with_samples",
            "fields": [{"raw_name": "source_row_key", "display_name": "账单行唯一键"}],
        }
    }

    view = data_sources._build_dataset_view(dataset)

    assert view["publish_status"] == "unpublished"
    assert view["semantic_status"] == "generated_with_samples"
```

- [ ] **Step 3: Run the guard test**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_platform_shop_detail_does_not_publish_dataset_by_itself -v
```

Expected: test passes, proving semantic generation and publish eligibility stay separate.

- [ ] **Step 4: Commit the guard test**

Run:

```bash
git add finance-mcp/tests/test_platform_order_collection.py
git commit -m "test: guard platform dataset publish eligibility"
```

### Task 6: End-To-End Verification And Service Restart

**Files:**
- No planned source edits.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py finance-mcp/tests/test_platform_connections_alipay.py finance-mcp/tests/test_platform_connections_taobao.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend type check and build**

Run:

```bash
cd finance-web
npx tsc --noEmit
npm run build
```

Expected: both commands exit with status 0.

- [ ] **Step 3: Restart services**

Run from repository root:

```bash
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, and finance-mcp restart successfully.

- [ ] **Step 4: Health check**

Run:

```bash
curl -s http://localhost:3335/health
curl -s http://localhost:8100/health
curl -I http://localhost:5173
```

Expected: MCP and data-agent return healthy JSON responses; web returns HTTP 200 or 304.

- [ ] **Step 5: Manual browser acceptance**

Open `http://localhost:5173`, then verify:

1. 进入“数据连接 -> 电商平台授权 -> 淘宝/天猫店铺”，点击某个店铺的“数据集”。
2. 后台初始化运行中时，只看到“初始化中/等待初始化”，不出现可点击的“立即初始化/刷新语义”。
3. 淘宝/天猫初始化成功后，店铺详情展示“淘宝/天猫订单明细”的字段结构和最多 20 条真实订单行。
4. 进入“支付宝商户”，点击“数据集”，看到资金账单和交易账单两个数据集。
5. 支付宝样本里标准字段、原始账单字段、系统字段分组展示，`raw.收入` 这类字段显示中文表头。
6. 点击“管理发布”打开现有语义发布侧栏，保存后仍写入 `data_source_datasets.meta.semantic_profile`。

- [ ] **Step 6: Final commit if verification required small fixes**

If verification caused source changes, commit them:

```bash
git add finance-mcp/tools/data_sources.py finance-agents/data-agent/graphs/data_source/api.py finance-agents/data-agent/tools/mcp_client.py finance-web/src/components/DataConnectionsPanel.tsx
git commit -m "fix: polish platform dataset semantic display"
```

If no source files changed during verification, do not create a commit.

## Implementation Notes

- The authorization initialization path remains responsible for creating datasets, collecting initial samples, generating semantic suggestions, and allowing human confirmation/publish.
- Auto reconciliation and rerun collection must not call semantic refresh. They only collect real business data for datasets that are already published and selectable.
- Running jobs must be represented as state, not as disabled duplicate action buttons. The backend should still be idempotent for duplicate trigger calls and return the existing job.
- Alipay metadata must remain:
  - `storage = "platform_alipay_bill_lines"`
  - `source = "alipay_bill_lines"`
  - `resource_key = "alipay_bill:<bill_type>:<shop_connection_id>"`
- Do not write semantic names into `platform_order_lines` or `platform_alipay_bill_lines`. Only row payload and raw values belong there.
- The platform API collection date field and reconciliation plan business date field remain separate. Taobao/Tmall collection uses created/modified API windows; reconciliation should prefer `biz_date`. Alipay collection and reconciliation both normally use `bill_date`, but the UI should not merge these configuration concepts.

## Self-Review

- Spec coverage: the plan covers platform semantic sample loading, Alipay `raw.*` expansion, 20-row real preview, running-state UX, failure retry actions, publish gating, and the confirmed Alipay metadata shape.
- Placeholder scan: the plan contains no deferred implementation markers and every code-changing step includes concrete paths, snippets, commands, and expected outcomes.
- Type consistency: backend response keys are `collection_status`, `semantic_status`, `field_groups`, `sample_limit`; frontend normalizers consume the same keys and keep existing `rows` / `jobs` compatibility.

# Alipay Platform Table Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move newly collected Alipay bill rows from `dataset_collection_records` into the channel-specific `platform_alipay_bill_lines` table and make recon read from that table.

**Architecture:** Keep dataset catalog discovery unified through `data_source_datasets`, but route Alipay bill physical storage to a dedicated platform table. The Alipay collector becomes driver-managed storage, just like Taobao/Tmall `platform_order_lines`, so `_execute_sync_job()` records job/event metrics without re-upserting bill rows into the generic collection table. Existing local/test data in `dataset_collection_records` is not migrated.

**Tech Stack:** Python FastAPI/MCP tools, PostgreSQL migrations and `psycopg2`, pandas recon dataset loaders, pytest.

---

## Confirmed Decisions

- Use one physical table per high-volume ecommerce channel.
- Add `platform_alipay_bill_lines` for Alipay bill rows.
- Do not migrate old Alipay rows already stored in `dataset_collection_records`.
- New Alipay dataset metadata must point to `platform_alipay_bill_lines`.
- Alipay bill rows are bill-line records, not order-line records.
- First version promotes only reconciliation-needed fields and keeps the full row in `payload`.
- Unique key is `company_id + shop_connection_id + bill_type + bill_date + source_row_key`.
- Recon loader source types are `platform_alipay_bill_lines` and alias `alipay_bill_lines`.
- Do not change this agreed design later without explicit user confirmation.

## File Structure

- Create `finance-mcp/auth/migrations/025_platform_alipay_bill_lines.sql`
  - Owns the new Alipay bill physical table, constraints, indexes, and update trigger.
- Modify `finance-mcp/auth/migrations/README.md`
  - Documents migration 025 in execution order.
- Modify `finance-mcp/auth/db.py`
  - Applies migration 025 when the table is missing.
  - Adds `upsert_platform_alipay_bill_lines()`.
  - Adds `list_platform_alipay_bill_lines()`.
  - Adds `get_platform_alipay_bill_line_stats()`.
- Modify `finance-mcp/tools/platform_connections.py`
  - Emits Alipay dataset metadata with `storage=platform_alipay_bill_lines` and `source=alipay_bill_lines`.
- Modify `finance-mcp/tools/data_sources.py`
  - Recognizes the Alipay platform table storage marker.
  - Upserts Alipay fetched rows into `platform_alipay_bill_lines`.
  - Marks Alipay bill collection as driver-managed storage.
  - Reads Alipay samples/details/list records from the new table.
- Modify `finance-mcp/recon/mcp_server/dataset_loader.py`
  - Registers `platform_alipay_bill_lines` and `alipay_bill_lines`.
  - Loads and filters Alipay bill rows from the new table.
- Modify tests:
  - `finance-mcp/tests/test_platform_alipay_bill_lines.py`
  - `finance-mcp/tests/test_platform_connections_alipay.py`
  - `finance-mcp/tests/test_platform_order_collection.py`
  - `finance-mcp/tests/test_alipay_dataset_loader_contract.py`
  - `finance-mcp/tests/test_platform_order_dataset_loader.py`

---

### Task 1: Add Alipay Bill Table Migration

**Files:**
- Create: `finance-mcp/auth/migrations/025_platform_alipay_bill_lines.sql`
- Modify: `finance-mcp/auth/migrations/README.md`
- Modify: `finance-mcp/auth/db.py`

- [ ] **Step 1: Write the table migration**

Create `finance-mcp/auth/migrations/025_platform_alipay_bill_lines.sql`:

```sql
CREATE TABLE IF NOT EXISTS public.platform_alipay_bill_lines (
    id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    company_id uuid NOT NULL,
    data_source_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    shop_connection_id uuid NOT NULL,
    external_shop_id character varying(128) DEFAULT ''::character varying NOT NULL,
    bill_type character varying(64) NOT NULL,
    bill_date date NOT NULL,
    source_file_name text DEFAULT ''::text NOT NULL,
    source_row_number integer,
    source_row_key character varying(128) NOT NULL,
    alipay_trade_no character varying(128) DEFAULT ''::character varying NOT NULL,
    merchant_order_no character varying(128) DEFAULT ''::character varying NOT NULL,
    business_order_no character varying(128) DEFAULT ''::character varying NOT NULL,
    amount numeric(18, 2),
    income_amount numeric(18, 2),
    expense_amount numeric(18, 2),
    trade_time timestamp with time zone,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    first_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    latest_seen_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_company_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_data_source_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_data_source_id_fkey
            FOREIGN KEY (data_source_id) REFERENCES public.data_sources(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_dataset_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_dataset_id_fkey
            FOREIGN KEY (dataset_id) REFERENCES public.data_source_datasets(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_shop_connection_id_fkey') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_shop_connection_id_fkey
            FOREIGN KEY (shop_connection_id) REFERENCES public.shop_connections(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'platform_alipay_bill_lines_unique_bill_row') THEN
        ALTER TABLE ONLY public.platform_alipay_bill_lines
            ADD CONSTRAINT platform_alipay_bill_lines_unique_bill_row
            UNIQUE (company_id, shop_connection_id, bill_type, bill_date, source_row_key);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_dataset_date
    ON public.platform_alipay_bill_lines USING btree (company_id, dataset_id, bill_date, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_source_dataset_date
    ON public.platform_alipay_bill_lines USING btree (company_id, data_source_id, dataset_id, bill_date DESC);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_shop_type_date
    ON public.platform_alipay_bill_lines USING btree (company_id, shop_connection_id, bill_type, bill_date DESC);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_alipay_trade_no
    ON public.platform_alipay_bill_lines USING btree (company_id, alipay_trade_no);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_merchant_order_no
    ON public.platform_alipay_bill_lines USING btree (company_id, merchant_order_no);

CREATE INDEX IF NOT EXISTS idx_platform_alipay_bill_lines_business_order_no
    ON public.platform_alipay_bill_lines USING btree (company_id, business_order_no);

DROP TRIGGER IF EXISTS update_platform_alipay_bill_lines_updated_at ON public.platform_alipay_bill_lines;
CREATE TRIGGER update_platform_alipay_bill_lines_updated_at
    BEFORE UPDATE ON public.platform_alipay_bill_lines
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
```

- [ ] **Step 2: Apply migration automatically when missing**

In `finance-mcp/auth/db.py`, inside `ensure_unified_data_source_schema()` after the `platform_order_lines` block, add:

```python
    if not _table_exists("platform_alipay_bill_lines"):
        _execute_sql_script(_migration_path("025_platform_alipay_bill_lines.sql"))
        applied.append("025_platform_alipay_bill_lines.sql")
```

- [ ] **Step 3: Document migration 025**

In `finance-mcp/auth/migrations/README.md`, append the new ordered item after migration 024:

```markdown
17. **025_platform_alipay_bill_lines.sql** - 支付宝账单行物理表，用于支付宝授权采集后的资金账单和交易账单
```

- [ ] **Step 4: Verify migration SQL parses against PostgreSQL**

Run:

```bash
source .venv/bin/activate
python -m pytest finance-mcp/tests/test_platform_order_lines.py -q
```

Expected: existing tests still pass. No new table tests exist yet.

- [ ] **Step 5: Commit migration**

```bash
git add finance-mcp/auth/migrations/025_platform_alipay_bill_lines.sql finance-mcp/auth/migrations/README.md finance-mcp/auth/db.py
git commit -m "feat: add alipay bill line platform table"
```

---

### Task 2: Add Alipay Bill DB Helpers

**Files:**
- Modify: `finance-mcp/auth/db.py`
- Create: `finance-mcp/tests/test_platform_alipay_bill_lines.py`

- [ ] **Step 1: Write failing tests for upsert/list/stats helpers**

Create `finance-mcp/tests/test_platform_alipay_bill_lines.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth import db as auth_db


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed_sql: list[str] = []
        self.params_seen: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, sql, params=None):
        self.executed_sql.append(sql)
        self.params_seen.append(tuple(params or ()))

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        return {"inserted": True}

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def cursor(self, *args, **kwargs):
        return self.cursor_obj

    def commit(self):
        return None


def test_upsert_platform_alipay_bill_lines_promotes_recon_fields(monkeypatch):
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn(cursor))

    summary = auth_db.upsert_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        shop_connection_id="shop-001",
        external_shop_id="2088123412341234",
        bill_type="trade",
        bill_date="2026-05-06",
        rows=[
            {
                "source_file_name": "trade.csv",
                "source_row_number": "12",
                "source_row_key": "row-key-1",
                "alipay_trade_no": "2026050622001",
                "merchant_order_no": "M001",
                "business_order_no": "B001",
                "raw": {
                    "金额": "12.30",
                    "收入": "12.30",
                    "支出": "",
                    "入账时间": "2026-05-06 12:30:00",
                },
            }
        ],
    )

    assert summary == {"input_count": 1, "upserted_count": 1, "inserted_count": 1, "updated_count": 0}
    assert "INSERT INTO platform_alipay_bill_lines" in cursor.executed_sql[0]
    assert "ON CONFLICT (company_id, shop_connection_id, bill_type, bill_date, source_row_key)" in cursor.executed_sql[0]
    values = [str(value) for value in cursor.params_seen[0]]
    assert "2026050622001" in values
    assert "M001" in values
    assert "B001" in values
    assert values.count("12.30") >= 2


def test_list_platform_alipay_bill_lines_filters_resource_key(monkeypatch):
    cursor = FakeCursor(rows=[{"payload": {"source_row_key": "row-key-1"}}])
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConn(cursor))

    rows = auth_db.list_platform_alipay_bill_lines(
        company_id="company-001",
        data_source_id="source-001",
        dataset_id="dataset-001",
        resource_key="alipay_bill:trade:shop-001",
        biz_date="2026-05-06",
        filters={"merchant_order_no": "M001"},
        limit=20,
        offset=5,
    )

    assert rows == [{"payload": {"source_row_key": "row-key-1"}}]
    sql = cursor.executed_sql[0]
    assert "FROM platform_alipay_bill_lines" in sql
    assert "bill_type = %s" in sql
    assert "shop_connection_id = %s" in sql
    assert "bill_date = %s" in sql
    assert "merchant_order_no = %s" in sql
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_alipay_bill_lines.py -q
```

Expected: FAIL with `AttributeError` for missing `upsert_platform_alipay_bill_lines`.

- [ ] **Step 3: Add normalization helpers**

In `finance-mcp/auth/db.py`, near `_clean_decimal_text()` and `_clean_timestamp_text()`, add:

```python
def _safe_int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _first_non_empty_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    return ""


def _alipay_raw_payload(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("raw")
    if isinstance(raw, dict):
        return raw
    payload = item.get("payload")
    if isinstance(payload, dict):
        nested_raw = payload.get("raw")
        if isinstance(nested_raw, dict):
            return nested_raw
        return payload
    return {}


def _alipay_bill_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else dict(item)
    raw = _alipay_raw_payload(item)
    promoted = {
        "bill_type": item.get("bill_type"),
        "bill_date": item.get("bill_date"),
        "source_file_name": item.get("source_file_name"),
        "source_row_number": item.get("source_row_number"),
        "source_row_key": item.get("source_row_key"),
        "alipay_trade_no": item.get("alipay_trade_no"),
        "merchant_order_no": item.get("merchant_order_no"),
        "business_order_no": item.get("business_order_no"),
        "amount": item.get("amount") or _first_payload_text(raw, "金额", "发生金额", "账务金额", "交易金额", "订单金额"),
        "income_amount": item.get("income_amount") or _first_payload_text(raw, "收入", "收入金额", "入账金额"),
        "expense_amount": item.get("expense_amount") or _first_payload_text(raw, "支出", "支出金额", "出账金额"),
        "trade_time": item.get("trade_time") or _first_payload_text(raw, "入账时间", "创建时间", "交易创建时间", "发生时间", "付款时间", "交易时间"),
    }
    merged = {**payload, **{key: value for key, value in promoted.items() if value not in (None, "")}}
    if raw:
        merged["raw"] = raw
    return merged
```

- [ ] **Step 4: Add DB helper functions**

In `finance-mcp/auth/db.py`, after `get_platform_order_line_stats()`, add complete helpers:

```python
def upsert_platform_alipay_bill_lines(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    shop_connection_id: str,
    external_shop_id: str,
    bill_type: str,
    bill_date: str,
    rows: list[dict] | None = None,
) -> dict:
    """按支付宝账单行唯一键 upsert 支付宝账单明细。"""
    items = rows or []
    if not items:
        return {"input_count": 0, "upserted_count": 0, "inserted_count": 0, "updated_count": 0}

    conn_manager = get_conn()
    inserted_count = 0
    updated_count = 0
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for item in items:
                    raw = _alipay_raw_payload(item)
                    payload = _alipay_bill_payload({**item, "bill_type": bill_type, "bill_date": bill_date})
                    amount = item.get("amount") or _first_payload_text(raw, "金额", "发生金额", "账务金额", "交易金额", "订单金额")
                    income_amount = item.get("income_amount") or _first_payload_text(raw, "收入", "收入金额", "入账金额")
                    expense_amount = item.get("expense_amount") or _first_payload_text(raw, "支出", "支出金额", "出账金额")
                    trade_time = item.get("trade_time") or _first_payload_text(
                        raw,
                        "入账时间",
                        "创建时间",
                        "交易创建时间",
                        "发生时间",
                        "付款时间",
                        "交易时间",
                    )
                    cur.execute(
                        """
                        INSERT INTO platform_alipay_bill_lines (
                            company_id, data_source_id, dataset_id, shop_connection_id,
                            external_shop_id, bill_type, bill_date,
                            source_file_name, source_row_number, source_row_key,
                            alipay_trade_no, merchant_order_no, business_order_no,
                            amount, income_amount, expense_amount, trade_time, payload
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s::jsonb
                        )
                        ON CONFLICT (company_id, shop_connection_id, bill_type, bill_date, source_row_key)
                        DO UPDATE SET
                            data_source_id = EXCLUDED.data_source_id,
                            dataset_id = EXCLUDED.dataset_id,
                            external_shop_id = EXCLUDED.external_shop_id,
                            source_file_name = EXCLUDED.source_file_name,
                            source_row_number = EXCLUDED.source_row_number,
                            alipay_trade_no = EXCLUDED.alipay_trade_no,
                            merchant_order_no = EXCLUDED.merchant_order_no,
                            business_order_no = EXCLUDED.business_order_no,
                            amount = EXCLUDED.amount,
                            income_amount = EXCLUDED.income_amount,
                            expense_amount = EXCLUDED.expense_amount,
                            trade_time = EXCLUDED.trade_time,
                            payload = EXCLUDED.payload,
                            latest_seen_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING (xmax = 0) AS inserted
                        """,
                        (
                            company_id,
                            data_source_id,
                            dataset_id,
                            shop_connection_id,
                            str(external_shop_id or ""),
                            str(bill_type or ""),
                            bill_date,
                            str(item.get("source_file_name") or ""),
                            _safe_int_or_none(item.get("source_row_number")),
                            str(item.get("source_row_key") or ""),
                            _first_non_empty_text(item.get("alipay_trade_no")),
                            _first_non_empty_text(item.get("merchant_order_no")),
                            _first_non_empty_text(item.get("business_order_no")),
                            _clean_decimal_text(amount),
                            _clean_decimal_text(income_amount),
                            _clean_decimal_text(expense_amount),
                            _clean_timestamp_text(trade_time),
                            psycopg2.extras.Json(_json_safe_payload(payload)),
                        ),
                    )
                    row = cur.fetchone() or {}
                    if not row:
                        continue
                    if bool(row.get("inserted")):
                        inserted_count += 1
                    else:
                        updated_count += 1
            conn.commit()
            return {
                "input_count": len(items),
                "upserted_count": inserted_count + updated_count,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
            }
    except Exception as e:
        logger.error(
            f"写入 platform_alipay_bill_lines 失败 (company_id={company_id}, dataset_id={dataset_id}, bill_date={bill_date}, rows={len(items)}): {e}"
        )
        raise


def list_platform_alipay_bill_lines(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    shop_connection_id: str | None = None,
    resource_key: str | None = None,
    biz_date: str | None = None,
    filters: dict | None = None,
    limit: int | None = 100,
    offset: int = 0,
) -> list[dict]:
    """查询支付宝账单行，返回结构化字段和 payload。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_id, shop_connection_id,
                           external_shop_id, bill_type, bill_date, source_file_name,
                           source_row_number, source_row_key, alipay_trade_no,
                           merchant_order_no, business_order_no, amount, income_amount,
                           expense_amount, trade_time, payload,
                           first_seen_at, latest_seen_at, created_at, updated_at
                    FROM platform_alipay_bill_lines
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(shop_connection_id)
                if resource_key and resource_key.startswith("alipay_bill:"):
                    parts = resource_key.split(":")
                    if len(parts) >= 2 and parts[1]:
                        sql += " AND bill_type = %s"
                        params.append(parts[1])
                    if len(parts) >= 3 and parts[2]:
                        sql += " AND shop_connection_id = %s"
                        params.append(parts[2])
                if biz_date:
                    sql += " AND bill_date = %s"
                    params.append(biz_date)
                for field, value in dict(filters or {}).items():
                    if value in (None, "", []):
                        continue
                    if field not in {
                        "bill_type",
                        "source_row_key",
                        "alipay_trade_no",
                        "merchant_order_no",
                        "business_order_no",
                    }:
                        continue
                    if isinstance(value, list):
                        sql += f" AND {field} = ANY(%s)"
                        params.append([str(item) for item in value])
                    else:
                        sql += f" AND {field} = %s"
                        params.append(str(value))
                sql += " ORDER BY bill_date DESC, updated_at DESC, id DESC OFFSET %s"
                params.append(max(0, offset))
                if limit is not None:
                    sql += " LIMIT %s"
                    params.append(max(1, min(limit, 1000)))
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall() or []]
    except Exception as e:
        logger.error(f"查询 platform_alipay_bill_lines 失败 (company_id={company_id}, dataset_id={dataset_id}): {e}")
        return []


def get_platform_alipay_bill_line_stats(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    shop_connection_id: str | None = None,
    biz_date: str | None = None,
) -> dict:
    """统计支付宝账单行。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT COUNT(*)::bigint AS total_count,
                           COUNT(DISTINCT bill_date)::bigint AS biz_date_count,
                           MIN(first_seen_at) AS first_seen_at,
                           MAX(latest_seen_at) AS latest_seen_at
                    FROM platform_alipay_bill_lines
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(shop_connection_id)
                if biz_date:
                    sql += " AND bill_date = %s"
                    params.append(biz_date)
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else {}
    except Exception as e:
        logger.error(f"统计 platform_alipay_bill_lines 失败 (company_id={company_id}, dataset_id={dataset_id}): {e}")
        return {}
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_alipay_bill_lines.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit DB helpers**

```bash
git add finance-mcp/auth/db.py finance-mcp/tests/test_platform_alipay_bill_lines.py
git commit -m "feat: add alipay bill line db helpers"
```

---

### Task 3: Correct Alipay Dataset Metadata

**Files:**
- Modify: `finance-mcp/tools/platform_connections.py`
- Modify: `finance-mcp/tests/test_platform_connections_alipay.py`

- [ ] **Step 1: Update failing metadata assertions**

In `finance-mcp/tests/test_platform_connections_alipay.py`, in `test_alipay_callback_creates_merchant_and_two_datasets`, replace the old storage assertions with:

```python
    assert all(
        dataset["extract_config"]["storage"] == "platform_alipay_bill_lines"
        for dataset in calls["datasets"]
    )
    assert all(
        dataset["schema_summary"]["storage"] == "platform_alipay_bill_lines"
        for dataset in calls["datasets"]
    )
    assert all(
        dataset["schema_summary"]["source"] == "alipay_bill_lines"
        for dataset in calls["datasets"]
    )
```

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_connections_alipay.py::test_alipay_callback_creates_merchant_and_two_datasets -q
```

Expected: FAIL because current payload still says `dataset_collection_records`.

- [ ] **Step 3: Change Alipay dataset payload storage markers**

In `finance-mcp/tools/platform_connections.py`, inside `build_alipay_bill_dataset_payload()`, change the Alipay dataset payload to:

```python
        "extract_config": {
            "storage": "platform_alipay_bill_lines",
            "platform_code": "alipay",
            "shop_connection_id": shop_connection_id,
            "external_shop_id": str(external_shop_id or ""),
            "bill_kind": normalized_bill_kind,
            "bill_type": normalized_bill_type,
            "date_field": "bill_date",
            "collection_date_field": "bill_date",
            "key_fields": key_fields,
        },
        "schema_summary": {
            "source": "alipay_bill_lines",
            "storage": "platform_alipay_bill_lines",
            "columns": [],
            "key_fields": key_fields,
        },
```

- [ ] **Step 4: Run Alipay platform connection tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_connections_alipay.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit metadata correction**

```bash
git add finance-mcp/tools/platform_connections.py finance-mcp/tests/test_platform_connections_alipay.py
git commit -m "fix: point alipay datasets to platform bill table"
```

---

### Task 4: Route Alipay Collection Into the Dedicated Table

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Modify: `finance-mcp/tests/test_platform_order_collection.py`

- [ ] **Step 1: Update test dataset helper to the new storage marker**

In `finance-mcp/tests/test_platform_order_collection.py`, change `_alipay_bill_dataset()`:

```python
        "extract_config": {
            "storage": "platform_alipay_bill_lines",
            "platform_code": "alipay",
            "shop_connection_id": "shop-alipay-1",
            "bill_type": "trade",
            "date_field": "bill_date",
            "collection_date_field": "bill_date",
            "key_fields": ["bill_type", "bill_date", "source_row_key"],
        },
        "schema_summary": {"source": "alipay_bill_lines", "storage": "platform_alipay_bill_lines"},
```

- [ ] **Step 2: Replace the old generic-storage routing test**

In `finance-mcp/tests/test_platform_order_collection.py`, replace `test_execute_sync_job_routes_alipay_bill_rows_to_collection_records` with:

```python
@pytest.mark.anyio
async def test_execute_sync_job_routes_alipay_bill_rows_to_platform_alipay_bill_line_storage(
    monkeypatch,
) -> None:
    calls: dict[str, Any] = {"upsert_dataset_collection_records": 0}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(),
    )

    def fake_run_alipay_bill_download_import(**kwargs: Any) -> dict[str, Any]:
        calls["alipay_kwargs"] = kwargs
        return {
            "success": True,
            "healthy": True,
            "rows": [
                {
                    "bill_type": "trade",
                    "bill_date": "2026-05-06",
                    "source_row_key": "row-1",
                    "amount": "12.30",
                }
            ],
            "original_files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
            "collection_summary": {
                "input_count": 1,
                "upserted_count": 1,
                "inserted_count": 1,
                "updated_count": 0,
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_1",
                "biz_date": "2026-05-06",
                "bill_type": "trade",
                "bill_date": "2026-05-06",
                "record_count": 1,
                "storage": "platform_alipay_bill_lines",
                "original_files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
            },
            "message": "支付宝账单采集成功",
        }

    monkeypatch.setattr(data_sources, "_run_alipay_bill_download_import", fake_run_alipay_bill_download_import)
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_dataset_collection_records",
        lambda **kwargs: calls.__setitem__("upsert_dataset_collection_records", 1),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "update_unified_sync_job_attempt",
        lambda **kwargs: calls.setdefault("attempt", kwargs),
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
    monkeypatch.setattr(data_sources.auth_db, "update_unified_data_source_health", lambda **kwargs: None)
    monkeypatch.setattr(data_sources, "_update_dataset_health_by_resource", lambda **kwargs: None)

    result = await data_sources._execute_sync_job(
        company_id="company-1",
        source_id="source-alipay-1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        runtime_source={"source_kind": "platform_oauth", "provider_code": "alipay"},
        arguments={
            "params": {
                "dataset_id": "dataset-alipay-1",
                "dataset_code": "alipay_trade_bill_shop_1",
                "biz_date": "2026-05-06",
            }
        },
        job={"id": "job-1", "current_attempt": 1},
        attempt={"id": "attempt-1"},
        checkpoint_before={},
        window_start=None,
        window_end=None,
    )

    assert result["success"] is True
    assert calls["upsert_dataset_collection_records"] == 0
    assert calls["alipay_kwargs"]["params"]["bill_date"] == "2026-05-06"
    assert result["collection_summary"]["storage"] == "platform_alipay_bill_lines"
    assert calls["attempt"]["metrics"]["collection_upserted"] == 1
    assert calls["event"]["event_payload"]["original_files"] == [
        {"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}
    ]
```

- [ ] **Step 3: Add a direct collector upsert test**

Append this test to `finance-mcp/tests/test_platform_order_collection.py`:

```python
def test_run_alipay_bill_collection_upserts_platform_bill_lines(monkeypatch) -> None:
    calls: dict[str, Any] = {}

    monkeypatch.setattr(
        data_sources.auth_db,
        "get_shop_connection_by_id",
        lambda shop_connection_id: {
            "id": shop_connection_id,
            "company_id": "company-1",
            "platform_code": "alipay",
            "external_shop_id": "2088123412341234",
            "external_shop_name": "福游网络",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_current_shop_authorization",
        lambda **kwargs: {
            "id": "auth-1",
            "platform_app_id": "alipay-app-1",
            "auth_status": "authorized",
            "access_token": "app-auth-token",
            "refresh_token": "refresh-token",
            "raw_auth_payload": {"source": "test"},
        },
    )
    monkeypatch.setattr(
        data_sources,
        "_load_platform_app_for_authorization",
        lambda **kwargs: {
            "id": "alipay-app-1",
            "company_id": data_sources.SERVICE_PROVIDER_COMPANY_ID,
            "platform_code": "alipay",
            "app_name": "支付宝服务商应用",
            "app_key": "2021006152656574",
            "app_secret": "PRIVATE-KEY",
            "app_type": "isv",
            "auth_base_url": "",
            "token_url": "",
            "refresh_url": "",
            "scopes_config": [],
            "extra": {"mode": "mock"},
            "status": "active",
        },
    )

    class FakeConnector:
        def fetch_bill_rows(self, **kwargs: Any) -> dict[str, Any]:
            calls["fetch_bill_rows"] = kwargs
            return {
                "success": True,
                "rows": [
                    {
                        "bill_type": "trade",
                        "bill_date": "2026-05-06",
                        "source_file_name": "trade.csv",
                        "source_row_number": 2,
                        "source_row_key": "row-1",
                        "alipay_trade_no": "2026050622001",
                        "merchant_order_no": "M001",
                        "raw": {"金额": "12.30"},
                    }
                ],
                "files": [{"file_name": "trade.csv", "path": "uploads/platform/alipay/x"}],
            }

    monkeypatch.setattr(data_sources, "build_platform_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_platform_alipay_bill_lines",
        lambda **kwargs: calls.setdefault("upsert_platform_alipay_bill_lines", kwargs)
        or {"input_count": len(kwargs["rows"]), "upserted_count": len(kwargs["rows"]), "inserted_count": len(kwargs["rows"]), "updated_count": 0},
    )

    result = data_sources._run_alipay_bill_collection(
        company_id="company-1",
        source_id="source-alipay-1",
        dataset_id="dataset-alipay-1",
        dataset_code="alipay_trade_bill_shop_1",
        resource_key="alipay_bill:trade:shop-alipay-1",
        collection_config=_alipay_bill_dataset()["extract_config"],
        params={"biz_date": "2026-05-06"},
        checkpoint_before={"keep": "yes"},
    )

    assert result["success"] is True
    assert result["collection_summary"]["storage"] == "platform_alipay_bill_lines"
    assert result["collection_summary"]["record_count"] == 1
    assert result["next_checkpoint"]["keep"] == "yes"
    upsert = calls["upsert_platform_alipay_bill_lines"]
    assert upsert["company_id"] == "company-1"
    assert upsert["data_source_id"] == "source-alipay-1"
    assert upsert["dataset_id"] == "dataset-alipay-1"
    assert upsert["shop_connection_id"] == "shop-alipay-1"
    assert upsert["external_shop_id"] == "2088123412341234"
    assert upsert["bill_type"] == "trade"
    assert upsert["bill_date"] == "2026-05-06"
```

- [ ] **Step 4: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py -q
```

Expected: FAIL because `_run_alipay_bill_collection()` still reports `dataset_collection_records` and does not call `upsert_platform_alipay_bill_lines()`.

- [ ] **Step 5: Add the Alipay platform-table detector**

In `finance-mcp/tools/data_sources.py`, after `_dataset_uses_platform_order_lines()`, add:

```python
def _dataset_uses_platform_alipay_bill_lines(dataset_row: dict[str, Any] | None) -> bool:
    return _dataset_storage_value(dataset_row) in {"platform_alipay_bill_lines", "alipay_bill_lines"}
```

- [ ] **Step 6: Update not-ready collection summary storage**

In `_run_alipay_bill_collection()`, in the `_is_alipay_bill_not_ready_error()` return payload, change:

```python
                    "storage": "platform_alipay_bill_lines",
```

- [ ] **Step 7: Upsert successful Alipay rows into the dedicated table**

In `_run_alipay_bill_collection()`, replace the current `summary = {...}` block with:

```python
    rows, original_files = _normalize_bill_fetch_result(fetch_result)
    collection_summary = auth_db.upsert_platform_alipay_bill_lines(
        company_id=company_id,
        data_source_id=source_id,
        dataset_id=dataset_id,
        shop_connection_id=shop_connection_id,
        external_shop_id=_safe_text(collection_config.get("external_shop_id") or shop.get("external_shop_id")),
        bill_type=bill_type,
        bill_date=bill_date,
        rows=rows,
    )
    collection_summary.update(
        {
            "storage": "platform_alipay_bill_lines",
            "platform_code": "alipay",
            "bill_type": bill_type,
            "bill_date": bill_date,
            "record_count": collection_summary.get("upserted_count", 0),
            "original_files": original_files,
            "dataset_id": dataset_id,
            "dataset_code": dataset_code,
            "biz_date": bill_date,
        }
    )
```

Then in the returned payload, change:

```python
        "collection_summary": collection_summary,
```

- [ ] **Step 8: Keep `_execute_sync_job()` driver-managed behavior**

No code change should be needed if Step 7 sets `collection_summary.storage = "platform_alipay_bill_lines"`. Verify this existing expression remains true:

```python
        uses_driver_managed_storage = collection_driver == COLLECTION_DRIVER_TAOBAO_ORDER_API or (
            collection_driver == COLLECTION_DRIVER_ALIPAY_BILL_DOWNLOAD_IMPORT
            and bool(collection_storage)
            and collection_storage != "dataset_collection_records"
        )
```

- [ ] **Step 9: Run collection tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py -q
```

Expected: PASS.

- [ ] **Step 10: Commit collection routing**

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_platform_order_collection.py
git commit -m "fix: route alipay bills to platform storage"
```

---

### Task 5: Read Alipay Samples and Collection Details From the Dedicated Table

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Modify: `finance-mcp/tests/test_platform_order_collection.py`

- [ ] **Step 1: Add focused API branch tests**

Append to `finance-mcp/tests/test_platform_order_collection.py`:

```python
@pytest.mark.anyio
async def test_list_collection_records_reads_alipay_platform_bill_lines(monkeypatch) -> None:
    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda auth_token: {"company_id": "company-1", "user_id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {"id": "source-alipay-1", "source_kind": "platform_oauth", "provider_code": "alipay"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_dataset_by_id",
        lambda company_id, dataset_id: _alipay_bill_dataset(),
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_platform_alipay_bill_lines",
        lambda **kwargs: [{"payload": {"source_row_key": "row-1", "amount": "12.30"}}],
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_platform_alipay_bill_line_stats",
        lambda **kwargs: {"total_count": 1, "biz_date_count": 1},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_dataset_collection_records",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not read generic collection records")),
    )

    result = await data_sources._handle_data_source_list_collection_records(
        {
            "auth_token": "token",
            "source_id": "source-alipay-1",
            "dataset_id": "dataset-alipay-1",
            "biz_date": "2026-05-06",
            "item_key": "row-1",
        }
    )

    assert result["success"] is True
    assert result["records"][0]["payload"]["source_row_key"] == "row-1"
    assert result["stats"]["total_count"] == 1
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_list_collection_records_reads_alipay_platform_bill_lines -q
```

Expected: FAIL because the handler still routes non-Taobao datasets to `dataset_collection_records`.

- [ ] **Step 3: Route collection detail to Alipay table**

In `_handle_data_source_get_dataset_collection_detail()`, between the platform-order branch and the generic branch, add:

```python
    elif _dataset_uses_platform_alipay_bill_lines(dataset_row):
        stats = auth_db.get_platform_alipay_bill_line_stats(
            company_id=company_id,
            data_source_id=source_id,
            dataset_id=dataset_id,
        )
        collection_records = auth_db.list_platform_alipay_bill_lines(
            company_id=company_id,
            data_source_id=source_id,
            dataset_id=dataset_id,
            resource_key=resource_key,
            limit=sample_limit,
            offset=0,
        )
```

- [ ] **Step 4: Route collection list to Alipay table**

In `_handle_data_source_list_collection_records()`, between the platform-order branch and the generic branch, add:

```python
    elif _dataset_uses_platform_alipay_bill_lines(dataset_row):
        records = auth_db.list_platform_alipay_bill_lines(
            company_id=company_id,
            data_source_id=source_id,
            dataset_id=dataset_id,
            resource_key=resource_key or None,
            biz_date=_safe_text(arguments.get("biz_date")) or None,
            filters={"source_row_key": _safe_text(arguments.get("item_key")) or None},
            limit=limit,
            offset=offset,
        )
        stats = auth_db.get_platform_alipay_bill_line_stats(
            company_id=company_id,
            data_source_id=source_id,
            dataset_id=dataset_id,
            biz_date=_safe_text(arguments.get("biz_date")) or None,
        )
```

- [ ] **Step 5: Route preview to Alipay table**

In `_handle_data_source_preview()`, between the platform-order return block and `_load_dataset_sample_rows_from_collection_records()`, add:

```python
    if _dataset_uses_platform_alipay_bill_lines(dataset_row):
        records = auth_db.list_platform_alipay_bill_lines(
            company_id=company_id,
            data_source_id=source_id,
            dataset_id=_safe_text((dataset_row or {}).get("id")) or None,
            resource_key=_safe_text((dataset_row or {}).get("resource_key")) or _resource_key_from_args(arguments),
            limit=max(1, min(limit, 100)),
            offset=0,
        )
        rows = [
            dict(item.get("payload") or item)
            for item in records
            if isinstance(item, dict)
        ]
        return {
            "success": True,
            "source_id": source_id,
            "count": len(rows),
            "rows": rows,
            "message": "已返回支付宝账单样例",
        }
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_order_collection.py::test_list_collection_records_reads_alipay_platform_bill_lines -q
```

Expected: PASS.

- [ ] **Step 7: Commit API read branches**

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_platform_order_collection.py
git commit -m "fix: read alipay bill samples from platform table"
```

---

### Task 6: Add Recon Loader for Alipay Bill Lines

**Files:**
- Modify: `finance-mcp/recon/mcp_server/dataset_loader.py`
- Modify: `finance-mcp/tests/test_alipay_dataset_loader_contract.py`
- Modify: `finance-mcp/tests/test_platform_order_dataset_loader.py`

- [ ] **Step 1: Remove the skip from the loader contract test**

Replace `finance-mcp/tests/test_alipay_dataset_loader_contract.py` with:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from recon.mcp_server import dataset_loader


def test_alipay_bill_lines_loader_contract() -> None:
    assert "platform_alipay_bill_lines" in dataset_loader._DATASET_LOADERS
    assert "alipay_bill_lines" in dataset_loader._DATASET_LOADERS
```

- [ ] **Step 2: Add an Alipay loader test**

Append to `finance-mcp/tests/test_platform_order_dataset_loader.py`:

```python
def test_load_platform_alipay_bill_lines_from_dataset_ref(monkeypatch):
    def fake_columns(table_name: str) -> set[str]:
        assert table_name == "platform_alipay_bill_lines"
        return {
            "company_id",
            "data_source_id",
            "dataset_id",
            "shop_connection_id",
            "bill_type",
            "bill_date",
            "source_row_key",
            "merchant_order_no",
            "amount",
            "payload",
            "updated_at",
        }

    def fake_query(*, source_key: str, query: dict):
        assert source_key == "source-alipay-001"
        assert query["dataset_id"] == "dataset-alipay-001"
        assert query["resource_key"] == "alipay_bill:trade:shop-alipay-001"
        assert query["biz_date"] == "2026-05-06"
        return [
            {
                "payload": {"source_row_key": "row-1", "merchant_order_no": "M001", "amount": "12.30"}
            }
        ]

    monkeypatch.setattr(dataset_loader, "_table_columns", fake_columns)
    monkeypatch.setattr(dataset_loader, "_load_platform_alipay_bill_line_rows", fake_query)

    df = dataset_loader.load_dataset_as_df(
        {
            "source_type": "platform_alipay_bill_lines",
            "source_key": "source-alipay-001",
            "query": {
                "dataset_id": "dataset-alipay-001",
                "resource_key": "alipay_bill:trade:shop-alipay-001",
                "biz_date": "2026-05-06",
            },
        },
        "支付宝交易账单",
    )

    assert list(df["merchant_order_no"]) == ["M001"]
    assert list(df["amount"]) == ["12.30"]
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_alipay_dataset_loader_contract.py finance-mcp/tests/test_platform_order_dataset_loader.py -q
```

Expected: FAIL because the Alipay loaders and helper do not exist.

- [ ] **Step 4: Add allowed query keys**

In `finance-mcp/recon/mcp_server/dataset_loader.py`, after `_PLATFORM_ORDER_LINES_QUERY_ALLOWED_KEYS`, add:

```python
_PLATFORM_ALIPAY_BILL_LINES_QUERY_ALLOWED_KEYS = {
    "dataset_id",
    "resource_key",
    "biz_date",
    "bill_type",
    "filters",
    "order_by",
    "limit",
}
```

- [ ] **Step 5: Add the row query helper**

In `finance-mcp/recon/mcp_server/dataset_loader.py`, after `_load_platform_order_line_rows()`, add:

```python
def _load_platform_alipay_bill_line_rows(
    *,
    source_key: str,
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    columns = _table_columns("platform_alipay_bill_lines")
    if not columns:
        raise DatasetLoadError("未找到 platform_alipay_bill_lines 表，请先完成支付宝账单采集能力部署。")

    data_source_col = _first_existing_column(columns, ["data_source_id", "source_id"])
    payload_col = _first_existing_column(
        columns,
        ["payload", "record_payload", "payload_json", "item_payload", "data"],
    )
    if not data_source_col or not payload_col:
        raise DatasetLoadError("platform_alipay_bill_lines 缺少 data_source_id/source_id 或 payload 字段。")

    where_parts = [f"{_safe_identifier(data_source_col)} = %s"]
    params: list[Any] = [source_key]

    dataset_id = str(query.get("dataset_id") or "").strip()
    if dataset_id:
        dataset_col = _first_existing_column(columns, ["dataset_id", "data_source_dataset_id"])
        if not dataset_col:
            raise DatasetLoadError("platform_alipay_bill_lines 缺少 dataset_id 字段，无法按数据集过滤。")
        where_parts.append(f"{_safe_identifier(dataset_col)} = %s")
        params.append(dataset_id)

    resource_key = str(query.get("resource_key") or "").strip()
    if resource_key:
        parts = resource_key.split(":")
        if len(parts) != 3 or parts[0] != "alipay_bill" or not parts[1] or not parts[2]:
            raise DatasetLoadError(
                "platform_alipay_bill_lines query.resource_key 必须为 alipay_bill:<bill_type>:<shop_connection_id>"
            )
        if "bill_type" not in columns or "shop_connection_id" not in columns:
            raise DatasetLoadError("platform_alipay_bill_lines 缺少 bill_type/shop_connection_id 字段，无法按 resource_key 过滤。")
        where_parts.append("bill_type = %s")
        params.append(parts[1])
        where_parts.append("shop_connection_id = %s")
        params.append(parts[2])

    bill_type = str(query.get("bill_type") or "").strip()
    if bill_type:
        if "bill_type" not in columns:
            raise DatasetLoadError("platform_alipay_bill_lines 缺少 bill_type 字段，无法按账单类型过滤。")
        where_parts.append("bill_type = %s")
        params.append(bill_type)

    biz_date = str(query.get("biz_date") or "").strip()
    if biz_date:
        bill_date_col = _first_existing_column(columns, ["bill_date", "biz_date", "business_date", "data_date"])
        if not bill_date_col:
            raise DatasetLoadError("platform_alipay_bill_lines 缺少 bill_date 字段，无法按业务日期过滤。")
        where_parts.append(f"{_safe_identifier(bill_date_col)} = %s")
        params.append(biz_date)

    filters = query.get("filters")
    if isinstance(filters, dict):
        for field, value in filters.items():
            field_name = str(field or "").strip()
            if not field_name or field_name not in columns or field_name == payload_col:
                continue
            if not _is_collection_filter_value(value):
                raise DatasetLoadError(f"platform_alipay_bill_lines query.filters 字段 '{field_name}' 仅支持标量值或标量数组")
            _append_db_filter_condition(
                where_parts=where_parts,
                params=params,
                field_name=field_name,
                value=value,
                coerce_filters_to_text=True,
            )

    order_by = query.get("order_by")
    if isinstance(order_by, str):
        order_by = [order_by]
    if order_by is None:
        order_by = []
    if not isinstance(order_by, list):
        raise DatasetLoadError("platform_alipay_bill_lines query.order_by 必须是字符串或数组")

    order_parts: list[str] = []
    for item in order_by:
        token = str(item or "").strip()
        if not token:
            continue
        parts = token.split()
        field_name = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        if field_name not in columns:
            raise DatasetLoadError(f"platform_alipay_bill_lines 表中不存在排序字段: {field_name}")
        if direction not in {"ASC", "DESC"}:
            raise DatasetLoadError(f"platform_alipay_bill_lines query.order_by 仅支持 ASC/DESC，当前: {direction}")
        order_parts.append(f"{_safe_identifier(field_name)} {direction}")
    if not order_parts:
        updated_col = _first_existing_column(columns, ["updated_at", "latest_seen_at", "created_at", "id"])
        if updated_col:
            order_parts.append(f"{_safe_identifier(updated_col)} DESC")

    limit = query.get("limit")
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            raise DatasetLoadError("platform_alipay_bill_lines query.limit 必须是正整数")
    limit_sql = f" LIMIT {limit}" if isinstance(limit, int) and limit > 0 else ""

    select_columns = [
        _safe_identifier(column)
        for column in sorted(
            columns
            & {
                "bill_type",
                "bill_date",
                "source_file_name",
                "source_row_number",
                "source_row_key",
                "alipay_trade_no",
                "merchant_order_no",
                "business_order_no",
                "amount",
                "income_amount",
                "expense_amount",
                "trade_time",
                payload_col,
            }
        )
    ]
    sql = f"SELECT {', '.join(select_columns)} FROM platform_alipay_bill_lines"
    sql += " WHERE " + " AND ".join(where_parts)
    if order_parts:
        sql += " ORDER BY " + ", ".join(order_parts)
    sql += limit_sql

    conn = None
    cur = None
    try:
        import psycopg2.extras

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall() or []]
    except Exception as exc:
        logger.error("[recon][dataset] source_key=%s platform_alipay_bill_lines 查询失败", source_key, exc_info=True)
        raise DatasetLoadError("platform_alipay_bill_lines 查询失败，请检查支付宝账单采集记录。") from exc
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                conn.close()
```

- [ ] **Step 6: Add the DataFrame loader**

In `finance-mcp/recon/mcp_server/dataset_loader.py`, after `_load_from_platform_order_lines()`, add:

```python
def _load_from_platform_alipay_bill_lines(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """Load dataset from published platform_alipay_bill_lines rows."""
    _, source_key, query = _require_dataset_protocol(dataset_ref, table_name)
    extra_keys = sorted(set(query.keys()) - _PLATFORM_ALIPAY_BILL_LINES_QUERY_ALLOWED_KEYS)
    if extra_keys:
        raise DatasetLoadError(
            f"source_key={source_key} query 含不支持字段。"
            f"仅支持: {', '.join(sorted(_PLATFORM_ALIPAY_BILL_LINES_QUERY_ALLOWED_KEYS))}"
        )

    columns = _table_columns("platform_alipay_bill_lines")
    if not columns:
        raise DatasetLoadError("未找到 platform_alipay_bill_lines 表，请先完成支付宝账单采集能力部署。")

    rows = _load_platform_alipay_bill_line_rows(source_key=source_key, query=query)
    payload_rows: list[dict[str, Any]] = []
    promoted_fields = {
        "bill_type",
        "bill_date",
        "source_file_name",
        "source_row_number",
        "source_row_key",
        "alipay_trade_no",
        "merchant_order_no",
        "business_order_no",
        "amount",
        "income_amount",
        "expense_amount",
        "trade_time",
    }
    for row in rows:
        payload = row.get("payload")
        merged = dict(payload) if isinstance(payload, dict) else {}
        for field in promoted_fields:
            if field in row and row.get(field) is not None:
                merged.setdefault(field, row.get(field))
        if merged:
            payload_rows.append(merged)

    if not payload_rows:
        raise DatasetLoadError(f"source_key={source_key} 暂无支付宝账单行。请先采集数据后再执行对账。")

    df = pd.DataFrame(payload_rows)

    filters = query.get("filters")
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise DatasetLoadError("platform_alipay_bill_lines query.filters 必须是对象")
    for field, value in filters.items():
        field_name = str(field or "").strip()
        if not field_name:
            continue
        if field_name not in df.columns:
            if field_name in columns:
                continue
            raise DatasetLoadError(f"platform_alipay_bill_lines 数据中不存在过滤字段: {field_name}")
        if not _is_collection_filter_value(value):
            raise DatasetLoadError(f"platform_alipay_bill_lines query.filters 字段 '{field_name}' 仅支持标量值或标量数组")
        df = _apply_collection_record_scalar_filter(df, field_name, value)

    if df.empty:
        raise DatasetLoadError(f"source_key={source_key} 支付宝账单行过滤后为空。请检查 query 条件。")

    return df.reset_index(drop=True)
```

- [ ] **Step 7: Register source types**

At the bottom of `finance-mcp/recon/mcp_server/dataset_loader.py`, change loader registration to:

```python
register_dataset_loader("collection_records", _load_from_collection_records)
register_dataset_loader("platform_order_lines", _load_from_platform_order_lines)
register_dataset_loader("platform_alipay_bill_lines", _load_from_platform_alipay_bill_lines)
register_dataset_loader("alipay_bill_lines", _load_from_platform_alipay_bill_lines)
```

- [ ] **Step 8: Run loader tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_alipay_dataset_loader_contract.py finance-mcp/tests/test_platform_order_dataset_loader.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit loader**

```bash
git add finance-mcp/recon/mcp_server/dataset_loader.py finance-mcp/tests/test_alipay_dataset_loader_contract.py finance-mcp/tests/test_platform_order_dataset_loader.py
git commit -m "feat: load alipay bill lines for recon"
```

---

### Task 7: Run Integrated Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
source .venv/bin/activate
pytest \
  finance-mcp/tests/test_platform_alipay_bill_lines.py \
  finance-mcp/tests/test_platform_connections_alipay.py \
  finance-mcp/tests/test_platform_order_collection.py \
  finance-mcp/tests/test_alipay_dataset_loader_contract.py \
  finance-mcp/tests/test_platform_order_dataset_loader.py \
  finance-mcp/tests/test_scheduler_collection_plans.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run a broader platform/auth slice**

Run:

```bash
source .venv/bin/activate
pytest \
  finance-mcp/tests/test_alipay_connector.py \
  finance-mcp/tests/test_platform_collection_driver_routing.py \
  finance-mcp/tests/test_platform_connections_taobao.py \
  finance-mcp/tests/test_platform_order_lines.py \
  -q
```

Expected: PASS.

- [ ] **Step 3: Check git status excludes unrelated recon output files**

Run:

```bash
git status --short
```

Expected: only the two existing untracked `finance-mcp/recon/output/...093117.xlsx` files remain untracked, or no unrelated changes. Do not add those output files.

- [ ] **Step 4: Restart services after code changes**

Run:

```bash
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, and finance-mcp restart successfully.

- [ ] **Step 5: Health check services**

Run:

```bash
curl -s http://127.0.0.1:3335/health
curl -s http://127.0.0.1:8100/health
curl -I http://127.0.0.1:5173
```

Expected: MCP and data-agent return healthy JSON; web returns HTTP 200/304.

---

## Self-Review

- Spec coverage:
  - Dedicated table: Task 1.
  - DB upsert/list/stats helpers: Task 2.
  - Dataset metadata storage/source/resource key: Task 3.
  - Alipay collection writes专表 and no longer writes `dataset_collection_records`: Task 4.
  - Data source detail/list/preview reads专表: Task 5.
  - Recon source types `platform_alipay_bill_lines` and `alipay_bill_lines`: Task 6.
  - No historical migration: no task migrates existing data.
- Placeholder scan:
  - No placeholder implementation instructions remain.
- Type consistency:
  - Storage marker is consistently `platform_alipay_bill_lines`.
  - Loader alias is consistently `alipay_bill_lines`.
  - Business date API argument remains `biz_date`; physical table column is `bill_date`.
  - `resource_key` remains `alipay_bill:<bill_type>:<shop_connection_id>`.

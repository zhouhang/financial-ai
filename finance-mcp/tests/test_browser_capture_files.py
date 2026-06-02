from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


class FakeCursor:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.sql.append(sql)


class FakeConn:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeConn":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self, *args, **kwargs) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        pass


class FakeConnManager:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor

    def __enter__(self) -> FakeConn:
        return FakeConn(self.cursor)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class _FakeConn:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def cursor(self, *args, **kwargs):
        return _FakeCursor()

    def commit(self):
        self._captured["committed"] = True


class _FakeConnManager:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def __enter__(self):
        return _FakeConn(self._captured)

    def __exit__(self, exc_type, exc, tb):
        return None


def test_insert_browser_capture_files_uses_execute_values(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute_values(cur, sql, values, template=None, page_size=1000, fetch=False):
        captured["sql"] = sql
        captured["values"] = list(values)
        return []

    monkeypatch.setattr(auth_db, "get_conn", lambda: _FakeConnManager(captured))
    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.insert_browser_capture_files(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        resource_key="qianniu-daily-bill-export@1.0.0",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-18",
        capture_files=[
            {
                "storage_path": "oss://finance-oss/browser-captures/shop-001/export.csv",
                "storage_bucket": "finance-oss",
                "storage_key": "browser-captures/shop-001/export.csv",
                "storage_uri": "oss://finance-oss/browser-captures/shop-001/export.csv",
                "content_type": "text/csv",
                "size_bytes": 123,
                "encoding": "utf-8",
                "checksum": "sha256:abc",
                "row_count": 10,
            }
        ],
    )

    assert result["inserted_count"] == 1
    assert "INSERT INTO browser_capture_files" in str(captured["sql"])
    assert captured["committed"] is True
    assert len(captured["values"]) == 1
    row = captured["values"][0]
    assert row[8] == "oss://finance-oss/browser-captures/shop-001/export.csv"
    assert row[12] == "oss"
    assert row[13] == "finance-oss"
    assert row[14] == "browser-captures/shop-001/export.csv"
    assert row[15] == "oss://finance-oss/browser-captures/shop-001/export.csv"
    assert row[16] == "text/csv"
    assert row[17] == 123


def test_insert_browser_capture_files_parses_minimal_oss_storage_path(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute_values(cur, sql, values, template=None, page_size=1000, fetch=False):
        captured["sql"] = sql
        captured["values"] = list(values)
        return []

    monkeypatch.setattr(auth_db, "get_conn", lambda: _FakeConnManager(captured))
    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.insert_browser_capture_files(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        resource_key="qianniu-daily-bill-export@1.0.0",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-18",
        capture_files=[
            {
                "storage_path": "oss://finance-oss/browser-captures/shop-001/export.csv",
                "encoding": "utf-8",
                "checksum": "sha256:abc",
                "row_count": 10,
            }
        ],
    )

    assert result["inserted_count"] == 1
    row = captured["values"][0]
    assert row[8] == "oss://finance-oss/browser-captures/shop-001/export.csv"
    assert row[12] == "oss"
    assert row[13] == "finance-oss"
    assert row[14] == "browser-captures/shop-001/export.csv"
    assert row[15] == "oss://finance-oss/browser-captures/shop-001/export.csv"


def test_insert_browser_capture_files_synthesizes_oss_uri_from_bucket_and_key(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute_values(cur, sql, values, template=None, page_size=1000, fetch=False):
        captured["values"] = list(values)
        return []

    monkeypatch.setattr(auth_db, "get_conn", lambda: _FakeConnManager(captured))
    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.insert_browser_capture_files(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        resource_key="qianniu-daily-bill-export@1.0.0",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-18",
        capture_files=[
            {
                "storage_path": "browser-captures/shop-001/export.csv",
                "storage_provider": "oss",
                "storage_bucket": "finance-oss",
                "storage_key": "browser-captures/shop-001/export.csv",
                "encoding": "utf-8",
                "checksum": "sha256:abc",
                "row_count": 10,
            }
        ],
    )

    assert result["inserted_count"] == 1
    row = captured["values"][0]
    assert row[12] == "oss"
    assert row[13] == "finance-oss"
    assert row[14] == "browser-captures/shop-001/export.csv"
    assert row[15] == "oss://finance-oss/browser-captures/shop-001/export.csv"


def test_insert_browser_capture_files_keeps_legacy_local_defaults(monkeypatch) -> None:
    captured: dict = {}

    def fake_execute_values(cur, sql, values, template=None, page_size=1000, fetch=False):
        captured["values"] = list(values)
        return []

    monkeypatch.setattr(auth_db, "get_conn", lambda: _FakeConnManager(captured))
    monkeypatch.setattr(auth_db.psycopg2.extras, "execute_values", fake_execute_values)

    result = auth_db.insert_browser_capture_files(
        company_id="00000000-0000-0000-0000-000000000001",
        data_source_id="00000000-0000-0000-0000-000000000002",
        dataset_id="00000000-0000-0000-0000-000000000003",
        sync_job_id="00000000-0000-0000-0000-000000000004",
        resource_key="qianniu-daily-bill-export@1.0.0",
        shop_id="shop-001",
        playbook_id="qianniu-daily-bill-export",
        biz_date="2026-05-18",
        capture_files=[
            {
                "storage_path": "/tmp/export.csv",
                "encoding": "utf-8",
                "checksum": "sha256:abc",
                "row_count": 10,
            }
        ],
    )

    assert result["inserted_count"] == 1
    row = captured["values"][0]
    assert row[8] == "/tmp/export.csv"
    assert row[12] == "local"
    assert row[13] == ""
    assert row[14] == ""
    assert row[15] == ""


def test_insert_browser_capture_files_empty_returns_zero(monkeypatch) -> None:
    monkeypatch.setattr(auth_db, "get_conn", lambda: _FakeConnManager({}))

    result = auth_db.insert_browser_capture_files(
        company_id="c",
        data_source_id="s",
        dataset_id="d",
        sync_job_id="j",
        resource_key="rk",
        shop_id="shop",
        playbook_id="pb",
        biz_date="2026-05-18",
        capture_files=[],
    )

    assert result == {"inserted_count": 0}


def test_insert_browser_capture_files_upserts_on_conflict(monkeypatch) -> None:
    cursor = FakeCursor()
    monkeypatch.setattr(auth_db, "get_conn", lambda: FakeConnManager(cursor))
    # execute_values writes via cur.execute under the hood for our FakeCursor; capture the SQL.
    monkeypatch.setattr(
        auth_db.psycopg2.extras,
        "execute_values",
        lambda cur, sql, rows, template=None, **kw: cur.execute(sql, tuple(rows)),
    )

    auth_db.insert_browser_capture_files(
        company_id="c1", data_source_id="d1", dataset_id="ds1", sync_job_id="j1",
        resource_key="rk", shop_id="s1", playbook_id="p1", biz_date="2026-05-31",
        capture_files=[{"storage_path": "/tmp/a.csv", "checksum": "x", "row_count": 1}],
    )

    sql = "\n".join(cursor.sql)
    assert "ON CONFLICT (sync_job_id, storage_path)" in sql
    assert "DO UPDATE" in sql

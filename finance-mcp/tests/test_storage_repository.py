from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from storage.refs import StorageObjectRef
from storage import repository


class _FakeCursor:
    def __init__(self, captured: dict, row: dict | None = None) -> None:
        self._captured = captured
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, sql, params=None):
        self._captured["sql"] = sql
        self._captured["params"] = params

    def fetchone(self):
        return self._row


class _FakeConn:
    def __init__(self, captured: dict, row: dict | None = None) -> None:
        self._captured = captured
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def cursor(self, *args, **kwargs):
        self._captured["cursor_args"] = args
        self._captured["cursor_kwargs"] = kwargs
        return _FakeCursor(self._captured, self._row)

    def commit(self):
        self._captured["committed"] = True


class _FakeConnManager:
    def __init__(self, captured: dict, row: dict | None = None) -> None:
        self._captured = captured
        self._row = row

    def __enter__(self):
        return _FakeConn(self._captured, self._row)

    def __exit__(self, exc_type, exc, tb):
        return None


def test_save_storage_object_metadata_upserts_commits_and_returns_row(monkeypatch) -> None:
    captured: dict = {}
    returned_row = {
        "logical_path": "browser-captures/shop-001/export.csv",
        "storage_provider": "oss",
        "storage_bucket": "finance-oss",
        "storage_key": "browser-captures/shop-001/export.csv",
    }
    monkeypatch.setattr(
        repository.auth_db,
        "get_conn",
        lambda: _FakeConnManager(captured, returned_row),
    )

    result = repository.save_storage_object_metadata(
        owner_user_id="00000000-0000-0000-0000-000000000001",
        company_id="00000000-0000-0000-0000-000000000002",
        module="browser_capture",
        logical_path="browser-captures/shop-001/export.csv",
        ref=StorageObjectRef(
            provider="oss",
            bucket="finance-oss",
            key="browser-captures/shop-001/export.csv",
            original_filename="export.csv",
            content_type="text/csv",
            size_bytes=123,
            checksum="sha256:abc",
        ),
        metadata={"来源": "千牛", "rows": 10},
    )

    assert result == returned_row
    assert "INSERT INTO storage_objects" in str(captured["sql"])
    assert "ON CONFLICT (logical_path) DO UPDATE" in str(captured["sql"])
    assert "RETURNING *" in str(captured["sql"])
    assert captured["params"]["logical_path"] == "browser-captures/shop-001/export.csv"
    assert captured["params"]["storage_provider"] == "oss"
    assert captured["params"]["storage_bucket"] == "finance-oss"
    assert captured["params"]["storage_key"] == "browser-captures/shop-001/export.csv"
    assert captured["params"]["storage_uri"] == "oss://finance-oss/browser-captures/shop-001/export.csv"
    assert captured["params"]["metadata_json"] == '{"来源": "千牛", "rows": 10}'
    assert captured["committed"] is True
    assert captured["cursor_kwargs"]["cursor_factory"] is repository.psycopg2.extras.RealDictCursor


def test_save_storage_object_metadata_returns_params_fallback_when_no_row(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(repository.auth_db, "get_conn", lambda: _FakeConnManager(captured))

    result = repository.save_storage_object_metadata(
        owner_user_id=" ",
        company_id="",
        module="exports",
        logical_path="local/export.csv",
        ref=StorageObjectRef(provider="local", local_path="/tmp/export.csv"),
    )

    assert result["owner_user_id"] is None
    assert result["company_id"] is None
    assert result["logical_path"] == "local/export.csv"
    assert result["storage_provider"] == "local"
    assert result["local_path"] == "/tmp/export.csv"
    assert result["metadata_json"] == "{}"
    assert captured["committed"] is True


def test_get_storage_object_by_logical_path_selects_by_logical_path(monkeypatch) -> None:
    captured: dict = {}
    returned_row = {
        "logical_path": "browser-captures/shop-001/export.csv",
        "storage_provider": "oss",
    }
    monkeypatch.setattr(
        repository.auth_db,
        "get_conn",
        lambda: _FakeConnManager(captured, returned_row),
    )

    result = repository.get_storage_object_by_logical_path(
        "browser-captures/shop-001/export.csv"
    )

    assert result == returned_row
    assert "SELECT *" in str(captured["sql"])
    assert "FROM storage_objects" in str(captured["sql"])
    assert "WHERE logical_path = %(logical_path)s" in str(captured["sql"])
    assert captured["params"] == {"logical_path": "browser-captures/shop-001/export.csv"}
    assert captured["cursor_kwargs"]["cursor_factory"] is repository.psycopg2.extras.RealDictCursor

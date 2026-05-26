from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db


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
                "storage_path": "/tmp/export.csv",
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

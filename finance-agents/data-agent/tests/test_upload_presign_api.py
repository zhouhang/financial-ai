from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _mod in (
    "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio",
    "psycopg",
    "psycopg.conninfo",
    "psycopg.sql",
):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import server


def test_upload_presign_calls_mcp_with_bearer_token(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_call(tool_name: str, args: dict):
        calls.append({"tool_name": tool_name, "args": args})
        return {
            "success": True,
            "storage_key": "uploads/a.xlsx",
            "upload_url": "https://oss.example/upload",
        }

    monkeypatch.setattr(server, "mcp_call_tool", fake_call)

    response = TestClient(server.app).post(
        "/upload/presign",
        headers={"Authorization": "bearer token-1"},
        json={
            "filename": "orders.xlsx",
            "size": 1234,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "storage_key": "uploads/a.xlsx",
        "upload_url": "https://oss.example/upload",
    }
    assert calls == [
        {
            "tool_name": "file_upload_presign",
            "args": {
                "auth_token": "token-1",
                "filename": "orders.xlsx",
                "size": 1234,
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
        }
    ]


def test_upload_confirm_calls_mcp_with_upload_metadata(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_call(tool_name: str, args: dict):
        calls.append({"tool_name": tool_name, "args": args})
        return {
            "success": True,
            "file_id": "file-1",
            "file_path": "oss://bucket/uploads/a.csv",
        }

    monkeypatch.setattr(server, "mcp_call_tool", fake_call)

    response = TestClient(server.app).post(
        "/upload/confirm",
        headers={"Authorization": "Bearer token-2"},
        json={
            "storage_key": "uploads/a.csv",
            "filename": "orders.csv",
            "size": 5678,
            "content_type": "text/csv",
            "checksum": "sha256:abc123",
            "thread_id": "thread-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "file_id": "file-1",
        "file_path": "oss://bucket/uploads/a.csv",
    }
    assert calls == [
        {
            "tool_name": "file_upload_confirm",
            "args": {
                "auth_token": "token-2",
                "storage_key": "uploads/a.csv",
                "filename": "orders.csv",
                "size": 5678,
                "content_type": "text/csv",
                "checksum": "sha256:abc123",
                "thread_id": "thread-1",
            },
        }
    ]


def test_upload_presign_requires_bearer_token(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_call(tool_name: str, args: dict):
        calls.append({"tool_name": tool_name, "args": args})
        return {"success": True}

    monkeypatch.setattr(server, "mcp_call_tool", fake_call)

    response = TestClient(server.app).post(
        "/upload/presign",
        json={
            "filename": "orders.xlsx",
            "size": 1234,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "缺少 auth_token，请先登录"}
    assert calls == []

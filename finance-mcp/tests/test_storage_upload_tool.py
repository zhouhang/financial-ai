from __future__ import annotations

import json
import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import pytest


@pytest.fixture
def upload_user() -> dict[str, str]:
    return {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "username": "alice",
        "role": "member",
        "company_id": "00000000-0000-0000-0000-000000000002",
    }


@pytest.mark.asyncio
async def test_presign_rejects_bad_extension_with_chinese_error(monkeypatch, upload_user) -> None:
    import tools.storage_upload_tool as storage_upload_tool

    monkeypatch.setattr(storage_upload_tool, "get_user_from_token", lambda token: upload_user)

    result = await storage_upload_tool.create_upload_presign(
        {
            "auth_token": "token",
            "filename": "report.txt",
            "size_bytes": 12,
        }
    )

    assert result["success"] is False
    assert "不支持的文件类型" in result["error"]


@pytest.mark.asyncio
async def test_local_backend_presign_returns_proxy_upload_fallback(monkeypatch, upload_user) -> None:
    import tools.storage_upload_tool as storage_upload_tool

    monkeypatch.setattr(storage_upload_tool, "get_user_from_token", lambda token: upload_user)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("OSS_UPLOAD_MAX_SIZE", "1024")

    result = await storage_upload_tool.create_upload_presign(
        {
            "auth_token": "token",
            "filename": "report.csv",
            "size_bytes": 12,
            "content_type": "text/csv",
        }
    )

    assert result["success"] is True
    assert result["direct_upload"] is False
    assert result["storage_provider"] == "local"


@pytest.mark.asyncio
async def test_oss_confirm_saves_metadata_and_returns_logical_path(monkeypatch, upload_user) -> None:
    import tools.storage_upload_tool as storage_upload_tool
    from storage.refs import StorageObjectRef

    saved: dict = {}
    storage_key = (
        "financial-ai/test/uploads/"
        "00000000-0000-0000-0000-000000000002/2026/06/02/abc-report.csv"
    )

    monkeypatch.setattr(storage_upload_tool, "get_user_from_token", lambda token: upload_user)
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "finance-bucket")
    monkeypatch.setenv("OSS_ENDPOINT", "https://oss.example.com")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "sk")
    monkeypatch.setenv("OSS_PREFIX", "financial-ai/test")
    monkeypatch.setattr(storage_upload_tool, "_oss_object_exists", lambda ref, settings: True)

    def fake_save_storage_object_metadata(**kwargs):
        saved.update(kwargs)
        return {"logical_path": kwargs["logical_path"]}

    monkeypatch.setattr(
        storage_upload_tool.repository,
        "save_storage_object_metadata",
        fake_save_storage_object_metadata,
    )

    result = await storage_upload_tool.confirm_upload(
        {
            "auth_token": "token",
            "storage_key": storage_key,
            "filename": "report.csv",
            "size_bytes": 12,
            "content_type": "text/csv",
        }
    )

    assert result["success"] is True
    assert result["logical_path"].startswith("/uploads/oss/")
    assert result["logical_path"].endswith("/abc-report.csv")
    assert saved["module"] == "upload"
    assert saved["logical_path"] == result["logical_path"]
    assert saved["owner_user_id"] == upload_user["user_id"]
    assert saved["company_id"] == upload_user["company_id"]
    assert isinstance(saved["ref"], StorageObjectRef)
    assert saved["ref"].provider == "oss"
    assert saved["ref"].bucket == "finance-bucket"
    assert saved["ref"].key == storage_key


@pytest.mark.asyncio
async def test_handle_tool_call_routes_file_upload_presign(monkeypatch) -> None:
    import tools.storage_upload_tool as storage_upload_tool

    called: dict = {}

    async def fake_create_upload_presign(arguments):
        called["arguments"] = arguments
        return {"success": True}

    monkeypatch.setattr(
        storage_upload_tool,
        "create_upload_presign",
        fake_create_upload_presign,
    )

    result = await storage_upload_tool.handle_tool_call("file_upload_presign", {})

    assert result == {"success": True}
    assert called["arguments"] == {}


@pytest.mark.asyncio
async def test_unified_call_tool_routes_file_upload_presign(monkeypatch) -> None:
    import unified_mcp_server

    called: dict = {}

    async def fake_handle_storage_upload_tool_call(name, arguments):
        called["name"] = name
        called["arguments"] = arguments
        return {"success": True, "routed": name}

    monkeypatch.setattr(
        unified_mcp_server,
        "handle_storage_upload_tool_call",
        fake_handle_storage_upload_tool_call,
        raising=False,
    )

    [content] = await unified_mcp_server.call_tool("file_upload_presign", {})
    result = json.loads(content.text)

    assert result == {"success": True, "routed": "file_upload_presign"}
    assert called == {"name": "file_upload_presign", "arguments": {}}

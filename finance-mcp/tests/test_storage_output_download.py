from __future__ import annotations

import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))


def test_persist_generated_output_uploads_oss_and_saves_metadata(monkeypatch, tmp_path: Path) -> None:
    from storage import output_manager
    from storage.refs import StorageObjectRef

    source = tmp_path / "recon-结果.xlsx"
    source.write_bytes(b"xlsx")
    captured: dict = {}

    class FakeClient:
        def put_file(
            self,
            source_path,
            *,
            key: str,
            original_filename: str,
            content_type: str = "",
            checksum: str = "",
        ):
            captured["source_path"] = source_path
            captured["key"] = key
            captured["original_filename"] = original_filename
            captured["content_type"] = content_type
            return StorageObjectRef(
                provider="oss",
                bucket="finance-bucket",
                key=key,
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=source.stat().st_size,
            )

    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_PREFIX", "financial-ai/test")
    monkeypatch.setattr(output_manager, "_today_parts", lambda: ("2026", "06", "02"))
    def fake_storage_from_env(*, local_root):
        captured["local_root"] = local_root
        return FakeClient()

    monkeypatch.setattr(output_manager, "storage_from_env", fake_storage_from_env)
    monkeypatch.setattr(
        output_manager.repository,
        "save_storage_object_metadata",
        lambda **kwargs: captured.setdefault("saved", kwargs),
    )

    logical_path = output_manager.persist_generated_output(
        source,
        module="recon",
        owner_user_id="user-1",
        company_id="company-1",
        rule_code="recon-rule",
        run_id="run-7",
    )

    assert logical_path == "/output/recon/recon-结果.xlsx"
    assert captured["source_path"] == source
    assert captured["key"] == (
        "financial-ai/test/recon-output/company-1/2026/06/02/run-7/recon-结果.xlsx"
    )
    assert captured["original_filename"] == "recon-结果.xlsx"
    assert captured["content_type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert captured["saved"]["owner_user_id"] == "user-1"
    assert captured["saved"]["company_id"] == "company-1"
    assert captured["saved"]["module"] == "recon"
    assert captured["saved"]["logical_path"] == logical_path
    assert captured["saved"]["metadata"] == {"rule_code": "recon-rule", "run_id": "run-7"}
    assert captured["saved"]["ref"].provider == "oss"


def test_persist_generated_output_local_backend_returns_logical_path_without_save(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from storage import output_manager

    source = tmp_path / "整理.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setattr(
        output_manager,
        "storage_from_env",
        lambda *, local_root: (_ for _ in ()).throw(AssertionError("should not upload")),
    )
    monkeypatch.setattr(
        output_manager.repository,
        "save_storage_object_metadata",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not save")),
    )

    logical_path = output_manager.persist_generated_output(
        source,
        module="proc",
        owner_user_id="user-1",
        company_id="company-1",
        rule_code="rule-a",
    )

    assert logical_path == "/output/proc/rule-a/整理.csv"


def test_build_output_download_url_encodes_each_path_segment() -> None:
    from storage.output_manager import build_output_download_url

    url = build_output_download_url(
        "https://api.example.com/",
        "/output/proc/rule #1/结果 100%.xlsx",
        "token+/=",
    )

    assert url == (
        "https://api.example.com/output/proc/"
        "rule%20%231/%E7%BB%93%E6%9E%9C%20100%25.xlsx"
        "?auth_token=token%2B%2F%3D"
    )


def test_persist_generated_output_safely_falls_back_on_storage_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from storage import output_manager

    source = tmp_path / "result.xlsx"
    source.write_bytes(b"xlsx")
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setattr(
        output_manager,
        "storage_from_env",
        lambda *, local_root: (_ for _ in ()).throw(RuntimeError("oss down")),
    )

    assert output_manager.persist_generated_output_safely(
        source,
        module="recon",
        owner_user_id="user-1",
        company_id="company-1",
        rule_code="rule-a",
    ) == ""


class _FakeRequest:
    def __init__(
        self,
        *,
        module: str = "recon",
        file_path: str = "report.xlsx",
        auth_token: str = "token",
    ) -> None:
        self.path_params = {"module": module, "path": file_path}
        self.query_params = {"auth_token": auth_token}
        self.headers = {}


@pytest.mark.asyncio
async def test_storage_backed_download_returns_bytes_without_local_file(monkeypatch, tmp_path: Path):
    import unified_mcp_server

    class FakeClient:
        def exists(self, ref):
            return True

        def iter_bytes(self, ref):
            assert ref.provider == "oss"
            assert ref.key == "outputs/recon/report.xlsx"
            yield b"oss-"
            yield b"bytes"

    monkeypatch.setattr(unified_mcp_server, "_MODULE_OUTPUT_DIRS", {"recon": tmp_path})
    monkeypatch.setattr(unified_mcp_server, "_get_module_output_dir", lambda module: tmp_path)
    monkeypatch.setattr(
        unified_mcp_server,
        "get_user_from_token",
        lambda token: {"user_id": "owner-1", "role": "member"},
    )
    requested_paths: list[str] = []

    def fake_get_storage_object_by_logical_path(logical_path: str):
        requested_paths.append(logical_path)
        if logical_path != "/output/recon/report.xlsx":
            return None
        return {
            "owner_user_id": "owner-1",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "outputs/recon/report.xlsx",
            "original_filename": "报告.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }

    monkeypatch.setattr(
        unified_mcp_server.storage_repository,
        "get_storage_object_by_logical_path",
        fake_get_storage_object_by_logical_path,
    )
    monkeypatch.setattr(
        unified_mcp_server,
        "storage_from_env",
        lambda *, local_root: FakeClient(),
    )

    response = await unified_mcp_server.download_output_file(_FakeRequest())
    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.status_code == 200
    assert body == b"oss-bytes"
    assert response.media_type == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "filename*=UTF-8''%E6%8A%A5%E5%91%8A.xlsx" in response.headers[
        "content-disposition"
    ]
    assert not (tmp_path / "report.xlsx").exists()
    assert requested_paths == ["/output/recon/report.xlsx"]


@pytest.mark.asyncio
async def test_storage_backed_download_rejects_wrong_user(monkeypatch, tmp_path: Path):
    import unified_mcp_server

    monkeypatch.setattr(unified_mcp_server, "_MODULE_OUTPUT_DIRS", {"recon": tmp_path})
    monkeypatch.setattr(unified_mcp_server, "_get_module_output_dir", lambda module: tmp_path)
    monkeypatch.setattr(
        unified_mcp_server,
        "get_user_from_token",
        lambda token: {"user_id": "other-user", "role": "member"},
    )
    monkeypatch.setattr(
        unified_mcp_server.storage_repository,
        "get_storage_object_by_logical_path",
        lambda logical_path: {
            "owner_user_id": "owner-1",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "outputs/recon/report.xlsx",
            "original_filename": "report.xlsx",
            "content_type": "application/octet-stream",
        },
    )

    response = await unified_mcp_server.download_output_file(_FakeRequest())

    assert response.status_code == 403
    assert response.body


@pytest.mark.asyncio
async def test_storage_backed_download_returns_not_found_for_missing_object(monkeypatch, tmp_path: Path):
    import unified_mcp_server

    class FakeClient:
        def exists(self, ref):
            return False

    monkeypatch.setattr(unified_mcp_server, "_MODULE_OUTPUT_DIRS", {"recon": tmp_path})
    monkeypatch.setattr(unified_mcp_server, "_get_module_output_dir", lambda module: tmp_path)
    monkeypatch.setattr(
        unified_mcp_server,
        "get_user_from_token",
        lambda token: {"user_id": "owner-1", "role": "member"},
    )
    monkeypatch.setattr(
        unified_mcp_server.storage_repository,
        "get_storage_object_by_logical_path",
        lambda logical_path: {
            "owner_user_id": "owner-1",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "outputs/recon/missing.xlsx",
            "original_filename": "missing.xlsx",
            "content_type": "application/octet-stream",
        },
    )
    monkeypatch.setattr(unified_mcp_server, "storage_from_env", lambda *, local_root: FakeClient())

    response = await unified_mcp_server.download_output_file(_FakeRequest())

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_storage_backed_download_maps_storage_errors(monkeypatch, tmp_path: Path):
    import unified_mcp_server

    class FakeClient:
        def exists(self, ref):
            raise RuntimeError("oss unavailable")

    monkeypatch.setattr(unified_mcp_server, "_MODULE_OUTPUT_DIRS", {"recon": tmp_path})
    monkeypatch.setattr(unified_mcp_server, "_get_module_output_dir", lambda module: tmp_path)
    monkeypatch.setattr(
        unified_mcp_server,
        "get_user_from_token",
        lambda token: {"user_id": "owner-1", "role": "member"},
    )
    monkeypatch.setattr(
        unified_mcp_server.storage_repository,
        "get_storage_object_by_logical_path",
        lambda logical_path: {
            "owner_user_id": "owner-1",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "outputs/recon/report.xlsx",
            "original_filename": "report.xlsx",
            "content_type": "application/octet-stream",
        },
    )
    monkeypatch.setattr(unified_mcp_server, "storage_from_env", lambda *, local_root: FakeClient())

    response = await unified_mcp_server.download_output_file(_FakeRequest())

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_storage_backed_download_allows_admin(monkeypatch, tmp_path: Path):
    import unified_mcp_server

    class FakeClient:
        def exists(self, ref):
            return True

        def iter_bytes(self, ref):
            yield b"admin-bytes"

    monkeypatch.setattr(unified_mcp_server, "_MODULE_OUTPUT_DIRS", {"recon": tmp_path})
    monkeypatch.setattr(unified_mcp_server, "_get_module_output_dir", lambda module: tmp_path)
    monkeypatch.setattr(
        unified_mcp_server,
        "get_user_from_token",
        lambda token: {"user_id": "admin-user", "role": "admin"},
    )
    monkeypatch.setattr(
        unified_mcp_server.storage_repository,
        "get_storage_object_by_logical_path",
        lambda logical_path: {
            "owner_user_id": "owner-1",
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "outputs/recon/report.xlsx",
            "original_filename": "report.xlsx",
            "content_type": "application/octet-stream",
        },
    )
    monkeypatch.setattr(unified_mcp_server, "storage_from_env", lambda *, local_root: FakeClient())

    response = await unified_mcp_server.download_output_file(_FakeRequest())
    body = b"".join([chunk async for chunk in response.body_iterator])

    assert response.status_code == 200
    assert body == b"admin-bytes"

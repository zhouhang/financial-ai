from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import pytest

from storage.client import LocalStorageClient, OssStorageClient, storage_from_env
from storage.config import StorageSettings
from storage.refs import StorageObjectRef
from storage.tempfiles import materialize_to_temp


def test_local_put_and_download_to_temp(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")
    root = tmp_path / "storage"
    client = LocalStorageClient(root=root)

    ref = client.put_file(source, key="uploads/c1/source.csv", original_filename="source.csv")

    assert ref.provider == "local"
    assert ref.local_path.endswith("uploads/c1/source.csv")
    assert (root / "uploads/c1/source.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    with materialize_to_temp(client, ref) as path:
        assert path.read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_local_rejects_path_escape(tmp_path: Path) -> None:
    client = LocalStorageClient(root=tmp_path)

    with pytest.raises(ValueError, match="storage key"):
        client.put_bytes(b"x", key="../escape.txt", original_filename="escape.txt")


def test_local_rejects_ref_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    client = LocalStorageClient(root=root)
    ref = StorageObjectRef(provider="local", local_path=str(outside))

    with pytest.raises(ValueError, match="local storage path"):
        client.read_bytes(ref)
    with pytest.raises(ValueError, match="local storage path"):
        client.exists(ref)
    with pytest.raises(ValueError, match="local storage path"):
        with materialize_to_temp(client, ref):
            pass


def test_storage_from_env_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    client = storage_from_env(local_root=tmp_path)

    assert isinstance(client, LocalStorageClient)


def test_storage_from_env_rejects_unknown_backend(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "s3")

    with pytest.raises(RuntimeError, match="Unsupported storage backend"):
        storage_from_env(local_root=tmp_path)


def test_oss_client_requires_complete_config(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "")
    settings = StorageSettings.from_env()

    with pytest.raises(RuntimeError, match="OSS 配置不完整"):
        OssStorageClient(settings)


class _FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.headers: dict[str, dict[str, str]] = {}
        self.signed: list[tuple[str, str, int]] = []

    def put_object_from_file(self, key: str, filename: str, headers=None):
        self.objects[key] = Path(filename).read_bytes()
        self.headers[key] = headers or {}
        return type("Result", (), {"status": 200, "request_id": "req-1"})()

    def put_object(self, key: str, data: bytes, headers=None):
        self.objects[key] = data
        self.headers[key] = headers or {}
        return type("Result", (), {"status": 200, "request_id": "req-2"})()

    def get_object(self, key: str):
        data = self.objects[key]
        return type("Body", (), {"read": lambda self_: data})()

    def object_exists(self, key: str):
        return key in self.objects

    def sign_url(self, method: str, key: str, expires: int, headers=None):
        self.signed.append((method, key, expires))
        return f"https://oss.test/{key}?signature=yes"


def test_oss_client_with_fake_bucket(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "bucket-a")
    monkeypatch.setenv("OSS_ENDPOINT", "https://oss-cn.example.aliyuncs.com")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "sk")
    settings = StorageSettings.from_env()
    fake_bucket = _FakeBucket()
    client = OssStorageClient(settings, bucket=fake_bucket)

    ref = client.put_bytes(b"abc", key="uploads/c1/a.txt", original_filename="a.txt")
    assert ref == StorageObjectRef(
        provider="oss",
        bucket="bucket-a",
        key="uploads/c1/a.txt",
        original_filename="a.txt",
        content_type="text/plain",
        size_bytes=3,
    )
    assert fake_bucket.headers["uploads/c1/a.txt"] == {"Content-Type": "text/plain"}
    assert client.exists(ref)
    assert client.read_bytes(ref) == b"abc"
    assert client.create_presigned_upload(key="uploads/c1/b.txt", content_type="text/plain")[
        "url"
    ].startswith("https://oss.test/uploads/c1/b.txt")


def test_oss_put_file_uses_resolved_content_type(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "bucket-a")
    monkeypatch.setenv("OSS_ENDPOINT", "https://oss-cn.example.aliyuncs.com")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "sk")
    settings = StorageSettings.from_env()
    fake_bucket = _FakeBucket()
    client = OssStorageClient(settings, bucket=fake_bucket)
    source = tmp_path / "report.unknownext"
    source.write_bytes(b"abc")

    ref = client.put_file(
        source,
        key="uploads/c1/report.bin",
        original_filename="report.unknownext",
        content_type="application/custom",
    )

    assert ref.content_type == "application/custom"
    assert fake_bucket.headers["uploads/c1/report.bin"] == {
        "Content-Type": "application/custom"
    }

# OSS Storage and Production Log Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move new uploads, generated outputs, and browser capture files to Alibaba Cloud OSS in production while preserving local development and legacy local file compatibility.

**Architecture:** Add a focused storage layer in `finance-mcp` with local and OSS backends, then route uploads, input reads, generated outputs, downloads, and browser capture audit files through that layer. Store new object ownership metadata in PostgreSQL so backend-proxied downloads can authorize OSS objects the same way current sidecar metadata authorizes local output files.

**Tech Stack:** Python 3.12, FastAPI/Starlette, MCP SSE, PostgreSQL/psycopg2, pandas/openpyxl, React/TypeScript, Alibaba Cloud `oss2`, Docker Compose, logrotate.

---

## File Structure

- Create `finance-mcp/storage/__init__.py`: package exports for storage types and factory.
- Create `finance-mcp/storage/config.py`: reads `STORAGE_BACKEND`, OSS endpoint/bucket/prefix, upload limits, and presign expiry.
- Create `finance-mcp/storage/refs.py`: `StorageObjectRef` dataclass plus parsing/serialization for local paths, OSS URIs, and metadata dicts.
- Create `finance-mcp/storage/client.py`: `StorageClient` protocol, `LocalStorageClient`, and `OssStorageClient`.
- Create `finance-mcp/storage/repository.py`: DB helpers for persisted object metadata and browser capture columns.
- Create `finance-mcp/storage/tempfiles.py`: context manager to materialize refs as safe temp files.
- Create `finance-mcp/tools/storage_upload_tool.py`: MCP tools for presign and confirm upload.
- Modify `finance-mcp/tools/file_upload_tool.py`: keep old proxy upload API, but route new stored files through storage metadata.
- Modify `finance-mcp/unified_mcp_server.py`: register new upload tools and stream OSS-backed output downloads.
- Modify `finance-mcp/security_utils.py`: preserve local path resolvers and add metadata-aware output helpers.
- Modify `finance-mcp/recon/mcp_server/recon_tool.py`: materialize OSS-backed inputs and upload generated output.
- Modify `finance-mcp/proc/mcp_server/proc_rule.py`: materialize OSS-backed inputs and upload generated/merged outputs.
- Modify `finance-mcp/proc/mcp_server/merge_rule.py`: use storage temp materialization for merge inputs.
- Modify `finance-mcp/proc/mcp_server/steps_runtime.py`: resolve OSS-backed read paths where runtime steps read input files.
- Modify `finance-mcp/auth/db.py`: insert and query browser capture file storage fields.
- Add migration `finance-mcp/auth/migrations/037_storage_objects_and_browser_capture_oss.sql`.
- Modify `finance-mcp/auth/migrations/README.md`: list migration 037.
- Modify `finance-mcp/requirements.txt`: add `oss2`.
- Modify `finance-agents/data-agent/server.py`: expose upload presign/confirm HTTP endpoints and use them from frontend; retain old `/upload`.
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`: upload downloaded capture files to OSS before reporting success when configured.
- Create `finance-agents/browser-agent/finance_browser_agent/storage_client.py`: small OSS uploader for the collection machine.
- Modify `finance-web/src/components/ChatArea.tsx`: direct upload to OSS when presign is available, fallback to old `/api/upload`.
- Modify `env.prod.example`, `.env.example`, and `deploy.env.example`: document storage/log settings.
- Modify `docker-compose.prod.yml`: keep JSON log limits and add OSS env checklist if needed.
- Create `deploy/logrotate/financial-ai`: local logrotate config.
- Modify `docs/deployment/ghcr-ecs.md`: add OSS and logrotate production setup.
- Add focused tests under `finance-mcp/tests/`, `finance-agents/data-agent/tests/`, and `finance-web/tests/components/`.

## Task 1: Storage Configuration and Ref Types

**Files:**
- Create: `finance-mcp/storage/__init__.py`
- Create: `finance-mcp/storage/config.py`
- Create: `finance-mcp/storage/refs.py`
- Test: `finance-mcp/tests/test_storage_refs.py`

- [ ] **Step 1: Write failing tests for storage config and refs**

Create `finance-mcp/tests/test_storage_refs.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from storage.config import StorageSettings
from storage.refs import StorageObjectRef, parse_storage_ref


def test_parse_legacy_upload_path() -> None:
    ref = parse_storage_ref("/uploads/2026/6/1/a.xlsx")

    assert ref.provider == "local"
    assert ref.local_path == "/uploads/2026/6/1/a.xlsx"
    assert ref.bucket == ""
    assert ref.key == ""


def test_parse_oss_uri() -> None:
    ref = parse_storage_ref("oss://private-bucket/uploads/company/file.xlsx")

    assert ref.provider == "oss"
    assert ref.bucket == "private-bucket"
    assert ref.key == "uploads/company/file.xlsx"
    assert ref.to_uri() == "oss://private-bucket/uploads/company/file.xlsx"


def test_parse_metadata_dict() -> None:
    ref = parse_storage_ref(
        {
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "recon-output/c1/file.xlsx",
            "original_filename": "file.xlsx",
            "size_bytes": 123,
            "checksum": "sha256:abc",
        }
    )

    assert ref.provider == "oss"
    assert ref.bucket == "bucket-a"
    assert ref.key == "recon-output/c1/file.xlsx"
    assert ref.original_filename == "file.xlsx"
    assert ref.size_bytes == 123
    assert ref.checksum == "sha256:abc"


def test_storage_settings_default_local(monkeypatch) -> None:
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)

    settings = StorageSettings.from_env()

    assert settings.backend == "local"
    assert settings.oss_presign_expire_seconds == 900
    assert settings.oss_upload_max_size == 100 * 1024 * 1024


def test_storage_settings_oss_requires_bucket_and_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "")
    monkeypatch.setenv("OSS_ENDPOINT", "")

    settings = StorageSettings.from_env()

    assert settings.backend == "oss"
    assert settings.missing_oss_fields() == [
        "OSS_BUCKET",
        "OSS_ENDPOINT",
        "OSS_ACCESS_KEY_ID",
        "OSS_ACCESS_KEY_SECRET",
    ]


def test_ref_from_output_row() -> None:
    ref = StorageObjectRef.from_output_row(
        {
            "storage_provider": "oss",
            "storage_bucket": "bucket-a",
            "storage_key": "proc-output/c1/out.xlsx",
            "original_filename": "out.xlsx",
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size_bytes": 456,
        }
    )

    assert ref.provider == "oss"
    assert ref.to_uri() == "oss://bucket-a/proc-output/c1/out.xlsx"
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_refs.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'storage'`.

- [ ] **Step 3: Implement storage config and refs**

Create `finance-mcp/storage/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class StorageSettings:
    backend: str
    oss_bucket: str
    oss_endpoint: str
    oss_region: str
    oss_access_key_id: str
    oss_access_key_secret: str
    oss_prefix: str
    oss_presign_expire_seconds: int
    oss_upload_max_size: int

    @classmethod
    def from_env(cls) -> "StorageSettings":
        backend = os.getenv("STORAGE_BACKEND", "local").strip().lower() or "local"
        return cls(
            backend=backend,
            oss_bucket=os.getenv("OSS_BUCKET", "").strip(),
            oss_endpoint=os.getenv("OSS_ENDPOINT", "").strip(),
            oss_region=os.getenv("OSS_REGION", "").strip(),
            oss_access_key_id=os.getenv("OSS_ACCESS_KEY_ID", "").strip(),
            oss_access_key_secret=os.getenv("OSS_ACCESS_KEY_SECRET", "").strip(),
            oss_prefix=os.getenv("OSS_PREFIX", "financial-ai/prod").strip().strip("/"),
            oss_presign_expire_seconds=int(os.getenv("OSS_PRESIGN_EXPIRE_SECONDS", "900")),
            oss_upload_max_size=int(os.getenv("OSS_UPLOAD_MAX_SIZE", str(100 * 1024 * 1024))),
        )

    def missing_oss_fields(self) -> list[str]:
        if self.backend != "oss":
            return []
        missing: list[str] = []
        if not self.oss_bucket:
            missing.append("OSS_BUCKET")
        if not self.oss_endpoint:
            missing.append("OSS_ENDPOINT")
        if not self.oss_access_key_id:
            missing.append("OSS_ACCESS_KEY_ID")
        if not self.oss_access_key_secret:
            missing.append("OSS_ACCESS_KEY_SECRET")
        return missing

    def require_oss_ready(self) -> None:
        missing = self.missing_oss_fields()
        if missing:
            raise RuntimeError(f"OSS 配置不完整: {', '.join(missing)}")
```

Create `finance-mcp/storage/refs.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class StorageObjectRef:
    provider: str
    bucket: str = ""
    key: str = ""
    local_path: str = ""
    original_filename: str = ""
    content_type: str = ""
    size_bytes: int = 0
    checksum: str = ""

    def to_uri(self) -> str:
        if self.provider == "oss":
            return f"oss://{self.bucket}/{self.key}"
        return self.local_path

    def to_metadata(self) -> dict[str, Any]:
        return {
            "storage_provider": self.provider,
            "storage_bucket": self.bucket,
            "storage_key": self.key,
            "storage_uri": self.to_uri(),
            "local_path": self.local_path,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
        }

    @classmethod
    def from_output_row(cls, row: dict[str, Any]) -> "StorageObjectRef":
        return parse_storage_ref(row)


def parse_storage_ref(value: str | dict[str, Any] | StorageObjectRef) -> StorageObjectRef:
    if isinstance(value, StorageObjectRef):
        return value
    if isinstance(value, dict):
        provider = str(value.get("storage_provider") or value.get("provider") or "").strip()
        storage_uri = str(value.get("storage_uri") or "").strip()
        if not provider and storage_uri:
            return parse_storage_ref(storage_uri)
        return StorageObjectRef(
            provider=provider or "local",
            bucket=str(value.get("storage_bucket") or value.get("bucket") or "").strip(),
            key=str(value.get("storage_key") or value.get("key") or "").strip().lstrip("/"),
            local_path=str(value.get("local_path") or value.get("storage_path") or "").strip(),
            original_filename=str(value.get("original_filename") or value.get("file_name") or "").strip(),
            content_type=str(value.get("content_type") or "").strip(),
            size_bytes=int(value.get("size_bytes") or value.get("size") or 0),
            checksum=str(value.get("checksum") or "").strip(),
        )

    ref = str(value or "").strip()
    if ref.startswith("oss://"):
        parsed = urlparse(ref)
        return StorageObjectRef(
            provider="oss",
            bucket=parsed.netloc,
            key=parsed.path.lstrip("/"),
        )
    return StorageObjectRef(provider="local", local_path=ref)
```

Create `finance-mcp/storage/__init__.py`:

```python
from storage.config import StorageSettings
from storage.refs import StorageObjectRef, parse_storage_ref

__all__ = ["StorageObjectRef", "StorageSettings", "parse_storage_ref"]
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_refs.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finance-mcp/storage/__init__.py finance-mcp/storage/config.py finance-mcp/storage/refs.py finance-mcp/tests/test_storage_refs.py
git commit -m "feat: add storage refs and config"
```

## Task 2: Storage Clients

**Files:**
- Create: `finance-mcp/storage/client.py`
- Create: `finance-mcp/storage/tempfiles.py`
- Modify: `finance-mcp/requirements.txt`
- Test: `finance-mcp/tests/test_storage_clients.py`

- [ ] **Step 1: Write failing client tests**

Create `finance-mcp/tests/test_storage_clients.py`:

```python
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


def test_storage_from_env_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    client = storage_from_env(local_root=tmp_path)

    assert isinstance(client, LocalStorageClient)


def test_oss_client_requires_complete_config(monkeypatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "")
    settings = StorageSettings.from_env()

    with pytest.raises(RuntimeError, match="OSS 配置不完整"):
        OssStorageClient(settings)


class _FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.signed: list[tuple[str, str, int]] = []

    def put_object_from_file(self, key: str, filename: str, headers=None):
        self.objects[key] = Path(filename).read_bytes()
        return type("Result", (), {"status": 200, "request_id": "req-1"})()

    def put_object(self, key: str, data: bytes, headers=None):
        self.objects[key] = data
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
        size_bytes=3,
    )
    assert client.exists(ref)
    assert client.read_bytes(ref) == b"abc"
    assert client.create_presigned_upload(key="uploads/c1/b.txt", content_type="text/plain")["url"].startswith(
        "https://oss.test/uploads/c1/b.txt"
    )
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_clients.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'storage.client'`.

- [ ] **Step 3: Add OSS dependency**

Append this line to `finance-mcp/requirements.txt`:

```text
oss2>=2.18.0
```

- [ ] **Step 4: Implement storage clients**

Create `finance-mcp/storage/client.py`:

```python
from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any, Protocol

from storage.config import StorageSettings
from storage.refs import StorageObjectRef


class StorageClient(Protocol):
    def put_file(
        self,
        source_path: str | Path,
        *,
        key: str,
        original_filename: str,
        content_type: str = "",
        checksum: str = "",
    ) -> StorageObjectRef:
        raise NotImplementedError

    def put_bytes(
        self,
        data: bytes,
        *,
        key: str,
        original_filename: str,
        content_type: str = "",
        checksum: str = "",
    ) -> StorageObjectRef:
        raise NotImplementedError

    def read_bytes(self, ref: StorageObjectRef) -> bytes:
        raise NotImplementedError

    def exists(self, ref: StorageObjectRef) -> bool:
        raise NotImplementedError

    def create_presigned_upload(self, *, key: str, content_type: str = "") -> dict[str, Any]:
        raise NotImplementedError


def _safe_key(key: str) -> str:
    normalized = str(key or "").strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        raise ValueError("invalid storage key")
    return normalized


def _guess_content_type(filename: str, fallback: str = "") -> str:
    return fallback or mimetypes.guess_type(filename)[0] or "application/octet-stream"


class LocalStorageClient:
    def __init__(self, *, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        safe_key = _safe_key(key)
        target = (self.root / safe_key).resolve()
        target.relative_to(self.root)
        return target

    def put_file(
        self,
        source_path: str | Path,
        *,
        key: str,
        original_filename: str,
        content_type: str = "",
        checksum: str = "",
    ) -> StorageObjectRef:
        target = self._path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        return StorageObjectRef(
            provider="local",
            local_path=str(target),
            original_filename=original_filename,
            content_type=_guess_content_type(original_filename, content_type),
            size_bytes=target.stat().st_size,
            checksum=checksum,
        )

    def put_bytes(
        self,
        data: bytes,
        *,
        key: str,
        original_filename: str,
        content_type: str = "",
        checksum: str = "",
    ) -> StorageObjectRef:
        target = self._path_for_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return StorageObjectRef(
            provider="local",
            local_path=str(target),
            original_filename=original_filename,
            content_type=_guess_content_type(original_filename, content_type),
            size_bytes=len(data),
            checksum=checksum,
        )

    def read_bytes(self, ref: StorageObjectRef) -> bytes:
        return Path(ref.local_path).read_bytes()

    def exists(self, ref: StorageObjectRef) -> bool:
        return bool(ref.local_path) and Path(ref.local_path).is_file()

    def create_presigned_upload(self, *, key: str, content_type: str = "") -> dict[str, Any]:
        return {"provider": "local", "key": _safe_key(key), "url": "", "fields": {}, "headers": {}}


class OssStorageClient:
    def __init__(self, settings: StorageSettings, *, bucket: Any | None = None) -> None:
        settings.require_oss_ready()
        self.settings = settings
        self.bucket_name = settings.oss_bucket
        if bucket is not None:
            self.bucket = bucket
            return
        import oss2

        auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
        self.bucket = oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)

    def put_file(
        self,
        source_path: str | Path,
        *,
        key: str,
        original_filename: str,
        content_type: str = "",
        checksum: str = "",
    ) -> StorageObjectRef:
        safe_key = _safe_key(key)
        headers = {"Content-Type": _guess_content_type(original_filename, content_type)}
        self.bucket.put_object_from_file(safe_key, str(source_path), headers=headers)
        return StorageObjectRef(
            provider="oss",
            bucket=self.bucket_name,
            key=safe_key,
            original_filename=original_filename,
            content_type=headers["Content-Type"],
            size_bytes=Path(source_path).stat().st_size,
            checksum=checksum,
        )

    def put_bytes(
        self,
        data: bytes,
        *,
        key: str,
        original_filename: str,
        content_type: str = "",
        checksum: str = "",
    ) -> StorageObjectRef:
        safe_key = _safe_key(key)
        headers = {"Content-Type": _guess_content_type(original_filename, content_type)}
        self.bucket.put_object(safe_key, data, headers=headers)
        return StorageObjectRef(
            provider="oss",
            bucket=self.bucket_name,
            key=safe_key,
            original_filename=original_filename,
            content_type=headers["Content-Type"],
            size_bytes=len(data),
            checksum=checksum,
        )

    def read_bytes(self, ref: StorageObjectRef) -> bytes:
        return self.bucket.get_object(ref.key).read()

    def exists(self, ref: StorageObjectRef) -> bool:
        return bool(ref.key) and bool(self.bucket.object_exists(ref.key))

    def create_presigned_upload(self, *, key: str, content_type: str = "") -> dict[str, Any]:
        safe_key = _safe_key(key)
        headers = {"Content-Type": content_type} if content_type else None
        url = self.bucket.sign_url("PUT", safe_key, self.settings.oss_presign_expire_seconds, headers=headers)
        return {
            "provider": "oss",
            "bucket": self.bucket_name,
            "key": safe_key,
            "url": url,
            "method": "PUT",
            "headers": headers or {},
            "expires_in": self.settings.oss_presign_expire_seconds,
        }


def storage_from_env(*, local_root: str | Path) -> StorageClient:
    settings = StorageSettings.from_env()
    if settings.backend == "oss":
        return OssStorageClient(settings)
    return LocalStorageClient(root=local_root)
```

Create `finance-mcp/storage/tempfiles.py`:

```python
from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from storage.client import StorageClient
from storage.refs import StorageObjectRef


@contextmanager
def materialize_to_temp(client: StorageClient, ref: StorageObjectRef) -> Iterator[Path]:
    if ref.provider == "local":
        yield Path(ref.local_path)
        return

    suffix = Path(ref.original_filename or ref.key).suffix
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    temp_path = Path(handle.name)
    try:
        handle.write(client.read_bytes(ref))
        handle.close()
        yield temp_path
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_clients.py finance-mcp/tests/test_storage_refs.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add finance-mcp/requirements.txt finance-mcp/storage/client.py finance-mcp/storage/tempfiles.py finance-mcp/tests/test_storage_clients.py
git commit -m "feat: add storage clients"
```

## Task 3: Persist Storage Object Metadata

**Files:**
- Create: `finance-mcp/storage/repository.py`
- Create: `finance-mcp/auth/migrations/037_storage_objects_and_browser_capture_oss.sql`
- Modify: `finance-mcp/auth/migrations/README.md`
- Test: `finance-mcp/tests/test_storage_repository.py`
- Modify test: `finance-mcp/tests/test_browser_capture_files.py`
- Modify: `finance-mcp/auth/db.py`

- [ ] **Step 1: Write failing repository tests**

Create `finance-mcp/tests/test_storage_repository.py`:

```python
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
        self.captured = captured
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, sql, params=None):
        self.captured["sql"] = sql
        self.captured["params"] = params

    def fetchone(self):
        return self.row


class _FakeConn:
    def __init__(self, captured: dict, row: dict | None = None) -> None:
        self.captured = captured
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def cursor(self, *args, **kwargs):
        return _FakeCursor(self.captured, self.row)

    def commit(self):
        self.captured["committed"] = True


class _FakeConnManager:
    def __init__(self, captured: dict, row: dict | None = None) -> None:
        self.captured = captured
        self.row = row

    def __enter__(self):
        return _FakeConn(self.captured, self.row)

    def __exit__(self, exc_type, exc, tb):
        return None


def test_save_storage_object_metadata(monkeypatch) -> None:
    captured: dict = {}
    monkeypatch.setattr(repository.auth_db, "get_conn", lambda: _FakeConnManager(captured))

    row = repository.save_storage_object_metadata(
        owner_user_id="user-1",
        company_id="company-1",
        module="upload",
        logical_path="/uploads/company-1/a.xlsx",
        ref=StorageObjectRef(
            provider="oss",
            bucket="bucket-a",
            key="uploads/company-1/a.xlsx",
            original_filename="a.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=12,
            checksum="sha256:abc",
        ),
        metadata={"thread_id": "thread-1"},
    )

    assert row["logical_path"] == "/uploads/company-1/a.xlsx"
    assert "INSERT INTO storage_objects" in captured["sql"]
    assert captured["params"]["storage_provider"] == "oss"
    assert captured["params"]["storage_key"] == "uploads/company-1/a.xlsx"
    assert captured["committed"] is True


def test_get_storage_object_by_logical_path(monkeypatch) -> None:
    captured: dict = {}
    db_row = {
        "logical_path": "/output/recon/a.xlsx",
        "storage_provider": "oss",
        "storage_bucket": "bucket-a",
        "storage_key": "recon-output/c1/a.xlsx",
        "original_filename": "a.xlsx",
    }
    monkeypatch.setattr(repository.auth_db, "get_conn", lambda: _FakeConnManager(captured, db_row))

    row = repository.get_storage_object_by_logical_path("/output/recon/a.xlsx")

    assert row == db_row
    assert "FROM storage_objects" in captured["sql"]
    assert captured["params"] == {"logical_path": "/output/recon/a.xlsx"}
```

Modify `finance-mcp/tests/test_browser_capture_files.py` first test capture assertions:

```python
    values = captured["values"][0]
    assert values[8] == "oss://bucket-a/browser-captures/c1/file.csv"
    assert values[12] == "oss"
    assert values[13] == "bucket-a"
    assert values[14] == "browser-captures/c1/file.csv"
```

Change its `capture_files` entry to:

```python
            {
                "storage_path": "oss://bucket-a/browser-captures/c1/file.csv",
                "storage_provider": "oss",
                "storage_bucket": "bucket-a",
                "storage_key": "browser-captures/c1/file.csv",
                "storage_uri": "oss://bucket-a/browser-captures/c1/file.csv",
                "content_type": "text/csv",
                "size_bytes": 99,
                "encoding": "utf-8",
                "checksum": "sha256:abc",
                "row_count": 10,
            }
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_repository.py finance-mcp/tests/test_browser_capture_files.py -v
```

Expected: repository import failure and browser capture column assertion failure.

- [ ] **Step 3: Add migration**

Create `finance-mcp/auth/migrations/037_storage_objects_and_browser_capture_oss.sql`:

```sql
CREATE TABLE IF NOT EXISTS public.storage_objects (
    object_id uuid DEFAULT public.uuid_generate_v4() NOT NULL PRIMARY KEY,
    logical_path text NOT NULL UNIQUE,
    owner_user_id uuid,
    company_id uuid,
    module character varying(64) NOT NULL DEFAULT ''::character varying,
    storage_provider character varying(32) NOT NULL,
    storage_bucket text NOT NULL DEFAULT ''::text,
    storage_key text NOT NULL DEFAULT ''::text,
    storage_uri text NOT NULL DEFAULT ''::text,
    local_path text NOT NULL DEFAULT ''::text,
    original_filename text NOT NULL DEFAULT ''::text,
    content_type text NOT NULL DEFAULT ''::text,
    size_bytes bigint NOT NULL DEFAULT 0,
    checksum text NOT NULL DEFAULT ''::text,
    metadata_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamptz DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_storage_objects_owner_user_id
    ON public.storage_objects(owner_user_id);

CREATE INDEX IF NOT EXISTS idx_storage_objects_company_module
    ON public.storage_objects(company_id, module);

DROP TRIGGER IF EXISTS update_storage_objects_updated_at ON public.storage_objects;
CREATE TRIGGER update_storage_objects_updated_at
    BEFORE UPDATE ON public.storage_objects
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

ALTER TABLE public.browser_capture_files
    ADD COLUMN IF NOT EXISTS storage_provider character varying(32) NOT NULL DEFAULT 'local',
    ADD COLUMN IF NOT EXISTS storage_bucket text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS storage_key text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS storage_uri text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS content_type text NOT NULL DEFAULT ''::text,
    ADD COLUMN IF NOT EXISTS size_bytes bigint NOT NULL DEFAULT 0;
```

Update `finance-mcp/auth/migrations/README.md` by adding:

```markdown
31. **031_browser_playbook_collection.sql** - 浏览器 playbook 采集注册、任务与采集审计文件
32. **032_data_sources_browser_playbook_source_kind.sql** - 浏览器 playbook 数据源类型
33. **033_browser_handoff_sessions.sql** - 浏览器人工接管会话
34. **034_browser_handoff_lifecycle.sql** - 浏览器人工接管生命周期字段
35. **035_sync_jobs_handoff_statuses.sql** - sync_jobs 接管状态扩展
36. **036_execution_run_exceptions_pending_index.sql** - execution_run_exceptions 待办索引
37. **037_storage_objects_and_browser_capture_oss.sql** - OSS 对象元数据与浏览器采集文件存储字段
```

If the README currently stops at 30, append entries 31-37 after entry 30.

- [ ] **Step 4: Implement repository helpers**

Create `finance-mcp/storage/repository.py`:

```python
from __future__ import annotations

import json
from typing import Any

import psycopg2.extras

from auth import db as auth_db
from storage.refs import StorageObjectRef


def save_storage_object_metadata(
    *,
    owner_user_id: str,
    company_id: str,
    module: str,
    logical_path: str,
    ref: StorageObjectRef,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = {
        "logical_path": logical_path,
        "owner_user_id": owner_user_id or None,
        "company_id": company_id or None,
        "module": module,
        "storage_provider": ref.provider,
        "storage_bucket": ref.bucket,
        "storage_key": ref.key,
        "storage_uri": ref.to_uri(),
        "local_path": ref.local_path,
        "original_filename": ref.original_filename,
        "content_type": ref.content_type,
        "size_bytes": ref.size_bytes,
        "checksum": ref.checksum,
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
    }
    conn_manager = auth_db.get_conn()
    with conn_manager as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO storage_objects (
                    logical_path, owner_user_id, company_id, module,
                    storage_provider, storage_bucket, storage_key, storage_uri, local_path,
                    original_filename, content_type, size_bytes, checksum, metadata_json
                ) VALUES (
                    %(logical_path)s, %(owner_user_id)s, %(company_id)s, %(module)s,
                    %(storage_provider)s, %(storage_bucket)s, %(storage_key)s, %(storage_uri)s, %(local_path)s,
                    %(original_filename)s, %(content_type)s, %(size_bytes)s, %(checksum)s, %(metadata_json)s::jsonb
                )
                ON CONFLICT (logical_path) DO UPDATE SET
                    owner_user_id = EXCLUDED.owner_user_id,
                    company_id = EXCLUDED.company_id,
                    module = EXCLUDED.module,
                    storage_provider = EXCLUDED.storage_provider,
                    storage_bucket = EXCLUDED.storage_bucket,
                    storage_key = EXCLUDED.storage_key,
                    storage_uri = EXCLUDED.storage_uri,
                    local_path = EXCLUDED.local_path,
                    original_filename = EXCLUDED.original_filename,
                    content_type = EXCLUDED.content_type,
                    size_bytes = EXCLUDED.size_bytes,
                    checksum = EXCLUDED.checksum,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING *
                """,
                params,
            )
            row = dict(cur.fetchone() or params)
            conn.commit()
            return row


def get_storage_object_by_logical_path(logical_path: str) -> dict[str, Any] | None:
    conn_manager = auth_db.get_conn()
    with conn_manager as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM storage_objects
                WHERE logical_path = %(logical_path)s
                """,
                {"logical_path": logical_path},
            )
            row = cur.fetchone()
            return dict(row) if row else None
```

- [ ] **Step 5: Extend browser capture DB insert**

In `finance-mcp/auth/db.py`, update `insert_browser_capture_files()` row tuple to append fields after `row_count`:

```python
                int(entry.get("row_count") or 0),
                str(entry.get("storage_provider") or ("oss" if str(entry.get("storage_path") or "").startswith("oss://") else "local")),
                str(entry.get("storage_bucket") or ""),
                str(entry.get("storage_key") or ""),
                str(entry.get("storage_uri") or entry.get("storage_path") or ""),
                str(entry.get("content_type") or ""),
                int(entry.get("size_bytes") or 0),
```

Update the SQL columns:

```sql
                        shop_id, playbook_id, biz_date, storage_path, encoding, checksum, row_count,
                        storage_provider, storage_bucket, storage_key, storage_uri, content_type, size_bytes
```

Update the template:

```python
                    template="(%s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_repository.py finance-mcp/tests/test_browser_capture_files.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-mcp/storage/repository.py finance-mcp/auth/migrations/037_storage_objects_and_browser_capture_oss.sql finance-mcp/auth/migrations/README.md finance-mcp/auth/db.py finance-mcp/tests/test_storage_repository.py finance-mcp/tests/test_browser_capture_files.py
git commit -m "feat: persist storage object metadata"
```

## Task 4: Upload Presign and Confirm Tools

**Files:**
- Create: `finance-mcp/tools/storage_upload_tool.py`
- Modify: `finance-mcp/unified_mcp_server.py`
- Modify: `finance-mcp/tools/file_upload_tool.py`
- Test: `finance-mcp/tests/test_storage_upload_tool.py`

- [ ] **Step 1: Write failing tests for upload tools**

Create `finance-mcp/tests/test_storage_upload_tool.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import pytest

from tools import storage_upload_tool


def _user() -> dict:
    return {"user_id": "00000000-0000-0000-0000-000000000001", "company_id": "00000000-0000-0000-0000-000000000002"}


def test_create_upload_presign_rejects_bad_extension(monkeypatch) -> None:
    monkeypatch.setattr(storage_upload_tool, "get_user_from_token", lambda token: _user())

    result = storage_upload_tool.create_upload_presign(
        {
            "auth_token": "tok",
            "filename": "bad.exe",
            "size": 10,
            "content_type": "application/octet-stream",
        }
    )

    assert result["success"] is False
    assert "不支持的文件类型" in result["error"]


def test_create_upload_presign_returns_local_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setattr(storage_upload_tool, "get_user_from_token", lambda token: _user())
    monkeypatch.setattr(storage_upload_tool, "UPLOAD_ROOT", tmp_path)

    result = storage_upload_tool.create_upload_presign(
        {
            "auth_token": "tok",
            "filename": "a.xlsx",
            "size": 10,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
    )

    assert result["success"] is True
    assert result["direct_upload"] is False
    assert result["storage_provider"] == "local"


def test_confirm_upload_saves_metadata(monkeypatch) -> None:
    saved: dict = {}
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "bucket-a")
    monkeypatch.setenv("OSS_ENDPOINT", "https://oss.example")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "sk")
    monkeypatch.setattr(storage_upload_tool, "get_user_from_token", lambda token: _user())
    monkeypatch.setattr(storage_upload_tool, "_oss_object_exists", lambda key: True)
    monkeypatch.setattr(
        storage_upload_tool.repository,
        "save_storage_object_metadata",
        lambda **kwargs: saved.update(kwargs) or {"logical_path": kwargs["logical_path"]},
    )

    result = storage_upload_tool.confirm_upload(
        {
            "auth_token": "tok",
            "storage_key": "financial-ai/prod/uploads/00000000-0000-0000-0000-000000000002/2026/06/01/id-a.xlsx",
            "filename": "a.xlsx",
            "size": 10,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "checksum": "sha256:abc",
        }
    )

    assert result["success"] is True
    assert result["file_path"].startswith("/uploads/oss/")
    assert saved["module"] == "upload"
    assert saved["ref"].provider == "oss"


@pytest.mark.asyncio
async def test_handle_tool_call_routes(monkeypatch) -> None:
    monkeypatch.setattr(storage_upload_tool, "create_upload_presign", lambda args: {"success": True})

    result = await storage_upload_tool.handle_tool_call("file_upload_presign", {})

    assert result == {"success": True}
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_upload_tool.py -v
```

Expected: FAIL with import error.

- [ ] **Step 3: Implement upload tool**

Create `finance-mcp/tools/storage_upload_tool.py`:

```python
from __future__ import annotations

import hashlib
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import Tool

from auth.jwt_utils import get_user_from_token
from security_utils import UPLOAD_ROOT, validate_filename
from storage.client import OssStorageClient, storage_from_env
from storage.config import StorageSettings
from storage.refs import StorageObjectRef
from storage import repository

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".xlsm", ".xlsb"}


def create_tools() -> list[Tool]:
    return [
        Tool(
            name="file_upload_presign",
            description="为前端直传 OSS 创建短期上传 URL。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "filename": {"type": "string"},
                    "size": {"type": "integer"},
                    "content_type": {"type": "string"},
                },
                "required": ["auth_token", "filename", "size"],
            },
        ),
        Tool(
            name="file_upload_confirm",
            description="确认前端直传对象已上传，并登记文件元数据。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "storage_key": {"type": "string"},
                    "filename": {"type": "string"},
                    "size": {"type": "integer"},
                    "content_type": {"type": "string"},
                    "checksum": {"type": "string"},
                    "thread_id": {"type": "string"},
                },
                "required": ["auth_token", "storage_key", "filename", "size"],
            },
        ),
    ]


def _validate_upload_request(filename: str, size: int) -> str | None:
    if not filename or not validate_filename(filename):
        return "非法文件名，可能存在安全风险"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"不支持的文件类型: {ext}"
    max_size = StorageSettings.from_env().oss_upload_max_size
    if size > max_size:
        return f"文件大小超过限制 ({max_size} bytes)"
    return None


def _build_upload_key(company_id: str, filename: str) -> str:
    settings = StorageSettings.from_env()
    now = datetime.now()
    safe_name = Path(filename).name
    unique = uuid.uuid4().hex
    prefix = settings.oss_prefix.strip("/")
    return (
        f"{prefix}/uploads/{company_id}/"
        f"{now:%Y}/{now:%m}/{now:%d}/{unique}-{safe_name}"
    ).strip("/")


def _allowed_upload_prefix(company_id: str) -> str:
    settings = StorageSettings.from_env()
    return f"{settings.oss_prefix.strip('/')}/uploads/{company_id}/".strip("/")


def _content_type(filename: str, content_type: str = "") -> str:
    return content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _oss_object_exists(storage_key: str) -> bool:
    settings = StorageSettings.from_env()
    client = OssStorageClient(settings)
    return client.exists(StorageObjectRef(provider="oss", bucket=settings.oss_bucket, key=storage_key))


def create_upload_presign(args: dict[str, Any]) -> dict[str, Any]:
    auth_token = str(args.get("auth_token") or "")
    user = get_user_from_token(auth_token)
    if not user:
        return {"success": False, "error": "无效的 auth_token"}
    filename = str(args.get("filename") or "")
    size = int(args.get("size") or 0)
    validation_error = _validate_upload_request(filename, size)
    if validation_error:
        return {"success": False, "error": validation_error}

    settings = StorageSettings.from_env()
    if settings.backend != "oss":
        return {
            "success": True,
            "direct_upload": False,
            "storage_provider": "local",
            "message": "local storage backend uses /upload proxy",
        }

    settings.require_oss_ready()
    company_id = str(user.get("company_id") or "")
    key = _build_upload_key(company_id, filename)
    client = storage_from_env(local_root=UPLOAD_ROOT)
    upload = client.create_presigned_upload(key=key, content_type=_content_type(filename, str(args.get("content_type") or "")))
    return {
        "success": True,
        "direct_upload": True,
        "storage_provider": "oss",
        "bucket": settings.oss_bucket,
        "key": key,
        **upload,
    }


def confirm_upload(args: dict[str, Any]) -> dict[str, Any]:
    auth_token = str(args.get("auth_token") or "")
    user = get_user_from_token(auth_token)
    if not user:
        return {"success": False, "error": "无效的 auth_token"}
    filename = str(args.get("filename") or "")
    size = int(args.get("size") or 0)
    validation_error = _validate_upload_request(filename, size)
    if validation_error:
        return {"success": False, "error": validation_error}

    settings = StorageSettings.from_env()
    if settings.backend != "oss":
        return {"success": False, "error": "当前存储后端不支持直传确认"}
    settings.require_oss_ready()

    company_id = str(user.get("company_id") or "")
    storage_key = str(args.get("storage_key") or "").strip().lstrip("/")
    if not storage_key.startswith(_allowed_upload_prefix(company_id)):
        return {"success": False, "error": "上传对象不属于当前公司"}
    if not _oss_object_exists(storage_key):
        return {"success": False, "error": "上传对象不存在或尚未完成"}

    digest = hashlib.sha256(storage_key.encode("utf-8")).hexdigest()[:16]
    logical_path = f"/uploads/oss/{digest}/{Path(filename).name}"
    ref = StorageObjectRef(
        provider="oss",
        bucket=settings.oss_bucket,
        key=storage_key,
        original_filename=filename,
        content_type=_content_type(filename, str(args.get("content_type") or "")),
        size_bytes=size,
        checksum=str(args.get("checksum") or ""),
    )
    repository.save_storage_object_metadata(
        owner_user_id=str(user.get("user_id") or user.get("id") or ""),
        company_id=company_id,
        module="upload",
        logical_path=logical_path,
        ref=ref,
        metadata={"thread_id": str(args.get("thread_id") or "")},
    )
    return {
        "success": True,
        "file_path": logical_path,
        "original_filename": filename,
        "filename": filename,
        "size": size,
        "storage_provider": "oss",
        "storage_key": storage_key,
    }


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "file_upload_presign":
        return create_upload_presign(arguments)
    if name == "file_upload_confirm":
        return confirm_upload(arguments)
    return {"success": False, "error": f"未知的上传工具: {name}"}
```

- [ ] **Step 4: Register tools in unified MCP**

In `finance-mcp/unified_mcp_server.py`, add import:

```python
from tools.storage_upload_tool import (
    create_tools as create_storage_upload_tools,
    handle_tool_call as handle_storage_upload_tool_call,
)
```

In `list_tools()`, after `upload_tools`:

```python
        storage_upload_tools = create_storage_upload_tools()
        logger.info(f"存储上传工具数量: {len(storage_upload_tools)}")
```

Initialize `storage_upload_tools = []` in that `except` block and add it to `all_tools`.

Change:

```python
_UPLOAD_TOOL_NAMES = {"file_upload"}
```

to:

```python
_UPLOAD_TOOL_NAMES = {"file_upload", "file_upload_presign", "file_upload_confirm"}
```

In `call_tool`, route:

```python
        elif name in {"file_upload_presign", "file_upload_confirm"}:
            result = await handle_storage_upload_tool_call(name, arguments)

        elif name == "file_upload":
            result = await handle_file_upload_tool_call(name, arguments)
```

- [ ] **Step 5: Keep old proxy upload compatible with storage metadata**

In `finance-mcp/tools/file_upload_tool.py`, after local file write and `file_path_str` creation, add:

```python
                try:
                    from storage.refs import StorageObjectRef
                    from storage import repository

                    repository.save_storage_object_metadata(
                        owner_user_id=str(user_info.get("user_id") or user_info.get("id") or ""),
                        company_id=str(user_info.get("company_id") or ""),
                        module="upload",
                        logical_path=file_path_str,
                        ref=StorageObjectRef(
                            provider="local",
                            local_path=str(file_path),
                            original_filename=filename,
                            content_type="",
                            size_bytes=len(file_content),
                        ),
                        metadata={},
                    )
                except Exception as exc:
                    logger.warning(f"保存上传文件元数据失败，继续兼容本地路径: {exc}")
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_upload_tool.py finance-mcp/tests/test_unified_mcp_recon_auto_routes.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-mcp/tools/storage_upload_tool.py finance-mcp/unified_mcp_server.py finance-mcp/tools/file_upload_tool.py finance-mcp/tests/test_storage_upload_tool.py
git commit -m "feat: add upload presign and confirm tools"
```

## Task 5: Data-Agent Upload Presign/Confirm API

**Files:**
- Modify: `finance-agents/data-agent/server.py`
- Test: `finance-agents/data-agent/tests/test_upload_presign_api.py`

- [ ] **Step 1: Write failing API tests**

Create `finance-agents/data-agent/tests/test_upload_presign_api.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

import server


def test_upload_presign_calls_mcp(monkeypatch) -> None:
    async def fake_call(tool_name, args):
        assert tool_name == "file_upload_presign"
        assert args["filename"] == "a.xlsx"
        return {"success": True, "direct_upload": True, "url": "https://oss/upload", "key": "k"}

    monkeypatch.setattr(server, "mcp_call_tool", fake_call)
    client = TestClient(server.app)

    response = client.post(
        "/upload/presign",
        json={"filename": "a.xlsx", "size": 12, "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        headers={"Authorization": "Bearer tok"},
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://oss/upload"


def test_upload_confirm_calls_mcp(monkeypatch) -> None:
    async def fake_call(tool_name, args):
        assert tool_name == "file_upload_confirm"
        assert args["storage_key"] == "uploads/c1/a.xlsx"
        return {"success": True, "file_path": "/uploads/oss/id/a.xlsx", "filename": "a.xlsx", "size": 12}

    monkeypatch.setattr(server, "mcp_call_tool", fake_call)
    client = TestClient(server.app)

    response = client.post(
        "/upload/confirm",
        json={"storage_key": "uploads/c1/a.xlsx", "filename": "a.xlsx", "size": 12},
        headers={"Authorization": "Bearer tok"},
    )

    assert response.status_code == 200
    assert response.json()["file_path"] == "/uploads/oss/id/a.xlsx"


def test_upload_presign_requires_token() -> None:
    client = TestClient(server.app)

    response = client.post("/upload/presign", json={"filename": "a.xlsx", "size": 12})

    assert response.status_code == 401
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/test_upload_presign_api.py -v
```

Expected: FAIL with 404 routes.

- [ ] **Step 3: Add request models and auth helper**

In `finance-agents/data-agent/server.py`, near upload route helpers, add:

```python
from pydantic import BaseModel


class UploadPresignRequest(BaseModel):
    filename: str
    size: int
    content_type: str = ""


class UploadConfirmRequest(BaseModel):
    storage_key: str
    filename: str
    size: int
    content_type: str = ""
    checksum: str = ""
    thread_id: str = "default"


def _extract_bearer_token(headers) -> str:
    auth_header = headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""
```

If `BaseModel` is already imported, only add the models.

At module scope, immediately after the existing `from tools.mcp_client import (...)` block, add an alias that tests and routes can patch cleanly:

```python
mcp_call_tool = call_mcp_tool
```

- [ ] **Step 4: Add API routes**

In `finance-agents/data-agent/server.py`, before existing `@app.post("/upload")`, add:

```python
@app.post("/upload/presign")
async def upload_presign(payload: UploadPresignRequest, request: Request):
    auth_token = _extract_bearer_token(request.headers)
    if not auth_token:
        raise HTTPException(401, "缺少 auth_token，请先登录")
    result = await mcp_call_tool(
        "file_upload_presign",
        {
            "auth_token": auth_token,
            "filename": payload.filename,
            "size": payload.size,
            "content_type": payload.content_type,
        },
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "创建上传凭证失败"))
    return result


@app.post("/upload/confirm")
async def upload_confirm(payload: UploadConfirmRequest, request: Request):
    auth_token = _extract_bearer_token(request.headers)
    if not auth_token:
        raise HTTPException(401, "缺少 auth_token，请先登录")
    result = await mcp_call_tool(
        "file_upload_confirm",
        {
            "auth_token": auth_token,
            "storage_key": payload.storage_key,
            "filename": payload.filename,
            "size": payload.size,
            "content_type": payload.content_type,
            "checksum": payload.checksum,
            "thread_id": payload.thread_id,
        },
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "确认上传失败"))
    return result
```

Ensure `Request` is imported from `fastapi`.

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-agents/data-agent/tests/test_upload_presign_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add finance-agents/data-agent/server.py finance-agents/data-agent/tests/test_upload_presign_api.py
git commit -m "feat: expose upload presign api"
```

## Task 6: Frontend Direct Upload with Fallback

**Files:**
- Modify: `finance-web/src/components/ChatArea.tsx`
- Test: `finance-web/tests/components/chat-upload-direct-oss.spec.tsx`

- [ ] **Step 1: Write failing frontend tests**

Create `finance-web/tests/components/chat-upload-direct-oss.spec.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import ChatArea from '../../src/components/ChatArea';

const baseProps = {
  messages: [],
  isLoading: false,
  connectionStatus: 'connected' as const,
  onSendMessage: vi.fn(),
  onFileUploaded: vi.fn(),
  threadId: 'thread-1',
  authToken: 'tok',
};

describe('ChatArea OSS direct upload', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it('uses presign, PUT upload, confirm, then sends attachment', async () => {
    const calls: Array<{ url: string; method?: string }> = [];
    global.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(url), method: init?.method });
      if (String(url) === '/api/upload/presign') {
        return new Response(
          JSON.stringify({
            success: true,
            direct_upload: true,
            url: 'https://oss.example/upload',
            key: 'financial-ai/prod/uploads/c1/a.xlsx',
            headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (String(url) === 'https://oss.example/upload') {
        return new Response('', { status: 200 });
      }
      if (String(url) === '/api/upload/confirm') {
        return new Response(
          JSON.stringify({ success: true, file_path: '/uploads/oss/id/a.xlsx', filename: 'a.xlsx', size: 12 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('{}', { status: 500 });
    }) as typeof fetch;

    render(<ChatArea {...baseProps} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['hello'], 'a.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), { target: { value: 'process' } });
    fireEvent.click(screen.getByRole('button', { name: /发送/ }));

    await waitFor(() => {
      expect(baseProps.onSendMessage).toHaveBeenCalledWith(
        'process',
        [{ name: 'a.xlsx', path: '/uploads/oss/id/a.xlsx', size: 12 }],
        undefined,
      );
    });
    expect(calls.map((call) => call.url)).toEqual([
      '/api/upload/presign',
      'https://oss.example/upload',
      '/api/upload/confirm',
    ]);
  });

  it('falls back to legacy upload when presign says direct_upload false', async () => {
    global.fetch = vi.fn(async (url: RequestInfo | URL) => {
      if (String(url) === '/api/upload/presign') {
        return new Response(JSON.stringify({ success: true, direct_upload: false }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (String(url) === '/api/upload') {
        return new Response(JSON.stringify({ file_path: '/uploads/a.xlsx', filename: 'a.xlsx', size: 5 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response('{}', { status: 500 });
    }) as typeof fetch;

    render(<ChatArea {...baseProps} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['hello'], 'a.xlsx')] } });
    fireEvent.change(screen.getByPlaceholderText(/输入消息/), { target: { value: 'process' } });
    fireEvent.click(screen.getByRole('button', { name: /发送/ }));

    await waitFor(() => {
      expect(baseProps.onSendMessage).toHaveBeenCalledWith(
        'process',
        [{ name: 'a.xlsx', path: '/uploads/a.xlsx', size: 5 }],
        undefined,
      );
    });
  });
});
```

The test selectors target the current upload input and send button in `ChatArea.tsx`; keep behavior changes limited to the upload flow.

- [ ] **Step 2: Run failing frontend test**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test -- chat-upload-direct-oss.spec.tsx
```

Expected: FAIL because direct upload logic is absent.

- [ ] **Step 3: Add upload helper inside ChatArea**

In `finance-web/src/components/ChatArea.tsx`, inside the component before `handleSend`, add:

```tsx
  const uploadStagedFile = useCallback(async (staged: StagedFile, index: number) => {
    const legacyUpload = async () => {
      const formData = new FormData();
      formData.append('file', staged.file);
      formData.append('thread_id', threadId);
      formData.append('is_first_file', index === 0 ? '1' : '0');
      if (authToken) {
        formData.append('auth_token', authToken);
      }
      const resp = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(String(err.detail || err.message || '上传失败'));
      }
      return await resp.json();
    };

    if (!authToken) {
      return await legacyUpload();
    }

    const presignResp = await fetch('/api/upload/presign', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        filename: staged.file.name,
        size: staged.file.size,
        content_type: staged.file.type || '',
      }),
    });

    if (!presignResp.ok) {
      return await legacyUpload();
    }
    const presign = await presignResp.json();
    if (!presign.direct_upload) {
      return await legacyUpload();
    }

    const putResp = await fetch(presign.url, {
      method: presign.method || 'PUT',
      headers: presign.headers || {},
      body: staged.file,
    });
    if (!putResp.ok) {
      throw new Error('文件直传 OSS 失败');
    }

    const confirmResp = await fetch('/api/upload/confirm', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authToken}`,
      },
      body: JSON.stringify({
        storage_key: presign.key,
        filename: staged.file.name,
        size: staged.file.size,
        content_type: staged.file.type || '',
        thread_id: threadId,
      }),
    });
    if (!confirmResp.ok) {
      const err = await confirmResp.json().catch(() => ({}));
      throw new Error(String(err.detail || err.message || '确认上传失败'));
    }
    return await confirmResp.json();
  }, [authToken, threadId]);
```

- [ ] **Step 4: Replace inline upload logic**

In `handleSend`, replace the `FormData`/`fetch('/api/upload')` block inside the staged files loop with:

```tsx
          const result = await uploadStagedFile(staged, index);
          attachmentsList.push({
            name: result.filename,
            size: result.size,
            path: result.file_path,
          });
          uploadedList.push({
            name: result.filename,
            path: result.file_path,
            size: result.size,
            uploadedAt: new Date(),
          });
```

Ensure the `catch` still alerts upload failure and does not send the message.

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test -- chat-upload-direct-oss.spec.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add finance-web/src/components/ChatArea.tsx finance-web/tests/components/chat-upload-direct-oss.spec.tsx
git commit -m "feat: direct upload files to oss"
```

## Task 7: Resolve OSS-Backed Inputs to Temp Files

**Files:**
- Create: `finance-mcp/storage/input_resolver.py`
- Modify: `finance-mcp/security_utils.py`
- Modify: `finance-mcp/recon/mcp_server/recon_tool.py`
- Modify: `finance-mcp/proc/mcp_server/proc_rule.py`
- Modify: `finance-mcp/proc/mcp_server/merge_rule.py`
- Test: `finance-mcp/tests/test_storage_input_resolver.py`

- [ ] **Step 1: Write failing input resolver tests**

Create `finance-mcp/tests/test_storage_input_resolver.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from storage import input_resolver
from storage.refs import StorageObjectRef


def test_resolve_legacy_upload_path(monkeypatch, tmp_path: Path) -> None:
    legacy = tmp_path / "a.xlsx"
    legacy.write_text("x", encoding="utf-8")
    monkeypatch.setattr(input_resolver, "resolve_recon_input_file_path", lambda path: legacy)
    monkeypatch.setattr(input_resolver.repository, "get_storage_object_by_logical_path", lambda path: None)

    with input_resolver.materialize_input_file("/uploads/a.xlsx") as path:
        assert path == legacy


def test_resolve_oss_metadata_to_temp(monkeypatch) -> None:
    row = {
        "storage_provider": "oss",
        "storage_bucket": "bucket-a",
        "storage_key": "uploads/c1/a.csv",
        "original_filename": "a.csv",
    }
    monkeypatch.setattr(input_resolver.repository, "get_storage_object_by_logical_path", lambda path: row)

    class FakeClient:
        def read_bytes(self, ref: StorageObjectRef) -> bytes:
            assert ref.key == "uploads/c1/a.csv"
            return b"a,b\n1,2\n"

    monkeypatch.setattr(input_resolver, "storage_from_env", lambda local_root: FakeClient())

    with input_resolver.materialize_input_file("/uploads/oss/id/a.csv") as path:
        assert path.read_text(encoding="utf-8") == "a,b\n1,2\n"
        assert path.name.endswith(".csv")

    assert not path.exists()
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_input_resolver.py -v
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement input resolver**

Create `finance-mcp/storage/input_resolver.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from security_utils import UPLOAD_ROOT, resolve_recon_input_file_path
from storage.client import storage_from_env
from storage.refs import parse_storage_ref
from storage.tempfiles import materialize_to_temp
from storage import repository


@contextmanager
def materialize_input_file(file_ref: str) -> Iterator[Path]:
    row = repository.get_storage_object_by_logical_path(str(file_ref))
    if row:
        ref = parse_storage_ref(row)
        client = storage_from_env(local_root=UPLOAD_ROOT)
        with materialize_to_temp(client, ref) as path:
            yield path
        return

    yield resolve_recon_input_file_path(str(file_ref))
```

- [ ] **Step 4: Update recon input reads**

In `finance-mcp/recon/mcp_server/recon_tool.py`, import:

```python
from storage.input_resolver import materialize_input_file
```

Change `_read_file_as_df(file_path: str)` so it materializes the input before pandas reads it:

```python
def _read_file_as_df(file_path: str) -> pd.DataFrame:
    with materialize_input_file(file_path) as local_path:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = path.suffix.lower()
        if ext == ".csv":
            try:
                return pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                import chardet

                raw = path.read_bytes()
                enc = chardet.detect(raw).get("encoding") or "utf-8"
                return pd.read_csv(path, encoding=enc)
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path, dtype=object)
        raise ValueError(f"不支持的文件类型: {ext}")
```

Keep `source_path` and `target_path` in the result as the original logical refs returned by `_resolve_input_to_df()`.

- [ ] **Step 5: Update proc input reads**

In `finance-mcp/proc/mcp_server/proc_rule.py`, import:

```python
from storage.input_resolver import materialize_input_file
```

Change `_read_file_as_df(file_path: str)` so all proc file reads go through the resolver:

```python
def _read_file_as_df(file_path: str) -> pd.DataFrame:
    with materialize_input_file(file_path) as local_path:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = path.suffix.lower()
        if ext == ".csv":
            try:
                return pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                import chardet

                raw = path.read_bytes()
                enc = chardet.detect(raw).get("encoding") or "utf-8"
                return pd.read_csv(path, encoding=enc)
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path, dtype=object)
        raise ValueError(f"不支持的文件类型: {ext}")
```

Keep `table_file_map` values as logical refs; do not replace them with temp paths globally because temp files are scoped to the read.

- [ ] **Step 6: Update merge and steps runtime reads**

In `finance-mcp/proc/mcp_server/merge_rule.py`, import `materialize_input_file` and change `_read_file_as_df(file_path: str)`:

```python
def _read_file_as_df(file_path: str) -> pd.DataFrame:
    with materialize_input_file(file_path) as local_path:
        path = Path(local_path)
        if not path.exists():
            raise FileReadError(
                cause=f"文件「{file_path}」不存在。",
                suggestion="请重新上传文件后再执行整理。",
            )
        ext = path.suffix.lower()
        if ext == ".csv":
            try:
                return pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                import chardet

                raw = path.read_bytes()
                enc = chardet.detect(raw).get("encoding") or "utf-8"
                return pd.read_csv(path, encoding=enc)
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(path)
        raise FileReadError(
            cause=f"文件「{file_path}」类型不受支持。",
            suggestion="请上传 CSV、XLS 或 XLSX 文件。",
        )
```

In `finance-mcp/proc/mcp_server/steps_runtime.py`, import `materialize_input_file` and change `_read_file_as_df(file_path: str)`:

```python
def _read_file_as_df(file_path: str) -> pd.DataFrame:
    with materialize_input_file(file_path) as local_path:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        suffix = path.suffix.lower()
        if suffix == ".csv":
            try:
                return pd.read_csv(path, encoding="utf-8-sig")
            except UnicodeDecodeError:
                import chardet

                raw = path.read_bytes()
                encoding = chardet.detect(raw).get("encoding") or "utf-8"
                return pd.read_csv(path, encoding=encoding)
        if suffix in {".xlsx", ".xls", ".xlsm", ".xlsb"}:
            return pd.read_excel(path, dtype=object)
        raise ValueError(f"不支持的文件类型: {suffix}")
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_input_resolver.py finance-mcp/tests/test_recon_execution_waiting_data.py finance-mcp/tests/test_execution_scheme_dataset_hydration.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add finance-mcp/storage/input_resolver.py finance-mcp/recon/mcp_server/recon_tool.py finance-mcp/proc/mcp_server/proc_rule.py finance-mcp/proc/mcp_server/merge_rule.py finance-mcp/proc/mcp_server/steps_runtime.py finance-mcp/tests/test_storage_input_resolver.py
git commit -m "feat: materialize stored inputs for processing"
```

## Task 8: Upload Generated Outputs and Stream Downloads

**Files:**
- Create: `finance-mcp/storage/output_manager.py`
- Modify: `finance-mcp/unified_mcp_server.py`
- Modify: `finance-mcp/recon/mcp_server/recon_tool.py`
- Modify: `finance-mcp/proc/mcp_server/proc_rule.py`
- Test: `finance-mcp/tests/test_storage_output_download.py`

- [ ] **Step 1: Write failing output tests**

Create `finance-mcp/tests/test_storage_output_download.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from storage import output_manager
from storage.refs import StorageObjectRef


def test_persist_generated_output_uploads_and_saves_metadata(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "result.xlsx"
    output.write_bytes(b"xlsx")
    saved: dict = {}

    class FakeClient:
        def put_file(self, source_path, *, key, original_filename, content_type="", checksum=""):
            assert Path(source_path) == output
            return StorageObjectRef(
                provider="oss",
                bucket="bucket-a",
                key=key,
                original_filename=original_filename,
                content_type=content_type,
                size_bytes=4,
            )

    monkeypatch.setattr(output_manager, "storage_from_env", lambda local_root: FakeClient())
    monkeypatch.setattr(
        output_manager.repository,
        "save_storage_object_metadata",
        lambda **kwargs: saved.update(kwargs) or {"logical_path": kwargs["logical_path"]},
    )
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_PREFIX", "financial-ai/prod")
    monkeypatch.setenv("OSS_BUCKET", "bucket-a")

    logical_path = output_manager.persist_generated_output(
        output,
        module="recon",
        owner_user_id="user-1",
        company_id="company-1",
        rule_code="rule-1",
        run_id="run-1",
    )

    assert logical_path == "/output/recon/result.xlsx"
    assert saved["ref"].key.startswith("financial-ai/prod/recon-output/company-1/")
    assert saved["module"] == "recon"


def test_legacy_local_backend_keeps_local_path(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "result.xlsx"
    output.write_bytes(b"xlsx")
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    logical_path = output_manager.persist_generated_output(
        output,
        module="recon",
        owner_user_id="user-1",
        company_id="company-1",
        rule_code="rule-1",
        run_id="run-1",
    )

    assert logical_path == "/output/recon/result.xlsx"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_output_download.py -v
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement output manager**

Create `finance-mcp/storage/output_manager.py`:

```python
from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path

from security_utils import PROC_OUTPUT_ROOT, RECON_OUTPUT_ROOT
from storage.client import storage_from_env
from storage.config import StorageSettings
from storage import repository


def _output_key(*, module: str, company_id: str, run_id: str, filename: str) -> str:
    settings = StorageSettings.from_env()
    now = datetime.now()
    purpose = "recon-output" if module == "recon" else "proc-output"
    return (
        f"{settings.oss_prefix.strip('/')}/{purpose}/{company_id}/"
        f"{now:%Y}/{now:%m}/{now:%d}/{run_id or 'manual'}/{filename}"
    ).strip("/")


def _local_root_for_module(module: str) -> Path:
    return RECON_OUTPUT_ROOT if module == "recon" else PROC_OUTPUT_ROOT


def persist_generated_output(
    output_path: str | Path,
    *,
    module: str,
    owner_user_id: str,
    company_id: str,
    rule_code: str,
    run_id: str = "",
) -> str:
    path = Path(output_path)
    logical_path = f"/output/{module}/{path.name}" if module == "recon" else f"/output/{module}/{rule_code}/{path.name}"
    settings = StorageSettings.from_env()
    if settings.backend != "oss":
        return logical_path

    client = storage_from_env(local_root=_local_root_for_module(module))
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    ref = client.put_file(
        path,
        key=_output_key(module=module, company_id=company_id, run_id=run_id, filename=path.name),
        original_filename=path.name,
        content_type=content_type,
    )
    repository.save_storage_object_metadata(
        owner_user_id=owner_user_id,
        company_id=company_id,
        module=module,
        logical_path=logical_path,
        ref=ref,
        metadata={"rule_code": rule_code, "run_id": run_id},
    )
    return logical_path
```

- [ ] **Step 4: Update generated output writers**

In `finance-mcp/recon/mcp_server/recon_tool.py`, import:

```python
from storage.output_manager import persist_generated_output
```

After `write_output_metadata(...)`, call:

```python
        logical_output_path = persist_generated_output(
            output_path,
            module="recon",
            owner_user_id=user_id,
            company_id=str(user_info.get("company_id") or ""),
            rule_code=rule_code,
            run_id=str(rule.get("run_id") or ""),
        )
```

Use `logical_output_path` when building download URL path if it starts with `/output/recon/`; keep `output_file` as local `output_path` for existing anomaly extraction in the same process.

In `finance-mcp/proc/mcp_server/proc_rule.py`, call `persist_generated_output()` after each `write_output_metadata(...)` for generated and merged files. Keep returned logical path in each item:

```python
            f["storage_output_path"] = persist_generated_output(
                output_file,
                module="proc",
                owner_user_id=user_id,
                company_id=str(user_info.get("company_id") or ""),
                rule_code=rule_code,
                run_id=str(run_context.get("run_id") or ""),
            )
```

Use `storage_output_path` for future download URL construction when present.

- [ ] **Step 5: Extend output download route for storage metadata**

In `finance-mcp/unified_mcp_server.py`, import:

```python
from storage import repository
from storage.client import storage_from_env
from storage.refs import parse_storage_ref
```

In `download_output_file()`, after constructing module/file_path and before local `full_path.exists()` check, add:

```python
    logical_path = f"/output/{module}/{file_path}"
    storage_row = repository.get_storage_object_by_logical_path(logical_path)
    if storage_row:
        owner_user_id = str(storage_row.get("owner_user_id") or "")
        current_user_id = str(user.get("user_id") or user.get("id") or "")
        current_role = str(user.get("role") or "")
        if current_role != "admin" and (not owner_user_id or owner_user_id != current_user_id):
            return JSONResponse({"error": "无权下载该文件"}, status_code=403)
        ref = parse_storage_ref(storage_row)
        client = storage_from_env(local_root=output_dir)
        data = client.read_bytes(ref)
        from urllib.parse import quote
        filename = ref.original_filename or Path(file_path).name
        encoded_filename = quote(filename, safe="")
        return Response(
            data,
            media_type=ref.content_type or "application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
```

Leave the existing local sidecar flow unchanged for legacy files.

- [ ] **Step 6: Run tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_storage_output_download.py finance-mcp/tests/test_unified_mcp_recon_auto_routes.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-mcp/storage/output_manager.py finance-mcp/unified_mcp_server.py finance-mcp/recon/mcp_server/recon_tool.py finance-mcp/proc/mcp_server/proc_rule.py finance-mcp/tests/test_storage_output_download.py
git commit -m "feat: store generated outputs in oss"
```

## Task 9: Browser-Agent OSS Capture Upload

**Files:**
- Create: `finance-agents/browser-agent/finance_browser_agent/storage_client.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
- Test: `finance-mcp/tests/test_browser_dispatcher.py`
- Test: `finance-agents/data-agent/tests/test_browser_agent_gateway.py`

- [ ] **Step 1: Write failing browser capture normalization tests**

In `finance-mcp/tests/test_browser_dispatcher.py`, add a test near `test_dispatcher_persists_capture_files`:

```python
def test_dispatcher_persists_oss_capture_metadata() -> None:
    fake_db = FakeDb()
    manager = FakeAgentConnectionManager()
    manager.register_result(
        "agent-001",
        {
            "job_id": "job-001",
            "status": "success",
            "records": [],
            "capture_files": [
                {
                    "storage_path": "oss://bucket-a/browser-captures/c1/qn.csv",
                    "storage_provider": "oss",
                    "storage_bucket": "bucket-a",
                    "storage_key": "browser-captures/c1/qn.csv",
                    "storage_uri": "oss://bucket-a/browser-captures/c1/qn.csv",
                    "content_type": "text/csv",
                    "size_bytes": 20,
                    "encoding": "utf-8",
                    "checksum": "sha256:abc",
                    "row_count": 0,
                }
            ],
        },
    )

    dispatcher = BrowserPlaybookDispatcher(db=fake_db, connections=manager)
    dispatcher.run_once()

    capture = fake_db.capture_files[0]["capture_files"][0]
    assert capture["storage_provider"] == "oss"
    assert capture["storage_key"] == "browser-captures/c1/qn.csv"
```

- [ ] **Step 2: Run current browser tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_dispatcher.py::test_dispatcher_persists_oss_capture_metadata -v
```

Expected: PASS. The dispatcher should pass capture dicts through without filtering because `insert_browser_capture_files()` owns persistence shaping.

- [ ] **Step 3: Implement browser-agent OSS uploader**

Create `finance-agents/browser-agent/finance_browser_agent/storage_client.py`:

```python
from __future__ import annotations

import mimetypes
import os
from datetime import datetime
from pathlib import Path
from typing import Any


def _storage_backend() -> str:
    return os.getenv("STORAGE_BACKEND", "local").strip().lower() or "local"


def _safe_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in str(value or ""))


def _build_capture_key(*, company_id: str, shop_id: str, biz_date: str, sync_job_id: str, filename: str) -> str:
    prefix = os.getenv("OSS_PREFIX", "financial-ai/prod").strip().strip("/")
    if not biz_date:
        biz_date = datetime.now().strftime("%Y-%m-%d")
    return (
        f"{prefix}/browser-captures/{_safe_segment(company_id)}/{_safe_segment(shop_id)}/"
        f"{_safe_segment(biz_date)}/{_safe_segment(sync_job_id)}/{_safe_segment(filename)}"
    )


def upload_capture_file_if_configured(
    path: str | Path,
    *,
    company_id: str,
    shop_id: str,
    biz_date: str,
    sync_job_id: str,
) -> dict[str, Any]:
    local_path = Path(path)
    if _storage_backend() != "oss":
        return {
            "storage_path": str(local_path),
            "storage_provider": "local",
            "storage_bucket": "",
            "storage_key": "",
            "storage_uri": str(local_path),
            "content_type": mimetypes.guess_type(local_path.name)[0] or "",
            "size_bytes": local_path.stat().st_size if local_path.exists() else 0,
        }

    bucket_name = os.getenv("OSS_BUCKET", "").strip()
    endpoint = os.getenv("OSS_ENDPOINT", "").strip()
    access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "").strip()
    access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "").strip()
    if not all([bucket_name, endpoint, access_key_id, access_key_secret]):
        raise RuntimeError("OSS 配置不完整，browser-agent 无法上传原始下载文件")

    import oss2

    key = _build_capture_key(
        company_id=company_id,
        shop_id=shop_id,
        biz_date=biz_date,
        sync_job_id=sync_job_id,
        filename=local_path.name,
    )
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    bucket.put_object_from_file(key, str(local_path), headers={"Content-Type": content_type})
    uri = f"oss://{bucket_name}/{key}"
    return {
        "storage_path": uri,
        "storage_provider": "oss",
        "storage_bucket": bucket_name,
        "storage_key": key,
        "storage_uri": uri,
        "content_type": content_type,
        "size_bytes": local_path.stat().st_size,
    }
```

- [ ] **Step 4: Enrich capture files after download**

In `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`, import:

```python
from finance_browser_agent.storage_client import upload_capture_file_if_configured
```

Add this helper near `_save_download()`:

```python
def _append_capture_file(
    target: Path,
    *,
    message: dict[str, Any],
    params: dict[str, Any],
    capture_files: list[dict[str, Any]],
) -> None:
    storage_meta = upload_capture_file_if_configured(
        target,
        company_id=str(message.get("company_id") or params.get("company_id") or ""),
        shop_id=str(message.get("shop_id") or params.get("shop_id") or ""),
        biz_date=str(params.get("biz_date") or ""),
        sync_job_id=str(message.get("job_id") or ""),
    )
    capture_files.append({**storage_meta, "encoding": "", "checksum": "", "row_count": 0})
```

Then replace each direct capture append:

```python
        _append_capture_file(
            target,
            message=message,
            params=params,
            capture_files=capture_files,
        )
```

Apply this in `_save_download`, direct `download`, history download, and qianiu export download branches.

- [ ] **Step 5: Ensure dispatcher passes company_id to browser-agent**

In `finance-mcp/browser_playbook/dispatcher.py` and `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`, include `company_id` in the message sent to the runner:

```python
            "company_id": company_id,
```

For `dispatcher_loop.py`, use the claimed job `company_id`.

- [ ] **Step 6: Run browser tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest finance-mcp/tests/test_browser_dispatcher.py finance-agents/data-agent/tests/test_browser_agent_gateway.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-agents/browser-agent/finance_browser_agent/storage_client.py finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-mcp/browser_playbook/dispatcher.py finance-mcp/tests/test_browser_dispatcher.py
git commit -m "feat: upload browser captures to oss"
```

## Task 10: Environment, Docker, and Logrotate

**Files:**
- Modify: `.env.example`
- Modify: `env.prod.example`
- Modify: `deploy.env.example`
- Modify: `docker-compose.prod.yml`
- Create: `deploy/logrotate/financial-ai`
- Modify: `docs/deployment/ghcr-ecs.md`
- Test: shell validation commands

- [ ] **Step 1: Add env examples**

In `.env.example`, add:

```env
# Storage backend: local for development, oss for production
STORAGE_BACKEND=local
OSS_BUCKET=
OSS_ENDPOINT=
OSS_REGION=
OSS_ACCESS_KEY_ID=
OSS_ACCESS_KEY_SECRET=
OSS_PREFIX=financial-ai/dev
OSS_PRESIGN_EXPIRE_SECONDS=900
OSS_UPLOAD_MAX_SIZE=104857600
```

In `env.prod.example`, add:

```env
# Alibaba Cloud OSS private bucket
STORAGE_BACKEND=oss
OSS_BUCKET=<private-bucket-name>
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OSS_REGION=cn-hangzhou
OSS_ACCESS_KEY_ID=<oss-access-key-id>
OSS_ACCESS_KEY_SECRET=<oss-access-key-secret>
OSS_PREFIX=financial-ai/prod
OSS_PRESIGN_EXPIRE_SECONDS=900
OSS_UPLOAD_MAX_SIZE=104857600
```

In `deploy.env.example`, add comments:

```env
# Docker compose image selection only; runtime OSS secrets live in .env.prod.
```

- [ ] **Step 2: Confirm Docker log options remain on every service**

Inspect `docker-compose.prod.yml`. If any service lacks logging options, add:

```yaml
    logging:
      driver: json-file
      options:
        max-size: "50m"
        max-file: "5"
```

Do not remove existing volume mounts; they remain temp/legacy compatibility.

- [ ] **Step 3: Add local logrotate config**

Create `deploy/logrotate/financial-ai`:

```text
/Users/kevin/workspace/financial-ai/logs/*.log {
    size 50M
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

- [ ] **Step 4: Update deployment docs**

In `docs/deployment/ghcr-ecs.md`, add an "OSS Storage" section:

```markdown
## OSS Storage

Production should set `STORAGE_BACKEND=oss` in `/opt/tally/.env.prod` and use a private OSS bucket.
The application only serves downloads through backend-authenticated routes. Do not make the bucket
public.

Required variables:

```env
STORAGE_BACKEND=oss
OSS_BUCKET=<private-bucket-name>
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
OSS_REGION=cn-hangzhou
OSS_ACCESS_KEY_ID=<oss-access-key-id>
OSS_ACCESS_KEY_SECRET=<oss-access-key-secret>
OSS_PREFIX=financial-ai/prod
```

The Windows browser-agent must use the same OSS variables so raw browser downloads are uploaded
before `browser_sync_job_complete` reports success.
```

Add a "Logs" section:

```markdown
## Logs

Docker JSON logs are capped at `50m x 5` per service in `docker-compose.prod.yml`.

For script-based local deployments, install the provided logrotate config or adapt the path:

```bash
sudo cp deploy/logrotate/financial-ai /etc/logrotate.d/financial-ai
sudo logrotate -d /etc/logrotate.d/financial-ai
```
```

- [ ] **Step 5: Validate compose and docs**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
docker compose -f docker-compose.prod.yml config >/tmp/tally-compose-config.yml
rg -n "max-size: 50m|max-file: '5'|max-file: \"5\"" /tmp/tally-compose-config.yml
```

Expected: compose config succeeds and log options appear for all services.

Run:

```bash
logrotate -d deploy/logrotate/financial-ai
```

Expected: debug output shows the `logs/*.log` pattern. If `logrotate` is unavailable locally, note that in the final execution report and validate syntax visually.

- [ ] **Step 6: Commit**

```bash
git add .env.example env.prod.example deploy.env.example docker-compose.prod.yml deploy/logrotate/financial-ai docs/deployment/ghcr-ecs.md
git commit -m "chore: document oss storage and log rotation"
```

## Task 11: End-to-End Verification

**Files:**
- No new files expected unless fixing issues found by verification.

- [ ] **Step 1: Run finance-mcp focused tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest \
  finance-mcp/tests/test_storage_refs.py \
  finance-mcp/tests/test_storage_clients.py \
  finance-mcp/tests/test_storage_repository.py \
  finance-mcp/tests/test_storage_upload_tool.py \
  finance-mcp/tests/test_storage_input_resolver.py \
  finance-mcp/tests/test_storage_output_download.py \
  finance-mcp/tests/test_browser_capture_files.py \
  finance-mcp/tests/test_browser_dispatcher.py \
  -v
```

Expected: PASS.

- [ ] **Step 2: Run data-agent focused tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
pytest \
  finance-agents/data-agent/tests/test_upload_presign_api.py \
  finance-agents/data-agent/tests/test_browser_agent_gateway.py \
  finance-agents/data-agent/tests/recon/test_scheme_execution_proc_routing.py \
  -v
```

Expected: PASS.

- [ ] **Step 3: Run frontend focused tests**

Run:

```bash
cd /Users/kevin/workspace/financial-ai/finance-web
npm run test -- chat-upload-direct-oss.spec.tsx
npx tsc --noEmit
```

Expected: PASS and TypeScript check exits 0.

- [ ] **Step 4: Run production compose validation**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
docker compose -f docker-compose.prod.yml config >/tmp/tally-compose-config.yml
```

Expected: exit 0.

- [ ] **Step 5: Start services locally**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-mcp, data-agent, finance-cron, recon-worker, and finance-web start successfully.

- [ ] **Step 6: Health checks**

Run:

```bash
curl -s http://127.0.0.1:3335/health
curl -s http://127.0.0.1:8100/health
curl -I http://127.0.0.1:5173/
```

Expected: first two commands return healthy JSON or `ok`; web returns HTTP 200.

- [ ] **Step 7: Commit verification fixes if needed**

If verification required fixes, commit them:

```bash
git add <changed-files>
git commit -m "fix: stabilize oss storage rollout"
```

If no fixes were needed, do not create an empty commit.

## Self-Review

- Spec coverage: The plan covers OSS private bucket storage for uploads, proc/recon outputs, browser raw downloads, backend-proxied downloads, local fallback, legacy file compatibility, Docker JSON log limits, local logrotate, configuration, tests, and rollout.
- Placeholder scan: No `TBD`, `TODO`, or "implement later" placeholders are present. Protocol methods use explicit `raise NotImplementedError` bodies, and output/browser examples include concrete calls instead of ellipsis placeholders.
- Type consistency: `StorageObjectRef`, `StorageSettings`, `StorageClient`, `storage_from_env`, `materialize_input_file`, and `persist_generated_output` are introduced before later tasks use them.

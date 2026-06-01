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
            content_type=content_type,
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
            content_type=content_type,
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
        url = self.bucket.sign_url(
            "PUT",
            safe_key,
            self.settings.oss_presign_expire_seconds,
            headers=headers,
        )
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

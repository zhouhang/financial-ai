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
            original_filename=str(
                value.get("original_filename") or value.get("file_name") or ""
            ).strip(),
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

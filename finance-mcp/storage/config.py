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

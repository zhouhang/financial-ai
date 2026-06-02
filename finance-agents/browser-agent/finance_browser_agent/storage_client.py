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


def _build_capture_key(
    *,
    company_id: str,
    shop_id: str,
    biz_date: str,
    sync_job_id: str,
    filename: str,
) -> str:
    prefix = os.getenv("OSS_PREFIX", "financial-ai/prod").strip().strip("/")
    if not biz_date:
        biz_date = datetime.now().strftime("%Y-%m-%d")
    segments = [
        prefix,
        "browser-captures",
        _safe_segment(company_id),
        _safe_segment(shop_id),
        _safe_segment(biz_date),
        _safe_segment(sync_job_id),
        _safe_segment(filename),
    ]
    return "/".join(segment for segment in segments if segment)


def _metadata_for_local(local_path: Path) -> dict[str, Any]:
    return {
        "storage_path": str(local_path),
        "storage_provider": "local",
        "storage_bucket": "",
        "storage_key": "",
        "storage_uri": str(local_path),
        "local_path": str(local_path),
        "original_filename": local_path.name,
        "content_type": mimetypes.guess_type(local_path.name)[0] or "",
        "size_bytes": local_path.stat().st_size if local_path.exists() else 0,
    }


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
        return _metadata_for_local(local_path)

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
    content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    bucket.put_object_from_file(key, str(local_path), headers={"Content-Type": content_type})
    uri = f"oss://{bucket_name}/{key}"
    return {
        "storage_path": uri,
        "storage_provider": "oss",
        "storage_bucket": bucket_name,
        "storage_key": key,
        "storage_uri": uri,
        "local_path": str(local_path),
        "original_filename": local_path.name,
        "content_type": content_type,
        "size_bytes": local_path.stat().st_size,
    }

from __future__ import annotations

import sys
from pathlib import Path

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from storage.config import StorageSettings
from storage.refs import StorageObjectRef, parse_storage_ref


STORAGE_ENV_VARS = [
    "STORAGE_BACKEND",
    "OSS_BUCKET",
    "OSS_ENDPOINT",
    "OSS_REGION",
    "OSS_ACCESS_KEY_ID",
    "OSS_ACCESS_KEY_SECRET",
    "OSS_PREFIX",
    "OSS_PRESIGN_EXPIRE_SECONDS",
    "OSS_UPLOAD_MAX_SIZE",
]


def clear_storage_env(monkeypatch) -> None:
    for env_var in STORAGE_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


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


def test_parse_metadata_dict_uses_storage_uri_for_missing_oss_fields() -> None:
    ref = parse_storage_ref(
        {
            "storage_provider": "oss",
            "storage_uri": "oss://bucket-from-uri/recon-output/c1/file.xlsx",
            "original_filename": "file.xlsx",
        }
    )

    assert ref.provider == "oss"
    assert ref.bucket == "bucket-from-uri"
    assert ref.key == "recon-output/c1/file.xlsx"
    assert ref.local_path == ""
    assert ref.original_filename == "file.xlsx"


def test_parse_metadata_dict_preserves_explicit_fields_over_storage_uri() -> None:
    ref = parse_storage_ref(
        {
            "storage_provider": "oss",
            "storage_bucket": "explicit-bucket",
            "storage_key": "explicit/key.xlsx",
            "storage_uri": "oss://bucket-from-uri/recon-output/c1/file.xlsx",
        }
    )

    assert ref.provider == "oss"
    assert ref.bucket == "explicit-bucket"
    assert ref.key == "explicit/key.xlsx"


def test_storage_settings_default_local(monkeypatch) -> None:
    clear_storage_env(monkeypatch)

    settings = StorageSettings.from_env()

    assert settings.backend == "local"
    assert settings.oss_presign_expire_seconds == 900
    assert settings.oss_upload_max_size == 100 * 1024 * 1024


def test_storage_settings_oss_requires_bucket_and_endpoint(monkeypatch) -> None:
    clear_storage_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "")
    monkeypatch.setenv("OSS_ENDPOINT", "")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "")
    monkeypatch.setenv("OSS_PRESIGN_EXPIRE_SECONDS", "900")
    monkeypatch.setenv("OSS_UPLOAD_MAX_SIZE", str(100 * 1024 * 1024))

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

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_browser_agent.storage_client import upload_capture_file_if_configured


def test_upload_capture_file_local_metadata(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    source = tmp_path / "export.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    metadata = upload_capture_file_if_configured(
        source,
        company_id="company-001",
        shop_id="shop-001",
        biz_date="2026-05-18",
        sync_job_id="job-001",
    )

    assert metadata == {
        "storage_path": str(source),
        "storage_provider": "local",
        "storage_bucket": "",
        "storage_key": "",
        "storage_uri": str(source),
        "local_path": str(source),
        "original_filename": "export.csv",
        "content_type": "text/csv",
        "size_bytes": source.stat().st_size,
    }


def test_upload_capture_file_to_oss(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakeAuth:
        def __init__(self, access_key_id: str, access_key_secret: str) -> None:
            captured["auth"] = (access_key_id, access_key_secret)

    class FakeBucket:
        def __init__(self, auth, endpoint: str, bucket_name: str) -> None:
            captured["bucket"] = (auth, endpoint, bucket_name)

        def put_object_from_file(self, key: str, filename: str, headers=None) -> None:
            captured["upload"] = (key, filename, headers)

    monkeypatch.setitem(sys.modules, "oss2", SimpleNamespace(Auth=FakeAuth, Bucket=FakeBucket))
    monkeypatch.setenv("STORAGE_BACKEND", "oss")
    monkeypatch.setenv("OSS_BUCKET", "bucket-a")
    monkeypatch.setenv("OSS_ENDPOINT", "https://oss-cn.example.aliyuncs.com")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "sk")
    monkeypatch.setenv("OSS_PREFIX", "financial-ai/prod")
    source = tmp_path / "export.csv"
    source.write_text("a,b\n1,2\n", encoding="utf-8")

    metadata = upload_capture_file_if_configured(
        source,
        company_id="company-001",
        shop_id="shop-001",
        biz_date="2026-05-18",
        sync_job_id="job-001",
    )

    expected_key = "financial-ai/prod/browser-captures/company-001/shop-001/2026-05-18/job-001/export.csv"
    assert captured["auth"] == ("ak", "sk")
    assert captured["bucket"][1:] == ("https://oss-cn.example.aliyuncs.com", "bucket-a")
    assert captured["upload"] == (expected_key, str(source), {"Content-Type": "text/csv"})
    assert metadata == {
        "storage_path": f"oss://bucket-a/{expected_key}",
        "storage_provider": "oss",
        "storage_bucket": "bucket-a",
        "storage_key": expected_key,
        "storage_uri": f"oss://bucket-a/{expected_key}",
        "local_path": str(source),
        "original_filename": "export.csv",
        "content_type": "text/csv",
        "size_bytes": source.stat().st_size,
    }

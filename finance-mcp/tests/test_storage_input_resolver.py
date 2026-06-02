from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from storage import input_resolver
from storage.refs import StorageObjectRef
from recon.mcp_server import recon_tool


def test_materialize_input_file_falls_back_to_legacy_local_resolver(
    monkeypatch,
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "a.xlsx"
    legacy_path.write_bytes(b"legacy")

    monkeypatch.setattr(
        input_resolver.repository,
        "get_storage_object_by_logical_path",
        lambda logical_path: None,
    )
    monkeypatch.setattr(
        input_resolver,
        "resolve_recon_input_file_path",
        lambda file_ref: legacy_path,
    )

    with input_resolver.materialize_input_file("/uploads/a.xlsx") as resolved:
        assert resolved == legacy_path
        assert resolved.read_bytes() == b"legacy"

    assert legacy_path.exists()


def test_materialize_input_file_downloads_storage_object_to_temp_file(
    monkeypatch,
) -> None:
    logical_path = "/uploads/oss/company-1/a.csv"
    row = {
        "logical_path": logical_path,
        "storage_provider": "oss",
        "storage_bucket": "finance-oss",
        "storage_key": "uploads/company-1/a.csv",
        "storage_uri": "oss://finance-oss/uploads/company-1/a.csv",
        "original_filename": "a.csv",
    }
    calls: dict[str, object] = {}

    class FakeStorageClient:
        def read_bytes(self, ref: StorageObjectRef) -> bytes:
            calls["ref"] = ref
            return b"col\n1\n"

    monkeypatch.setattr(
        input_resolver.repository,
        "get_storage_object_by_logical_path",
        lambda requested_path: row if requested_path == logical_path else None,
    )

    def fake_storage_from_env(*, local_root: str | Path) -> FakeStorageClient:
        calls["local_root"] = local_root
        return FakeStorageClient()

    monkeypatch.setattr(input_resolver, "storage_from_env", fake_storage_from_env)

    with input_resolver.materialize_input_file(logical_path) as resolved:
        temp_path = resolved
        assert temp_path.suffix == ".csv"
        assert temp_path.read_bytes() == b"col\n1\n"
        assert temp_path.exists()

    assert not temp_path.exists()
    assert calls["local_root"] == input_resolver.UPLOAD_ROOT
    assert calls["ref"] == StorageObjectRef(
        provider="oss",
        bucket="finance-oss",
        key="uploads/company-1/a.csv",
        original_filename="a.csv",
    )


def test_materialize_input_file_looks_up_sheet_ref_by_base_logical_path(
    monkeypatch,
) -> None:
    base_ref = "/uploads/oss/company-1/workbook.xlsx"
    sheet_ref = input_resolver.build_sheet_input_ref(base_ref, "Sheet2")
    requested_paths: list[str] = []
    row = {
        "logical_path": base_ref,
        "storage_provider": "oss",
        "storage_bucket": "finance-oss",
        "storage_key": "uploads/company-1/workbook.xlsx",
        "storage_uri": "oss://finance-oss/uploads/company-1/workbook.xlsx",
        "original_filename": "workbook.xlsx",
    }

    class FakeStorageClient:
        def read_bytes(self, ref: StorageObjectRef) -> bytes:
            return b"stored"

    def fake_get_storage_object_by_logical_path(logical_path: str):
        requested_paths.append(logical_path)
        return row if logical_path == base_ref else None

    monkeypatch.setattr(
        input_resolver.repository,
        "get_storage_object_by_logical_path",
        fake_get_storage_object_by_logical_path,
    )
    monkeypatch.setattr(
        input_resolver,
        "storage_from_env",
        lambda *, local_root: FakeStorageClient(),
    )

    with input_resolver.materialize_input_file(sheet_ref) as resolved:
        assert resolved.read_bytes() == b"stored"

    assert requested_paths == [base_ref]


def test_sheet_input_ref_uses_base_ref_for_materialization() -> None:
    ref = input_resolver.build_sheet_input_ref(
        "/uploads/oss/company-1/workbook.xlsx",
        "退款 Sheet",
    )

    assert ref == "/uploads/oss/company-1/workbook.xlsx#sheet=%E9%80%80%E6%AC%BE%20Sheet"
    assert input_resolver.split_input_file_ref(ref) == (
        "/uploads/oss/company-1/workbook.xlsx",
        "退款 Sheet",
    )


def test_recon_reader_reads_selected_excel_sheet(monkeypatch, tmp_path: Path) -> None:
    workbook_path = tmp_path / "workbook.xlsx"
    with pd.ExcelWriter(workbook_path, engine="openpyxl") as writer:
        pd.DataFrame({"col": ["default"]}).to_excel(writer, index=False, sheet_name="Sheet1")
        pd.DataFrame({"col": ["selected"]}).to_excel(writer, index=False, sheet_name="Sheet2")

    def fake_materialize_input_file(file_ref: str):
        assert file_ref == "/uploads/oss/company-1/workbook.xlsx#sheet=Sheet2"

        from contextlib import contextmanager

        @contextmanager
        def _materialized():
            yield workbook_path

        return _materialized()

    monkeypatch.setattr(recon_tool, "materialize_input_file", fake_materialize_input_file)

    df = recon_tool._read_file_as_df("/uploads/oss/company-1/workbook.xlsx#sheet=Sheet2")

    assert df["col"].tolist() == ["selected"]

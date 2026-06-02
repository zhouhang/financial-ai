from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from security_utils import UPLOAD_ROOT, resolve_recon_input_file_path, resolve_upload_file_path
from storage import repository
from storage.client import storage_from_env
from storage.refs import parse_storage_ref
from storage.tempfiles import materialize_to_temp


def build_sheet_input_ref(base_ref: str, sheet_name: str) -> str:
    """Attach an Excel sheet selector to a stable logical input ref."""
    clean_base_ref, _ = split_input_file_ref(base_ref)
    return f"{clean_base_ref}#sheet={quote(str(sheet_name or ''), safe='')}"


def split_input_file_ref(file_ref: str) -> tuple[str, str | None]:
    """Split a logical input ref into the storage-resolvable base ref and sheet selector."""
    raw_ref = str(file_ref or "").strip()
    parsed = urlsplit(raw_ref)
    fragment = parsed.fragment
    if not fragment:
        return raw_ref, None

    params = parse_qs(fragment, keep_blank_values=True)
    sheet_values = params.get("sheet")
    if not sheet_values:
        return raw_ref, None
    base_ref = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
    return base_ref, str(sheet_values[0])


@contextmanager
def materialize_input_file(file_ref: str, *, legacy_mode: str = "recon") -> Iterator[Path]:
    """Resolve an input file ref to a local path for the lifetime of this context."""
    base_ref, _ = split_input_file_ref(file_ref)
    row = repository.get_storage_object_by_logical_path(base_ref)
    if row:
        storage_ref = parse_storage_ref(row)
        client = storage_from_env(local_root=UPLOAD_ROOT)
        with materialize_to_temp(client, storage_ref) as path:
            yield path
        return

    if legacy_mode == "upload":
        yield resolve_upload_file_path(base_ref)
        return
    if legacy_mode == "recon":
        yield resolve_recon_input_file_path(base_ref)
        return
    raise ValueError(f"不支持的 legacy input 解析模式: {legacy_mode}")

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from security_utils import UPLOAD_ROOT, resolve_recon_input_file_path
from storage import repository
from storage.client import storage_from_env
from storage.refs import parse_storage_ref
from storage.tempfiles import materialize_to_temp


@contextmanager
def materialize_input_file(file_ref: str) -> Iterator[Path]:
    """Resolve an input file ref to a local path for the lifetime of this context."""
    row = repository.get_storage_object_by_logical_path(file_ref)
    if row:
        storage_ref = parse_storage_ref(row)
        client = storage_from_env(local_root=UPLOAD_ROOT)
        with materialize_to_temp(client, storage_ref) as path:
            yield path
        return

    yield resolve_recon_input_file_path(file_ref)

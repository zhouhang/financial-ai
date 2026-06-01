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

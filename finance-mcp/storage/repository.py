from __future__ import annotations

import json
from typing import Any

import psycopg2.extras

from auth import db as auth_db
from storage.refs import StorageObjectRef, parse_storage_ref


def save_storage_object_metadata(
    *,
    owner_user_id: str | None,
    company_id: str | None,
    module: str,
    logical_path: str,
    ref: StorageObjectRef | dict[str, Any] | str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert or update storage object metadata by logical path."""
    storage_ref = parse_storage_ref(ref)
    params: dict[str, Any] = {
        "owner_user_id": str(owner_user_id or "").strip() or None,
        "company_id": str(company_id or "").strip() or None,
        "module": str(module or "").strip(),
        "logical_path": str(logical_path or "").strip(),
        "storage_provider": storage_ref.provider,
        "storage_bucket": storage_ref.bucket,
        "storage_key": storage_ref.key,
        "storage_uri": storage_ref.to_uri(),
        "local_path": storage_ref.local_path,
        "original_filename": storage_ref.original_filename,
        "content_type": storage_ref.content_type,
        "size_bytes": storage_ref.size_bytes,
        "checksum": storage_ref.checksum,
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False, default=str),
    }

    conn_manager = auth_db.get_conn()
    with conn_manager as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO storage_objects (
                    owner_user_id, company_id, module, logical_path,
                    storage_provider, storage_bucket, storage_key, storage_uri,
                    local_path, original_filename, content_type, size_bytes,
                    checksum, metadata_json
                ) VALUES (
                    %(owner_user_id)s, %(company_id)s, %(module)s, %(logical_path)s,
                    %(storage_provider)s, %(storage_bucket)s, %(storage_key)s,
                    %(storage_uri)s, %(local_path)s, %(original_filename)s,
                    %(content_type)s, %(size_bytes)s, %(checksum)s,
                    %(metadata_json)s::jsonb
                )
                ON CONFLICT (logical_path) DO UPDATE SET
                    owner_user_id = EXCLUDED.owner_user_id,
                    company_id = EXCLUDED.company_id,
                    module = EXCLUDED.module,
                    storage_provider = EXCLUDED.storage_provider,
                    storage_bucket = EXCLUDED.storage_bucket,
                    storage_key = EXCLUDED.storage_key,
                    storage_uri = EXCLUDED.storage_uri,
                    local_path = EXCLUDED.local_path,
                    original_filename = EXCLUDED.original_filename,
                    content_type = EXCLUDED.content_type,
                    size_bytes = EXCLUDED.size_bytes,
                    checksum = EXCLUDED.checksum,
                    metadata_json = EXCLUDED.metadata_json
                RETURNING *
                """,
                params,
            )
            row = cur.fetchone()
            conn.commit()
    return dict(row or params)


def get_storage_object_by_logical_path(logical_path: str) -> dict[str, Any] | None:
    """Load one storage object by logical path."""
    params = {"logical_path": logical_path}
    conn_manager = auth_db.get_conn()
    with conn_manager as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM storage_objects
                WHERE logical_path = %(logical_path)s
                """,
                params,
            )
            row = cur.fetchone()
    return dict(row) if row else None

"""Thin browser collection record helpers."""

from __future__ import annotations

from typing import Any

from auth import db as auth_db


def upsert_browser_collection_records(**kwargs: Any) -> dict[str, Any]:
    """Proxy to auth.db browser collection record upsert."""
    return auth_db.upsert_browser_collection_records(**kwargs)


def list_browser_collection_records(**kwargs: Any) -> list[dict[str, Any]]:
    """Proxy to auth.db browser collection record listing."""
    return auth_db.list_browser_collection_records(**kwargs)


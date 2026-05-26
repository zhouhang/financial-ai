"""Helpers for carrying browser handoff context into collection jobs."""

from __future__ import annotations

from typing import Any


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def handoff_owner_from_mapping(owner_mapping_json: Any) -> dict[str, Any]:
    default_owner = _safe_dict(_safe_dict(owner_mapping_json).get("default_owner"))
    owner: dict[str, Any] = {}
    name = str(default_owner.get("name") or default_owner.get("display_name") or "").strip()
    identifier = str(
        default_owner.get("identifier")
        or default_owner.get("owner_identifier")
        or default_owner.get("user_id")
        or ""
    ).strip()
    if name:
        owner["name"] = name
    if identifier:
        owner["identifier"] = identifier
    return owner


def build_handoff_collection_params(source: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    channel_config_id = str(source.get("channel_config_id") or "").strip()
    if channel_config_id:
        params["handoff_channel_config_id"] = channel_config_id
    owner = handoff_owner_from_mapping(source.get("owner_mapping_json"))
    if owner:
        params["handoff_owner"] = owner
    return params

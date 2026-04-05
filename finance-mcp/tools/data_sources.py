"""Unified data source MCP tools.

Phase-1 goals:
- Persist data sources / configs / sync jobs in PostgreSQL
- Keep `platform_*` tools intact and reuse them for OAuth platforms
- Support publish-only snapshot semantics for deterministic syncs
- Reserve browser / desktop_cli for future agent-assisted execution
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2.extras
from mcp import Tool

from auth import db as auth_db
from auth.jwt_utils import get_user_from_token
from connectors.factory import build_connector
from tools.platform_connections import handle_tool_call as handle_platform_tool_call

logger = logging.getLogger("tools.data_sources")

SOURCE_KINDS = {
    "platform_oauth",
    "database",
    "api",
    "file",
    "browser",
    "desktop_cli",
}

DOMAIN_TYPES = {
    "ecommerce",
    "bank",
    "finance_mid",
    "erp",
    "supplier",
    "internal_business",
}

CONFIG_TYPES = ("connection", "extract", "mapping", "runtime")
AGENT_ASSISTED_KINDS = {"browser", "desktop_cli"}
HEALTH_STATUSES = {"unknown", "healthy", "warning", "error", "auth_expired", "disabled"}
DATASET_ORIGIN_TYPES = {"fixed", "discovered", "imported_openapi", "manual"}


def _default_execution_mode(source_kind: str) -> str:
    return "agent_assisted" if source_kind in AGENT_ASSISTED_KINDS else "deterministic"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha1(_json_safe(payload).encode("utf-8")).hexdigest()


def _require_user(auth_token: str) -> dict[str, Any]:
    token = str(auth_token or "").strip()
    if not token:
        raise ValueError("未提供认证 token，请先登录")
    user = get_user_from_token(token)
    if not user:
        raise ValueError("token 无效或已过期，请重新登录")
    if not user.get("company_id"):
        raise ValueError("当前用户未绑定公司，无法配置数据源")
    return user


def _normalize_source_kind(value: Any) -> str:
    source_kind = str(value or "").strip().lower()
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"不支持的 source_kind: {source_kind}")
    return source_kind


def _normalize_domain_type(value: Any) -> str:
    domain_type = str(value or "").strip().lower() or "internal_business"
    if domain_type not in DOMAIN_TYPES:
        raise ValueError(f"不支持的 domain_type: {domain_type}")
    return domain_type


def _normalize_execution_mode(source_kind: str, value: Any) -> str:
    mode = str(value or "").strip().lower() or _default_execution_mode(source_kind)
    if mode not in {"deterministic", "agent_assisted"}:
        raise ValueError(f"不支持的 execution_mode: {mode}")
    if source_kind in AGENT_ASSISTED_KINDS:
        return "agent_assisted"
    return mode


def _normalize_status(value: Any, *, default: str = "active") -> str:
    status = str(value or "").strip().lower() or default
    if status not in {"active", "disabled", "deleted"}:
        raise ValueError(f"不支持的 status: {status}")
    return status


def _normalize_bool(value: Any, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _source_id_from_args(arguments: dict[str, Any]) -> str:
    return str(arguments.get("source_id") or arguments.get("data_source_id") or "").strip()


def _dataset_id_from_args(arguments: dict[str, Any]) -> str:
    return str(arguments.get("dataset_id") or arguments.get("id") or "").strip()


def _resource_key_from_args(arguments: dict[str, Any]) -> str:
    if str(arguments.get("resource_key") or "").strip():
        return str(arguments.get("resource_key")).strip()
    params = arguments.get("params") or {}
    if isinstance(params, dict) and str(params.get("resource_key") or "").strip():
        return str(params.get("resource_key")).strip()
    return "default"


def _window_from_args(arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    window_start = str(arguments.get("window_start") or "").strip() or None
    window_end = str(arguments.get("window_end") or "").strip() or None
    window = arguments.get("window") or {}
    if isinstance(window, dict):
        window_start = window_start or str(window.get("start") or window.get("window_start") or "").strip() or None
        window_end = window_end or str(window.get("end") or window.get("window_end") or "").strip() or None
    return window_start, window_end


def _compute_idempotency_key(source_id: str, arguments: dict[str, Any]) -> str:
    explicit = str(arguments.get("idempotency_key") or "").strip()
    if explicit:
        return explicit
    window_start, window_end = _window_from_args(arguments)
    scope_payload = {
        "source_id": source_id,
        "resource_key": _resource_key_from_args(arguments),
        "window_start": window_start or "",
        "window_end": window_end or "",
        "params": arguments.get("params") or {},
    }
    return _hash_payload(scope_payload)


def _generate_source_code(source_kind: str, provider_code: str, name: str) -> str:
    if source_kind == "platform_oauth":
        return f"{source_kind}__{provider_code}"
    base = f"{source_kind}__{provider_code or 'default'}"
    digest = hashlib.sha1(f"{base}:{name}:{uuid.uuid4()}".encode("utf-8")).hexdigest()[:10]
    return f"{base}__{digest}"


def _resolve_provider_code(
    source_kind: str,
    *,
    provider_code: Any = "",
    connection_config: dict[str, Any] | None = None,
    current_provider_code: str = "",
) -> str:
    explicit = str(provider_code or "").strip().lower()
    if explicit:
        return explicit

    if current_provider_code.strip():
        return current_provider_code.strip().lower()

    cfg = dict(connection_config or {})
    if source_kind == "platform_oauth":
        return "platform_oauth"
    if source_kind == "database":
        db_type = str(cfg.get("db_type") or "").strip().lower()
        return db_type or "database"
    if source_kind == "api":
        return "custom_api"
    if source_kind == "file":
        return "manual_file"
    if source_kind == "browser":
        return "browser"
    if source_kind == "desktop_cli":
        return "desktop_cli"
    return source_kind


def _query_source_any_company(source_id: str) -> dict[str, Any] | None:
    conn_manager = auth_db.get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, code, name, source_kind, domain_type, provider_code,
                           execution_mode, description, status, is_enabled,
                           health_status, last_checked_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_sources
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (source_id,),
                )
                row = cur.fetchone()
                return auth_db._normalize_record(dict(row)) if row else None
    except Exception as exc:
        logger.error("query source by id failed: %s", exc, exc_info=True)
        return None


def _list_snapshot_rows(snapshot_id: str, limit: int = 20) -> list[dict[str, Any]]:
    conn_manager = auth_db.get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT item_key, item_payload, item_hash, created_at
                    FROM dataset_snapshot_items
                    WHERE snapshot_id = %s
                    ORDER BY id ASC
                    LIMIT %s
                    """,
                    (snapshot_id, max(1, min(limit, 100))),
                )
                rows = cur.fetchall()
                return [auth_db._normalize_record(dict(row)) for row in rows]
    except Exception as exc:
        logger.error("list snapshot rows failed: %s", exc, exc_info=True)
        return []


def _load_source_configs(source_id: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for config_type in CONFIG_TYPES:
        config_row = auth_db.get_unified_data_source_config(
            data_source_id=source_id,
            config_type=config_type,
            active_only=True,
        )
        result[config_type] = dict((config_row or {}).get("config") or {})
    return result


def _load_runtime_source(
    source_row: dict[str, Any],
    *,
    include_secret: bool,
) -> dict[str, Any]:
    source_id = str(source_row.get("id") or "")
    configs = _load_source_configs(source_id)
    credential = auth_db.get_unified_data_source_credentials(
        data_source_id=source_id,
        credential_type="default",
        include_secret=include_secret,
    )
    runtime_source = {
        **source_row,
        "connection_config": configs.get("connection") or {},
        "extract_config": configs.get("extract") or {},
        "mapping_config": configs.get("mapping") or {},
        "runtime_config": configs.get("runtime") or {},
        "auth_config": dict((credential or {}).get("credential_payload") or {}),
    }
    connector = build_connector(runtime_source)
    runtime_source["capabilities"] = connector.capabilities
    return runtime_source


def _normalize_health_status(value: Any, *, default: str = "unknown") -> str:
    health_status = str(value or "").strip().lower() or default
    if health_status not in HEALTH_STATUSES:
        return default
    return health_status


def _normalize_dataset_origin_type(value: Any, *, default: str = "manual") -> str:
    origin_type = str(value or "").strip().lower() or default
    if origin_type not in DATASET_ORIGIN_TYPES:
        return default
    return origin_type


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _pick_latest_iso(values: list[Any]) -> str:
    latest: datetime | None = None
    for value in values:
        parsed = _parse_datetime(value)
        if not parsed:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest else ""


def _sanitize_dataset_code(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    chars: list[str] = []
    for ch in text:
        chars.append(ch if ch.isalnum() else "_")
    cleaned = "".join(chars).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:128]


def _build_dataset_view(dataset_row: dict[str, Any]) -> dict[str, Any]:
    extract_config = dict(dataset_row.get("extract_config") or {})
    schema_summary = dict(dataset_row.get("schema_summary") or {})
    sync_strategy = dict(dataset_row.get("sync_strategy") or {})
    meta = dict(dataset_row.get("meta") or {})
    dataset_code = str(dataset_row.get("dataset_code") or "")
    return {
        "id": str(dataset_row.get("id") or ""),
        "data_source_id": str(dataset_row.get("data_source_id") or ""),
        "dataset_code": dataset_code,
        "dataset_name": str(dataset_row.get("dataset_name") or dataset_code),
        "resource_key": str(dataset_row.get("resource_key") or "default"),
        "dataset_kind": str(dataset_row.get("dataset_kind") or "table"),
        "origin_type": str(dataset_row.get("origin_type") or "manual"),
        "status": str(dataset_row.get("status") or "active"),
        "enabled": bool(dataset_row.get("is_enabled", True)),
        "health_status": _normalize_health_status(dataset_row.get("health_status")),
        "last_checked_at": dataset_row.get("last_checked_at"),
        "last_sync_at": dataset_row.get("last_sync_at"),
        "last_error_message": str(dataset_row.get("last_error_message") or ""),
        "extract_config": extract_config,
        "schema_summary": schema_summary,
        "sync_strategy": sync_strategy,
        "metadata": meta,
        "created_at": dataset_row.get("created_at"),
        "updated_at": dataset_row.get("updated_at"),
    }


def _summarize_datasets(dataset_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_health: dict[str, int] = {}
    enabled_count = 0
    active_count = 0
    for row in dataset_rows:
        status = str(row.get("status") or "active")
        health_status = _normalize_health_status(row.get("health_status"))
        by_status[status] = by_status.get(status, 0) + 1
        by_health[health_status] = by_health.get(health_status, 0) + 1
        if bool(row.get("is_enabled", True)):
            enabled_count += 1
        if status == "active":
            active_count += 1
    return {
        "total": len(dataset_rows),
        "active_count": active_count,
        "enabled_count": enabled_count,
        "by_status": by_status,
        "by_health_status": by_health,
        "last_sync_at": _pick_latest_iso([row.get("last_sync_at") for row in dataset_rows]),
        "last_checked_at": _pick_latest_iso([row.get("last_checked_at") for row in dataset_rows]),
    }


def _build_source_summary(source_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(source_row.get("id") or ""),
        "code": str(source_row.get("code") or ""),
        "name": str(source_row.get("name") or ""),
        "source_kind": str(source_row.get("source_kind") or ""),
        "provider_code": str(source_row.get("provider_code") or ""),
        "domain_type": str(source_row.get("domain_type") or ""),
        "execution_mode": str(source_row.get("execution_mode") or ""),
        "status": str(source_row.get("status") or "active"),
        "enabled": bool(source_row.get("is_enabled", True)),
    }


def _build_health_summary(source_row: dict[str, Any], dataset_rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_status = str(source_row.get("status") or "active")
    source_enabled = bool(source_row.get("is_enabled", True))
    source_health_status = _normalize_health_status(source_row.get("health_status"))
    source_last_error = str(source_row.get("last_error_message") or "")
    source_last_checked_at = source_row.get("last_checked_at")
    dataset_summary = _summarize_datasets(dataset_rows)
    dataset_health = dict(dataset_summary.get("by_health_status") or {})

    overall_status = "unknown"
    if source_status == "disabled" or not source_enabled:
        overall_status = "disabled"
    elif source_health_status in {"error", "auth_expired", "disabled"}:
        overall_status = "error"
    elif (dataset_health.get("error", 0) + dataset_health.get("auth_expired", 0) + dataset_health.get("disabled", 0)) > 0:
        overall_status = "error"
    elif source_health_status == "warning" or dataset_health.get("warning", 0) > 0:
        overall_status = "warning"
    elif source_health_status == "healthy" or dataset_health.get("healthy", 0) > 0:
        overall_status = "healthy"

    return {
        "overall_status": overall_status,
        "source": {
            "health_status": source_health_status,
            "last_checked_at": source_last_checked_at,
            "last_error_message": source_last_error,
        },
        "datasets": {
            "total": int(dataset_summary.get("total") or 0),
            "by_health_status": dataset_health,
            "last_checked_at": dataset_summary.get("last_checked_at"),
            "last_sync_at": dataset_summary.get("last_sync_at"),
        },
    }


def _load_source_datasets(company_id: str, source_id: str) -> list[dict[str, Any]]:
    return auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=source_id,
        status=None,
        include_deleted=False,
        limit=2000,
    )


def _update_dataset_health_by_resource(
    *,
    company_id: str,
    source_id: str,
    resource_key: str,
    health_status: str,
    last_error_message: str = "",
    last_sync_at: str | None = None,
) -> dict[str, Any] | None:
    dataset_row = auth_db.get_unified_data_source_dataset_by_source_resource(
        company_id=company_id,
        data_source_id=source_id,
        resource_key=resource_key,
        status=None,
    )
    if not dataset_row:
        return None
    return auth_db.update_unified_data_source_dataset_health(
        dataset_id=str(dataset_row.get("id") or ""),
        health_status=_normalize_health_status(health_status, default="unknown"),
        last_sync_at=last_sync_at,
        last_error_message=last_error_message,
    )


def _normalize_discovered_dataset(item: dict[str, Any], source_row: dict[str, Any], index: int) -> dict[str, Any]:
    resource_key = str(item.get("resource_key") or item.get("dataset_code") or f"default_{index + 1}").strip()
    dataset_code = _sanitize_dataset_code(item.get("dataset_code") or resource_key)
    if not dataset_code:
        dataset_code = f"dataset_{index + 1}"
    dataset_name = str(item.get("dataset_name") or resource_key or dataset_code).strip() or dataset_code
    return {
        "dataset_code": dataset_code[:128],
        "dataset_name": dataset_name[:255],
        "resource_key": resource_key[:100] or "default",
        "dataset_kind": str(item.get("dataset_kind") or "table")[:30],
        "origin_type": _normalize_dataset_origin_type(item.get("origin_type"), default="discovered"),
        "extract_config": dict(item.get("extract_config") or {}),
        "schema_summary": dict(item.get("schema_summary") or {}),
        "sync_strategy": dict(item.get("sync_strategy") or {}),
        "status": _normalize_status(item.get("status"), default="active"),
        "is_enabled": _normalize_bool(item.get("is_enabled"), default=True),
        "health_status": _normalize_health_status(item.get("health_status"), default="unknown"),
        "last_checked_at": item.get("last_checked_at"),
        "last_sync_at": item.get("last_sync_at"),
        "last_error_message": str(item.get("last_error_message") or ""),
        "meta": {
            **dict(item.get("meta") or {}),
            "discovered_from": str(source_row.get("source_kind") or ""),
            "discovered_provider": str(source_row.get("provider_code") or ""),
        },
    }


def _build_data_source_view(
    source_row: dict[str, Any],
    *,
    datasets: list[dict[str, Any]] | None = None,
    include_dataset_details: bool = False,
) -> dict[str, Any]:
    runtime_source = _load_runtime_source(source_row, include_secret=False)
    source_id = str(source_row.get("id") or "")
    company_id = str(source_row.get("company_id") or "")
    dataset_rows = datasets if datasets is not None else _load_source_datasets(company_id, source_id)
    dataset_summary = _summarize_datasets(dataset_rows)
    health_summary = _build_health_summary(source_row, dataset_rows)
    latest_jobs = auth_db.list_unified_sync_jobs(
        company_id=company_id,
        data_source_id=source_id,
        limit=1,
    )
    latest_job = latest_jobs[0] if latest_jobs else None
    published_snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=source_id,
        resource_key="default",
    )
    meta = dict(source_row.get("meta") or {})
    result = {
        "id": str(source_row.get("id") or ""),
        "code": str(source_row.get("code") or ""),
        "name": str(source_row.get("name") or ""),
        "source_kind": str(source_row.get("source_kind") or ""),
        "domain_type": str(source_row.get("domain_type") or ""),
        "provider_code": str(source_row.get("provider_code") or ""),
        "execution_mode": str(source_row.get("execution_mode") or ""),
        "status": str(source_row.get("status") or "active"),
        "enabled": bool(source_row.get("is_enabled", True)),
        "capabilities": list(runtime_source.get("capabilities") or []),
        "auth_status": str(meta.get("auth_status") or ""),
        "description": str(source_row.get("description") or ""),
        "connection_config": dict(runtime_source.get("connection_config") or {}),
        "extract_config": dict(runtime_source.get("extract_config") or {}),
        "mapping_config": dict(runtime_source.get("mapping_config") or {}),
        "runtime_config": dict(runtime_source.get("runtime_config") or {}),
        "source_summary": _build_source_summary(source_row),
        "dataset_summary": dataset_summary,
        "health_summary": health_summary,
        "health_status": _normalize_health_status(source_row.get("health_status")),
        "last_checked_at": source_row.get("last_checked_at"),
        "last_error_message": str(source_row.get("last_error_message") or ""),
        "last_sync_at": (latest_job or {}).get("completed_at") or (latest_job or {}).get("updated_at"),
        "last_sync_job_id": str((latest_job or {}).get("id") or ""),
        "last_sync_status": str((latest_job or {}).get("job_status") or ""),
        "published_snapshot_id": str((published_snapshot or {}).get("id") or ""),
        "published_snapshot_at": (published_snapshot or {}).get("published_at"),
        "created_at": source_row.get("created_at"),
        "updated_at": source_row.get("updated_at"),
        "metadata": meta,
    }
    if include_dataset_details:
        result["datasets"] = [_build_dataset_view(row) for row in dataset_rows]
    return result


def _upsert_source_configs(company_id: str, source_id: str, arguments: dict[str, Any]) -> None:
    config_mapping = {
        "connection_config": "connection",
        "extract_config": "extract",
        "mapping_config": "mapping",
        "runtime_config": "runtime",
    }
    for arg_key, config_type in config_mapping.items():
        if arguments.get(arg_key) is None:
            continue
        auth_db.upsert_unified_data_source_config(
            company_id=company_id,
            data_source_id=source_id,
            config_type=config_type,
            config=dict(arguments.get(arg_key) or {}),
            is_active=True,
        )

    if arguments.get("auth_config") is not None:
        auth_db.upsert_unified_data_source_credentials(
            company_id=company_id,
            data_source_id=source_id,
            credential_type="default",
            credential_payload=dict(arguments.get("auth_config") or {}),
            extra={},
        )


def _sync_rows_from_payload(result: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(result.get("rows"), list):
        return [row for row in result.get("rows") if isinstance(row, dict)]
    if isinstance(result.get("records"), list):
        return [row for row in result.get("records") if isinstance(row, dict)]
    payload = result.get("payload")
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        nested_rows = payload.get("rows")
        if isinstance(nested_rows, list):
            return [row for row in nested_rows if isinstance(row, dict)]
        if payload:
            return [payload]
    return []


def _build_raw_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        source_record_key = str(
            row.get("id")
            or row.get("item_key")
            or row.get("record_id")
            or row.get("biz_key")
            or row.get("shop_id")
            or index + 1
        )
        payload_hash = _hash_payload(row)
        records.append(
            {
                "source_record_key": source_record_key,
                "source_event_time": row.get("event_time") or row.get("updated_at"),
                "payload": row,
                "payload_hash": payload_hash,
            }
        )
    return records


def _build_snapshot_items(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item_key = str(
            row.get("id")
            or row.get("item_key")
            or row.get("record_id")
            or row.get("biz_key")
            or row.get("shop_id")
            or index + 1
        )
        item_hash = _hash_payload(row)
        items.append(
            {
                "item_key": item_key,
                "item_payload": row,
                "item_hash": item_hash,
            }
        )
    return items


def _build_checkpoint_after(
    before: dict[str, Any] | None,
    *,
    window_start: str | None,
    window_end: str | None,
    rows_count: int,
    result: dict[str, Any],
) -> dict[str, Any]:
    next_checkpoint = result.get("next_checkpoint")
    if isinstance(next_checkpoint, dict) and next_checkpoint:
        return next_checkpoint
    checkpoint_after = dict(before or {})
    checkpoint_after.update(
        {
            "last_window_start": window_start or "",
            "last_window_end": window_end or "",
            "last_synced_at": _now_iso(),
            "last_row_count": rows_count,
        }
    )
    return checkpoint_after


async def _run_connector_sync(
    source: dict[str, Any],
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if source["source_kind"] == "platform_oauth":
        list_result = await handle_platform_tool_call(
            "platform_list_connections",
            {
                "auth_token": arguments.get("auth_token"),
                "platform_code": source.get("provider_code"),
                "mode": arguments.get("mode", ""),
            },
        )
        if not list_result.get("success"):
            return list_result
        rows = []
        for item in list_result.get("connections") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "shop_id": item.get("external_shop_id"),
                    "shop_name": item.get("external_shop_name"),
                    "auth_status": item.get("auth_status"),
                    "status": item.get("status"),
                    "last_sync_at": item.get("last_sync_at"),
                }
            )
        return {
            "success": True,
            "rows": rows,
            "healthy": True,
            "message": "平台店铺连接已同步为快照",
        }

    connector = build_connector(source)
    result = connector.trigger_sync(arguments)
    params = arguments.get("params") or {}
    if not _sync_rows_from_payload(result) and isinstance(params, dict) and isinstance(params.get("rows"), list):
        result = {
            **result,
            "rows": [row for row in params.get("rows") or [] if isinstance(row, dict)],
            "healthy": result.get("healthy", True),
        }
    return result


def _attach_aliases_to_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job:
        return None
    return {
        **job,
        "sync_job_id": str(job.get("id") or ""),
        "source_id": str(job.get("data_source_id") or ""),
        "status": str(job.get("job_status") or ""),
        "finished_at": job.get("completed_at"),
    }


def _attach_aliases_to_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    return {
        **snapshot,
        "snapshot_id": str(snapshot.get("id") or ""),
        "source_id": str(snapshot.get("data_source_id") or ""),
        "status": str(snapshot.get("snapshot_status") or ""),
        "version": int(snapshot.get("snapshot_version") or 0),
        "row_count": int(snapshot.get("record_count") or 0),
    }


def create_tools() -> list[Tool]:
    source_id_schema = {
        "source_id": {"type": "string"},
        "data_source_id": {"type": "string", "description": "兼容旧字段名"},
    }
    dataset_id_schema = {
        "dataset_id": {"type": "string"},
        "id": {"type": "string", "description": "兼容字段名"},
    }
    return [
        Tool(
            name="data_source_list",
            description="列出当前企业的数据源配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "source_kind": {"type": "string"},
                    "domain_type": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_get",
            description="获取单个数据源详情。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_discover_datasets",
            description="自动发现数据源可用数据集，可选持久化为目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "persist": {"type": "boolean"},
                    "limit": {"type": "integer"},
                    "schema_whitelist": {"type": "array", "items": {"type": "string"}},
                    "discover_mode": {"type": "string"},
                    "openapi_url": {"type": "string"},
                    "openapi_spec": {"type": ["object", "string"]},
                    "manual_endpoints": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_list_datasets",
            description="列出数据源的数据集目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "status": {"type": "string"},
                    "include_deleted": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_get_dataset",
            description="获取单个数据集目录详情。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_upsert_dataset",
            description="创建或更新数据集目录。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "dataset_name": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "dataset_kind": {"type": "string"},
                    "origin_type": {"type": "string"},
                    "extract_config": {"type": "object"},
                    "schema_summary": {"type": "object"},
                    "sync_strategy": {"type": "object"},
                    "status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "health_status": {"type": "string"},
                    "last_checked_at": {"type": "string"},
                    "last_sync_at": {"type": "string"},
                    "last_error_message": {"type": "string"},
                    "meta": {"type": "object"},
                },
                "required": ["auth_token", "source_id", "dataset_code"],
            },
        ),
        Tool(
            name="data_source_disable_dataset",
            description="停用数据集目录项。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    "reason": {"type": "string"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_import_openapi",
            description="通过 OpenAPI 文档导入 API 数据集（discover+upsert 封装）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "openapi_url": {"type": "string"},
                    "openapi_spec": {"type": ["object", "string"]},
                    "persist": {"type": "boolean"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_preflight_rule_binding",
            description="执行规则绑定预检，返回阻塞问题与健康摘要。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "binding_scope": {"type": "string"},
                    "binding_code": {"type": "string"},
                    "stale_after_minutes": {"type": "integer"},
                },
                "required": ["auth_token", "binding_scope", "binding_code"],
            },
        ),
        Tool(
            name="data_source_list_events",
            description="查询数据源事件日志。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "sync_job_id": {"type": "string"},
                    "event_level": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_create",
            description="创建数据源配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "name": {"type": "string"},
                    "source_kind": {"type": "string"},
                    "provider_code": {"type": "string"},
                    "domain_type": {"type": "string"},
                    "execution_mode": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "connection_config": {"type": "object"},
                    "auth_config": {"type": "object"},
                    "extract_config": {"type": "object"},
                    "mapping_config": {"type": "object"},
                    "runtime_config": {"type": "object"},
                },
                "required": ["auth_token", "name", "source_kind"],
            },
        ),
        Tool(
            name="data_source_update",
            description="更新数据源配置。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "name": {"type": "string"},
                    "provider_code": {"type": "string"},
                    "domain_type": {"type": "string"},
                    "execution_mode": {"type": "string"},
                    "description": {"type": "string"},
                    "status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "connection_config": {"type": "object"},
                    "auth_config": {"type": "object"},
                    "extract_config": {"type": "object"},
                    "mapping_config": {"type": "object"},
                    "runtime_config": {"type": "object"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_disable",
            description="停用数据源。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "reason": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_test",
            description="测试数据源连接能力。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "mode": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_authorize",
            description="发起授权（主要用于 platform_oauth）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "return_path": {"type": "string"},
                    "redirect_uri": {"type": "string"},
                    "mode": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_handle_callback",
            description="处理授权回调（主要用于 platform_oauth）。",
            inputSchema={
                "type": "object",
                "properties": {
                    **source_id_schema,
                    "state": {"type": "string"},
                    "code": {"type": "string"},
                    "error": {"type": "string"},
                    "error_description": {"type": "string"},
                    "callback_payload": {"type": "object"},
                    "mode": {"type": "string"},
                },
                "required": ["source_id", "state"],
            },
        ),
        Tool(
            name="data_source_trigger_sync",
            description="触发一次同步任务（幂等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "idempotency_key": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "window_start": {"type": "string"},
                    "window_end": {"type": "string"},
                    "window": {"type": "object"},
                    "params": {"type": "object"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_get_sync_job",
            description="查询单个同步任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    "sync_job_id": {"type": "string"},
                },
                "required": ["auth_token", "sync_job_id"],
            },
        ),
        Tool(
            name="data_source_list_sync_jobs",
            description="列出同步任务。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "status": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_preview",
            description="预览数据源数据样例。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_get_published_snapshot",
            description="获取数据源当前已发布快照。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "resource_key": {"type": "string"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
    ]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        if name == "data_source_list":
            return await _handle_data_source_list(arguments)
        if name == "data_source_get":
            return await _handle_data_source_get(arguments)
        if name == "data_source_discover_datasets":
            return await _handle_data_source_discover_datasets(arguments)
        if name == "data_source_list_datasets":
            return await _handle_data_source_list_datasets(arguments)
        if name == "data_source_get_dataset":
            return await _handle_data_source_get_dataset(arguments)
        if name == "data_source_upsert_dataset":
            return await _handle_data_source_upsert_dataset(arguments)
        if name == "data_source_disable_dataset":
            return await _handle_data_source_disable_dataset(arguments)
        if name == "data_source_import_openapi":
            return await _handle_data_source_import_openapi(arguments)
        if name == "data_source_preflight_rule_binding":
            return await _handle_data_source_preflight_rule_binding(arguments)
        if name == "data_source_list_events":
            return await _handle_data_source_list_events(arguments)
        if name == "data_source_create":
            return await _handle_data_source_create(arguments)
        if name == "data_source_update":
            return await _handle_data_source_update(arguments)
        if name == "data_source_disable":
            return await _handle_data_source_disable(arguments)
        if name == "data_source_test":
            return await _handle_data_source_test(arguments)
        if name == "data_source_authorize":
            return await _handle_data_source_authorize(arguments)
        if name == "data_source_handle_callback":
            return await _handle_data_source_callback(arguments)
        if name == "data_source_trigger_sync":
            return await _handle_data_source_trigger_sync(arguments)
        if name == "data_source_get_sync_job":
            return await _handle_data_source_get_sync_job(arguments)
        if name == "data_source_list_sync_jobs":
            return await _handle_data_source_list_sync_jobs(arguments)
        if name == "data_source_preview":
            return await _handle_data_source_preview(arguments)
        if name == "data_source_get_published_snapshot":
            return await _handle_data_source_get_published_snapshot(arguments)
        return {"success": False, "error": f"未知工具: {name}"}
    except Exception as exc:
        logger.error("data_source tool error: %s", exc, exc_info=True)
        return {"success": False, "error": str(exc)}


async def _handle_data_source_list(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_kind = str(arguments.get("source_kind") or "").strip().lower() or None
    domain_type = str(arguments.get("domain_type") or "").strip().lower() or None
    status = str(arguments.get("status") or "").strip().lower() or None
    rows = auth_db.list_unified_data_sources(
        company_id=company_id,
        source_kind=source_kind,
        domain_type=domain_type,
        status=status,
        include_deleted=False,
    )
    dataset_rows = auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=None,
        status=None,
        include_deleted=False,
        limit=5000,
    )
    datasets_by_source: dict[str, list[dict[str, Any]]] = {}
    for dataset_row in dataset_rows:
        source_id = str(dataset_row.get("data_source_id") or "")
        datasets_by_source.setdefault(source_id, []).append(dataset_row)

    sources = [
        _build_data_source_view(
            row,
            datasets=datasets_by_source.get(str(row.get("id") or ""), []),
            include_dataset_details=False,
        )
        for row in rows
    ]
    source_kind_counts: dict[str, int] = {}
    for row in rows:
        kind = str(row.get("source_kind") or "")
        source_kind_counts[kind] = source_kind_counts.get(kind, 0) + 1
    health_counts: dict[str, int] = {}
    for item in sources:
        health_status = str((item.get("health_summary") or {}).get("overall_status") or "unknown")
        health_counts[health_status] = health_counts.get(health_status, 0) + 1
    return {
        "success": True,
        "count": len(sources),
        "sources": sources,
        "source_summary": {
            "total": len(sources),
            "by_source_kind": source_kind_counts,
            "by_health_status": health_counts,
        },
    }


async def _handle_data_source_get(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(
        company_id=company_id,
        data_source_id=source_id,
    )
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    include_datasets = _normalize_bool(arguments.get("include_datasets"), default=True)
    dataset_rows = _load_source_datasets(company_id, source_id)
    source_view = _build_data_source_view(
        source_row,
        datasets=dataset_rows,
        include_dataset_details=include_datasets,
    )
    snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=source_id,
        resource_key=_resource_key_from_args(arguments),
    )
    return {
        "success": True,
        "source": source_view,
        "source_summary": dict(source_view.get("source_summary") or {}),
        "dataset_summary": dict(source_view.get("dataset_summary") or {}),
        "health_summary": dict(source_view.get("health_summary") or {}),
        "published_snapshot": _attach_aliases_to_snapshot(snapshot),
    }


async def _handle_data_source_discover_datasets(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    runtime_source = _load_runtime_source(source_row, include_secret=True)
    connector = build_connector(runtime_source)
    discover_result = connector.discover_datasets(arguments)
    if not bool(discover_result.get("success")):
        message = str(discover_result.get("message") or discover_result.get("error") or "发现数据集失败")
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="error",
            last_error_message=message,
        )
        auth_db.create_unified_data_source_event(
            company_id=company_id,
            data_source_id=source_id,
            event_type="dataset_discover_failed",
            event_level="error",
            event_message=message,
            event_payload={"arguments": arguments},
        )
        return {
            "success": False,
            "source_id": source_id,
            "datasets": [],
            "dataset_count": 0,
            "error": str(discover_result.get("error") or "discover_failed"),
            "message": message,
        }

    discovered_raw = [item for item in discover_result.get("datasets") or [] if isinstance(item, dict)]
    normalized = [
        _normalize_discovered_dataset(item, source_row=source_row, index=index)
        for index, item in enumerate(discovered_raw)
    ]
    persist = _normalize_bool(arguments.get("persist"), default=True)
    persisted_rows: list[dict[str, Any]] = []
    persist_errors: list[str] = []
    if persist:
        for item in normalized:
            upserted = auth_db.upsert_unified_data_source_dataset(
                company_id=company_id,
                data_source_id=source_id,
                dataset_code=item["dataset_code"],
                dataset_name=item["dataset_name"],
                resource_key=item["resource_key"],
                dataset_kind=item["dataset_kind"],
                origin_type=item["origin_type"],
                extract_config=item["extract_config"],
                schema_summary=item["schema_summary"],
                sync_strategy=item["sync_strategy"],
                status=item["status"],
                is_enabled=item["is_enabled"],
                health_status=item["health_status"],
                last_checked_at=item.get("last_checked_at"),
                last_sync_at=item.get("last_sync_at"),
                last_error_message=item.get("last_error_message") or "",
                meta=item["meta"],
            )
            if upserted:
                persisted_rows.append(upserted)
            else:
                persist_errors.append(item["dataset_code"])

    if persist:
        dataset_rows = _load_source_datasets(company_id, source_id)
        datasets = [_build_dataset_view(item) for item in dataset_rows]
    else:
        datasets = [
            _build_dataset_view(
                {
                    "id": "",
                    "data_source_id": source_id,
                    **item,
                    "created_at": None,
                    "updated_at": None,
                }
            )
            for item in normalized
        ]
    dataset_summary = _summarize_datasets(
        [
            {
                "status": item.get("status"),
                "is_enabled": item.get("enabled"),
                "health_status": item.get("health_status"),
                "last_sync_at": item.get("last_sync_at"),
                "last_checked_at": item.get("last_checked_at"),
            }
            for item in datasets
        ]
    )

    auth_db.update_unified_data_source_health(
        data_source_id=source_id,
        health_status="healthy" if not persist_errors else "warning",
        last_error_message="" if not persist_errors else f"部分数据集写入失败: {', '.join(persist_errors[:5])}",
    )
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="datasets_discovered",
        event_level="info" if not persist_errors else "warn",
        event_message=f"发现 {len(normalized)} 个数据集，写入 {len(persisted_rows)} 个",
        event_payload={
            "persist": persist,
            "dataset_count": len(normalized),
            "persisted_count": len(persisted_rows),
            "persist_errors": persist_errors,
        },
    )
    return {
        "success": True,
        "source_id": source_id,
        "persist": persist,
        "dataset_count": len(datasets),
        "persisted_count": len(persisted_rows),
        "persist_error_count": len(persist_errors),
        "datasets": datasets,
        "dataset_summary": dataset_summary,
        "message": f"发现 {len(normalized)} 个数据集",
    }


async def _handle_data_source_list_datasets(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments) or None
    status = str(arguments.get("status") or "").strip().lower() or None
    include_deleted = _normalize_bool(arguments.get("include_deleted"), default=False)
    limit = max(1, min(int(arguments.get("limit") or 500), 2000))

    source_row = None
    if source_id:
        source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
        if not source_row:
            return {"success": False, "error": "数据源不存在"}
    rows = auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=source_id,
        status=status,
        include_deleted=include_deleted,
        limit=limit,
    )
    datasets = [_build_dataset_view(row) for row in rows]
    result: dict[str, Any] = {
        "success": True,
        "count": len(datasets),
        "datasets": datasets,
        "dataset_summary": _summarize_datasets(rows),
    }
    if source_row:
        result["source_summary"] = _build_source_summary(source_row)
        result["health_summary"] = _build_health_summary(source_row, rows)
    return result


async def _handle_data_source_get_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_id = _dataset_id_from_args(arguments)

    row = None
    if dataset_id:
        row = auth_db.get_unified_data_source_dataset_by_id(company_id=company_id, dataset_id=dataset_id)
    else:
        source_id = _source_id_from_args(arguments)
        dataset_code = _sanitize_dataset_code(arguments.get("dataset_code"))
        resource_key = str(arguments.get("resource_key") or "").strip()
        if not source_id:
            return {"success": False, "error": "缺少 dataset_id 或 source_id"}
        rows = auth_db.list_unified_data_source_datasets(
            company_id=company_id,
            data_source_id=source_id,
            status=None,
            include_deleted=True,
            limit=2000,
        )
        if dataset_code:
            row = next((item for item in rows if str(item.get("dataset_code") or "") == dataset_code), None)
        elif resource_key:
            row = next((item for item in rows if str(item.get("resource_key") or "") == resource_key), None)
    if not row:
        return {"success": False, "error": "数据集不存在"}

    source_row = auth_db.get_unified_data_source_by_id(
        company_id=company_id,
        data_source_id=str(row.get("data_source_id") or ""),
    )
    source_datasets = []
    if source_row:
        source_datasets = _load_source_datasets(company_id, str(source_row.get("id") or ""))
    return {
        "success": True,
        "dataset": _build_dataset_view(row),
        "source_summary": _build_source_summary(source_row) if source_row else {},
        "health_summary": _build_health_summary(source_row, source_datasets) if source_row else {},
    }


async def _handle_data_source_upsert_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    dataset_code = _sanitize_dataset_code(arguments.get("dataset_code"))
    if not dataset_code:
        return {"success": False, "error": "dataset_code 不能为空"}
    resource_key = str(arguments.get("resource_key") or dataset_code).strip() or "default"
    dataset_name = str(arguments.get("dataset_name") or resource_key).strip() or dataset_code
    enabled = _normalize_bool(arguments.get("enabled"), default=True)
    status = _normalize_status(arguments.get("status"), default="active" if enabled else "disabled")
    health_status = _normalize_health_status(arguments.get("health_status"), default="unknown")

    row = auth_db.upsert_unified_data_source_dataset(
        company_id=company_id,
        data_source_id=source_id,
        dataset_code=dataset_code,
        dataset_name=dataset_name,
        resource_key=resource_key,
        dataset_kind=str(arguments.get("dataset_kind") or "table"),
        origin_type=_normalize_dataset_origin_type(arguments.get("origin_type"), default="manual"),
        extract_config=dict(arguments.get("extract_config") or {}),
        schema_summary=dict(arguments.get("schema_summary") or {}),
        sync_strategy=dict(arguments.get("sync_strategy") or {}),
        status=status,
        is_enabled=enabled,
        health_status=health_status,
        last_checked_at=arguments.get("last_checked_at"),
        last_sync_at=arguments.get("last_sync_at"),
        last_error_message=str(arguments.get("last_error_message") or ""),
        meta=dict(arguments.get("meta") or {}),
    )
    if not row:
        return {"success": False, "error": "写入数据集失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="dataset_upserted",
        event_level="info",
        event_message=f"更新数据集：{dataset_name}",
        event_payload={
            "dataset_id": str(row.get("id") or ""),
            "dataset_code": dataset_code,
            "resource_key": resource_key,
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(row),
        "source_summary": _build_source_summary(source_row),
        "message": "数据集已更新",
    }


async def _handle_data_source_disable_dataset(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_id = _dataset_id_from_args(arguments)
    if not dataset_id:
        return {"success": False, "error": "dataset_id 不能为空"}
    current = auth_db.get_unified_data_source_dataset_by_id(company_id=company_id, dataset_id=dataset_id)
    if not current:
        return {"success": False, "error": "数据集不存在"}
    updated = auth_db.update_unified_data_source_dataset_status(
        dataset_id=dataset_id,
        status="disabled",
        is_enabled=False,
    )
    if not updated:
        return {"success": False, "error": "停用数据集失败"}
    reason = str(arguments.get("reason") or "数据集已停用")
    health_updated = auth_db.update_unified_data_source_dataset_health(
        dataset_id=dataset_id,
        health_status="disabled",
        last_error_message=reason,
    )
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=str(current.get("data_source_id") or ""),
        event_type="dataset_disabled",
        event_level="warn",
        event_message=reason,
        event_payload={"dataset_id": dataset_id, "reason": reason},
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(health_updated or updated),
        "message": "数据集已停用",
    }


async def _handle_data_source_import_openapi(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = dict(arguments or {})
    payload["discover_mode"] = "openapi"
    payload["persist"] = _normalize_bool(payload.get("persist"), default=True)
    return await _handle_data_source_discover_datasets(payload)


async def _handle_data_source_preflight_rule_binding(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    binding_scope = str(arguments.get("binding_scope") or "").strip().lower()
    binding_code = str(arguments.get("binding_code") or "").strip()
    if not binding_scope or not binding_code:
        return {"success": False, "error": "binding_scope 和 binding_code 不能为空"}
    stale_after_minutes = max(1, min(int(arguments.get("stale_after_minutes") or 24 * 60), 30 * 24 * 60))
    preflight = auth_db.evaluate_unified_rule_binding_preflight(
        company_id=company_id,
        binding_scope=binding_scope,
        binding_code=binding_code,
        stale_after_minutes=stale_after_minutes,
    )
    issues = [item for item in preflight.get("issues") or [] if isinstance(item, dict)]
    issue_level_count: dict[str, int] = {}
    issue_code_count: dict[str, int] = {}
    for item in issues:
        level = str(item.get("level") or "unknown")
        code = str(item.get("code") or "unknown")
        issue_level_count[level] = issue_level_count.get(level, 0) + 1
        issue_code_count[code] = issue_code_count.get(code, 0) + 1
    return {
        "success": True,
        "ready": bool(preflight.get("ready")),
        "binding_scope": binding_scope,
        "binding_code": binding_code,
        "summary": {
            "issue_count": int(preflight.get("issue_count") or 0),
            "blocking_issue_count": int(preflight.get("blocking_issue_count") or 0),
            "requirement_count": len(preflight.get("requirements") or []),
            "issue_level_count": issue_level_count,
            "issue_code_count": issue_code_count,
        },
        "preflight": preflight,
    }


async def _handle_data_source_list_events(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments) or None
    if source_id:
        source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
        if not source_row:
            return {"success": False, "error": "数据源不存在"}
    events = auth_db.list_unified_data_source_events(
        company_id=company_id,
        data_source_id=source_id,
        sync_job_id=str(arguments.get("sync_job_id") or "").strip() or None,
        event_level=str(arguments.get("event_level") or "").strip().lower() or None,
        limit=max(1, min(int(arguments.get("limit") or 200), 1000)),
    )
    return {
        "success": True,
        "count": len(events),
        "events": events,
    }


async def _handle_data_source_create(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_kind = _normalize_source_kind(arguments.get("source_kind"))
    provider_code = _resolve_provider_code(
        source_kind,
        provider_code=arguments.get("provider_code"),
        connection_config=dict(arguments.get("connection_config") or {}),
    )
    domain_type = _normalize_domain_type(arguments.get("domain_type"))
    execution_mode = _normalize_execution_mode(source_kind, arguments.get("execution_mode"))
    name = str(arguments.get("name") or "").strip() or f"{provider_code} 数据源"
    enabled = _normalize_bool(arguments.get("enabled"), default=source_kind not in AGENT_ASSISTED_KINDS)
    status = _normalize_status(
        arguments.get("status"),
        default="active" if enabled else "disabled",
    )
    code = _generate_source_code(source_kind, provider_code, name)
    meta = {"auth_status": "unauthorized" if source_kind == "platform_oauth" else ""}

    row = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=code,
        name=name,
        source_kind=source_kind,
        domain_type=domain_type,
        provider_code=provider_code,
        execution_mode=execution_mode,
        description=str(arguments.get("description") or ""),
        status=status,
        is_enabled=enabled,
        meta=meta,
    )
    if not row:
        return {"success": False, "error": "创建数据源失败，请检查数据库迁移是否已执行"}

    _upsert_source_configs(company_id, str(row["id"]), arguments)
    created_source = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=str(row["id"]))
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=str(row["id"]),
        event_type="data_source_created",
        event_message=f"创建数据源：{name}",
        event_payload={"source_kind": source_kind, "provider_code": provider_code},
    )
    return {
        "success": True,
        "source": _build_data_source_view(created_source or row),
        "message": "数据源创建成功",
    }


async def _handle_data_source_update(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    current = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not current:
        return {"success": False, "error": "数据源不存在"}

    source_kind = str(current.get("source_kind") or "")
    provider_code = _resolve_provider_code(
        source_kind,
        provider_code=arguments.get("provider_code"),
        current_provider_code=str(current.get("provider_code") or ""),
        connection_config=dict(arguments.get("connection_config") or {}),
    )
    domain_type = _normalize_domain_type(arguments.get("domain_type") or current.get("domain_type"))
    execution_mode = _normalize_execution_mode(source_kind, arguments.get("execution_mode") or current.get("execution_mode"))
    enabled = _normalize_bool(arguments.get("enabled"), default=bool(current.get("is_enabled", True)))
    status = _normalize_status(
        arguments.get("status"),
        default="active" if enabled else "disabled",
    )
    row = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=str(current.get("code") or ""),
        name=str(arguments.get("name") or current.get("name") or ""),
        source_kind=source_kind,
        domain_type=domain_type,
        provider_code=provider_code,
        execution_mode=execution_mode,
        description=str(arguments.get("description") or current.get("description") or ""),
        status=status,
        is_enabled=enabled,
        meta=dict(current.get("meta") or {}),
    )
    if not row:
        return {"success": False, "error": "更新数据源失败"}

    _upsert_source_configs(company_id, source_id, arguments)
    updated_source = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_updated",
        event_message=f"更新数据源：{updated_source.get('name') if updated_source else current.get('name')}",
        event_payload={"source_id": source_id},
    )
    return {
        "success": True,
        "source": _build_data_source_view(updated_source or row),
        "message": "数据源更新成功",
    }


async def _handle_data_source_disable(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    current = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not current:
        return {"success": False, "error": "数据源不存在"}
    row = auth_db.update_unified_data_source_status(
        data_source_id=source_id,
        status="disabled",
        is_enabled=False,
    )
    if not row:
        return {"success": False, "error": "停用数据源失败"}
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_disabled",
        event_level="warn",
        event_message=str(arguments.get("reason") or "数据源已停用"),
        event_payload={"reason": str(arguments.get("reason") or "")},
    )
    return {
        "success": True,
        "source": _build_data_source_view(row),
        "message": "数据源已停用",
    }


async def _handle_data_source_test(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    runtime_source = _load_runtime_source(source_row, include_secret=True)
    connector = build_connector(runtime_source)

    if runtime_source["source_kind"] == "platform_oauth":
        platform_result = await handle_platform_tool_call(
            "platform_list_connections",
            {
                "auth_token": arguments.get("auth_token"),
                "platform_code": runtime_source.get("provider_code"),
                "mode": arguments.get("mode", ""),
            },
        )
        success = bool(platform_result.get("success"))
        result = {
            "status": "ok" if success else "error",
            "authorized_shop_count": len(platform_result.get("connections") or []),
            "message": str(platform_result.get("message") or ""),
        }
    else:
        connector_result = connector.test_connection(arguments)
        success = bool(connector_result.get("success"))
        result = {
            "status": "ok" if success else "error",
            "execution_mode": runtime_source.get("execution_mode"),
            "message": str(connector_result.get("message") or connector_result.get("error") or ""),
        }

    source_health_status = "healthy" if success else "error"
    if not success and runtime_source["source_kind"] == "platform_oauth":
        source_health_status = "auth_expired"
    auth_db.update_unified_data_source_health(
        data_source_id=source_id,
        health_status=source_health_status,
        last_error_message="" if success else result["message"],
    )
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_tested",
        event_level="info" if success else "error",
        event_message=result["message"],
        event_payload=result,
    )
    return {"success": success, "source_id": source_id, "result": result}


async def _handle_data_source_authorize(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    if str(source_row.get("source_kind") or "") != "platform_oauth":
        return {"success": False, "error": "仅 platform_oauth 支持授权"}

    redirect_uri = str(arguments.get("redirect_uri") or "").strip() or (
        f"https://tally-placeholder.example.com/api/data-sources/auth/callback/{source_id}"
    )
    result = await handle_platform_tool_call(
        "platform_create_auth_session",
        {
            "auth_token": arguments.get("auth_token"),
            "platform_code": source_row.get("provider_code"),
            "return_path": arguments.get("return_path", "/"),
            "redirect_uri": redirect_uri,
            "mode": arguments.get("mode", ""),
        },
    )
    if result.get("success"):
        meta = dict(source_row.get("meta") or {})
        meta["auth_status"] = "authorizing"
        auth_db.upsert_unified_data_source(
            company_id=company_id,
            code=str(source_row.get("code") or ""),
            name=str(source_row.get("name") or ""),
            source_kind="platform_oauth",
            domain_type=str(source_row.get("domain_type") or "ecommerce"),
            provider_code=str(source_row.get("provider_code") or ""),
            execution_mode=str(source_row.get("execution_mode") or "deterministic"),
            description=str(source_row.get("description") or ""),
            status=str(source_row.get("status") or "active"),
            is_enabled=bool(source_row.get("is_enabled", True)),
            meta=meta,
        )
    return result


async def _handle_data_source_callback(arguments: dict[str, Any]) -> dict[str, Any]:
    source_id = _source_id_from_args(arguments)
    source_row = _query_source_any_company(source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    if str(source_row.get("source_kind") or "") != "platform_oauth":
        return {"success": False, "error": "仅 platform_oauth 支持回调"}

    result = await handle_platform_tool_call(
        "platform_handle_auth_callback",
        {
            "platform_code": source_row.get("provider_code"),
            "state": arguments.get("state", ""),
            "code": arguments.get("code", ""),
            "error": arguments.get("error", ""),
            "error_description": arguments.get("error_description", ""),
            "callback_payload": arguments.get("callback_payload") or {},
            "mode": arguments.get("mode", ""),
        },
    )
    meta = dict(source_row.get("meta") or {})
    meta["auth_status"] = "authorized" if result.get("success") else "unauthorized"
    auth_db.upsert_unified_data_source(
        company_id=str(source_row.get("company_id") or ""),
        code=str(source_row.get("code") or ""),
        name=str(source_row.get("name") or ""),
        source_kind="platform_oauth",
        domain_type=str(source_row.get("domain_type") or "ecommerce"),
        provider_code=str(source_row.get("provider_code") or ""),
        execution_mode=str(source_row.get("execution_mode") or "deterministic"),
        description=str(source_row.get("description") or ""),
        status=str(source_row.get("status") or "active"),
        is_enabled=bool(source_row.get("is_enabled", True)),
        meta=meta,
    )
    refreshed = _query_source_any_company(source_id)
    return {
        **result,
        "source": _build_data_source_view(refreshed) if refreshed else None,
    }


async def _handle_data_source_trigger_sync(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    if str(source_row.get("status") or "") != "active" or not bool(source_row.get("is_enabled", True)):
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="disabled",
            last_error_message="数据源未启用，无法触发同步",
        )
        return {"success": False, "error": "数据源未启用，无法触发同步"}

    runtime_source = _load_runtime_source(source_row, include_secret=True)
    if runtime_source["source_kind"] in AGENT_ASSISTED_KINDS:
        connector = build_connector(runtime_source)
        result = connector.trigger_sync(arguments)
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="warning",
            last_error_message=str(result.get("message") or "该数据源需由 agent loop 执行"),
        )
        return {
            "success": False,
            "source_id": source_id,
            "error": str(result.get("error") or "agent_assisted_required"),
            "message": str(result.get("message") or "该数据源需由 agent loop 执行"),
        }

    resource_key = _resource_key_from_args(arguments)
    window_start, window_end = _window_from_args(arguments)
    idempotency_key = _compute_idempotency_key(source_id, arguments)
    existing_job = auth_db.find_unified_sync_job_by_idempotency_key(
        company_id=company_id,
        data_source_id=source_id,
        idempotency_key=idempotency_key,
    )
    if existing_job:
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="healthy",
            last_error_message="",
        )
        return {
            "success": True,
            "source_id": source_id,
            "job": _attach_aliases_to_job(existing_job),
            "published_snapshot": _attach_aliases_to_snapshot(
                auth_db.get_unified_published_dataset_snapshot(
                    data_source_id=source_id,
                    resource_key=resource_key,
                )
            ),
            "reused": True,
            "message": "命中幂等键，返回已有同步任务",
        }

    checkpoint_before_row = auth_db.get_unified_sync_checkpoint(
        data_source_id=source_id,
        resource_key=resource_key,
    )
    checkpoint_before = dict((checkpoint_before_row or {}).get("checkpoint_value") or {})
    job = auth_db.create_unified_sync_job(
        company_id=company_id,
        data_source_id=source_id,
        trigger_mode="manual",
        resource_key=resource_key,
        idempotency_key=idempotency_key,
        window_start=window_start,
        window_end=window_end,
        request_payload=dict(arguments.get("params") or {}),
        checkpoint_before=checkpoint_before,
    )
    if not job:
        return {"success": False, "error": "创建同步任务失败"}

    attempt = auth_db.create_unified_sync_job_attempt(
        company_id=company_id,
        sync_job_id=str(job["id"]),
        attempt_no=int(job.get("current_attempt") or 0) + 1,
        checkpoint_before=checkpoint_before,
    )
    if not attempt:
        return {"success": False, "error": "创建同步任务尝试失败"}

    batch = auth_db.create_unified_raw_ingestion_batch(
        company_id=company_id,
        data_source_id=source_id,
        sync_job_id=str(job["id"]),
        sync_job_attempt_id=str(attempt["id"]),
        resource_key=resource_key,
        meta={"source_kind": runtime_source["source_kind"], "provider_code": runtime_source["provider_code"]},
    )
    if not batch:
        auth_db.update_unified_sync_job_attempt(
            attempt_id=str(attempt["id"]),
            attempt_status="failed",
            error_message="创建原始批次失败",
            metrics={},
            checkpoint_after=checkpoint_before,
        )
        auth_db.update_unified_sync_job_status(
            sync_job_id=str(job["id"]),
            job_status="failed",
            error_message="创建原始批次失败",
            checkpoint_after=checkpoint_before,
            finish_job=True,
        )
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="error",
            last_error_message="创建原始批次失败",
        )
        return {"success": False, "error": "创建原始批次失败"}

    result = await _run_connector_sync(runtime_source, arguments)
    rows = _sync_rows_from_payload(result)
    raw_records = _build_raw_records(rows)
    raw_inserted = auth_db.append_unified_raw_ingestion_records(
        company_id=company_id,
        data_source_id=source_id,
        batch_id=str(batch["id"]),
        records=raw_records,
    )
    data_hash = _hash_payload(rows)
    auth_db.update_unified_raw_ingestion_batch_status(
        batch_id=str(batch["id"]),
        batch_status="loaded" if result.get("success") else "failed",
        data_hash=data_hash,
        meta={"row_count": len(rows)},
    )

    snapshot = auth_db.create_unified_dataset_snapshot(
        company_id=company_id,
        data_source_id=source_id,
        resource_key=resource_key,
        sync_job_id=str(job["id"]),
        sync_job_attempt_id=str(attempt["id"]),
        snapshot_name=f"{runtime_source['name']}_{resource_key}_{_now_iso()}",
        snapshot_status="candidate",
        record_count=0,
        data_hash=data_hash,
        schema_hash=_hash_payload(sorted({key for row in rows for key in row.keys()})),
        window_start=window_start,
        window_end=window_end,
        meta={"connector_message": result.get("message", ""), "raw_inserted": raw_inserted},
    )
    if not snapshot:
        auth_db.update_unified_sync_job_attempt(
            attempt_id=str(attempt["id"]),
            attempt_status="failed",
            error_message="创建数据快照失败",
            metrics={"raw_inserted": raw_inserted},
            checkpoint_after=checkpoint_before,
        )
        auth_db.update_unified_sync_job_status(
            sync_job_id=str(job["id"]),
            job_status="failed",
            error_message="创建数据快照失败",
            checkpoint_after=checkpoint_before,
            finish_job=True,
        )
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="error",
            last_error_message="创建数据快照失败",
        )
        return {"success": False, "error": "创建数据快照失败"}

    snapshot_inserted = auth_db.append_unified_dataset_snapshot_items(
        company_id=company_id,
        data_source_id=source_id,
        snapshot_id=str(snapshot["id"]),
        items=_build_snapshot_items(rows),
    )
    healthy = bool(result.get("healthy", result.get("success", False)))
    checkpoint_after = _build_checkpoint_after(
        checkpoint_before,
        window_start=window_start,
        window_end=window_end,
        rows_count=snapshot_inserted,
        result=result,
    )

    if not bool(result.get("success")) or not healthy:
        message = str(result.get("error") or result.get("message") or "同步失败")
        auth_db.update_unified_sync_job_attempt(
            attempt_id=str(attempt["id"]),
            attempt_status="failed",
            error_message=message,
            metrics={"raw_inserted": raw_inserted, "snapshot_inserted": snapshot_inserted},
            checkpoint_after=checkpoint_before,
        )
        auth_db.update_unified_sync_job_status(
            sync_job_id=str(job["id"]),
            job_status="failed",
            error_message=message,
            checkpoint_after=checkpoint_before,
            finish_job=True,
        )
        auth_db.create_unified_data_source_event(
            company_id=company_id,
            data_source_id=source_id,
            sync_job_id=str(job["id"]),
            event_type="sync_failed",
            event_level="error",
            event_message=message,
            event_payload={"rows": len(rows), "resource_key": resource_key},
        )
        auth_db.update_unified_data_source_health(
            data_source_id=source_id,
            health_status="error",
            last_error_message=message,
        )
        _update_dataset_health_by_resource(
            company_id=company_id,
            source_id=source_id,
            resource_key=resource_key,
            health_status="error",
            last_error_message=message,
        )
        return {
            "success": False,
            "source_id": source_id,
            "job": _attach_aliases_to_job(auth_db.get_unified_sync_job_by_id(str(job["id"]))),
            "published_snapshot": _attach_aliases_to_snapshot(
                auth_db.get_unified_published_dataset_snapshot(data_source_id=source_id, resource_key=resource_key)
            ),
            "reused": False,
            "message": message,
        }

    published_snapshot = auth_db.mark_unified_dataset_snapshot_published(
        snapshot_id=str(snapshot["id"]),
        published_by_job_id=str(job["id"]),
    )
    auth_db.upsert_unified_sync_checkpoint(
        company_id=company_id,
        data_source_id=source_id,
        resource_key=resource_key,
        checkpoint_value=checkpoint_after,
        updated_by_job_id=str(job["id"]),
    )
    auth_db.update_unified_sync_job_attempt(
        attempt_id=str(attempt["id"]),
        attempt_status="success",
        error_message="",
        metrics={"raw_inserted": raw_inserted, "snapshot_inserted": snapshot_inserted},
        checkpoint_after=checkpoint_after,
    )
    updated_job = auth_db.update_unified_sync_job_status(
        sync_job_id=str(job["id"]),
        job_status="success",
        error_message="",
        checkpoint_after=checkpoint_after,
        active_snapshot_id=str((published_snapshot or {}).get("id") or ""),
        published_snapshot_id=str((published_snapshot or {}).get("id") or ""),
        finish_job=True,
    )
    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        sync_job_id=str(job["id"]),
        event_type="sync_succeeded",
        event_level="info",
        event_message=str(result.get("message") or "同步成功"),
        event_payload={
            "rows": len(rows),
            "resource_key": resource_key,
            "published_snapshot_id": str((published_snapshot or {}).get("id") or ""),
        },
    )
    auth_db.update_unified_data_source_health(
        data_source_id=source_id,
        health_status="healthy",
        last_error_message="",
    )
    _update_dataset_health_by_resource(
        company_id=company_id,
        source_id=source_id,
        resource_key=resource_key,
        health_status="healthy",
        last_error_message="",
        last_sync_at=_now_iso(),
    )
    return {
        "success": True,
        "source_id": source_id,
        "job": _attach_aliases_to_job(updated_job),
        "published_snapshot": _attach_aliases_to_snapshot(published_snapshot),
        "reused": False,
        "message": "同步成功并发布新快照",
    }


async def _handle_data_source_get_sync_job(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    job = auth_db.get_unified_sync_job_by_id(str(arguments.get("sync_job_id") or ""))
    if not job or str(job.get("company_id") or "") != company_id:
        return {"success": False, "error": "同步任务不存在"}
    published_snapshot = None
    published_snapshot_id = str(job.get("published_snapshot_id") or "")
    if published_snapshot_id:
        snapshots = auth_db.list_unified_dataset_snapshots(
            company_id=company_id,
            data_source_id=str(job.get("data_source_id") or ""),
            limit=20,
        )
        published_snapshot = next((item for item in snapshots if str(item.get("id") or "") == published_snapshot_id), None)
    return {
        "success": True,
        "job": _attach_aliases_to_job(job),
        "published_snapshot": _attach_aliases_to_snapshot(published_snapshot),
    }


async def _handle_data_source_list_sync_jobs(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments) or None
    status = str(arguments.get("status") or "").strip().lower() or None
    limit = int(arguments.get("limit") or 20)
    jobs = auth_db.list_unified_sync_jobs(
        company_id=company_id,
        data_source_id=source_id,
        job_status=status,
        limit=max(1, min(limit, 100)),
    )
    return {
        "success": True,
        "count": len(jobs),
        "jobs": [_attach_aliases_to_job(job) for job in jobs],
    }


async def _handle_data_source_preview(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    limit = int(arguments.get("limit") or 20)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    published_snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=source_id,
        resource_key=_resource_key_from_args(arguments),
    )
    if published_snapshot:
        rows = _list_snapshot_rows(str(published_snapshot["id"]), limit=limit)
        preview_rows = []
        for row in rows:
            payload = row.get("item_payload")
            if isinstance(payload, dict):
                preview_rows.append(payload)
        return {
            "success": True,
            "source_id": source_id,
            "count": len(preview_rows),
            "rows": preview_rows,
            "message": "已返回已发布快照样例",
        }

    runtime_source = _load_runtime_source(source_row, include_secret=True)
    if runtime_source["source_kind"] == "platform_oauth":
        result = await handle_platform_tool_call(
            "platform_list_connections",
            {
                "auth_token": arguments.get("auth_token"),
                "platform_code": runtime_source.get("provider_code"),
                "mode": arguments.get("mode", ""),
            },
        )
        rows = []
        for item in result.get("connections") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "shop_id": item.get("external_shop_id"),
                    "shop_name": item.get("external_shop_name"),
                    "auth_status": item.get("auth_status"),
                    "status": item.get("status"),
                }
            )
        return {
            "success": bool(result.get("success", True)),
            "source_id": source_id,
            "count": min(len(rows), limit),
            "rows": rows[: max(1, min(limit, 100))],
            "message": str(result.get("message") or ""),
        }

    connector = build_connector(runtime_source)
    result = connector.preview(arguments)
    rows = []
    for row in result.get("rows") or []:
        if isinstance(row, dict):
            rows.append(row)
    return {
        "success": bool(result.get("success", True)),
        "source_id": source_id,
        "count": len(rows[: max(1, min(limit, 100))]),
        "rows": rows[: max(1, min(limit, 100))],
        "message": str(result.get("message") or ""),
    }


async def _handle_data_source_get_published_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=source_id,
        resource_key=_resource_key_from_args(arguments),
    )
    if not snapshot:
        return {
            "success": True,
            "source_id": source_id,
            "published_snapshot": None,
            "message": "暂无已发布快照",
        }
    return {
        "success": True,
        "source_id": source_id,
        "published_snapshot": _attach_aliases_to_snapshot(snapshot),
    }

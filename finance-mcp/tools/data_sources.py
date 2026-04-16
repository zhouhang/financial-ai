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
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg2.extras
from mcp import Tool

from auth import db as auth_db
from auth.jwt_utils import get_user_from_token
from connectors.factory import build_connector
from security_utils import UPLOAD_ROOT
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
AUTO_DISCOVER_DATASET_LIMIT = 300
AUTO_SAMPLE_DATASET_LIMIT = 20
AUTO_SAMPLE_ROW_LIMIT = 10
SEMANTIC_STATUS_VALUES = {"generated_basic", "generated_with_samples", "manual_updated"}
SEMANTIC_FIELD_CONFIDENCE_THRESHOLD = 0.75
SEMANTIC_SAMPLE_ROW_LIMIT = 10

_FIELD_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_SEMANTIC_ROLE_HINTS: dict[str, tuple[tuple[str, ...], str, str, str]] = {
    "order_no": (("order", "id"), "identifier", "订单号", "订单唯一编号"),
    "trade_no": (("trade", "id"), "identifier", "交易号", "交易流水编号"),
    "biz_date": (("biz", "date"), "date", "业务日期", "业务发生日期"),
    "settle_date": (("settle", "date"), "date", "结算日期", "结算发生日期"),
    "created_at": (("created", "at"), "datetime", "创建时间", "记录创建时间"),
    "updated_at": (("updated", "at"), "datetime", "更新时间", "记录更新时间"),
    "pay_amount": (("pay", "amount"), "amount", "支付金额", "支付相关金额"),
    "order_amount": (("order", "amount"), "amount", "订单金额", "订单相关金额"),
    "total_amount": (("total", "amount"), "amount", "总金额", "汇总金额"),
    "refund_amount": (("refund", "amount"), "amount", "退款金额", "退款相关金额"),
    "bank_amount": (("bank", "amount"), "amount", "银行金额", "银行侧金额"),
    "quantity": (("quantity",), "number", "数量", "数量字段"),
    "status": (("status",), "status", "状态", "状态字段"),
    "shop_name": (("shop", "name"), "dimension", "店铺名称", "店铺名称"),
    "shop_id": (("shop", "id"), "identifier", "店铺ID", "店铺唯一标识"),
}
_BUSINESS_NAME_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("bank", "flow"), "银行流水"),
    (("bank", "statement"), "银行流水"),
    (("refund",), "退款明细"),
    (("settle",), "结算明细"),
    (("recon",), "对账明细"),
    (("order", "pay"), "订单支付明细"),
    (("order",), "订单明细"),
    (("trade",), "交易明细"),
    (("inventory",), "库存明细"),
    (("stock",), "库存明细"),
    (("invoice",), "发票明细"),
]


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_semantic_status(value: Any, *, default: str = "generated_basic") -> str:
    status = _safe_text(value).lower() or default
    if status not in SEMANTIC_STATUS_VALUES:
        return default
    return status


def _tokenize_identifier(value: Any) -> list[str]:
    text = _safe_text(value).lower()
    if not text:
        return []
    tokens = [token for token in _FIELD_TOKEN_SPLIT.split(text) if token]
    if tokens:
        return tokens
    return [text]


def _truncate_text(value: Any, *, limit: int = 80) -> str:
    raw = _safe_text(value)
    if len(raw) <= limit:
        return raw
    return f"{raw[: max(0, limit - 1)]}…"


def _extract_dataset_columns(dataset_row: dict[str, Any], sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    schema_summary = dict(dataset_row.get("schema_summary") or {})
    columns = schema_summary.get("columns")
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    if isinstance(columns, list):
        for item in columns:
            if not isinstance(item, dict):
                continue
            name = _safe_text(item.get("name"))
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(
                {
                    "name": name,
                    "data_type": _safe_text(item.get("data_type")) or "unknown",
                    "nullable": bool(item.get("nullable", True)),
                }
            )

    for row in sample_rows:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            name = _safe_text(key)
            if not name or name in seen:
                continue
            seen.add(name)
            ordered.append(
                {
                    "name": name,
                    "data_type": type(value).__name__,
                    "nullable": value is None,
                }
            )
    return ordered


def _guess_business_name(dataset_row: dict[str, Any], source_row: dict[str, Any] | None = None) -> str:
    dataset_name = _safe_text(dataset_row.get("dataset_name"))
    resource_key = _safe_text(dataset_row.get("resource_key"))
    dataset_code = _safe_text(dataset_row.get("dataset_code"))
    raw = " ".join([dataset_name, resource_key, dataset_code])
    tokens = set(_tokenize_identifier(raw))

    for hints, label in _BUSINESS_NAME_HINTS:
        if all(hint in tokens for hint in hints):
            return label

    source_kind = _safe_text((source_row or {}).get("source_kind")).lower()
    if source_kind == "api":
        return "API 数据集"
    if source_kind == "database":
        return "数据库数据集"
    if source_kind == "browser":
        return "网页采集数据集"
    if source_kind == "desktop_cli":
        return "桌面端采集数据集"
    if source_kind == "file":
        return "文件数据集"
    return "业务数据集"


def _guess_field_semantic(
    field_name: str,
    data_type: str,
    *,
    has_sample_rows: bool,
) -> dict[str, Any]:
    tokens = _tokenize_identifier(field_name)
    token_set = set(tokens)
    default_label = field_name
    semantic_type = "unknown"
    business_role = "unknown"
    description = ""
    confidence = 0.55

    for _, (hints, semantic, label, desc) in _SEMANTIC_ROLE_HINTS.items():
        if all(h in token_set for h in hints):
            semantic_type = semantic
            business_role = "_".join(hints)
            default_label = label
            description = desc
            confidence = 0.88 if has_sample_rows else 0.72
            break

    if semantic_type == "unknown":
        lowered_type = _safe_text(data_type).lower()
        if "time" in token_set or "date" in token_set or lowered_type in {"date", "datetime", "timestamp"}:
            semantic_type = "datetime"
            business_role = "time"
            default_label = "时间"
            description = "时间字段"
            confidence = 0.76 if has_sample_rows else 0.68
        elif any(token in token_set for token in {"amount", "amt", "money", "price", "fee", "balance"}):
            semantic_type = "amount"
            business_role = "amount"
            default_label = "金额"
            description = "金额字段"
            confidence = 0.8 if has_sample_rows else 0.7
        elif any(token in token_set for token in {"id", "no", "code", "uid", "sn"}):
            semantic_type = "identifier"
            business_role = "identifier"
            default_label = "标识"
            description = "业务标识字段"
            confidence = 0.74 if has_sample_rows else 0.66
        elif any(token in token_set for token in {"status", "state", "flag"}):
            semantic_type = "status"
            business_role = "status"
            default_label = "状态"
            description = "状态字段"
            confidence = 0.72 if has_sample_rows else 0.64

    if not has_sample_rows:
        confidence = min(confidence, 0.74)

    return {
        "raw_name": field_name,
        "display_name": default_label,
        "semantic_type": semantic_type,
        "business_role": business_role,
        "description": description,
        "confidence": round(float(confidence), 4),
    }


def _collect_sample_values(sample_rows: list[dict[str, Any]], field_name: str, *, max_values: int = 3) -> list[str]:
    values: list[str] = []
    for row in sample_rows:
        if not isinstance(row, dict) or field_name not in row:
            continue
        value = row.get(field_name)
        if value is None:
            continue
        normalized = _truncate_text(value, limit=40)
        if not normalized:
            continue
        if normalized in values:
            continue
        values.append(normalized)
        if len(values) >= max_values:
            break
    return values


def _build_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    source_row: dict[str, Any] | None,
    sample_rows: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    columns = _extract_dataset_columns(dataset_row, sample_rows)
    has_sample_rows = bool(sample_rows)
    field_items: list[dict[str, Any]] = []
    field_label_map: dict[str, str] = {}
    low_confidence_fields: list[str] = []

    for column in columns:
        name = _safe_text(column.get("name"))
        if not name:
            continue
        semantic = _guess_field_semantic(
            name,
            _safe_text(column.get("data_type")),
            has_sample_rows=has_sample_rows,
        )
        sample_values = _collect_sample_values(sample_rows, name)
        field_item = {
            **semantic,
            "sample_values": sample_values,
            "confirmed_by_user": False,
        }
        field_items.append(field_item)
        field_label_map[name] = _safe_text(semantic.get("display_name")) or name
        if float(semantic.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD:
            low_confidence_fields.append(name)

    key_fields: list[str] = []
    preferred_roles = {"order_id", "trade_id", "biz_date", "amount", "identifier", "time"}
    for field in field_items:
        role = _safe_text(field.get("business_role"))
        if role in preferred_roles:
            label = _safe_text(field.get("display_name")) or _safe_text(field.get("raw_name"))
            if label and label not in key_fields:
                key_fields.append(label)
        if len(key_fields) >= 6:
            break
    if not key_fields:
        for field in field_items[:6]:
            label = _safe_text(field.get("display_name")) or _safe_text(field.get("raw_name"))
            if label:
                key_fields.append(label)

    business_name = _guess_business_name(dataset_row, source_row=source_row)
    business_description = (
        f"{business_name}，用于{_safe_text((source_row or {}).get('source_kind')) or '数据源'}侧的数据采集与分析。"
    )
    if key_fields:
        business_description = f"{business_name}，关键字段包含：{', '.join(key_fields[:6])}。"

    schema_summary = dict(dataset_row.get("schema_summary") or {})
    generated_from = {
        "source_kind": _safe_text((source_row or {}).get("source_kind")),
        "provider_code": _safe_text((source_row or {}).get("provider_code")),
        "dataset_kind": _safe_text(dataset_row.get("dataset_kind")),
        "resource_key": _safe_text(dataset_row.get("resource_key")),
        "schema_hash": _hash_payload(schema_summary),
        "sample_hash": _hash_payload(sample_rows[:SEMANTIC_SAMPLE_ROW_LIMIT]) if has_sample_rows else "",
        "has_sample_rows": has_sample_rows,
    }
    semantic_status = _normalize_semantic_status(
        status,
        default="generated_with_samples" if has_sample_rows else "generated_basic",
    )
    return {
        "version": 1,
        "status": semantic_status,
        "business_name": business_name,
        "business_description": business_description,
        "key_fields": key_fields,
        "field_label_map": field_label_map,
        "fields": field_items,
        "low_confidence_fields": low_confidence_fields,
        "generated_from": generated_from,
        "updated_at": _now_iso(),
    }


def _extract_semantic_profile(dataset_row: dict[str, Any]) -> dict[str, Any]:
    meta = dict(dataset_row.get("meta") or {})
    semantic_profile = meta.get("semantic_profile")
    if not isinstance(semantic_profile, dict):
        return {}
    return semantic_profile


def _flatten_semantic_profile(dataset_row: dict[str, Any]) -> dict[str, Any]:
    profile = _extract_semantic_profile(dataset_row)
    if not profile:
        return {
            "semantic_status": "missing",
            "semantic_updated_at": "",
            "business_name": "",
            "business_description": "",
            "key_fields": [],
            "field_label_map": {},
            "semantic_fields": [],
            "low_confidence_fields": [],
        }
    return {
        "semantic_status": _normalize_semantic_status(
            profile.get("status"),
            default="generated_with_samples" if bool(profile.get("generated_from", {}).get("has_sample_rows")) else "generated_basic",
        ),
        "semantic_updated_at": _safe_text(profile.get("updated_at")),
        "business_name": _safe_text(profile.get("business_name")),
        "business_description": _safe_text(profile.get("business_description")),
        "key_fields": [str(item) for item in profile.get("key_fields") or [] if _safe_text(item)],
        "field_label_map": dict(profile.get("field_label_map") or {}),
        "semantic_fields": [item for item in profile.get("fields") or [] if isinstance(item, dict)],
        "low_confidence_fields": [str(item) for item in profile.get("low_confidence_fields") or [] if _safe_text(item)],
    }


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


def _extract_sample_payload_rows(snapshot_rows: list[dict[str, Any]], *, limit: int = SEMANTIC_SAMPLE_ROW_LIMIT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in snapshot_rows:
        payload = item.get("item_payload")
        if not isinstance(payload, dict):
            continue
        rows.append(payload)
        if len(rows) >= max(1, min(limit, 100)):
            break
    return rows


def _load_dataset_sample_rows_from_published_snapshot(
    *,
    data_source_id: str,
    resource_key: str,
    limit: int = SEMANTIC_SAMPLE_ROW_LIMIT,
) -> list[dict[str, Any]]:
    snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=data_source_id,
        resource_key=resource_key or "default",
    )
    if not snapshot:
        return []
    snapshot_rows = auth_db.list_unified_dataset_snapshot_items(
        snapshot_id=str(snapshot.get("id") or ""),
        limit=max(1, min(limit, 100)),
        offset=0,
    )
    return _extract_sample_payload_rows(snapshot_rows, limit=limit)


def _persist_dataset_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    semantic_profile: dict[str, Any],
) -> dict[str, Any] | None:
    dataset_id = _safe_text(dataset_row.get("id"))
    if not dataset_id:
        return None
    meta = dict(dataset_row.get("meta") or {})
    meta["semantic_profile"] = semantic_profile
    return auth_db.update_unified_data_source_dataset_meta(
        dataset_id=dataset_id,
        meta=meta,
    )


def _merge_existing_semantic_profile(
    *,
    generated_profile: dict[str, Any],
    existing_profile: dict[str, Any],
) -> dict[str, Any]:
    if not existing_profile:
        return generated_profile

    merged_profile = dict(generated_profile)
    existing_status = _normalize_semantic_status(
        existing_profile.get("status"),
        default="generated_basic",
    )
    valid_field_names = {
        _safe_text(item.get("raw_name"))
        for item in generated_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    }

    next_field_label_map = dict(generated_profile.get("field_label_map") or {})
    generated_fields = [
        dict(item)
        for item in generated_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    ]
    generated_fields_by_name = {
        _safe_text(item.get("raw_name")): item
        for item in generated_fields
        if _safe_text(item.get("raw_name"))
    }

    existing_field_label_map = dict(existing_profile.get("field_label_map") or {})
    existing_fields = [
        dict(item)
        for item in existing_profile.get("fields") or []
        if isinstance(item, dict) and _safe_text(item.get("raw_name"))
    ]
    existing_fields_by_name = {
        _safe_text(item.get("raw_name")): item
        for item in existing_fields
        if _safe_text(item.get("raw_name"))
    }

    preserve_manual_profile = existing_status == "manual_updated"
    if preserve_manual_profile:
        business_name = _safe_text(existing_profile.get("business_name"))
        if business_name:
            merged_profile["business_name"] = business_name
        business_description = _safe_text(existing_profile.get("business_description"))
        if business_description:
            merged_profile["business_description"] = business_description
        key_fields = [
            _safe_text(item)
            for item in existing_profile.get("key_fields") or []
            if _safe_text(item)
        ]
        if key_fields:
            merged_profile["key_fields"] = key_fields
        merged_profile["status"] = "manual_updated"

    for raw_name in valid_field_names:
        existing_field = existing_fields_by_name.get(raw_name)
        existing_label = _safe_text(existing_field_label_map.get(raw_name))
        preserve_field = preserve_manual_profile or bool(existing_field and existing_field.get("confirmed_by_user"))
        if not preserve_field and not existing_label:
            continue

        generated_field = dict(generated_fields_by_name.get(raw_name) or {"raw_name": raw_name})
        if existing_label:
            generated_field["display_name"] = existing_label
            next_field_label_map[raw_name] = existing_label
        for key in ("semantic_type", "business_role", "description"):
            value = _safe_text((existing_field or {}).get(key))
            if value:
                generated_field[key] = value
        if existing_field is not None and existing_field.get("confidence") is not None:
            try:
                generated_field["confidence"] = round(
                    max(0.0, min(float(existing_field.get("confidence")), 1.0)),
                    4,
                )
            except (TypeError, ValueError):
                pass
        if existing_field is not None:
            generated_field["confirmed_by_user"] = bool(existing_field.get("confirmed_by_user", preserve_manual_profile))
        elif existing_label:
            generated_field["confirmed_by_user"] = preserve_manual_profile
        generated_fields_by_name[raw_name] = generated_field

    merged_fields = [
        generated_fields_by_name.get(_safe_text(item.get("raw_name")), item)
        for item in generated_fields
    ]
    low_confidence_fields = [
        _safe_text(item.get("raw_name"))
        for item in merged_fields
        if _safe_text(item.get("raw_name"))
        and float(item.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD
        and not bool(item.get("confirmed_by_user"))
    ]

    merged_profile["field_label_map"] = next_field_label_map
    merged_profile["fields"] = merged_fields
    merged_profile["low_confidence_fields"] = low_confidence_fields
    return merged_profile


def _refresh_dataset_semantic_profile(
    *,
    dataset_row: dict[str, Any],
    source_row: dict[str, Any] | None,
    sample_rows: list[dict[str, Any]] | None = None,
    status: str = "",
) -> dict[str, Any] | None:
    rows = [row for row in (sample_rows or []) if isinstance(row, dict)]
    semantic_profile = _build_semantic_profile(
        dataset_row=dataset_row,
        source_row=source_row,
        sample_rows=rows,
        status=status or ("generated_with_samples" if rows else "generated_basic"),
    )
    semantic_profile = _merge_existing_semantic_profile(
        generated_profile=semantic_profile,
        existing_profile=_extract_semantic_profile(dataset_row),
    )
    updated = _persist_dataset_semantic_profile(
        dataset_row=dataset_row,
        semantic_profile=semantic_profile,
    )
    return updated or dataset_row


def _resolve_dataset_row(
    *,
    company_id: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    dataset_id = _dataset_id_from_args(arguments)
    if dataset_id:
        return auth_db.get_unified_data_source_dataset_by_id(
            company_id=company_id,
            dataset_id=dataset_id,
        )

    source_id = _source_id_from_args(arguments)
    if not source_id:
        return None
    dataset_code = _sanitize_dataset_code(arguments.get("dataset_code"))
    resource_key = _safe_text(arguments.get("resource_key"))
    rows = auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=source_id,
        status=None,
        include_deleted=True,
        limit=2000,
    )
    if dataset_code:
        return next((item for item in rows if _safe_text(item.get("dataset_code")) == dataset_code), None)
    if resource_key:
        return next((item for item in rows if _safe_text(item.get("resource_key")) == resource_key), None)
    return rows[0] if rows else None


def _normalize_manual_semantic_patch(
    arguments: dict[str, Any],
    *,
    valid_field_names: set[str],
) -> dict[str, Any]:
    patch = dict(arguments.get("semantic_profile") or {})
    for key in ("business_name", "business_description", "key_fields", "field_label_map", "fields", "status"):
        if arguments.get(key) is not None:
            patch[key] = arguments.get(key)

    normalized: dict[str, Any] = {}
    if patch.get("business_name") is not None:
        name = _safe_text(patch.get("business_name"))
        if name:
            normalized["business_name"] = name
    if patch.get("business_description") is not None:
        normalized["business_description"] = _safe_text(patch.get("business_description"))

    key_fields = patch.get("key_fields")
    if isinstance(key_fields, list):
        normalized["key_fields"] = [_safe_text(item) for item in key_fields if _safe_text(item)]

    field_label_map = patch.get("field_label_map")
    fields = patch.get("fields")
    if (isinstance(field_label_map, dict) or isinstance(fields, list)) and not valid_field_names:
        raise ValueError("当前数据集缺少 schema 字段定义，无法更新字段中文名或字段语义")

    if isinstance(field_label_map, dict):
        cleaned_map: dict[str, str] = {}
        for raw_name, display_name in field_label_map.items():
            raw_key = _safe_text(raw_name)
            if not raw_key:
                continue
            if raw_key not in valid_field_names:
                raise ValueError(f"field_label_map 包含不存在字段: {raw_key}")
            cleaned_map[raw_key] = _safe_text(display_name) or raw_key
        normalized["field_label_map"] = cleaned_map

    if isinstance(fields, list):
        cleaned_fields: list[dict[str, Any]] = []
        for item in fields:
            if not isinstance(item, dict):
                continue
            raw_name = _safe_text(item.get("raw_name"))
            if not raw_name:
                continue
            if raw_name not in valid_field_names:
                raise ValueError(f"fields 包含不存在字段: {raw_name}")
            confidence_value = item.get("confidence")
            try:
                confidence = float(confidence_value)
            except (TypeError, ValueError):
                confidence = 0.5
            cleaned_fields.append(
                {
                    "raw_name": raw_name,
                    "display_name": _safe_text(item.get("display_name")) or raw_name,
                    "semantic_type": _safe_text(item.get("semantic_type")) or "unknown",
                    "business_role": _safe_text(item.get("business_role")) or "unknown",
                    "description": _safe_text(item.get("description")),
                    "confidence": round(max(0.0, min(confidence, 1.0)), 4),
                    "sample_values": [str(v) for v in item.get("sample_values") or [] if _safe_text(v)],
                    "confirmed_by_user": bool(item.get("confirmed_by_user", True)),
                }
            )
        normalized["fields"] = cleaned_fields

    status = patch.get("status")
    if status is not None:
        normalized["status"] = _normalize_semantic_status(status, default="manual_updated")
    return normalized

def _export_snapshot_rows_to_excel(
    *,
    snapshot_id: str,
    table_name: str,
    query: dict[str, Any] | None = None,
) -> tuple[str, int]:
    rows = auth_db.list_unified_dataset_snapshot_items(snapshot_id=snapshot_id, limit=None, offset=0)
    payload_rows = [
        dict(item.get("item_payload") or {})
        for item in rows
        if isinstance(item, dict) and isinstance(item.get("item_payload"), dict)
    ]
    filters = dict((query or {}).get("filters") or {}) if isinstance(query, dict) else {}
    if filters:
        payload_rows = [
            row for row in payload_rows
            if all(str(row.get(key, "")) == str(value) for key, value in filters.items())
        ]
    export_root = UPLOAD_ROOT / "published_snapshot_exports"
    export_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="published_snapshot_export_", dir=str(export_root)))
    safe_name = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in table_name).strip("_") or "dataset"
    output_path = temp_dir / f"{safe_name}.xlsx"
    df = pd.DataFrame(payload_rows)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return str(output_path), len(payload_rows)


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


async def _refresh_dataset_samples(
    *,
    auth_token: str,
    company_id: str,
    source_row: dict[str, Any],
    mode: str = "",
    reason: str = "",
) -> int:
    source_kind = str(source_row.get("source_kind") or "")
    if source_kind != "database" or not auth_token:
        return 0
    source_id = str(source_row.get("id") or "")
    dataset_rows = auth_db.list_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=source_id,
        status=None,
        include_deleted=False,
        limit=AUTO_SAMPLE_DATASET_LIMIT,
    )
    if not dataset_rows:
        return 0

    runtime_source = _load_runtime_source(source_row, include_secret=True)
    connector = build_connector(runtime_source)
    sampled = 0
    for dataset_row in dataset_rows[:AUTO_SAMPLE_DATASET_LIMIT]:
        resource_key = str(dataset_row.get("resource_key") or "")
        preview_result = connector.preview(
            {
                "resource_key": resource_key,
                "dataset_code": str(dataset_row.get("dataset_code") or ""),
                "limit": AUTO_SAMPLE_ROW_LIMIT,
                "dataset": {
                    "dataset_code": dataset_row.get("dataset_code"),
                    "resource_key": resource_key,
                    "extract_config": dataset_row.get("extract_config"),
                },
            }
        )
        rows = [row for row in preview_result.get("rows") or [] if isinstance(row, dict)]
        if not rows:
            continue

        snapshot = auth_db.create_unified_dataset_snapshot(
            company_id=company_id,
            data_source_id=source_id,
            resource_key=resource_key or "default",
            snapshot_name=f"auto_sample_{dataset_row.get('dataset_code')}",
            record_count=len(rows),
            meta={
                "dataset_code": dataset_row.get("dataset_code"),
                "refresh_reason": reason or "auto_refresh",
                "mode": mode,
            },
        )
        if not snapshot:
            continue

        items = []
        for index, row in enumerate(rows):
            items.append(
                {
                    "item_key": str(index + 1),
                    "item_payload": row,
                    "item_hash": _hash_payload(row),
                }
            )
        auth_db.append_unified_dataset_snapshot_items(
            company_id=company_id,
            data_source_id=source_id,
            snapshot_id=str(snapshot["id"]),
            items=items,
        )
        auth_db.mark_unified_dataset_snapshot_published(snapshot_id=str(snapshot["id"]))
        try:
            refreshed_dataset_row = _refresh_dataset_semantic_profile(
                dataset_row=dataset_row,
                source_row=source_row,
                sample_rows=rows,
                status="generated_with_samples",
            )
            if refreshed_dataset_row:
                dataset_row = refreshed_dataset_row
        except Exception as exc:
            logger.warning(
                "refresh semantic profile after sample snapshot failed: source_id=%s dataset_code=%s error=%s",
                source_id,
                dataset_row.get("dataset_code"),
                exc,
            )
        sampled += 1

    if sampled:
        auth_db.create_unified_data_source_event(
            company_id=company_id,
            data_source_id=source_id,
            event_type="dataset_samples_refreshed",
            event_level="info",
            event_message=f"采集 {sampled} 个数据集的样例数据",
            event_payload={
                "sampled_dataset_count": sampled,
                "row_limit": AUTO_SAMPLE_ROW_LIMIT,
                "reason": reason or "auto_refresh",
            },
        )
    return sampled


async def _auto_refresh_datasets_and_samples(
    *,
    auth_token: str,
    company_id: str,
    source_row: dict[str, Any],
    mode: str = "",
    reason: str = "",
) -> dict[str, int]:
    summary = {"discovered": 0, "sampled": 0}
    source_kind = str(source_row.get("source_kind") or "")
    if source_kind != "database" or not auth_token:
        return summary

    source_id = str(source_row.get("id") or "")
    try:
        discover_args = {
            "auth_token": auth_token,
            "source_id": source_id,
            "persist": True,
            "limit": AUTO_DISCOVER_DATASET_LIMIT,
            "mode": mode,
        }
        discover_result = await _handle_data_source_discover_datasets(discover_args)
        if not discover_result.get("success"):
            return summary
        summary["discovered"] = int(discover_result.get("dataset_count") or 0)

        sampled = await _refresh_dataset_samples(
            auth_token=auth_token,
            company_id=company_id,
            source_row=source_row,
            mode=mode,
            reason=reason or "auto_refresh",
        )
        summary["sampled"] = sampled
        return summary
    except Exception as exc:
        logger.error("auto refresh datasets and samples failed: %s", exc, exc_info=True)
        return summary


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


def _merge_runtime_overrides(runtime_source: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    connection_override = arguments.get("connection_config")
    if isinstance(connection_override, dict) and connection_override:
        runtime_source["connection_config"] = {
            **dict(runtime_source.get("connection_config") or {}),
            **connection_override,
        }

    auth_override = arguments.get("auth_config")
    if isinstance(auth_override, dict) and auth_override:
        runtime_source["auth_config"] = {
            **dict(runtime_source.get("auth_config") or {}),
            **auth_override,
        }

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
    semantic_flat = _flatten_semantic_profile(dataset_row)
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
        "semantic_status": semantic_flat["semantic_status"],
        "semantic_updated_at": semantic_flat["semantic_updated_at"],
        "business_name": semantic_flat["business_name"] or str(dataset_row.get("dataset_name") or dataset_code),
        "business_description": semantic_flat["business_description"],
        "key_fields": semantic_flat["key_fields"],
        "field_label_map": semantic_flat["field_label_map"],
        "semantic_fields": semantic_flat["semantic_fields"],
        "low_confidence_fields": semantic_flat["low_confidence_fields"],
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
            name="data_source_refresh_dataset_semantic_profile",
            description="基于 schema 与样本刷新数据集语义层（business_name/字段中文名等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "sample_limit": {"type": "integer"},
                },
                "required": ["auth_token"],
            },
        ),
        Tool(
            name="data_source_update_dataset_semantic_profile",
            description="手动更新数据集语义层（业务名称、字段中文名等）。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **dataset_id_schema,
                    **source_id_schema,
                    "dataset_code": {"type": "string"},
                    "resource_key": {"type": "string"},
                    "semantic_profile": {"type": "object"},
                    "business_name": {"type": "string"},
                    "business_description": {"type": "string"},
                    "key_fields": {"type": "array", "items": {"type": "string"}},
                    "field_label_map": {"type": "object"},
                    "fields": {"type": "array", "items": {"type": "object"}},
                    "status": {"type": "string"},
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
            name="data_source_delete",
            description="删除数据源（标记为 deleted 并禁用）。",
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
        Tool(
            name="data_source_list_published_snapshot_rows",
            description="读取数据源当前已发布快照的前 N 行样本，供方案设计和试跑优先使用真实采集数据。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "resource_key": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["auth_token", "source_id"],
            },
        ),
        Tool(
            name="data_source_export_published_snapshot",
            description="将数据源当前已发布快照导出为临时 Excel 文件，供 proc/recon 运行时复用。",
            inputSchema={
                "type": "object",
                "properties": {
                    "auth_token": {"type": "string"},
                    **source_id_schema,
                    "resource_key": {"type": "string"},
                    "table_name": {"type": "string"},
                    "query": {"type": "object"},
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
        if name == "data_source_refresh_dataset_semantic_profile":
            return await _handle_data_source_refresh_dataset_semantic_profile(arguments)
        if name == "data_source_update_dataset_semantic_profile":
            return await _handle_data_source_update_dataset_semantic_profile(arguments)
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
        if name == "data_source_delete":
            return await _handle_data_source_delete(arguments)
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
        if name == "data_source_list_published_snapshot_rows":
            return await _handle_data_source_list_published_snapshot_rows(arguments)
        if name == "data_source_export_published_snapshot":
            return await _handle_data_source_export_published_snapshot(arguments)
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

    runtime_source = _merge_runtime_overrides(
        _load_runtime_source(source_row, include_secret=True),
        arguments,
    )
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
                try:
                    semantic_sample_rows = _load_dataset_sample_rows_from_published_snapshot(
                        data_source_id=source_id,
                        resource_key=_safe_text(upserted.get("resource_key")) or "default",
                        limit=SEMANTIC_SAMPLE_ROW_LIMIT,
                    )
                    refreshed = _refresh_dataset_semantic_profile(
                        dataset_row=upserted,
                        source_row=source_row,
                        sample_rows=semantic_sample_rows,
                        status="generated_with_samples" if semantic_sample_rows else "generated_basic",
                    )
                    persisted_rows.append(refreshed or upserted)
                except Exception as exc:
                    logger.warning(
                        "generate semantic profile during discover failed: source_id=%s dataset_code=%s error=%s",
                        source_id,
                        item["dataset_code"],
                        exc,
                    )
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
                    "meta": {
                        **dict(item.get("meta") or {}),
                        "semantic_profile": _build_semantic_profile(
                            dataset_row=item,
                            source_row=source_row,
                            sample_rows=[],
                            status="generated_basic",
                        ),
                    },
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
    sampled_count = 0
    auth_token = str(arguments.get("auth_token") or "").strip()
    if persist and auth_token:
        try:
            sampled_count = await _refresh_dataset_samples(
                auth_token=auth_token,
                company_id=company_id,
                source_row=source_row,
                mode=str(arguments.get("mode") or ""),
                reason="discover",
            )
        except Exception as exc:
            logger.error("refresh dataset samples after discover failed: %s", exc, exc_info=True)
    return {
        "success": True,
        "source_id": source_id,
        "persist": persist,
        "dataset_count": len(datasets),
        "persisted_count": len(persisted_rows),
        "persist_error_count": len(persist_errors),
        "sampled_dataset_count": sampled_count,
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
    row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
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

    sample_rows = _load_dataset_sample_rows_from_published_snapshot(
        data_source_id=source_id,
        resource_key=resource_key,
        limit=SEMANTIC_SAMPLE_ROW_LIMIT,
    )
    row = _refresh_dataset_semantic_profile(
        dataset_row=row,
        source_row=source_row,
        sample_rows=sample_rows,
        status="generated_with_samples" if sample_rows else "generated_basic",
    ) or row

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


async def _handle_data_source_refresh_dataset_semantic_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        return {"success": False, "error": "数据集不存在"}

    source_id = _safe_text(dataset_row.get("data_source_id"))
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    sample_limit = max(1, min(int(arguments.get("sample_limit") or SEMANTIC_SAMPLE_ROW_LIMIT), 100))
    resource_key = _safe_text(dataset_row.get("resource_key")) or "default"
    sample_rows = _load_dataset_sample_rows_from_published_snapshot(
        data_source_id=source_id,
        resource_key=resource_key,
        limit=sample_limit,
    )
    sample_source = "published_snapshot" if sample_rows else "none"

    if not sample_rows and str(source_row.get("source_kind") or "") not in AGENT_ASSISTED_KINDS:
        try:
            runtime_source = _load_runtime_source(source_row, include_secret=True)
            connector = build_connector(runtime_source)
            preview_result = connector.preview(
                {
                    "resource_key": resource_key,
                    "dataset_code": _safe_text(dataset_row.get("dataset_code")),
                    "limit": sample_limit,
                    "dataset": {
                        "dataset_code": _safe_text(dataset_row.get("dataset_code")),
                        "resource_key": resource_key,
                        "extract_config": dict(dataset_row.get("extract_config") or {}),
                    },
                }
            )
            sample_rows = [item for item in preview_result.get("rows") or [] if isinstance(item, dict)]
            if sample_rows:
                sample_source = "connector_preview"
        except Exception as exc:
            logger.warning(
                "refresh dataset semantic profile preview fallback failed: dataset_id=%s error=%s",
                dataset_row.get("id"),
                exc,
            )

    refreshed = _refresh_dataset_semantic_profile(
        dataset_row=dataset_row,
        source_row=source_row,
        sample_rows=sample_rows,
        status="generated_with_samples" if sample_rows else "generated_basic",
    )
    if not refreshed:
        return {"success": False, "error": "刷新语义层失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="dataset_semantic_refreshed",
        event_level="info",
        event_message=f"刷新数据集语义层：{_safe_text(dataset_row.get('dataset_name')) or _safe_text(dataset_row.get('dataset_code'))}",
        event_payload={
            "dataset_id": _safe_text(dataset_row.get("id")),
            "sample_rows_count": len(sample_rows),
            "sample_source": sample_source,
            "semantic_status": _flatten_semantic_profile(refreshed).get("semantic_status"),
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(refreshed),
        "sample_rows_count": len(sample_rows),
        "sample_source": sample_source,
        "message": "数据集语义层已刷新",
    }


async def _handle_data_source_update_dataset_semantic_profile(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    dataset_row = _resolve_dataset_row(company_id=company_id, arguments=arguments)
    if not dataset_row:
        return {"success": False, "error": "数据集不存在"}

    source_id = _safe_text(dataset_row.get("data_source_id"))
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    sample_rows = _load_dataset_sample_rows_from_published_snapshot(
        data_source_id=source_id,
        resource_key=_safe_text(dataset_row.get("resource_key")) or "default",
        limit=SEMANTIC_SAMPLE_ROW_LIMIT,
    )
    valid_field_names = {item.get("name") for item in _extract_dataset_columns(dataset_row, sample_rows) if _safe_text(item.get("name"))}
    try:
        patch = _normalize_manual_semantic_patch(
            arguments,
            valid_field_names={str(name) for name in valid_field_names if name},
        )
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    if not patch:
        return {"success": False, "error": "缺少可更新的语义层字段"}

    base_profile = _extract_semantic_profile(dataset_row)
    if not base_profile:
        base_profile = _build_semantic_profile(
            dataset_row=dataset_row,
            source_row=source_row,
            sample_rows=sample_rows,
            status="generated_with_samples" if sample_rows else "generated_basic",
        )
    next_profile = dict(base_profile)

    if "business_name" in patch:
        next_profile["business_name"] = patch["business_name"]
    if "business_description" in patch:
        next_profile["business_description"] = patch["business_description"]
    if "key_fields" in patch:
        next_profile["key_fields"] = patch["key_fields"]

    next_field_label_map = dict(next_profile.get("field_label_map") or {})
    if "field_label_map" in patch:
        next_field_label_map.update(dict(patch["field_label_map"]))

    existing_fields = [item for item in next_profile.get("fields") or [] if isinstance(item, dict)]
    fields_by_name = {_safe_text(item.get("raw_name")): dict(item) for item in existing_fields if _safe_text(item.get("raw_name"))}
    if "fields" in patch:
        for item in patch["fields"]:
            raw_name = _safe_text(item.get("raw_name"))
            if not raw_name:
                continue
            fields_by_name[raw_name] = item
            next_field_label_map[raw_name] = _safe_text(item.get("display_name")) or raw_name

    merged_fields = list(fields_by_name.values())
    low_confidence_fields = [
        _safe_text(item.get("raw_name"))
        for item in merged_fields
        if _safe_text(item.get("raw_name"))
        and float(item.get("confidence") or 0.0) < SEMANTIC_FIELD_CONFIDENCE_THRESHOLD
        and not bool(item.get("confirmed_by_user"))
    ]

    next_profile["field_label_map"] = next_field_label_map
    next_profile["fields"] = merged_fields
    next_profile["low_confidence_fields"] = low_confidence_fields
    next_profile["status"] = _normalize_semantic_status(patch.get("status"), default="manual_updated")
    next_profile["updated_at"] = _now_iso()
    next_profile["version"] = 1
    next_profile["generated_from"] = {
        **dict(next_profile.get("generated_from") or {}),
        "source_kind": _safe_text(source_row.get("source_kind")),
        "provider_code": _safe_text(source_row.get("provider_code")),
        "dataset_kind": _safe_text(dataset_row.get("dataset_kind")),
        "resource_key": _safe_text(dataset_row.get("resource_key")),
        "schema_hash": _hash_payload(dict(dataset_row.get("schema_summary") or {})),
        "sample_hash": _hash_payload(sample_rows[:SEMANTIC_SAMPLE_ROW_LIMIT]) if sample_rows else "",
        "has_sample_rows": bool(sample_rows),
    }

    updated = _persist_dataset_semantic_profile(
        dataset_row=dataset_row,
        semantic_profile=next_profile,
    )
    if not updated:
        return {"success": False, "error": "更新语义层失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="dataset_semantic_updated",
        event_level="info",
        event_message=f"更新数据集语义层：{_safe_text(dataset_row.get('dataset_name')) or _safe_text(dataset_row.get('dataset_code'))}",
        event_payload={
            "dataset_id": _safe_text(dataset_row.get("id")),
            "semantic_status": next_profile.get("status"),
        },
    )
    return {
        "success": True,
        "dataset": _build_dataset_view(updated),
        "message": "数据集语义层已更新",
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


async def _handle_data_source_delete(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    current = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not current:
        return {"success": False, "error": "数据源不存在"}

    row = auth_db.update_unified_data_source_status(
        data_source_id=source_id,
        status="deleted",
        is_enabled=False,
    )
    if not row:
        return {"success": False, "error": "删除数据源失败"}

    auth_db.create_unified_data_source_event(
        company_id=company_id,
        data_source_id=source_id,
        event_type="data_source_deleted",
        event_level="warn",
        event_message="数据源已删除",
        event_payload={"source_id": source_id},
    )
    return {
        "success": True,
        "source": _build_data_source_view(row),
        "message": "数据源已删除",
    }


async def _handle_data_source_test(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}
    runtime_source = _merge_runtime_overrides(
        _load_runtime_source(source_row, include_secret=True),
        arguments,
    )
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
        for key in ("db_type", "provider_code", "source_id"):
            if connector_result.get(key) is not None:
                result[key] = connector_result.get(key)

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
    response = {
        "success": success,
        "source_id": source_id,
        "result": result,
        "message": result["message"],
    }
    if not success:
        response["error"] = result["message"] or "数据源测试失败"
    return response


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
    updated_dataset_row = _update_dataset_health_by_resource(
        company_id=company_id,
        source_id=source_id,
        resource_key=resource_key,
        health_status="healthy",
        last_error_message="",
        last_sync_at=_now_iso(),
    )
    if updated_dataset_row:
        try:
            _refresh_dataset_semantic_profile(
                dataset_row=updated_dataset_row,
                source_row=source_row,
                sample_rows=rows[:SEMANTIC_SAMPLE_ROW_LIMIT],
                status="generated_with_samples" if rows else "generated_basic",
            )
        except Exception as exc:
            logger.warning(
                "refresh semantic profile after sync publish failed: source_id=%s resource_key=%s error=%s",
                source_id,
                resource_key,
                exc,
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


async def _handle_data_source_list_published_snapshot_rows(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    resource_key = _resource_key_from_args(arguments)
    snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=source_id,
        resource_key=resource_key,
    )
    if not snapshot:
        return {
            "success": True,
            "source_id": source_id,
            "resource_key": resource_key,
            "published_snapshot": None,
            "rows": [],
            "count": 0,
            "message": "暂无已发布快照",
        }

    limit = max(1, min(int(arguments.get("limit") or 3), 100))
    snapshot_rows = auth_db.list_unified_dataset_snapshot_items(
        snapshot_id=str(snapshot.get("id") or ""),
        limit=limit,
        offset=0,
    )
    rows = [
        dict(item.get("item_payload") or {})
        for item in snapshot_rows
        if isinstance(item, dict) and isinstance(item.get("item_payload"), dict)
    ]
    return {
        "success": True,
        "source_id": source_id,
        "resource_key": resource_key,
        "snapshot_id": str(snapshot.get("id") or ""),
        "published_snapshot": _attach_aliases_to_snapshot(snapshot),
        "rows": rows,
        "count": len(rows),
        "message": "已读取已发布快照样本",
    }


async def _handle_data_source_export_published_snapshot(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    source_id = _source_id_from_args(arguments)
    source_row = auth_db.get_unified_data_source_by_id(company_id=company_id, data_source_id=source_id)
    if not source_row:
        return {"success": False, "error": "数据源不存在"}

    resource_key = _resource_key_from_args(arguments)
    snapshot = auth_db.get_unified_published_dataset_snapshot(
        data_source_id=source_id,
        resource_key=resource_key,
    )
    if not snapshot:
        return {
            "success": False,
            "error": "暂无已发布快照，无法导出",
            "source_id": source_id,
        }

    table_name = str(
        arguments.get("table_name")
        or snapshot.get("resource_key")
        or snapshot.get("dataset_code")
        or resource_key
        or source_id
    ).strip()
    query = arguments.get("query") if isinstance(arguments.get("query"), dict) else {}
    file_path, row_count = _export_snapshot_rows_to_excel(
        snapshot_id=str(snapshot.get("id") or ""),
        table_name=table_name,
        query=query,
    )
    return {
        "success": True,
        "source_id": source_id,
        "resource_key": resource_key,
        "snapshot_id": str(snapshot.get("id") or ""),
        "table_name": table_name,
        "file_path": file_path,
        "row_count": row_count,
        "query": query,
        "published_snapshot": _attach_aliases_to_snapshot(snapshot),
        "message": "已导出已发布快照",
    }

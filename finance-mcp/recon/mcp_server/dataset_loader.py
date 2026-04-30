"""Dataset query loader for recon MCP.

统一 dataset 协议（对上游）：
- dataset_ref.source_type: "db" | "api" | 自定义类型
- dataset_ref.source_key: 数据源标识（必须）
- dataset_ref.query: 查询条件对象（必须）

说明：
- 不接受 rows/data 占位数据。
- 不接受 query.sql / query.url 这类原始数据源细节透传。
- 由 source_key 在 MCP 内部决定如何取数（registry 或 handler）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from auth import db as auth_db
from db_config import get_db_connection

logger = logging.getLogger(__name__)

DatasetLoader = Callable[[dict[str, Any], str], pd.DataFrame]
SourceKeyHandler = Callable[[str, dict[str, Any], dict[str, Any]], pd.DataFrame]

_DATASET_LOADERS: dict[str, DatasetLoader] = {}
_SOURCE_KEY_HANDLERS: dict[tuple[str, str], SourceKeyHandler] = {}
_DATASET_REF_ALLOWED_KEYS = {"source_type", "source_key", "query"}
_DB_QUERY_ALLOWED_KEYS = {"columns", "filters", "order_by", "limit"}
_API_QUERY_ALLOWED_KEYS = {"filters", "body", "timeout_seconds"}
_COLLECTION_RECORDS_QUERY_ALLOWED_KEYS = {
    "dataset_id",
    "resource_key",
    "biz_date",
    "date_field",
    "filters",
    "order_by",
    "limit",
}


class DatasetLoadError(RuntimeError):
    """Raised when dataset loading fails."""


_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FLOAT_INTEGER_RE = re.compile(r"^-?\d+\.0+$")


def _is_scalar_filter_value(value: Any) -> bool:
    """Only allow scalar DB filter values to avoid passing arbitrary structures."""
    return isinstance(value, (str, int, float, bool)) or value is None


def _is_db_filter_value(value: Any) -> bool:
    if _is_scalar_filter_value(value):
        return True
    if isinstance(value, list):
        return all(_is_scalar_filter_value(item) for item in value)
    return False


def _is_collection_filter_value(value: Any) -> bool:
    if _is_scalar_filter_value(value):
        return True
    if isinstance(value, list):
        return all(_is_scalar_filter_value(item) for item in value)
    return False


def _normalize_filter_token(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
            return value.strftime("%Y-%m-%d")
        return value.isoformat()
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0 and value.second == 0 and value.microsecond == 0:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    text = str(value).strip()
    if _FLOAT_INTEGER_RE.fullmatch(text):
        return text.split(".", 1)[0]
    return text


def _apply_collection_record_scalar_filter(df: pd.DataFrame, field_name: str, value: Any) -> pd.DataFrame:
    if isinstance(value, list):
        expected_values = {_normalize_filter_token(item) for item in value}
        series = df[field_name].map(_normalize_filter_token)
        return df[series.isin(expected_values)]
    if value is None:
        return df[df[field_name].isna()]

    expected = _normalize_filter_token(value)
    series = df[field_name]
    exact_mask = series.map(_normalize_filter_token) == expected
    if isinstance(value, str) and _DATE_ONLY_RE.fullmatch(expected):
        token_series = series.map(_normalize_filter_token)
        date_prefix_mask = (
            (token_series == expected)
            | token_series.str.startswith(f"{expected} ", na=False)
            | token_series.str.startswith(f"{expected}T", na=False)
        )
        if date_prefix_mask.any():
            return df[exact_mask | date_prefix_mask.fillna(False)]

        parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().any():
            date_mask = parsed.dt.strftime("%Y-%m-%d") == expected
            return df[exact_mask | date_mask.fillna(False)]
    return df[exact_mask]


def _safe_query_param_name(name: str) -> str:
    text = str(name or "").strip()
    if not text:
        raise DatasetLoadError("query 参数名不能为空")
    normalized = text.replace("_", "").replace("-", "").replace(".", "")
    if not normalized.isalnum():
        raise DatasetLoadError(f"非法 query 参数名: {text}")
    return text


def register_dataset_loader(source_type: str, loader: DatasetLoader) -> None:
    """Register source_type-level loader."""
    key = str(source_type or "").strip().lower()
    if not key:
        raise ValueError("source_type 不能为空")
    _DATASET_LOADERS[key] = loader


def register_source_key_handler(source_type: str, source_key: str, handler: SourceKeyHandler) -> None:
    """Register source_key-level handler for fine-grained data fetch."""
    st = str(source_type or "").strip().lower()
    sk = str(source_key or "").strip()
    if not st or not sk:
        raise ValueError("source_type/source_key 不能为空")
    _SOURCE_KEY_HANDLERS[(st, sk)] = handler


def _resolve_registry_source(source_type: str, source_key: str) -> dict[str, Any]:
    """Resolve source config from RECON_DATASET_SOURCE_REGISTRY env.

    Example:
    RECON_DATASET_SOURCE_REGISTRY='{
      "xm_statement_daily": {
        "source_type": "db",
        "table": "public.xm_statement_daily",
        "queryable_fields": ["biz_date", "channel_code", "shop_id"],
        "sortable_fields": ["id", "biz_date"],
        "default_order_by": ["id"],
        "max_limit": 50000
      },
      "xm_official_api": {
        "source_type": "api",
        "url": "https://example.com/recon/xm",
        "method": "GET",
        "headers": {"X-App": "recon"},
        "data_path": "data.items",
        "timeout_seconds": 30
      }
    }'
    """
    raw = os.getenv("RECON_DATASET_SOURCE_REGISTRY", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("[recon][dataset] RECON_DATASET_SOURCE_REGISTRY 不是合法 JSON，已忽略")
        return {}
    if not isinstance(parsed, dict):
        return {}
    item = parsed.get(source_key)
    if not isinstance(item, dict):
        return {}
    item_type = str(item.get("source_type") or "").strip().lower()
    if item_type and item_type != source_type:
        logger.warning(
            "[recon][dataset] source_key=%s registry source_type=%s 与请求 source_type=%s 不一致，按请求类型继续",
            source_key,
            item_type,
            source_type,
        )
    return item


def dataset_display_name(dataset_ref: dict[str, Any], table_name: str) -> str:
    """Resolve display name for dataset input."""
    source_key = str(dataset_ref.get("source_key") or "").strip()
    if source_key:
        return source_key
    return table_name


def _require_dataset_protocol(dataset_ref: dict[str, Any], table_name: str) -> tuple[str, str, dict[str, Any]]:
    """Validate dataset protocol and return source_type/source_key/query."""
    if not isinstance(dataset_ref, dict):
        raise DatasetLoadError(f"表 '{table_name}' 的 dataset_ref 必须是对象")
    legacy_rows_data = isinstance(dataset_ref.get("rows"), list) or isinstance(dataset_ref.get("data"), list)
    extra_dataset_ref_keys = sorted(set(dataset_ref.keys()) - _DATASET_REF_ALLOWED_KEYS - {"rows", "data"})
    if extra_dataset_ref_keys:
        raise DatasetLoadError(
            f"表 '{table_name}' 的 dataset_ref 含不支持字段。"
            "仅支持: source_type, source_key, query"
        )

    source_type = str(dataset_ref.get("source_type") or "").strip().lower()
    source_key = str(dataset_ref.get("source_key") or "").strip()
    query = dataset_ref.get("query")

    if not source_type:
        raise DatasetLoadError(
            f"表 '{table_name}' 缺少 dataset_ref.source_type。"
            "请传 source_type=db/api 和 dataset_ref.query。"
        )
    if not source_key:
        raise DatasetLoadError(
            f"表 '{table_name}' 缺少 dataset_ref.source_key。"
            "请传 source_key 作为数据源标识。"
        )
    if not isinstance(query, dict):
        if legacy_rows_data:
            raise DatasetLoadError(
                f"表 '{table_name}' 的 dataset_ref.rows/data 已废弃。请改为 query 条件模式。"
            )
        raise DatasetLoadError(
            f"表 '{table_name}' 缺少 dataset_ref.query。请使用 source_key + query 条件模式。"
        )
    if "sql" in query:
        raise DatasetLoadError(
            f"表 '{table_name}' 不允许 query.sql。请仅传 query 条件，由 source_key 在 MCP 内部决定取数。"
        )
    if "url" in query:
        raise DatasetLoadError(
            f"表 '{table_name}' 不允许 query.url。请由 source_key 在 registry/handler 中配置 API 地址。"
        )
    return source_type, source_key, query


def _safe_identifier(name: str) -> str:
    """Validate SQL identifier and return quoted identifier."""
    text = str(name or "").strip()
    if not text:
        raise DatasetLoadError("字段名不能为空")
    if not text.replace("_", "").replace(".", "").isalnum():
        raise DatasetLoadError(f"非法字段名: {text}")
    if "." in text:
        return ".".join(f'"{part}"' for part in text.split("."))
    return f'"{text}"'


def _safe_table_identifier(table_name: str) -> str:
    text = str(table_name or "").strip()
    if not text:
        raise DatasetLoadError("registry.table 不能为空")
    if not text.replace("_", "").replace(".", "").isalnum():
        raise DatasetLoadError(f"非法 table 名: {text}")
    return ".".join(f'"{part}"' for part in text.split("."))


def _append_db_filter_condition(
    *,
    where_parts: list[str],
    params: list[Any],
    field_name: str,
    value: Any,
    coerce_filters_to_text: bool,
) -> None:
    identifier = _safe_identifier(field_name)
    if isinstance(value, list):
        values = [_normalize_filter_token(item) for item in value] if coerce_filters_to_text else value
        if not values:
            where_parts.append("1 = 0")
            return
        if coerce_filters_to_text:
            where_parts.append(f"{identifier}::text = ANY(%s)")
        else:
            where_parts.append(f"{identifier} = ANY(%s)")
        params.append(values)
        return

    if coerce_filters_to_text:
        where_parts.append(f"{identifier}::text = %s")
        params.append(_normalize_filter_token(value))
        return
    where_parts.append(f"{identifier} = %s")
    params.append(value)


def _build_db_query_from_conditions(
    source_key: str,
    query: dict[str, Any],
    source_cfg: dict[str, Any],
    *,
    coerce_filters_to_text: bool = False,
) -> tuple[str, list[Any]]:
    """Build SQL from query conditions (no raw SQL from caller)."""
    extra_keys = sorted(set(query.keys()) - _DB_QUERY_ALLOWED_KEYS)
    if extra_keys:
        raise DatasetLoadError(
            f"source_key={source_key} query 含不支持字段。"
            f"仅支持: {', '.join(sorted(_DB_QUERY_ALLOWED_KEYS))}"
        )

    table = str(source_cfg.get("table") or "").strip()
    if not table:
        raise DatasetLoadError(
            f"source_key={source_key} 未配置 registry.table，也未注册 handler，无法构建 DB 查询。"
        )

    columns = query.get("columns")
    if columns is None:
        columns = source_cfg.get("default_columns") or []
    if columns and not isinstance(columns, list):
        raise DatasetLoadError("query.columns 必须是数组")
    if columns:
        select_clause = ", ".join(_safe_identifier(str(col)) for col in columns)
    else:
        select_clause = "*"

    queryable_fields = source_cfg.get("queryable_fields")
    if queryable_fields is None:
        queryable_fields = []
    if queryable_fields and not isinstance(queryable_fields, list):
        raise DatasetLoadError("registry.queryable_fields 必须是数组")
    queryable_set = {str(item) for item in queryable_fields}

    filters = query.get("filters")
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise DatasetLoadError("query.filters 必须是对象")

    where_parts: list[str] = []
    params: list[Any] = []
    for field, value in filters.items():
        field_name = str(field or "").strip()
        if not field_name:
            continue
        if queryable_set and field_name not in queryable_set:
            raise DatasetLoadError(
                f"source_key={source_key} 不允许按字段 '{field_name}' 过滤。"
            )
        if not _is_db_filter_value(value):
            raise DatasetLoadError(f"query.filters 字段 '{field_name}' 仅支持标量值或标量数组")
        _append_db_filter_condition(
            where_parts=where_parts,
            params=params,
            field_name=field_name,
            value=value,
            coerce_filters_to_text=coerce_filters_to_text,
        )

    default_filters = source_cfg.get("default_filters")
    if isinstance(default_filters, dict):
        for field, value in default_filters.items():
            field_name = str(field or "").strip()
            if not field_name:
                continue
            if not _is_db_filter_value(value):
                raise DatasetLoadError(f"registry.default_filters 字段 '{field_name}' 仅支持标量值或标量数组")
            _append_db_filter_condition(
                where_parts=where_parts,
                params=params,
                field_name=field_name,
                value=value,
                coerce_filters_to_text=coerce_filters_to_text,
            )

    sortable_fields = source_cfg.get("sortable_fields")
    if sortable_fields is None:
        sortable_fields = []
    if sortable_fields and not isinstance(sortable_fields, list):
        raise DatasetLoadError("registry.sortable_fields 必须是数组")
    sortable_set = {str(item) for item in sortable_fields}

    order_by = query.get("order_by")
    if order_by is None:
        order_by = source_cfg.get("default_order_by") or []
    if isinstance(order_by, str):
        order_by = [order_by]
    if not isinstance(order_by, list):
        raise DatasetLoadError("query.order_by 必须是字符串或数组")

    order_parts: list[str] = []
    for item in order_by:
        token = str(item or "").strip()
        if not token:
            continue
        parts = token.split()
        field_name = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        if direction not in {"ASC", "DESC"}:
            raise DatasetLoadError(f"排序方向仅支持 ASC/DESC，当前: {direction}")
        if sortable_set and field_name not in sortable_set:
            raise DatasetLoadError(
                f"source_key={source_key} 不允许按字段 '{field_name}' 排序。"
            )
        order_parts.append(f"{_safe_identifier(field_name)} {direction}")

    limit = query.get("limit")
    if limit is None:
        limit = source_cfg.get("default_limit", 10000)
    if not isinstance(limit, int) or limit <= 0:
        raise DatasetLoadError("query.limit 必须是正整数")
    max_limit = source_cfg.get("max_limit")
    if isinstance(max_limit, int) and max_limit > 0 and limit > max_limit:
        limit = max_limit

    sql = f"SELECT {select_clause} FROM {_safe_table_identifier(table)}"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    if order_parts:
        sql += " ORDER BY " + ", ".join(order_parts)
    sql += f" LIMIT {limit}"
    return sql, params


def _query_has_filters(query: dict[str, Any], source_cfg: dict[str, Any]) -> bool:
    return bool(query.get("filters")) or bool(source_cfg.get("default_filters"))


def _execute_db_query(
    *,
    source_key: str,
    query: dict[str, Any],
    source_cfg: dict[str, Any],
    coerce_filters_to_text: bool = False,
) -> pd.DataFrame:
    sql, params = _build_db_query_from_conditions(
        source_key,
        query,
        source_cfg,
        coerce_filters_to_text=coerce_filters_to_text,
    )
    conn = None
    cur = None

    try:
        import psycopg2.extras
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        if rows:
            return pd.DataFrame([dict(item) for item in rows])
        columns = [desc[0] for desc in (cur.description or [])]
        return pd.DataFrame(columns=columns)
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                conn.close()


def _load_from_db(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """Load dataset by DB query conditions (source_key + query)."""
    source_type, source_key, query = _require_dataset_protocol(dataset_ref, table_name)
    handler = _SOURCE_KEY_HANDLERS.get((source_type, source_key))
    source_cfg = _resolve_registry_source(source_type, source_key)
    if handler is not None:
        return handler(source_key, query, source_cfg)

    try:
        return _execute_db_query(source_key=source_key, query=query, source_cfg=source_cfg)
    except DatasetLoadError:
        raise
    except Exception as exc:
        if _query_has_filters(query, source_cfg):
            try:
                logger.warning(
                    "[recon][dataset] source_key=%s DB 查询类型不兼容，尝试文本兼容过滤",
                    source_key,
                )
                return _execute_db_query(
                    source_key=source_key,
                    query=query,
                    source_cfg=source_cfg,
                    coerce_filters_to_text=True,
                )
            except DatasetLoadError:
                raise
            except Exception as retry_exc:
                logger.error("[recon][dataset] source_key=%s DB 文本兼容查询仍失败", source_key, exc_info=True)
                raise DatasetLoadError(
                    f"source_key={source_key} DB 查询失败。字段类型可能与过滤值不一致，"
                    "或字段/过滤条件配置有误，请检查对账日期字段、关联字段和数据源配置。"
                ) from retry_exc
        logger.error("[recon][dataset] source_key=%s DB 查询失败", source_key, exc_info=True)
        raise DatasetLoadError(f"source_key={source_key} DB 查询失败，请检查 query 条件与数据源配置。") from exc


def _extract_data_by_path(payload: Any, path: str) -> Any:
    current = payload
    if not path:
        return current
    for part in path.split("."):
        key = part.strip()
        if not key:
            continue
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _load_from_api(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """Load dataset by API query conditions (source_key + query)."""
    source_type, source_key, query = _require_dataset_protocol(dataset_ref, table_name)
    extra_keys = sorted(set(query.keys()) - _API_QUERY_ALLOWED_KEYS)
    if extra_keys:
        raise DatasetLoadError(
            f"source_key={source_key} query 含不支持字段。"
            f"仅支持: {', '.join(sorted(_API_QUERY_ALLOWED_KEYS))}"
        )

    handler = _SOURCE_KEY_HANDLERS.get((source_type, source_key))
    source_cfg = _resolve_registry_source(source_type, source_key)
    if handler is not None:
        return handler(source_key, query, source_cfg)

    url = str(source_cfg.get("url") or "").strip()
    if not url:
        raise DatasetLoadError(
            f"source_key={source_key} 未注册 handler，且 registry 未配置 url，无法执行 API 读取。"
        )

    method = str(source_cfg.get("method") or "GET").strip().upper()
    if method not in {"GET", "POST"}:
        raise DatasetLoadError(f"source_key={source_key} 配置的 method={method} 不支持")

    timeout_seconds = query.get("timeout_seconds", source_cfg.get("timeout_seconds", 30))
    if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        timeout_seconds = 30

    params = query.get("filters")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise DatasetLoadError("query.filters 必须是对象")
    for key in params.keys():
        _safe_query_param_name(str(key))

    body = query.get("body")
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise DatasetLoadError("query.body 必须是对象")

    headers: dict[str, str] = {}
    for raw_headers in (source_cfg.get("headers"),):
        if isinstance(raw_headers, dict):
            for k, v in raw_headers.items():
                headers[str(k)] = str(v)

    request_data = None
    request_url = url
    if method == "GET":
        if params:
            query_str = urlencode(params, doseq=True)
            sep = "&" if "?" in url else "?"
            request_url = f"{url}{sep}{query_str}"
    else:
        headers.setdefault("Content-Type", "application/json")
        request_data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = Request(request_url, data=request_data, method=method, headers=headers)

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read()
    except HTTPError as exc:
        raise DatasetLoadError(f"source_key={source_key} API 请求失败: HTTP {exc.code}") from exc
    except URLError as exc:
        logger.warning("[recon][dataset] source_key=%s API 请求失败: %s", source_key, exc.reason)
        raise DatasetLoadError("API 请求失败，请检查 query 条件与数据源配置") from exc
    except Exception as exc:
        logger.error("[recon][dataset] source_key=%s API 请求异常", source_key, exc_info=True)
        raise DatasetLoadError("API 请求异常，请检查数据源配置") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise DatasetLoadError(f"source_key={source_key} API 响应不是合法 JSON") from exc

    data_path = str(source_cfg.get("data_path") or "data").strip()
    rows = payload if isinstance(payload, list) else _extract_data_by_path(payload, data_path)
    if rows is None and isinstance(payload, dict):
        rows = payload.get("items")

    if not isinstance(rows, list):
        raise DatasetLoadError(
            f"source_key={source_key} API 响应提取结果不是数组。请检查 registry.data_path。"
        )
    if rows and not isinstance(rows[0], dict):
        raise DatasetLoadError(f"source_key={source_key} API 响应数组元素必须是对象。")
    return pd.DataFrame(rows)


def _table_columns(table_name: str) -> set[str]:
    conn = None
    cur = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            """,
            (table_name,),
        )
        return {str(row[0]) for row in cur.fetchall() or []}
    except Exception as exc:
        logger.error("[recon][dataset] 查询表字段失败 table=%s", table_name, exc_info=True)
        raise DatasetLoadError(f"无法读取 {table_name} 表结构") from exc
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                conn.close()


def _first_existing_column(columns: set[str], candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return ""


def _load_collection_record_rows(
    *,
    source_key: str,
    query: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    columns = _table_columns("dataset_collection_records")
    if not columns:
        raise DatasetLoadError("未找到 dataset_collection_records 表，请先完成数据采集能力部署。")

    data_source_col = _first_existing_column(columns, ["data_source_id", "source_id"])
    payload_col = _first_existing_column(columns, ["record_payload", "payload", "payload_json", "item_payload", "data"])
    if not data_source_col or not payload_col:
        raise DatasetLoadError("dataset_collection_records 缺少 data_source_id/source_id 或 payload 字段。")

    dataset_col = _first_existing_column(columns, ["dataset_id", "data_source_dataset_id"])
    resource_col = _first_existing_column(columns, ["resource_key", "dataset_code"])
    biz_date_col = _first_existing_column(columns, ["biz_date", "business_date", "data_date"])
    created_col = _first_existing_column(columns, ["created_at", "collected_at", "updated_at", "id"])

    where_parts = [f"{_safe_identifier(data_source_col)} = %s"]
    params: list[Any] = [source_key]

    dataset_id = str(query.get("dataset_id") or "").strip()
    if dataset_id and dataset_col:
        where_parts.append(f"{_safe_identifier(dataset_col)} = %s")
        params.append(dataset_id)

    resource_key = str(query.get("resource_key") or "default").strip() or "default"
    if resource_key and resource_col:
        where_parts.append(f"{_safe_identifier(resource_col)} = %s")
        params.append(resource_key)

    biz_date = str(query.get("biz_date") or "").strip()
    if biz_date and biz_date_col:
        where_parts.append(f"{_safe_identifier(biz_date_col)} = %s")
        params.append(biz_date)

    filters = query.get("filters")
    if isinstance(filters, dict):
        for field, value in filters.items():
            field_name = str(field or "").strip()
            if not field_name:
                continue
            if isinstance(value, list):
                values = [str(item) for item in value if item is not None]
                if not values:
                    continue
                where_parts.append(f"({_safe_identifier(payload_col)} ->> %s) = ANY(%s)")
                params.extend([field_name, values])
            elif _is_scalar_filter_value(value) and value is not None:
                expected = str(value)
                if _DATE_ONLY_RE.fullmatch(expected):
                    continue
                where_parts.append(f"({_safe_identifier(payload_col)} ->> %s) = %s")
                params.extend([field_name, expected])

    order_by = query.get("order_by")
    if isinstance(order_by, str):
        order_by = [order_by]
    if order_by is None:
        order_by = []
    if not isinstance(order_by, list):
        raise DatasetLoadError("collection_records query.order_by 必须是字符串或数组")

    order_parts: list[str] = []
    for item in order_by:
        token = str(item or "").strip()
        if not token:
            continue
        parts = token.split()
        field_name = parts[0]
        direction = parts[1].upper() if len(parts) > 1 else "ASC"
        if field_name not in columns:
            raise DatasetLoadError(f"collection_records 表中不存在排序字段: {field_name}")
        if direction not in {"ASC", "DESC"}:
            raise DatasetLoadError(f"collection_records query.order_by 仅支持 ASC/DESC，当前: {direction}")
        order_parts.append(f"{_safe_identifier(field_name)} {direction}")
    if not order_parts and created_col:
        order_parts.append(f"{_safe_identifier(created_col)} ASC")

    limit = query.get("limit")
    if limit is not None:
        if not isinstance(limit, int) or limit <= 0:
            raise DatasetLoadError("collection_records query.limit 必须是正整数")
    limit_sql = f" LIMIT {limit}" if isinstance(limit, int) and limit > 0 else ""

    sql = f"SELECT {_safe_identifier(payload_col)} AS payload FROM dataset_collection_records"
    sql += " WHERE " + " AND ".join(where_parts)
    if order_parts:
        sql += " ORDER BY " + ", ".join(order_parts)
    sql += limit_sql

    conn = None
    cur = None
    try:
        import psycopg2.extras

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall() or []]
        return rows, payload_col
    except Exception as exc:
        logger.error("[recon][dataset] source_key=%s collection_records 查询失败", source_key, exc_info=True)
        raise DatasetLoadError("collection_records 查询失败，请检查数据采集记录。") from exc
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                conn.close()


def _load_from_collection_records(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """Load dataset from collected dataset_collection_records rows."""
    source_type, source_key, query = _require_dataset_protocol(dataset_ref, table_name)
    extra_keys = sorted(set(query.keys()) - _COLLECTION_RECORDS_QUERY_ALLOWED_KEYS)
    if extra_keys:
        raise DatasetLoadError(
            f"source_key={source_key} query 含不支持字段。"
            f"仅支持: {', '.join(sorted(_COLLECTION_RECORDS_QUERY_ALLOWED_KEYS))}"
        )

    rows, payload_col = _load_collection_record_rows(source_key=source_key, query=query)
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload") or row.get(payload_col)
        if isinstance(payload, dict):
            payload_rows.append(payload)

    if not payload_rows:
        raise DatasetLoadError(f"source_key={source_key} 暂无采集记录。请先采集数据后再执行对账。")

    df = pd.DataFrame(payload_rows)

    filters = query.get("filters")
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise DatasetLoadError("collection_records query.filters 必须是对象")
    for field, value in filters.items():
        field_name = str(field or "").strip()
        if not field_name:
            continue
        if field_name not in df.columns:
            raise DatasetLoadError(f"collection_records 数据中不存在过滤字段: {field_name}")
        if not _is_collection_filter_value(value):
            raise DatasetLoadError(f"collection_records query.filters 字段 '{field_name}' 仅支持标量值或标量数组")
        df = _apply_collection_record_scalar_filter(df, field_name, value)

    return df.reset_index(drop=True)


def load_dataset_as_df(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """Load dataset by source_type using source_key + query conditions."""
    source_type, _, _ = _require_dataset_protocol(dataset_ref, table_name)
    loader = _DATASET_LOADERS.get(source_type)
    if loader is None:
        if source_type == "db":
            loader = _load_from_db
        elif source_type == "api":
            loader = _load_from_api
        else:
            raise DatasetLoadError(
                f"不支持的 dataset source_type={source_type}。可通过 register_dataset_loader 扩展。"
            )
    return loader(dataset_ref, table_name)


register_dataset_loader("collection_records", _load_from_collection_records)

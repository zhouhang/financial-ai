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
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from db_config import get_db_connection

logger = logging.getLogger(__name__)

DatasetLoader = Callable[[dict[str, Any], str], pd.DataFrame]
SourceKeyHandler = Callable[[str, dict[str, Any], dict[str, Any]], pd.DataFrame]

_DATASET_LOADERS: dict[str, DatasetLoader] = {}
_SOURCE_KEY_HANDLERS: dict[tuple[str, str], SourceKeyHandler] = {}
_DATASET_REF_ALLOWED_KEYS = {"source_type", "source_key", "query"}
_DB_QUERY_ALLOWED_KEYS = {"columns", "filters", "order_by", "limit"}
_API_QUERY_ALLOWED_KEYS = {"filters", "body", "timeout_seconds"}


class DatasetLoadError(RuntimeError):
    """Raised when dataset loading fails."""


def _is_scalar_filter_value(value: Any) -> bool:
    """Only allow scalar DB filter values to avoid passing arbitrary structures."""
    return isinstance(value, (str, int, float, bool)) or value is None


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


def _build_db_query_from_conditions(source_key: str, query: dict[str, Any], source_cfg: dict[str, Any]) -> tuple[str, list[Any]]:
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
        if not _is_scalar_filter_value(value):
            raise DatasetLoadError(f"query.filters 字段 '{field_name}' 仅支持标量值")
        where_parts.append(f"{_safe_identifier(field_name)} = %s")
        params.append(value)

    default_filters = source_cfg.get("default_filters")
    if isinstance(default_filters, dict):
        for field, value in default_filters.items():
            field_name = str(field or "").strip()
            if not field_name:
                continue
            where_parts.append(f"{_safe_identifier(field_name)} = %s")
            params.append(value)

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


def _load_from_db(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """Load dataset by DB query conditions (source_key + query)."""
    source_type, source_key, query = _require_dataset_protocol(dataset_ref, table_name)
    handler = _SOURCE_KEY_HANDLERS.get((source_type, source_key))
    source_cfg = _resolve_registry_source(source_type, source_key)
    if handler is not None:
        return handler(source_key, query, source_cfg)

    sql, params = _build_db_query_from_conditions(source_key, query, source_cfg)

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
    except DatasetLoadError:
        raise
    except Exception as exc:
        logger.error("[recon][dataset] source_key=%s DB 查询失败", source_key, exc_info=True)
        raise DatasetLoadError("DB 查询失败，请检查 query 条件与数据源配置") from exc
    finally:
        try:
            if cur is not None:
                cur.close()
        finally:
            if conn is not None:
                conn.close()


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

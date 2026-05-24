"""认证模块的数据库操作"""

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
import time

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import OperationalError, InterfaceError

try:
    from auth.crypto import open_secret, seal_secret
except Exception:
    # Fallback to plain text in environments where encryption helpers are unavailable.
    def seal_secret(value: str) -> str:
        return value or ""

    def open_secret(value: str) -> str:
        return value or ""

logger = logging.getLogger(__name__)
_UNIFIED_DATA_SOURCE_SCHEMA_READY = False
_EXECUTION_RUN_TRIGGER_TYPES_SCHEMA_READY = False
_AUTH_SESSIONS_EXTRA_SCHEMA_READY = False
_PLATFORM_PENDING_AUTHORIZATIONS_SCHEMA_READY = False
_SYNC_JOBS_TRIGGER_MODES_SCHEMA_READY = False
_RECON_EXECUTION_QUEUE_SCHEMA_READY = False
_BROWSER_PLAYBOOK_COLLECTION_SCHEMA_READY = False
_BROWSER_HANDOFF_SCHEMA_READY = False

_UNIFIED_DATA_SOURCE_BASE_TABLES = {
    "data_sources",
    "data_source_credentials",
    "data_source_configs",
    "sync_jobs",
    "sync_job_attempts",
    "dataset_collection_records",
    "dataset_bindings",
}

_UNIFIED_DATA_SOURCE_HEALTH_COLUMNS = (
    "health_status",
    "last_checked_at",
    "last_error_message",
)

_UNIFIED_DATASET_CATALOG_COLUMNS = (
    "schema_name",
    "object_name",
    "object_type",
    "publish_status",
    "business_domain",
    "business_object_type",
    "grain",
    "usage_count",
    "last_used_at",
    "search_text",
)

_PLATFORM_ALIPAY_BILL_LINES_REQUIRED_COLUMNS = (
    "company_id",
    "data_source_id",
    "dataset_id",
    "shop_connection_id",
    "external_shop_id",
    "bill_type",
    "bill_date",
    "source_file_name",
    "source_row_number",
    "source_row_key",
    "payload",
)

_PLATFORM_ALIPAY_BILL_LINES_REQUIRED_CONSTRAINTS = (
    "platform_alipay_bill_lines_company_id_fkey",
    "platform_alipay_bill_lines_data_source_id_fkey",
    "platform_alipay_bill_lines_dataset_id_fkey",
    "platform_alipay_bill_lines_shop_connection_id_fkey",
    "platform_alipay_bill_lines_unique_bill_row",
)

_PLATFORM_ALIPAY_BILL_LINES_REQUIRED_INDEXES = (
    "idx_platform_alipay_bill_lines_dataset_date",
    "idx_platform_alipay_bill_lines_source_dataset_date",
    "idx_platform_alipay_bill_lines_shop_type_date",
)

_PLATFORM_ALIPAY_BILL_LINES_REQUIRED_TRIGGER = "update_platform_alipay_bill_lines_updated_at"
_PLATFORM_ALIPAY_BILL_LINES_DERIVED_BUSINESS_COLUMNS = (
    "alipay_trade_no",
    "merchant_order_no",
    "business_order_no",
    "amount",
    "income_amount",
    "expense_amount",
    "trade_time",
)
_PLATFORM_ALIPAY_SEMANTIC_PROFILE_HIDDEN_FIELDS = (
    "source_row_key",
    "source_file_name",
    "source_row_number",
    "data_source_id",
    "dataset_id",
    "shop_connection_id",
    "resource_key",
    "created_at",
    "updated_at",
    "bill_type",
    "bill_date",
    "biz_date",
    "company_id",
    "external_shop_id",
    "platform_code",
    "merchant_display_name",
    *_PLATFORM_ALIPAY_BILL_LINES_DERIVED_BUSINESS_COLUMNS,
    "raw",
    "payload",
    "meta",
    "metadata",
)

_RECON_EXECUTION_QUEUE_REQUIRED_COLUMNS = (
    "next_retry_at",
    "wait_deadline_at",
    "waiting_reason",
    "waiting_datasets",
    "collection_job_ids",
)

_RECON_EXECUTION_QUEUE_REQUIRED_CONSTRAINTS = (
    "recon_execution_queue_status_check",
)

_UNIFIED_DATASET_SELECT_COLUMNS_SQL = """
    id, company_id, data_source_id, dataset_code, dataset_name,
    resource_key, dataset_kind, origin_type,
    schema_name, object_name, object_type,
    publish_status, business_domain, business_object_type, grain,
    usage_count, last_used_at, search_text,
    extract_config, schema_summary, sync_strategy,
    status, is_enabled, health_status,
    last_checked_at, last_sync_at, last_error_message, meta,
    created_at, updated_at
""".strip()


def _serialize_datetimes(d: dict) -> dict:
    """将字典中所有 datetime 对象转为 ISO 格式字符串（原地修改并返回）"""
    from datetime import datetime, date
    for k, v in d.items():
        if isinstance(v, (datetime, date)):
            d[k] = v.isoformat()
    return d


def _json_safe_value(value: Any) -> Any:
    """将 JSON 不可序列化对象转换为可安全写入 jsonb 的值。"""
    from datetime import date, datetime
    from decimal import Decimal
    import uuid

    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return value


def _json_safe_payload(payload: Any) -> Any:
    return _json_safe_value(payload)


def _normalize_record(row: dict, decrypt_fields: list[str] | None = None) -> dict:
    """标准化数据库记录（UUID/Datetime 转字符串，可选解密字段）。"""
    from datetime import datetime, date
    import uuid

    result: dict = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
        elif isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value

    if decrypt_fields:
        for field in decrypt_fields:
            if field in result:
                result[field] = open_secret(result.get(field) or "")

    return result


def _seal_json_payload(payload: Any) -> str:
    """将结构化 payload 序列化后密封存储。"""
    if payload in (None, "", {}):
        return ""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return seal_secret(raw)


def _open_json_payload(value: str | None) -> dict[str, Any]:
    """读取密封后的 JSON payload。"""
    raw = open_secret(value or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return {"raw": raw}


def _normalize_catalog_status(
    value: str | None,
    *,
    allowed: tuple[str, ...],
    default: str,
) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _infer_schema_and_object_name(resource_key: str, dataset_name: str, dataset_code: str) -> tuple[str | None, str | None]:
    for candidate in (resource_key, dataset_name, dataset_code):
        text = str(candidate or "").strip()
        if not text:
            continue
        if "." in text:
            schema_name, object_name = text.split(".", 1)
            return schema_name.strip() or None, object_name.strip() or None
        return None, text
    return None, None


def _infer_object_type(dataset_kind: str, schema_summary: dict[str, Any] | None) -> str:
    schema_summary = schema_summary or {}
    object_type = str(schema_summary.get("object_type") or "").strip().lower()
    if object_type:
        return object_type
    normalized_kind = str(dataset_kind or "").strip().lower()
    if normalized_kind in {"table", "view", "foreign_table", "api", "api_endpoint", "file"}:
        return "api" if normalized_kind == "api_endpoint" else normalized_kind
    return "table"


def _build_dataset_search_text(
    *,
    dataset_name: str,
    dataset_code: str,
    resource_key: str,
    schema_name: str | None,
    object_name: str | None,
    object_type: str,
    business_domain: str | None,
    business_object_type: str | None,
    grain: str | None,
    meta: dict[str, Any] | None,
) -> str:
    meta = meta or {}
    semantic_profile = meta.get("semantic_profile") if isinstance(meta.get("semantic_profile"), dict) else {}
    terms = [
        dataset_name,
        dataset_code,
        resource_key,
        schema_name or "",
        object_name or "",
        object_type,
        business_domain or "",
        business_object_type or "",
        grain or "",
        str(semantic_profile.get("business_name") or ""),
        str(semantic_profile.get("tech_name") or ""),
        " ".join(str(item) for item in (semantic_profile.get("key_fields") or []) if str(item).strip()),
    ]
    return " ".join(part.strip() for part in terms if str(part).strip())


def _get_db_config() -> dict:
    """获取数据库连接配置 - 引用统一的 db_config"""
    from db_config import db_config
    return db_config.get_connection_params()


_DB_POOL: "psycopg2.pool.ThreadedConnectionPool | None" = None
_DB_POOL_LOCK = threading.Lock()


def _db_pool_enabled() -> bool:
    """连接池开关。env DB_POOL=0/false/no 可一键退回"每次新建连接"的旧行为。"""
    return os.getenv("DB_POOL", "1").strip().lower() not in ("0", "false", "no", "off")


def _get_pool() -> "psycopg2.pool.ThreadedConnectionPool":
    global _DB_POOL
    if _DB_POOL is None:
        with _DB_POOL_LOCK:
            if _DB_POOL is None:
                maxconn = max(2, int(os.getenv("DB_POOL_MAXCONN", "16") or "16"))
                _DB_POOL = psycopg2.pool.ThreadedConnectionPool(1, maxconn, **_get_db_config())
                logger.info("数据库连接池已初始化 (maxconn=%d)", maxconn)
    return _DB_POOL


def get_conn(max_retries=3, retry_delay=1):
    """获取数据库连接的上下文管理器，带重试机制。

    默认从连接池借用，避免每次新建连接(~13ms)的开销;用完归还而非关闭。
    陈旧连接由 `_ConnectionContextManager.cursor()` 的 SELECT 1 存活检测兜底。
    设 env DB_POOL=0 可退回"每次新建连接"的旧行为(出问题时的安全阀)。
    """
    pooled = _db_pool_enabled()
    for attempt in range(max_retries):
        try:
            if pooled:
                pool = _get_pool()
                return _ConnectionContextManager(pool.getconn(), pool=pool)
            conn = psycopg2.connect(**_get_db_config())
            return _ConnectionContextManager(conn)
        except (OperationalError, InterfaceError) as e:
            logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error(f"数据库连接失败，已达到最大重试次数: {e}")
                raise


def _migration_path(filename: str) -> Path:
    return Path(__file__).resolve().parent / "migrations" / filename


def _table_exists(table_name: str, *, schema: str = "public") -> bool:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = %s
                          AND table_name = %s
                    )
                    """,
                    (schema, table_name),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception as e:
        logger.error(f"检查表是否存在失败 (schema={schema}, table={table_name}): {e}")
        raise


def _column_exists(table_name: str, column_name: str, *, schema: str = "public") -> bool:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = %s
                          AND table_name = %s
                          AND column_name = %s
                    )
                    """,
                    (schema, table_name, column_name),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception as e:
        logger.error(
            f"检查列是否存在失败 (schema={schema}, table={table_name}, column={column_name}): {e}"
        )
        raise


def _table_columns(table_name: str, *, schema: str = "public") -> list[str]:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name = %s
                    ORDER BY ordinal_position ASC
                    """,
                    (schema, table_name),
                )
                return [str(row[0]) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"检查表列失败 (schema={schema}, table={table_name}): {e}")
        raise


def _constraint_definition(
    table_name: str,
    constraint_name: str,
    *,
    schema: str = "public",
) -> str:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pg_get_constraintdef(c.oid)
                    FROM pg_constraint c
                    JOIN pg_class t ON t.oid = c.conrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    WHERE n.nspname = %s
                      AND t.relname = %s
                      AND c.conname = %s
                    LIMIT 1
                    """,
                    (schema, table_name, constraint_name),
                )
                row = cur.fetchone()
                return str(row[0] or "") if row else ""
    except Exception as e:
        logger.error(
            f"检查约束定义失败 (schema={schema}, table={table_name}, constraint={constraint_name}): {e}"
        )
        raise


def _constraint_exists(table_name: str, constraint_name: str, *, schema: str = "public") -> bool:
    return bool(_constraint_definition(table_name, constraint_name, schema=schema))


def _index_exists(index_name: str, *, schema: str = "public") -> bool:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_class i
                        JOIN pg_namespace n ON n.oid = i.relnamespace
                        WHERE n.nspname = %s
                          AND i.relname = %s
                          AND i.relkind IN ('i', 'I')
                    )
                    """,
                    (schema, index_name),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception as e:
        logger.error(f"检查索引是否存在失败 (schema={schema}, index={index_name}): {e}")
        raise


def _trigger_exists(table_name: str, trigger_name: str, *, schema: str = "public") -> bool:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_trigger tr
                        JOIN pg_class t ON t.oid = tr.tgrelid
                        JOIN pg_namespace n ON n.oid = t.relnamespace
                        WHERE n.nspname = %s
                          AND t.relname = %s
                          AND tr.tgname = %s
                          AND NOT tr.tgisinternal
                    )
                    """,
                    (schema, table_name, trigger_name),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception as e:
        logger.error(
            f"检查触发器是否存在失败 (schema={schema}, table={table_name}, trigger={trigger_name}): {e}"
        )
        raise


def _platform_alipay_bill_lines_schema_ready() -> bool:
    table_name = "platform_alipay_bill_lines"
    if not _table_exists(table_name):
        return False

    return (
        all(
            _column_exists(table_name, column_name)
            for column_name in _PLATFORM_ALIPAY_BILL_LINES_REQUIRED_COLUMNS
        )
        and all(
            _constraint_exists(table_name, constraint_name)
            for constraint_name in _PLATFORM_ALIPAY_BILL_LINES_REQUIRED_CONSTRAINTS
        )
        and all(
            _index_exists(index_name)
            for index_name in _PLATFORM_ALIPAY_BILL_LINES_REQUIRED_INDEXES
        )
        and _trigger_exists(table_name, _PLATFORM_ALIPAY_BILL_LINES_REQUIRED_TRIGGER)
        )


def _recon_execution_queue_schema_ready() -> bool:
    if not _table_exists("recon_execution_queue"):
        return False

    return all(
        _column_exists("recon_execution_queue", column_name)
        for column_name in _RECON_EXECUTION_QUEUE_REQUIRED_COLUMNS
    ) and all(_constraint_exists("recon_execution_queue", constraint_name) for constraint_name in _RECON_EXECUTION_QUEUE_REQUIRED_CONSTRAINTS)


def _browser_playbook_collection_schema_ready() -> bool:
    required_tables = (
        "playbooks",
        "agents",
        "shop_runtime_bindings",
        "browser_collection_records",
        "browser_capture_files",
    )
    if not all(_table_exists(table_name) for table_name in required_tables):
        return False

    required_columns = {
        "playbooks": (
            "company_id",
            "playbook_id",
            "version",
            "description",
            "schema_check_result",
            "replay_result",
            "sample_data_path",
            "transcript_path",
            "canary_shop_ids",
            "emergency_page_changed",
            "bypass_canary_reason",
            "created_by",
            "approved_by",
            "approved_at",
            "canary_started_at",
            "canary_completed_at",
            "status",
        ),
        "browser_capture_files": (
            "company_id",
            "data_source_id",
            "dataset_id",
            "sync_job_id",
            "resource_key",
            "shop_id",
            "playbook_id",
            "biz_date",
            "storage_path",
            "encoding",
            "checksum",
            "row_count",
            "created_at",
            "updated_at",
        ),
        "browser_collection_records": (
            "company_id",
            "data_source_id",
            "dataset_id",
            "biz_date",
            "item_key",
            "item_hash",
            "payload",
            "record_status",
        ),
        "shop_runtime_bindings": (
            "profile_status",
            "playbook_status",
            "cron_pause_reason",
            "runtime_profile_ref",
        ),
        "recon_execution_queue": (
            "next_retry_at",
            "wait_deadline_at",
            "waiting_reason",
            "waiting_datasets",
            "collection_job_ids",
            "data_wait_resume_count",
            "last_data_wait_resumed_at",
        ),
        "sync_jobs": (
            "next_retry_at",
            "browser_fail_reason",
            "max_attempts",
            "is_verification",
        ),
    }
    return all(
        _column_exists(table_name, column_name)
        for table_name, column_names in required_columns.items()
        for column_name in column_names
    ) and (
        "draft" in _constraint_definition("playbooks", "playbooks_status_check")
        and "replayed" in _constraint_definition("playbooks", "playbooks_status_check")
        and "approved" in _constraint_definition("playbooks", "playbooks_status_check")
        and "canary" in _constraint_definition("playbooks", "playbooks_status_check")
        and "active" in _constraint_definition("playbooks", "playbooks_status_check")
        and "deprecated" in _constraint_definition("playbooks", "playbooks_status_check")
        and _recon_execution_queue_schema_ready()
    )


def _alipay_semantic_profiles_need_hidden_field_cleanup() -> bool:
    if not _table_exists("data_source_datasets"):
        return False

    hidden_fields = list(_PLATFORM_ALIPAY_SEMANTIC_PROFILE_HIDDEN_FIELDS)
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM data_source_datasets d
                        WHERE (
                            d.resource_key LIKE 'alipay_bill:%%'
                            OR d.schema_summary->>'storage' = 'platform_alipay_bill_lines'
                            OR d.extract_config->>'storage' = 'platform_alipay_bill_lines'
                        )
                          AND COALESCE(d.meta, '{}'::jsonb) ? 'semantic_profile'
                          AND (
                            EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements(
                                    CASE
                                        WHEN jsonb_typeof(d.meta->'semantic_profile'->'fields') = 'array'
                                        THEN d.meta->'semantic_profile'->'fields'
                                        ELSE '[]'::jsonb
                                    END
                                ) AS item
                                WHERE item->>'raw_name' = ANY(%s)
                                   OR item->>'name' = ANY(%s)
                                   OR item->>'raw_name' LIKE 'raw.%%'
                                   OR item->>'name' LIKE 'raw.%%'
                            )
                            OR EXISTS (
                                SELECT 1
                                FROM jsonb_object_keys(
                                    CASE
                                        WHEN jsonb_typeof(d.meta->'semantic_profile'->'field_label_map') = 'object'
                                        THEN d.meta->'semantic_profile'->'field_label_map'
                                        ELSE '{}'::jsonb
                                    END
                                ) AS raw_name
                                WHERE raw_name = ANY(%s)
                                   OR raw_name LIKE 'raw.%%'
                            )
                            OR EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements_text(
                                    CASE
                                        WHEN jsonb_typeof(d.meta->'semantic_profile'->'key_fields') = 'array'
                                        THEN d.meta->'semantic_profile'->'key_fields'
                                        ELSE '[]'::jsonb
                                    END
                                ) AS raw_name
                                WHERE raw_name = ANY(%s)
                                   OR raw_name LIKE 'raw.%%'
                            )
                            OR EXISTS (
                                SELECT 1
                                FROM jsonb_array_elements_text(
                                    CASE
                                        WHEN jsonb_typeof(d.meta->'semantic_profile'->'low_confidence_fields') = 'array'
                                        THEN d.meta->'semantic_profile'->'low_confidence_fields'
                                        ELSE '[]'::jsonb
                                    END
                                ) AS raw_name
                                WHERE raw_name = ANY(%s)
                                   OR raw_name LIKE 'raw.%%'
                            )
                          )
                        LIMIT 1
                    )
                    """,
                    (hidden_fields, hidden_fields, hidden_fields, hidden_fields, hidden_fields),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception as e:
        logger.error(f"检查支付宝账单语义字段是否需清理失败: {e}")
        raise


def _execute_sql_script(script_path: Path) -> None:
    sql = script_path.read_text(encoding="utf-8").strip()
    if not sql:
        return

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
    except Exception as e:
        try:
            conn_manager.rollback()
        except Exception:
            pass
        logger.error(f"执行 SQL 迁移失败 ({script_path.name}): {e}")
        raise


def ensure_unified_data_source_schema() -> list[str]:
    """确保统一数据源 schema 至少满足当前代码对 005/007 的要求。"""
    global _UNIFIED_DATA_SOURCE_SCHEMA_READY
    if _UNIFIED_DATA_SOURCE_SCHEMA_READY:
        return []

    missing_base_tables = sorted(
        table_name for table_name in _UNIFIED_DATA_SOURCE_BASE_TABLES if not _table_exists(table_name)
    )
    missing_health_columns = sorted(
        column_name
        for column_name in _UNIFIED_DATA_SOURCE_HEALTH_COLUMNS
        if not _column_exists("data_sources", column_name)
    ) if _table_exists("data_sources") else list(_UNIFIED_DATA_SOURCE_HEALTH_COLUMNS)
    missing_dataset_catalog_columns = sorted(
        column_name
        for column_name in _UNIFIED_DATASET_CATALOG_COLUMNS
        if not _column_exists("data_source_datasets", column_name)
    ) if _table_exists("data_source_datasets") else list(_UNIFIED_DATASET_CATALOG_COLUMNS)
    datasets_table_missing = not _table_exists("data_source_datasets")

    applied: list[str] = []
    if missing_base_tables:
        _execute_sql_script(_migration_path("005_unified_data_source_model.sql"))
        applied.append("005_unified_data_source_model.sql")
    if missing_base_tables or missing_health_columns or datasets_table_missing:
        _execute_sql_script(_migration_path("007_data_source_datasets_and_health.sql"))
        applied.append("007_data_source_datasets_and_health.sql")
    if missing_dataset_catalog_columns:
        _execute_sql_script(_migration_path("013_data_source_dataset_catalog_fields.sql"))
        applied.append("013_data_source_dataset_catalog_fields.sql")
    if "dataset_collection_records" in missing_base_tables:
        _execute_sql_script(_migration_path("016_dataset_collection_records.sql"))
        applied.append("016_dataset_collection_records.sql")
    legacy_collection_tables = {
        "dataset_snapshots",
        "dataset_snapshot_items",
        "raw_ingestion_records",
        "raw_ingestion_batches",
        "sync_checkpoints",
    }
    if any(_table_exists(table_name) for table_name in legacy_collection_tables):
        _execute_sql_script(_migration_path("017_drop_raw_snapshot_collection_tables.sql"))
        applied.append("017_drop_raw_snapshot_collection_tables.sql")
    if not _table_exists("platform_order_lines"):
        _execute_sql_script(_migration_path("022_platform_order_lines.sql"))
        applied.append("022_platform_order_lines.sql")
    if not _platform_alipay_bill_lines_schema_ready():
        _execute_sql_script(_migration_path("025_platform_alipay_bill_lines.sql"))
        applied.append("025_platform_alipay_bill_lines.sql")
    if _table_exists("platform_alipay_bill_lines") and any(
        _column_exists("platform_alipay_bill_lines", column_name)
        for column_name in _PLATFORM_ALIPAY_BILL_LINES_DERIVED_BUSINESS_COLUMNS
    ):
        _execute_sql_script(_migration_path("028_drop_alipay_derived_business_columns.sql"))
        applied.append("028_drop_alipay_derived_business_columns.sql")
    if _alipay_semantic_profiles_need_hidden_field_cleanup():
        _execute_sql_script(_migration_path("029_clean_alipay_semantic_profiles.sql"))
        applied.append("029_clean_alipay_semantic_profiles.sql")
    applied.extend(ensure_data_sources_browser_playbook_kind_schema())
    applied.extend(ensure_sync_jobs_trigger_modes_schema())

    remaining_missing_tables = sorted(
        table_name for table_name in _UNIFIED_DATA_SOURCE_BASE_TABLES if not _table_exists(table_name)
    )
    remaining_missing_health_columns = sorted(
        column_name
        for column_name in _UNIFIED_DATA_SOURCE_HEALTH_COLUMNS
        if not _column_exists("data_sources", column_name)
    )
    remaining_missing_dataset_catalog_columns = sorted(
        column_name
        for column_name in _UNIFIED_DATASET_CATALOG_COLUMNS
        if not _column_exists("data_source_datasets", column_name)
    ) if _table_exists("data_source_datasets") else list(_UNIFIED_DATASET_CATALOG_COLUMNS)
    if (
        remaining_missing_tables
        or remaining_missing_health_columns
        or remaining_missing_dataset_catalog_columns
        or not _table_exists("data_source_datasets")
    ):
        raise RuntimeError(
            "统一数据源 schema 仍不完整: "
            f"missing_tables={remaining_missing_tables}, "
            f"missing_health_columns={remaining_missing_health_columns}, "
            f"missing_dataset_catalog_columns={remaining_missing_dataset_catalog_columns}, "
            f"missing_data_source_datasets={not _table_exists('data_source_datasets')}"
        )
    if not _platform_alipay_bill_lines_schema_ready():
        raise RuntimeError("支付宝账单行 schema 仍不完整，自动迁移后仍缺少必要列、约束、索引或触发器")
    _UNIFIED_DATA_SOURCE_SCHEMA_READY = True
    if applied:
        logger.info("统一数据源 schema 已自动补齐: %s", ", ".join(applied))
    return applied


def ensure_sync_jobs_trigger_modes_schema() -> list[str]:
    """确保 sync_jobs.trigger_mode 允许初始化和调度采集语义。"""
    global _SYNC_JOBS_TRIGGER_MODES_SCHEMA_READY
    if _SYNC_JOBS_TRIGGER_MODES_SCHEMA_READY:
        return []
    if not _table_exists("sync_jobs"):
        return []

    required_modes = {"manual", "scheduled", "schedule", "event", "retry", "initial", "daily"}
    constraint_def = _constraint_definition("sync_jobs", "sync_jobs_trigger_mode_check")
    if all(mode in constraint_def for mode in required_modes):
        _SYNC_JOBS_TRIGGER_MODES_SCHEMA_READY = True
        return []

    migration_name = "027_sync_jobs_trigger_modes_initial_schedule.sql"
    _execute_sql_script(_migration_path(migration_name))
    applied_constraint_def = _constraint_definition("sync_jobs", "sync_jobs_trigger_mode_check")
    if not all(mode in applied_constraint_def for mode in required_modes):
        raise RuntimeError("sync_jobs.trigger_mode 约束升级失败，initial/schedule/daily 仍不可用")

    _SYNC_JOBS_TRIGGER_MODES_SCHEMA_READY = True
    logger.info("sync_jobs.trigger_mode 约束已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_data_sources_browser_playbook_kind_schema() -> list[str]:
    """确保 data_sources.source_kind 允许 browser_playbook。"""
    if not _table_exists("data_sources"):
        return []

    constraint_def = _constraint_definition("data_sources", "data_sources_source_kind_check")
    if "browser_playbook" in constraint_def:
        return []

    migration_name = "032_data_sources_browser_playbook_source_kind.sql"
    _execute_sql_script(_migration_path(migration_name))
    applied_constraint_def = _constraint_definition("data_sources", "data_sources_source_kind_check")
    if "browser_playbook" not in applied_constraint_def:
        raise RuntimeError("data_sources.source_kind 约束升级失败，browser_playbook 仍不可用")

    logger.info("data_sources.source_kind 约束已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_execution_run_trigger_types_schema() -> list[str]:
    """确保 execution_runs.trigger_type 允许 manual/rerun。"""
    global _EXECUTION_RUN_TRIGGER_TYPES_SCHEMA_READY
    if _EXECUTION_RUN_TRIGGER_TYPES_SCHEMA_READY:
        return []
    if not _table_exists("execution_runs"):
        return []

    constraint_def = _constraint_definition("execution_runs", "execution_runs_trigger_type_check")
    if "manual" in constraint_def and "rerun" in constraint_def:
        _EXECUTION_RUN_TRIGGER_TYPES_SCHEMA_READY = True
        return []

    migration_name = "020_execution_runs_trigger_type_manual_rerun.sql"
    _execute_sql_script(_migration_path(migration_name))
    applied_constraint_def = _constraint_definition("execution_runs", "execution_runs_trigger_type_check")
    if "manual" not in applied_constraint_def or "rerun" not in applied_constraint_def:
        raise RuntimeError("execution_runs.trigger_type 约束升级失败，manual/rerun 仍不可用")

    _EXECUTION_RUN_TRIGGER_TYPES_SCHEMA_READY = True
    logger.info("execution_runs.trigger_type 约束已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_auth_sessions_extra_schema() -> list[str]:
    """确保 auth_sessions.extra 元数据字段存在。"""
    global _AUTH_SESSIONS_EXTRA_SCHEMA_READY
    if _AUTH_SESSIONS_EXTRA_SCHEMA_READY:
        return []
    if not _table_exists("auth_sessions"):
        return []
    if _column_exists("auth_sessions", "extra"):
        _AUTH_SESSIONS_EXTRA_SCHEMA_READY = True
        return []

    migration_name = "024_auth_sessions_extra.sql"
    _execute_sql_script(_migration_path(migration_name))
    if not _column_exists("auth_sessions", "extra"):
        raise RuntimeError("auth_sessions.extra 字段升级失败，extra 仍不可用")

    _AUTH_SESSIONS_EXTRA_SCHEMA_READY = True
    logger.info("auth_sessions.extra 字段已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_platform_pending_authorizations_schema() -> list[str]:
    """确保无 state 平台授权待认领表存在。"""
    global _PLATFORM_PENDING_AUTHORIZATIONS_SCHEMA_READY
    if _PLATFORM_PENDING_AUTHORIZATIONS_SCHEMA_READY:
        return []
    if _table_exists("platform_pending_authorizations"):
        _PLATFORM_PENDING_AUTHORIZATIONS_SCHEMA_READY = True
        return []

    migration_name = "026_platform_pending_authorizations.sql"
    _execute_sql_script(_migration_path(migration_name))
    if not _table_exists("platform_pending_authorizations"):
        raise RuntimeError("platform_pending_authorizations 表升级失败，表仍不存在")

    _PLATFORM_PENDING_AUTHORIZATIONS_SCHEMA_READY = True
    logger.info("platform_pending_authorizations 表已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_recon_execution_queue_schema() -> list[str]:
    """确保 recon_execution_queue 已包含浏览器首店流程依赖的 waiting_data 结构。"""
    global _RECON_EXECUTION_QUEUE_SCHEMA_READY
    if _RECON_EXECUTION_QUEUE_SCHEMA_READY:
        return []
    if _recon_execution_queue_schema_ready():
        _RECON_EXECUTION_QUEUE_SCHEMA_READY = True
        return []

    migration_name = "019_recon_execution_queue.sql"
    _execute_sql_script(_migration_path(migration_name))
    if not _recon_execution_queue_schema_ready():
        raise RuntimeError("recon_execution_queue schema 升级失败，waiting_data 结构仍不完整")

    _RECON_EXECUTION_QUEUE_SCHEMA_READY = True
    logger.info("recon_execution_queue schema 已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_browser_playbook_collection_schema() -> list[str]:
    """确保浏览器采集首店 schema 已安装。"""
    global _BROWSER_PLAYBOOK_COLLECTION_SCHEMA_READY
    if _BROWSER_PLAYBOOK_COLLECTION_SCHEMA_READY:
        return []
    applied: list[str] = []
    applied.extend(ensure_recon_execution_queue_schema())
    if _browser_playbook_collection_schema_ready():
        _BROWSER_PLAYBOOK_COLLECTION_SCHEMA_READY = True
        return applied

    migration_name = "031_browser_playbook_collection.sql"
    _execute_sql_script(_migration_path(migration_name))
    if not _browser_playbook_collection_schema_ready():
        raise RuntimeError("browser_playbook collection schema 升级失败，仍缺少必要表或列")

    _BROWSER_PLAYBOOK_COLLECTION_SCHEMA_READY = True
    logger.info("browser_playbook collection schema 已自动补齐: %s", migration_name)
    applied.append(migration_name)
    return applied


def _browser_handoff_schema_ready() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("select to_regclass('public.browser_handoff_sessions')")
                return cur.fetchone()[0] is not None
    except Exception:
        return False


def ensure_browser_handoff_schema() -> list[str]:
    global _BROWSER_HANDOFF_SCHEMA_READY
    if _BROWSER_HANDOFF_SCHEMA_READY:
        return []
    if _browser_handoff_schema_ready():
        _BROWSER_HANDOFF_SCHEMA_READY = True
        return []
    migration_name = "033_browser_handoff_sessions.sql"
    _execute_sql_script(_migration_path(migration_name))
    if not _browser_handoff_schema_ready():
        raise RuntimeError("browser_handoff schema 升级失败")
    _BROWSER_HANDOFF_SCHEMA_READY = True
    logger.info("browser_handoff schema 已自动补齐: %s", migration_name)
    return [migration_name]


def ensure_schema() -> list[str]:
    """确保 auth 侧当前任务需要的基础 schema 已就绪。"""
    applied = ensure_unified_data_source_schema()
    applied.extend(ensure_browser_playbook_collection_schema())
    applied.extend(ensure_browser_handoff_schema())
    return applied


class _ConnectionContextManager:
    """数据库连接的上下文管理器类。

    `pool` 非空时连接来自连接池:退出时清理事务后归还(而非关闭);
    `pool` 为空时为直连模式,退出时关闭连接(DB_POOL=0 的旧行为)。
    """
    def __init__(self, conn, pool=None):
        self.conn = conn
        self._pool = pool

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.conn:
            return
        if self._pool is None:
            # 直连模式:关闭
            self.conn.close()
            self.conn = None
            return
        # 池化模式:清理未提交事务(写操作均已显式 commit,这里只清残留)后归还。
        # 若连接已坏,标记 close=True 让池丢弃该槽并补建,保持池计数正确。
        try:
            self.conn.rollback()
            self._pool.putconn(self.conn)
        except Exception:
            try:
                self._pool.putconn(self.conn, close=True)
            except Exception:
                try:
                    self.conn.close()
                except Exception:
                    pass
        self.conn = None

    def cursor(self, cursor_factory=None):
        """获取游标，自动处理连接失效"""
        try:
            # 检查连接是否仍然有效
            with self.conn.cursor() as test_cursor:
                test_cursor.execute('SELECT 1')
        except (OperationalError, InterfaceError):
            logger.warning("数据库连接已失效，尝试重新连接")
            if self._pool is not None:
                # 把坏连接还给池并标记关闭,再借一个新的,保持池计数正确
                try:
                    self._pool.putconn(self.conn, close=True)
                except Exception:
                    try:
                        self.conn.close()
                    except Exception:
                        pass
                self.conn = self._pool.getconn()
            else:
                self.conn.close()
                # 重新建立连接
                self.conn = psycopg2.connect(**_get_db_config())

        return self.conn.cursor(cursor_factory=cursor_factory)

    def commit(self):
        """提交事务"""
        self.conn.commit()

    def rollback(self):
        """回滚事务"""
        self.conn.rollback()


# ── 用户操作 ──────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名查询用户"""
    sql = """
    SELECT u.id, u.username, u.password_hash, u.email, u.phone, u.role, u.status,
           u.company_id, u.department_id,
           c.name AS company_name,
           d.name AS department_name
    FROM users u
    LEFT JOIN company c ON u.company_id = c.id
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.username = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (username,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"查询用户失败 (username={username}): {e}")
        return None


def get_user_by_id(user_id: str) -> Optional[dict]:
    """根据 ID 查询用户"""
    sql = """
    SELECT u.id, u.username, u.email, u.phone, u.role, u.status,
           u.company_id, u.department_id,
           c.name AS company_name,
           d.name AS department_name
    FROM users u
    LEFT JOIN company c ON u.company_id = c.id
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (user_id,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"查询用户失败 (user_id={user_id}): {e}")
        return None


def create_user(username: str, password_hash: str, email: str = None,
                phone: str = None, company_id: str = None,
                department_id: str = None, role: str = "member") -> dict:
    """创建新用户，返回用户信息"""
    sql = """
    INSERT INTO users (username, password_hash, email, phone, company_id, department_id, role)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id, username, email, phone, company_id, department_id, role, status
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (username, password_hash, email, phone,
                                  company_id, department_id, role))
                user = cur.fetchone()
                conn.commit()
                return dict(user)
    except Exception as e:
        logger.error(f"创建用户失败 (username={username}): {e}")
        raise


def update_last_login(user_id: str):
    """更新最后登录时间"""
    sql = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id,))
                conn.commit()
    except Exception as e:
        logger.error(f"更新登录时间失败 (user_id={user_id}): {e}")
        # Don't raise here as this is not critical for login


# ── 公司/部门查询 ────────────────────────────────────────────────────

def list_companies() -> list[dict]:
    """获取公司列表。"""
    sql = "SELECT id, name, created_at FROM company ORDER BY created_at DESC"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [_normalize_record(dict(r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询公司列表失败: {e}")
        return []


def list_departments(company_id: str | None = None) -> list[dict]:
    """获取部门列表，可按公司筛选。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, name, created_at
                        FROM departments
                        WHERE company_id = %s
                        ORDER BY created_at DESC
                        """,
                        (company_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, name, created_at
                        FROM departments
                        ORDER BY created_at DESC
                        """
                    )
                return [_normalize_record(dict(r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询部门列表失败 (company_id={company_id}): {e}")
        return []


def get_company_channel_config(
    company_id: str | None = None,
    provider: str = "dingtalk_dws",
    channel_code: str = "default",
) -> dict | None:
    """查询一个公司的启用 channel 配置；未传 company_id 时返回默认配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, provider, channel_code, name,
                               client_id, client_secret, robot_code, extra,
                               is_default, is_enabled, created_at, updated_at
                        FROM company_channel_configs
                        WHERE company_id = %s
                          AND provider = %s
                          AND is_enabled = TRUE
                        ORDER BY
                          (channel_code = %s) DESC,
                          is_default DESC,
                          updated_at DESC,
                          created_at DESC
                        LIMIT 1
                        """,
                        (company_id, provider, channel_code),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, provider, channel_code, name,
                               client_id, client_secret, robot_code, extra,
                               is_default, is_enabled, created_at, updated_at
                        FROM company_channel_configs
                        WHERE provider = %s
                          AND is_enabled = TRUE
                        ORDER BY
                          is_default DESC,
                          (channel_code = %s) DESC,
                          updated_at DESC,
                          created_at DESC
                        LIMIT 1
                        """,
                        (provider, channel_code),
                    )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(
            f"查询 company_channel_configs 失败 (company_id={company_id}, provider={provider}, channel_code={channel_code}): {e}"
        )
        return None


def upsert_company_channel_config(
    *,
    company_id: str,
    provider: str,
    channel_code: str = "default",
    name: str = "",
    client_id: str = "",
    client_secret: str = "",
    robot_code: str = "",
    extra: dict | None = None,
    is_default: bool = False,
    is_enabled: bool = True,
) -> dict | None:
    """创建或更新公司 channel 配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO company_channel_configs (
                        company_id, provider, channel_code, name,
                        client_id, client_secret, robot_code, extra,
                        is_default, is_enabled
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (company_id, provider, channel_code)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        client_id = EXCLUDED.client_id,
                        client_secret = EXCLUDED.client_secret,
                        robot_code = EXCLUDED.robot_code,
                        extra = EXCLUDED.extra,
                        is_default = EXCLUDED.is_default,
                        is_enabled = EXCLUDED.is_enabled,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, provider, channel_code, name,
                              client_id, client_secret, robot_code, extra,
                              is_default, is_enabled, created_at, updated_at
                    """,
                    (
                        company_id,
                        provider,
                        channel_code,
                        name,
                        client_id,
                        client_secret,
                        robot_code,
                        psycopg2.extras.Json(extra or {}),
                        is_default,
                        is_enabled,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return dict(row) if row else None
    except Exception as e:
        logger.error(
            f"写入 company_channel_configs 失败 (company_id={company_id}, provider={provider}, channel_code={channel_code}): {e}"
        )
        return None

# ══════════════════════════════════════════════════════════════════════════════
# 公司部门管理
# ══════════════════════════════════════════════════════════════════════════════

def create_company(name: str) -> dict | None:
    """创建公司，返回公司dict或None（如果已存在）"""
    import uuid
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 检查是否已存在
                cur.execute("SELECT id FROM company WHERE name = %s", (name,))
                if cur.fetchone():
                    return None
                
                # 生成唯一的 code
                code = f"COMP_{uuid.uuid4().hex[:8].upper()}"
                
                cur.execute(
                    "INSERT INTO company (name, code) VALUES (%s, %s) RETURNING id, name, code, created_at",
                    (name, code)
                )
                row = cur.fetchone()
                c.commit()
                return dict(row)
    except Exception as e:
        logger.error(f"创建公司失败: {e}")
        return None


def create_department(company_id: str, name: str) -> dict | None:
    """创建部门，返回部门dict或None（如果已存在）"""
    import uuid
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 检查是否已存在
                cur.execute(
                    "SELECT id FROM departments WHERE company_id = %s AND name = %s",
                    (company_id, name)
                )
                if cur.fetchone():
                    return None
                
                # 生成唯一的 code
                code = f"DEPT_{uuid.uuid4().hex[:8].upper()}"
                
                cur.execute(
                    "INSERT INTO departments (company_id, name, code) VALUES (%s, %s, %s) RETURNING id, company_id, name, code, created_at",
                    (company_id, name, code)
                )
                row = cur.fetchone()
                c.commit()
                return dict(row)
    except Exception as e:
        logger.error(f"创建部门失败: {e}")
        return None

def get_admin_view() -> dict:
    """获取管理员视图 - 公司部门员工层级"""
    conn = get_conn()
    result = {"companies": []}
    
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 获取所有公司
                cur.execute("SELECT id, name, created_at FROM company ORDER BY name")
                companies = cur.fetchall()
                
                for company in companies:
                    company_id = company["id"]
                    company_data = {
                        "id": str(company["id"]),
                        "name": company["name"],
                        "departments": []
                    }
                    
                    # 获取该公司的部门
                    cur.execute(
                        "SELECT id, name FROM departments WHERE company_id = %s ORDER BY name",
                        (company_id,)
                    )
                    departments = cur.fetchall()
                    
                    for dept in departments:
                        dept_id = dept["id"]
                        dept_data = {
                            "id": str(dept["id"]),
                            "name": dept["name"],
                            "employees": [],
                        }
                        
                        # 获取该部门的员工
                        cur.execute(
                            "SELECT id, username, email FROM users WHERE department_id = %s",
                            (dept_id,)
                        )
                        employees = cur.fetchall()
                        for emp in employees:
                            dept_data["employees"].append({
                                "id": str(emp["id"]),
                                "username": emp["username"],
                                "email": emp.get("email")
                            })
                        
                        company_data["departments"].append(dept_data)
                    
                    result["companies"].append(company_data)
        
        return result
    except Exception as e:
        logger.error(f"获取管理员视图失败: {e}")
        return {"companies": [], "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════════════════════

def create_conversation(user_id: str, title: str = None) -> dict | None:
    """创建新会话"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO conversations (user_id, title) 
                       VALUES (%s, %s) 
                       RETURNING id, user_id, title, created_at, updated_at, status""",
                    (user_id, title)
                )
                row = cur.fetchone()
                c.commit()
                result = dict(row)
                result["id"] = str(result["id"])
                result["user_id"] = str(result["user_id"])
                _serialize_datetimes(result)
                return result
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        return None


def get_conversation(conversation_id: str, user_id: str) -> dict | None:
    """获取单个会话（验证所有权）"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at, status 
                       FROM conversations 
                       WHERE id = %s AND user_id = %s""",
                    (conversation_id, user_id)
                )
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["user_id"] = str(result["user_id"])
                    _serialize_datetimes(result)
                    return result
                return None
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        return None


def list_conversations(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """获取用户的会话列表"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at, status 
                       FROM conversations 
                       WHERE user_id = %s AND status = 'active'
                       ORDER BY updated_at DESC
                       LIMIT %s OFFSET %s""",
                    (user_id, limit, offset)
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item["id"] = str(item["id"])
                    item["user_id"] = str(item["user_id"])
                    _serialize_datetimes(item)
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        return []


def update_conversation(conversation_id: str, user_id: str, title: str = None, status: str = None) -> dict | None:
    """更新会话"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 构建更新语句
                updates = []
                params = []
                if title is not None:
                    updates.append("title = %s")
                    params.append(title)
                if status is not None:
                    updates.append("status = %s")
                    params.append(status)
                
                if not updates:
                    return get_conversation(conversation_id, user_id)
                
                params.extend([conversation_id, user_id])
                cur.execute(
                    f"""UPDATE conversations 
                        SET {', '.join(updates)}
                        WHERE id = %s AND user_id = %s
                        RETURNING id, user_id, title, created_at, updated_at, status""",
                    params
                )
                row = cur.fetchone()
                c.commit()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["user_id"] = str(result["user_id"])
                    _serialize_datetimes(result)
                    return result
                return None
    except Exception as e:
        logger.error(f"更新会话失败: {e}")
        return None


def delete_conversation(conversation_id: str, user_id: str) -> bool:
    """删除会话（物理删除）及关联的历史消息"""
    conn_manager = get_conn()
    try:
        with conn_manager as c:
            with c.cursor() as cur:
                # 1. 删除该会话下的所有消息
                cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
                # 2. 物理删除会话
                cur.execute(
                    "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                    (conversation_id, user_id)
                )
                c.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        try:
            conn_manager.rollback()
        except Exception:
            pass
        return False


def save_message(conversation_id: str, role: str, content: str, metadata: dict = None, attachments: list = None) -> dict | None:
    """保存消息（支持附件，向后兼容）"""
    import json
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 尝试使用新的 attachments 列（如果存在）
                try:
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, metadata, attachments)
                           VALUES (%s, %s, %s, %s, %s)
                           RETURNING id, conversation_id, role, content, metadata, attachments, created_at""",
                        (conversation_id, role, content, json.dumps(metadata or {}), json.dumps(attachments or []))
                    )
                    row = cur.fetchone()
                except Exception as column_error:
                    # 如果 attachments 列不存在，回退到旧版本（不包含 attachments）
                    logger.warning(f"attachments 列不存在，使用旧版本保存: {column_error}")
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, metadata)
                           VALUES (%s, %s, %s, %s)
                           RETURNING id, conversation_id, role, content, metadata, created_at""",
                        (conversation_id, role, content, json.dumps(metadata or {}))
                    )
                    row = cur.fetchone()

                # 同时更新会话的 updated_at
                cur.execute(
                    "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (conversation_id,)
                )

                c.commit()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["conversation_id"] = str(result["conversation_id"])
                    # 确保总是返回 attachments 字段（即使是空数组）
                    if "attachments" not in result:
                        result["attachments"] = []
                    _serialize_datetimes(result)
                    return result
                return None
    except Exception as e:
        logger.error(f"保存消息失败: {e}")
        return None


def should_display_message(role: str, content: str, metadata: dict = None) -> bool:
    """判断消息是否应该显示给用户。

    过滤掉以下类型的消息：
    - JSON响应（意图识别等）
    - HTML表单
    - 代码块
    - 系统消息
    - 进度提示消息（包含SPINNER等临时标记）

    Args:
        role: 消息角色 (user/assistant/system)
        content: 消息内容
        metadata: 可选的元数据

    Returns:
        True 表示应该显示，False 表示应该过滤掉
    """
    if not content:
        return False

    content_stripped = content.strip()

    # 过滤JSON响应
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        return False

    # 过滤代码块
    if content_stripped.startswith("```"):
        return False

    # 过滤HTML表单
    if content_stripped.startswith("<"):
        return False

    # 过滤系统消息
    if role == "system":
        return False

    # 过滤进度消息（临时指示器）
    progress_patterns = [
        "{{SPINNER}}",
        "正在保存",
        "📊 进度：",
    ]
    for pattern in progress_patterns:
        if pattern in content:
            return False

    return True


def get_messages(conversation_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """获取会话的消息列表（已过滤不应显示的消息，向后兼容）"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 尝试查询包含 attachments 列
                try:
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, attachments, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY seq ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )
                except Exception as column_error:
                    # 如果 attachments 列不存在，查询不包含它
                    logger.warning(f"attachments 列不存在，使用旧版本查询: {column_error}")
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY seq ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )

                rows = cur.fetchall()
                result = []
                for row in rows:
                    # 应用过滤器：只返回应该显示的消息
                    if should_display_message(row["role"], row["content"], row.get("metadata")):
                        item = dict(row)
                        item["id"] = str(item["id"])
                        item["conversation_id"] = str(item["conversation_id"])
                        # 确保 attachments 总是一个列表
                        if "attachments" not in item or item.get("attachments") is None:
                            item["attachments"] = []
                        _serialize_datetimes(item)
                        result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 数据连接（平台应用/店铺连接/授权/同步源/授权会话）
# ══════════════════════════════════════════════════════════════════════════════

def upsert_platform_app(
    *,
    company_id: str,
    platform_code: str,
    app_key: str,
    app_secret: str,
    app_name: str = "",
    app_type: str = "isv",
    auth_base_url: str = "",
    token_url: str = "",
    refresh_url: str = "",
    scopes_config: list | None = None,
    extra: dict | None = None,
    status: str = "active",
    include_secrets: bool = False,
) -> dict | None:
    """创建或更新平台应用配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO platform_apps (
                        company_id, platform_code, app_name, app_key, app_secret,
                        app_type, auth_base_url, token_url, refresh_url,
                        scopes_config, extra, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                    ON CONFLICT (company_id, platform_code, app_key)
                    DO UPDATE SET
                        app_name = EXCLUDED.app_name,
                        app_secret = EXCLUDED.app_secret,
                        app_type = EXCLUDED.app_type,
                        auth_base_url = EXCLUDED.auth_base_url,
                        token_url = EXCLUDED.token_url,
                        refresh_url = EXCLUDED.refresh_url,
                        scopes_config = EXCLUDED.scopes_config,
                        extra = EXCLUDED.extra,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, platform_code, app_name, app_key, app_secret,
                              app_type, auth_base_url, token_url, refresh_url,
                              scopes_config, extra, status, created_at, updated_at
                    """,
                    (
                        company_id,
                        platform_code,
                        app_name,
                        app_key,
                        seal_secret(app_secret),
                        app_type,
                        auth_base_url,
                        token_url,
                        refresh_url,
                        psycopg2.extras.Json(scopes_config or []),
                        psycopg2.extras.Json(extra or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["app_secret"] = open_secret(result.get("app_secret") or "")
                else:
                    result["app_secret"] = ""
                return result
    except Exception as e:
        logger.error(
            f"写入 platform_apps 失败 (company_id={company_id}, platform_code={platform_code}): {e}"
        )
        return None


def get_platform_app(
    *,
    company_id: str,
    platform_code: str,
    app_key: str | None = None,
    include_secrets: bool = False,
) -> dict | None:
    """查询平台应用配置。未传 app_key 时按更新时间倒序取最新一条。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if app_key:
                    cur.execute(
                        """
                        SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                               app_type, auth_base_url, token_url, refresh_url,
                               scopes_config, extra, status, created_at, updated_at
                        FROM platform_apps
                        WHERE company_id = %s
                          AND platform_code = %s
                          AND app_key = %s
                        LIMIT 1
                        """,
                        (company_id, platform_code, app_key),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                               app_type, auth_base_url, token_url, refresh_url,
                               scopes_config, extra, status, created_at, updated_at
                        FROM platform_apps
                        WHERE company_id = %s
                          AND platform_code = %s
                          AND status <> 'deleted'
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT 1
                        """,
                        (company_id, platform_code),
                    )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["app_secret"] = open_secret(result.get("app_secret") or "")
                else:
                    result["app_secret"] = ""
                return result
    except Exception as e:
        logger.error(
            f"查询 platform_apps 失败 (company_id={company_id}, platform_code={platform_code}, app_key={app_key}): {e}"
        )
        return None


def get_platform_app_by_id(
    *,
    platform_app_id: str,
    company_id: str,
    owner_company_id: str | None = None,
    include_secrets: bool = False,
) -> dict | None:
    """按 ID 查询平台应用配置，并限制应用归属公司边界。"""
    lookup_company_id = owner_company_id or company_id
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                           app_type, auth_base_url, token_url, refresh_url,
                           scopes_config, extra, status, created_at, updated_at
                    FROM platform_apps
                    WHERE id = %s
                      AND company_id = %s
                      AND status <> 'deleted'
                    LIMIT 1
                    """,
                    (platform_app_id, lookup_company_id),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["app_secret"] = open_secret(result.get("app_secret") or "")
                else:
                    result["app_secret"] = ""
                return result
    except Exception as e:
        logger.error(f"按 ID 查询 platform_apps 失败 (id={platform_app_id}, company_id={lookup_company_id}): {e}")
        return None


def list_platform_apps(company_id: str, include_secrets: bool = False) -> list[dict]:
    """列出某公司全部平台应用配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, app_name, app_key, app_secret,
                           app_type, auth_base_url, token_url, refresh_url,
                           scopes_config, extra, status, created_at, updated_at
                    FROM platform_apps
                    WHERE company_id = %s
                    ORDER BY platform_code ASC, updated_at DESC
                    """,
                    (company_id,),
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    item = _normalize_record(dict(row))
                    if include_secrets:
                        item["app_secret"] = open_secret(item.get("app_secret") or "")
                    else:
                        item["app_secret"] = ""
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"查询 platform_apps 列表失败 (company_id={company_id}): {e}")
        return []


def upsert_shop_connection(
    *,
    company_id: str,
    platform_code: str,
    external_shop_id: str,
    external_shop_name: str = "",
    external_seller_id: str = "",
    auth_subject_name: str = "",
    shop_type: str = "standard",
    status: str = "active",
    meta: dict | None = None,
) -> dict | None:
    """创建或更新店铺连接记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO shop_connections (
                        company_id, platform_code, external_shop_id, external_shop_name,
                        external_seller_id, auth_subject_name, shop_type, status, meta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (company_id, platform_code, external_shop_id)
                    DO UPDATE SET
                        external_shop_name = EXCLUDED.external_shop_name,
                        external_seller_id = EXCLUDED.external_seller_id,
                        auth_subject_name = EXCLUDED.auth_subject_name,
                        shop_type = EXCLUDED.shop_type,
                        status = EXCLUDED.status,
                        meta = EXCLUDED.meta,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, platform_code, external_shop_id, external_shop_name,
                              external_seller_id, auth_subject_name, shop_type, status, meta,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        platform_code,
                        external_shop_id,
                        external_shop_name,
                        external_seller_id,
                        auth_subject_name,
                        shop_type,
                        status,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 shop_connections 失败 (company_id={company_id}, platform_code={platform_code}, external_shop_id={external_shop_id}): {e}"
        )
        return None


def get_shop_connection(
    *,
    company_id: str,
    platform_code: str,
    external_shop_id: str,
) -> dict | None:
    """按平台店铺编码查询店铺连接。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                           external_seller_id, auth_subject_name, shop_type, status, meta,
                           created_at, updated_at
                    FROM shop_connections
                    WHERE company_id = %s
                      AND platform_code = %s
                      AND external_shop_id = %s
                    LIMIT 1
                    """,
                    (company_id, platform_code, external_shop_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 shop_connections 失败 (company_id={company_id}, platform_code={platform_code}, external_shop_id={external_shop_id}): {e}"
        )
        return None


def get_shop_connection_by_id(shop_connection_id: str) -> dict | None:
    """按主键查询店铺连接。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                           external_seller_id, auth_subject_name, shop_type, status, meta,
                           created_at, updated_at
                    FROM shop_connections
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (shop_connection_id,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"按 id 查询 shop_connections 失败 (id={shop_connection_id}): {e}")
        return None


def list_shop_connections(
    *,
    company_id: str,
    platform_code: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    """查询公司下店铺连接列表，可按平台筛选。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if platform_code:
                    if include_deleted:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                              AND platform_code = %s
                            ORDER BY updated_at DESC, created_at DESC
                            """,
                            (company_id, platform_code),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                              AND platform_code = %s
                              AND status <> 'deleted'
                            ORDER BY updated_at DESC, created_at DESC
                            """,
                            (company_id, platform_code),
                        )
                else:
                    if include_deleted:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                            ORDER BY platform_code ASC, updated_at DESC
                            """,
                            (company_id,),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                                   external_seller_id, auth_subject_name, shop_type, status, meta,
                                   created_at, updated_at
                            FROM shop_connections
                            WHERE company_id = %s
                              AND status <> 'deleted'
                            ORDER BY platform_code ASC, updated_at DESC
                            """,
                            (company_id,),
                        )

                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 shop_connections 列表失败 (company_id={company_id}): {e}")
        return []


def update_shop_connection_status(
    *,
    shop_connection_id: str,
    status: str,
) -> dict | None:
    """更新店铺连接状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_connections
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, platform_code, external_shop_id, external_shop_name,
                              external_seller_id, auth_subject_name, shop_type, status, meta,
                              created_at, updated_at
                    """,
                    (status, shop_connection_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 shop_connections 状态失败 (id={shop_connection_id}, status={status}): {e}")
        return None


def get_active_alipay_connection_for_shop(
    *, company_id: str, merchant_display_name: str, external_shop_id: str = ""
) -> dict | None:
    """查该企业下是否已有匹配该店的有效(active)支付宝连接,用于落地页幂等。

    匹配规则:同 company + platform='alipay' + status='active',且
    external_shop_name == merchant_display_name 或(external_shop_id 非空且相等)。
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, external_shop_id, external_shop_name, status
                    FROM shop_connections
                    WHERE company_id = %s
                      AND platform_code = 'alipay'
                      AND status = 'active'
                      AND (
                          external_shop_name = %s
                          OR (%s <> '' AND external_shop_id = %s)
                      )
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (company_id, merchant_display_name, external_shop_id, external_shop_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"get_active_alipay_connection_for_shop 失败: {e}")
        return None


def create_shop_authorization(
    *,
    company_id: str,
    shop_connection_id: str,
    platform_app_id: str,
    access_token: str,
    refresh_token: str = "",
    auth_type: str = "oauth_code",
    token_expires_at: str | None = None,
    refresh_expires_at: str | None = None,
    scope_text: str = "",
    auth_status: str = "authorized",
    last_error: str = "",
    raw_auth_payload: dict | None = None,
    include_secrets: bool = False,
) -> dict | None:
    """创建新的店铺授权记录，并将历史 current 记录置为 false。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_authorizations
                    SET is_current = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE shop_connection_id = %s
                      AND is_current = true
                    """,
                    (shop_connection_id,),
                )

                cur.execute(
                    """
                    INSERT INTO shop_authorizations (
                        company_id, shop_connection_id, platform_app_id, auth_type,
                        access_token, refresh_token, token_expires_at, refresh_expires_at,
                        scope_text, auth_status, is_current, auth_time, last_refresh_at,
                        last_error, raw_auth_payload
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                        %s, %s::jsonb
                    )
                    RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                              access_token, refresh_token, token_expires_at, refresh_expires_at,
                              scope_text, auth_status, is_current, auth_time, last_refresh_at,
                              last_error, raw_auth_payload, created_at, updated_at
                    """,
                    (
                        company_id,
                        shop_connection_id,
                        platform_app_id,
                        auth_type,
                        seal_secret(access_token),
                        seal_secret(refresh_token),
                        token_expires_at,
                        refresh_expires_at,
                        scope_text,
                        auth_status,
                        last_error,
                        psycopg2.extras.Json(raw_auth_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["access_token"] = open_secret(result.get("access_token") or "")
                    result["refresh_token"] = open_secret(result.get("refresh_token") or "")
                else:
                    result["access_token"] = ""
                    result["refresh_token"] = ""
                return result
    except Exception as e:
        logger.error(
            f"创建 shop_authorizations 失败 (company_id={company_id}, shop_connection_id={shop_connection_id}): {e}"
        )
        return None


def get_current_shop_authorization(
    *,
    shop_connection_id: str,
    include_secrets: bool = False,
) -> dict | None:
    """查询店铺当前有效授权记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, shop_connection_id, platform_app_id, auth_type,
                           access_token, refresh_token, token_expires_at, refresh_expires_at,
                           scope_text, auth_status, is_current, auth_time, last_refresh_at,
                           last_error, raw_auth_payload, created_at, updated_at
                    FROM shop_authorizations
                    WHERE shop_connection_id = %s
                      AND is_current = true
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (shop_connection_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secrets:
                    result["access_token"] = open_secret(result.get("access_token") or "")
                    result["refresh_token"] = open_secret(result.get("refresh_token") or "")
                else:
                    result["access_token"] = ""
                    result["refresh_token"] = ""
                return result
    except Exception as e:
        logger.error(f"查询当前 shop_authorizations 失败 (shop_connection_id={shop_connection_id}): {e}")
        return None


def update_shop_authorization_tokens(
    *,
    authorization_id: str,
    access_token: str,
    refresh_token: str = "",
    token_expires_at: str | None = None,
    refresh_expires_at: str | None = None,
    scope_text: str | None = None,
    auth_status: str = "authorized",
    raw_auth_payload: dict | None = None,
) -> dict | None:
    """刷新授权 token。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_authorizations
                    SET access_token = %s,
                        refresh_token = %s,
                        token_expires_at = %s,
                        refresh_expires_at = %s,
                        scope_text = COALESCE(%s, scope_text),
                        auth_status = %s,
                        last_refresh_at = CURRENT_TIMESTAMP,
                        raw_auth_payload = CASE
                            WHEN %s::jsonb = '{}'::jsonb THEN raw_auth_payload
                            ELSE %s::jsonb
                        END,
                        last_error = '',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                              access_token, refresh_token, token_expires_at, refresh_expires_at,
                              scope_text, auth_status, is_current, auth_time, last_refresh_at,
                              last_error, raw_auth_payload, created_at, updated_at
                    """,
                    (
                        seal_secret(access_token),
                        seal_secret(refresh_token),
                        token_expires_at,
                        refresh_expires_at,
                        scope_text,
                        auth_status,
                        psycopg2.extras.Json(raw_auth_payload or {}),
                        psycopg2.extras.Json(raw_auth_payload or {}),
                        authorization_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row), decrypt_fields=["access_token", "refresh_token"])
                return result
    except Exception as e:
        logger.error(f"更新 shop_authorizations token 失败 (id={authorization_id}): {e}")
        return None


def update_shop_authorization_status(
    *,
    authorization_id: str,
    auth_status: str,
    last_error: str = "",
    is_current: bool | None = None,
) -> dict | None:
    """更新授权状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_current is None:
                    cur.execute(
                        """
                        UPDATE shop_authorizations
                        SET auth_status = %s,
                            last_error = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                                  access_token, refresh_token, token_expires_at, refresh_expires_at,
                                  scope_text, auth_status, is_current, auth_time, last_refresh_at,
                                  last_error, raw_auth_payload, created_at, updated_at
                        """,
                        (auth_status, last_error, authorization_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE shop_authorizations
                        SET auth_status = %s,
                            last_error = %s,
                            is_current = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, shop_connection_id, platform_app_id, auth_type,
                                  access_token, refresh_token, token_expires_at, refresh_expires_at,
                                  scope_text, auth_status, is_current, auth_time, last_refresh_at,
                                  last_error, raw_auth_payload, created_at, updated_at
                        """,
                        (auth_status, last_error, is_current, authorization_id),
                    )

                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                result["access_token"] = ""
                result["refresh_token"] = ""
                return result
    except Exception as e:
        logger.error(f"更新 shop_authorizations 状态失败 (id={authorization_id}): {e}")
        return None


def upsert_sync_source(
    *,
    company_id: str,
    shop_connection_id: str,
    source_type: str,
    enabled: bool = True,
    sync_strategy: str = "full_then_incremental",
    last_sync_cursor: str = "",
    last_sync_at: str | None = None,
    last_success_at: str | None = None,
    last_status: str = "idle",
    last_error: str = "",
    extra: dict | None = None,
) -> dict | None:
    """创建或更新同步源配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_sources (
                        company_id, shop_connection_id, source_type, enabled,
                        sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                        last_status, last_error, extra
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (shop_connection_id, source_type)
                    DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        sync_strategy = EXCLUDED.sync_strategy,
                        last_sync_cursor = EXCLUDED.last_sync_cursor,
                        last_sync_at = EXCLUDED.last_sync_at,
                        last_success_at = EXCLUDED.last_success_at,
                        last_status = EXCLUDED.last_status,
                        last_error = EXCLUDED.last_error,
                        extra = EXCLUDED.extra,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, shop_connection_id, source_type, enabled,
                              sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                              last_status, last_error, extra, created_at, updated_at
                    """,
                    (
                        company_id,
                        shop_connection_id,
                        source_type,
                        enabled,
                        sync_strategy,
                        last_sync_cursor,
                        last_sync_at,
                        last_success_at,
                        last_status,
                        last_error,
                        psycopg2.extras.Json(extra or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 sync_sources 失败 (company_id={company_id}, shop_connection_id={shop_connection_id}, source_type={source_type}): {e}"
        )
        return None


def list_sync_sources(
    *,
    company_id: str,
    shop_connection_id: str | None = None,
) -> list[dict]:
    """列出同步源配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if shop_connection_id:
                    cur.execute(
                        """
                        SELECT id, company_id, shop_connection_id, source_type, enabled,
                               sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                               last_status, last_error, extra, created_at, updated_at
                        FROM sync_sources
                        WHERE company_id = %s
                          AND shop_connection_id = %s
                        ORDER BY source_type ASC
                        """,
                        (company_id, shop_connection_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, shop_connection_id, source_type, enabled,
                               sync_strategy, last_sync_cursor, last_sync_at, last_success_at,
                               last_status, last_error, extra, created_at, updated_at
                        FROM sync_sources
                        WHERE company_id = %s
                        ORDER BY shop_connection_id ASC, source_type ASC
                        """,
                        (company_id,),
                    )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 sync_sources 失败 (company_id={company_id}, shop_connection_id={shop_connection_id}): {e}"
        )
        return []


def create_auth_session(
    *,
    company_id: str,
    platform_code: str,
    state_token: str,
    expires_at: str,
    operator_user_id: str | None = None,
    shop_connection_id: str | None = None,
    return_path: str = "",
    redirect_uri: str = "",
    extra: dict | None = None,
) -> dict | None:
    """创建授权会话。"""
    ensure_auth_sessions_extra_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO auth_sessions (
                        company_id, platform_code, operator_user_id, shop_connection_id,
                        state_token, return_path, redirect_uri, status, expires_at, extra
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s::jsonb)
                    RETURNING id, company_id, platform_code, operator_user_id, shop_connection_id,
                              state_token, return_path, redirect_uri, status, expires_at,
                              callback_code, callback_error, callback_payload, extra,
                              created_at, updated_at, completed_at
                    """,
                    (
                        company_id,
                        platform_code,
                        operator_user_id,
                        shop_connection_id,
                        state_token,
                        return_path,
                        redirect_uri,
                        expires_at,
                        psycopg2.extras.Json(extra or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 auth_sessions 失败 (company_id={company_id}, platform_code={platform_code}, state={state_token}): {e}"
        )
        return None


def get_auth_session_by_state(state_token: str) -> dict | None:
    """按 state token 查询授权会话。"""
    ensure_auth_sessions_extra_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, operator_user_id, shop_connection_id,
                           state_token, return_path, redirect_uri, status, expires_at,
                           callback_code, callback_error, callback_payload, extra,
                           created_at, updated_at, completed_at
                    FROM auth_sessions
                    WHERE state_token = %s
                    LIMIT 1
                    """,
                    (state_token,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 auth_sessions 失败 (state_token={state_token}): {e}")
        return None


def update_auth_session_callback(
    *,
    session_id: str,
    status: str,
    callback_code: str = "",
    callback_error: str = "",
    callback_payload: dict | None = None,
) -> dict | None:
    """更新授权回调结果。status 通常为 authorized/failed/expired/cancelled。"""
    ensure_auth_sessions_extra_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE auth_sessions
                    SET status = %s,
                        callback_code = %s,
                        callback_error = %s,
                        callback_payload = %s::jsonb,
                        completed_at = CASE
                            WHEN %s IN ('authorized', 'failed', 'expired', 'cancelled')
                            THEN CURRENT_TIMESTAMP
                            ELSE completed_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, platform_code, operator_user_id, shop_connection_id,
                              state_token, return_path, redirect_uri, status, expires_at,
                              callback_code, callback_error, callback_payload, extra,
                              created_at, updated_at, completed_at
                    """,
                    (
                        status,
                        callback_code,
                        callback_error,
                        psycopg2.extras.Json(callback_payload or {}),
                        status,
                        session_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 auth_sessions 回调结果失败 (id={session_id}, status={status}): {e}")
        return None


def list_auth_sessions(
    *,
    company_id: str,
    platform_code: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """查询授权会话列表。"""
    ensure_auth_sessions_extra_schema()
    try:
        safe_limit = min(max(int(limit or 50), 1), 200)
    except (TypeError, ValueError):
        safe_limit = 50
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, platform_code, operator_user_id, shop_connection_id,
                           state_token, return_path, redirect_uri, status, expires_at,
                           callback_code, callback_error, callback_payload, extra,
                           created_at, updated_at, completed_at
                    FROM auth_sessions
                    WHERE company_id = %s
                """
                params: list = [company_id]
                if platform_code:
                    sql += " AND platform_code = %s"
                    params.append(platform_code)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(safe_limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 auth_sessions 列表失败 (company_id={company_id}, platform_code={platform_code}, status={status}): {e}"
        )
        return []


_PENDING_AUTH_SELECT_SQL = """
    id, platform_code, platform_app_id, app_id, source, claim_code, status,
    access_token, refresh_token, token_expires_at, refresh_expires_at,
    raw_auth_payload, callback_payload, external_shop_id, external_seller_id,
    merchant_display_name, claimed_company_id, claimed_by_user_id,
    claimed_shop_connection_id, claimed_at, expires_at, last_error,
    created_at, updated_at
""".strip()


def _normalize_pending_authorization(row: dict, *, include_secrets: bool = False) -> dict:
    result = _normalize_record(row)
    if include_secrets:
        result["access_token"] = open_secret(result.get("access_token") or "")
        result["refresh_token"] = open_secret(result.get("refresh_token") or "")
    else:
        result["access_token"] = ""
        result["refresh_token"] = ""
    return result


def create_platform_pending_authorization(
    *,
    platform_code: str,
    platform_app_id: str | None = None,
    app_id: str = "",
    source: str = "",
    claim_code: str = "",
    access_token: str = "",
    refresh_token: str = "",
    token_expires_at: str | None = None,
    refresh_expires_at: str | None = None,
    raw_auth_payload: dict | None = None,
    callback_payload: dict | None = None,
    external_shop_id: str = "",
    external_seller_id: str = "",
    merchant_display_name: str = "",
    expires_at: str = "",
    last_error: str = "",
    include_secrets: bool = False,
) -> dict | None:
    """创建无 state 平台授权待认领记录。"""
    ensure_platform_pending_authorizations_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    INSERT INTO platform_pending_authorizations (
                        platform_code, platform_app_id, app_id, source, claim_code, status,
                        access_token, refresh_token, token_expires_at, refresh_expires_at,
                        raw_auth_payload, callback_payload, external_shop_id, external_seller_id,
                        merchant_display_name, expires_at, last_error
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'pending_claim',
                        %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, %s,
                        %s, %s, %s
                    )
                    RETURNING {_PENDING_AUTH_SELECT_SQL}
                    """,
                    (
                        platform_code,
                        platform_app_id or None,
                        app_id,
                        source,
                        claim_code,
                        seal_secret(access_token),
                        seal_secret(refresh_token),
                        token_expires_at,
                        refresh_expires_at,
                        psycopg2.extras.Json(raw_auth_payload or {}),
                        psycopg2.extras.Json(callback_payload or {}),
                        external_shop_id,
                        external_seller_id,
                        merchant_display_name,
                        expires_at,
                        last_error,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_pending_authorization(dict(row), include_secrets=include_secrets) if row else None
    except Exception as e:
        logger.error(
            f"创建 platform_pending_authorizations 失败 (platform_code={platform_code}, external_shop_id={external_shop_id}): {e}"
        )
        return None


def list_platform_pending_authorizations(
    *,
    platform_code: str,
    status: str = "pending_claim",
    limit: int = 50,
) -> list[dict]:
    """查询平台待认领授权列表，不返回 token 明文。"""
    ensure_platform_pending_authorizations_schema()
    try:
        safe_limit = min(max(int(limit or 50), 1), 200)
    except (TypeError, ValueError):
        safe_limit = 50

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = f"""
                    SELECT {_PENDING_AUTH_SELECT_SQL}
                    FROM platform_pending_authorizations
                    WHERE platform_code = %s
                """
                params: list = [platform_code]
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(safe_limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_pending_authorization(dict(row), include_secrets=False) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 platform_pending_authorizations 列表失败 (platform_code={platform_code}, status={status}): {e}"
        )
        return []


def get_platform_pending_authorization_by_id(
    pending_authorization_id: str,
    *,
    include_secrets: bool = False,
) -> dict | None:
    """按 ID 查询待认领平台授权。"""
    ensure_platform_pending_authorizations_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT {_PENDING_AUTH_SELECT_SQL}
                    FROM platform_pending_authorizations
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (pending_authorization_id,),
                )
                row = cur.fetchone()
                return _normalize_pending_authorization(dict(row), include_secrets=include_secrets) if row else None
    except Exception as e:
        logger.error(f"按 ID 查询 platform_pending_authorizations 失败 (id={pending_authorization_id}): {e}")
        return None


def get_platform_pending_authorization_by_claim_code(
    claim_code: str,
    *,
    include_secrets: bool = False,
) -> dict | None:
    """按认领码查询待认领平台授权。"""
    ensure_platform_pending_authorizations_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT {_PENDING_AUTH_SELECT_SQL}
                    FROM platform_pending_authorizations
                    WHERE claim_code = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (claim_code,),
                )
                row = cur.fetchone()
                return _normalize_pending_authorization(dict(row), include_secrets=include_secrets) if row else None
    except Exception as e:
        logger.error(f"按认领码查询 platform_pending_authorizations 失败 (claim_code={claim_code}): {e}")
        return None


def mark_platform_pending_authorization_claimed(
    *,
    pending_authorization_id: str,
    claimed_company_id: str,
    claimed_by_user_id: str,
    claimed_shop_connection_id: str,
    last_error: str = "",
) -> dict | None:
    """标记待认领授权已绑定到企业。"""
    ensure_platform_pending_authorizations_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE platform_pending_authorizations
                    SET status = 'claimed',
                        claimed_company_id = %s,
                        claimed_by_user_id = %s,
                        claimed_shop_connection_id = %s,
                        claimed_at = CURRENT_TIMESTAMP,
                        last_error = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING {_PENDING_AUTH_SELECT_SQL}
                    """,
                    (
                        claimed_company_id,
                        claimed_by_user_id,
                        claimed_shop_connection_id,
                        last_error,
                        pending_authorization_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_pending_authorization(dict(row), include_secrets=False) if row else None
    except Exception as e:
        logger.error(
            f"标记 platform_pending_authorizations 已认领失败 (id={pending_authorization_id}): {e}"
        )
        return None


def mark_platform_pending_authorization_failed(
    *,
    pending_authorization_id: str,
    status: str = "failed",
    last_error: str = "",
) -> dict | None:
    """标记待认领授权失败、过期或丢弃。"""
    ensure_platform_pending_authorizations_schema()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE platform_pending_authorizations
                    SET status = %s,
                        last_error = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING {_PENDING_AUTH_SELECT_SQL}
                    """,
                    (status, last_error, pending_authorization_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_pending_authorization(dict(row), include_secrets=False) if row else None
    except Exception as e:
        logger.error(
            f"标记 platform_pending_authorizations 失败状态失败 (id={pending_authorization_id}, status={status}): {e}"
        )
        return None


def find_shop_connection_by_platform_external_shop(
    *,
    platform_code: str,
    external_shop_id: str,
) -> dict | None:
    """跨企业查询某平台主体是否已绑定。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, platform_code, external_shop_id, external_shop_name,
                           external_seller_id, auth_subject_name, shop_type, status, meta,
                           created_at, updated_at
                    FROM shop_connections
                    WHERE platform_code = %s
                      AND external_shop_id = %s
                      AND status <> 'deleted'
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (platform_code, external_shop_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"跨企业查询 shop_connections 失败 (platform_code={platform_code}, external_shop_id={external_shop_id}): {e}"
        )
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 通用数据连接模型（data_sources / sync_jobs / data_source_datasets）
# ══════════════════════════════════════════════════════════════════════════════


def create_data_source(
    *,
    company_id: str,
    source_kind: str,
    domain_type: str,
    provider_code: str,
    source_code: str,
    name: str,
    execution_mode: str = "deterministic",
    description: str = "",
    status: str = "active",
    capabilities: list[str] | None = None,
    created_by: str | None = None,
    updated_by: str | None = None,
) -> dict | None:
    """创建数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_sources (
                        company_id, source_kind, domain_type, execution_mode,
                        provider_code, source_code, name, description, status,
                        capabilities, created_by, updated_by
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    RETURNING id, company_id, source_kind, domain_type, execution_mode,
                              provider_code, source_code, name, description, status,
                              capabilities, last_test_status, last_test_at, last_test_error,
                              created_by, updated_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        source_kind,
                        domain_type,
                        execution_mode,
                        provider_code,
                        source_code,
                        name,
                        description,
                        status,
                        psycopg2.extras.Json(capabilities or []),
                        created_by,
                        updated_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 data_sources 失败 (company_id={company_id}, source_code={source_code}): {e}")
        return None


def update_data_source(
    *,
    data_source_id: str,
    company_id: str,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    capabilities: list[str] | None = None,
    updated_by: str | None = None,
    last_test_status: str | None = None,
    last_test_error: str | None = None,
    touch_last_test_at: bool = False,
) -> dict | None:
    """更新数据源基础信息。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_sources
                    SET name = COALESCE(%s, name),
                        description = COALESCE(%s, description),
                        status = COALESCE(%s, status),
                        capabilities = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN capabilities
                            ELSE %s::jsonb
                        END,
                        updated_by = COALESCE(%s, updated_by),
                        last_test_status = COALESCE(%s, last_test_status),
                        last_test_error = COALESCE(%s, last_test_error),
                        last_test_at = CASE
                            WHEN %s THEN CURRENT_TIMESTAMP
                            ELSE last_test_at
                        END
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, source_kind, domain_type, execution_mode,
                              provider_code, source_code, name, description, status,
                              capabilities, last_test_status, last_test_at, last_test_error,
                              created_by, updated_by, created_at, updated_at
                    """,
                    (
                        name,
                        description,
                        status,
                        psycopg2.extras.Json(capabilities) if capabilities is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(capabilities) if capabilities is not None else psycopg2.extras.Json(None),
                        updated_by,
                        last_test_status,
                        last_test_error,
                        touch_last_test_at,
                        data_source_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_sources 失败 (id={data_source_id}, company_id={company_id}): {e}")
        return None


def get_data_source_by_id(data_source_id: str, company_id: str | None = None) -> dict | None:
    """按 id 查询数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, source_kind, domain_type, execution_mode,
                               provider_code, source_code, name, description, status,
                               capabilities, last_test_status, last_test_at, last_test_error,
                               created_by, updated_by, created_at, updated_at
                        FROM data_sources
                        WHERE id = %s AND company_id = %s
                        LIMIT 1
                        """,
                        (data_source_id, company_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, source_kind, domain_type, execution_mode,
                               provider_code, source_code, name, description, status,
                               capabilities, last_test_status, last_test_at, last_test_error,
                               created_by, updated_by, created_at, updated_at
                        FROM data_sources
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (data_source_id,),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_sources 失败 (id={data_source_id}, company_id={company_id}): {e}")
        return None


def get_data_source_by_code(company_id: str, source_code: str) -> dict | None:
    """按 source_code 查询数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, source_kind, domain_type, execution_mode,
                           provider_code, source_code, name, description, status,
                           capabilities, last_test_status, last_test_at, last_test_error,
                           created_by, updated_by, created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """,
                    (company_id, source_code),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"按 source_code 查询 data_sources 失败 (company_id={company_id}, source_code={source_code}): {e}")
        return None


def list_data_sources(
    *,
    company_id: str,
    source_kind: str | None = None,
    domain_type: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """列出数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, source_kind, domain_type, execution_mode,
                           provider_code, source_code, name, description, status,
                           capabilities, last_test_status, last_test_at, last_test_error,
                           created_by, updated_by, created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if source_kind:
                    sql += " AND source_kind = %s"
                    params.append(source_kind)
                if domain_type:
                    sql += " AND domain_type = %s"
                    params.append(domain_type)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY updated_at DESC, created_at DESC"
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 data_sources 列表失败 (company_id={company_id}): {e}")
        return []


def create_data_source_credential(
    *,
    company_id: str,
    data_source_id: str,
    credential_payload: dict[str, Any],
    credential_type: str = "primary",
    credential_mask: dict[str, Any] | None = None,
    status: str = "active",
    created_by: str | None = None,
) -> dict | None:
    """创建新的数据源凭证，并将历史 current 记录置为 false。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_source_credentials
                    SET is_current = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE data_source_id = %s
                      AND credential_type = %s
                      AND is_current = true
                    """,
                    (data_source_id, credential_type),
                )
                cur.execute(
                    """
                    INSERT INTO data_source_credentials (
                        company_id, data_source_id, credential_type, encrypted_payload,
                        credential_mask, version, is_current, status, last_rotated_at, created_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s::jsonb,
                        COALESCE(
                            (SELECT MAX(version) + 1
                             FROM data_source_credentials
                             WHERE data_source_id = %s AND credential_type = %s),
                            1
                        ),
                        true, %s, CURRENT_TIMESTAMP, %s
                    )
                    RETURNING id, company_id, data_source_id, credential_type, credential_mask,
                              version, is_current, status, last_rotated_at, created_by,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        credential_type,
                        _seal_json_payload(credential_payload),
                        psycopg2.extras.Json(credential_mask or {}),
                        data_source_id,
                        credential_type,
                        status,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 data_source_credentials 失败 (source_id={data_source_id}, type={credential_type}): {e}")
        return None


def get_current_data_source_credential(
    *,
    company_id: str,
    data_source_id: str,
    credential_type: str = "primary",
    include_secret: bool = False,
) -> dict | None:
    """查询当前生效凭证。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, credential_type, encrypted_payload,
                           credential_mask, version, is_current, status, last_rotated_at,
                           created_by, created_at, updated_at
                    FROM data_source_credentials
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND credential_type = %s
                      AND is_current = true
                    LIMIT 1
                    """,
                    (company_id, data_source_id, credential_type),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secret:
                    result["credential_payload"] = _open_json_payload(result.get("encrypted_payload") or "")
                result["encrypted_payload"] = ""
                return result
    except Exception as e:
        logger.error(f"查询 data_source_credentials 失败 (source_id={data_source_id}, type={credential_type}): {e}")
        return None


def upsert_data_source_config(
    *,
    company_id: str,
    data_source_id: str,
    config_type: str,
    config: dict[str, Any],
    created_by: str | None = None,
) -> dict | None:
    """写入数据源当前配置版本。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_source_configs
                    SET is_current = false,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE data_source_id = %s
                      AND config_type = %s
                      AND is_current = true
                    """,
                    (data_source_id, config_type),
                )
                cur.execute(
                    """
                    INSERT INTO data_source_configs (
                        company_id, data_source_id, config_type, version, is_current, config, created_by
                    )
                    VALUES (
                        %s, %s, %s,
                        COALESCE(
                            (SELECT MAX(version) + 1
                             FROM data_source_configs
                             WHERE data_source_id = %s AND config_type = %s),
                            1
                        ),
                        true, %s::jsonb, %s
                    )
                    RETURNING id, company_id, data_source_id, config_type, version,
                              is_current, config, created_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        config_type,
                        data_source_id,
                        config_type,
                        psycopg2.extras.Json(config or {}),
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 data_source_configs 失败 (source_id={data_source_id}, type={config_type}): {e}")
        return None


def get_current_data_source_config(
    *,
    company_id: str,
    data_source_id: str,
    config_type: str,
) -> dict | None:
    """读取当前配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, config_type, version,
                           is_current, config, created_by, created_at, updated_at
                    FROM data_source_configs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND config_type = %s
                      AND is_current = true
                    LIMIT 1
                    """,
                    (company_id, data_source_id, config_type),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_source_configs 失败 (source_id={data_source_id}, type={config_type}): {e}")
        return None


def list_current_data_source_configs(
    *,
    company_id: str,
    data_source_id: str,
) -> list[dict]:
    """列出当前所有配置分组。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, config_type, version,
                           is_current, config, created_by, created_at, updated_at
                    FROM data_source_configs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND is_current = true
                    ORDER BY config_type ASC
                    """,
                    (company_id, data_source_id),
                )
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 data_source_configs 列表失败 (source_id={data_source_id}): {e}")
        return []


def create_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    idempotency_key: str,
    job_type: str = "sync",
    trigger_type: str = "manual",
    resource_scope: dict[str, Any] | None = None,
    requested_window_start: str | None = None,
    requested_window_end: str | None = None,
    requested_cursor: str = "",
    requested_by: str | None = None,
    run_context: dict[str, Any] | None = None,
) -> dict | None:
    """创建同步任务；如果幂等键已存在则直接返回已有任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_jobs (
                        company_id, data_source_id, job_type, trigger_type, status,
                        idempotency_key, resource_scope, requested_window_start,
                        requested_window_end, requested_cursor, requested_by, run_context
                    ) VALUES (%s, %s, %s, %s, 'pending', %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (company_id, idempotency_key)
                    DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, job_type, trigger_type, status,
                              idempotency_key, resource_scope, requested_window_start,
                              requested_window_end, requested_cursor, active_attempt_no,
                              requested_by, run_context, error_summary, started_at, finished_at,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        job_type,
                        trigger_type,
                        idempotency_key,
                        psycopg2.extras.Json(resource_scope or {}),
                        requested_window_start,
                        requested_window_end,
                        requested_cursor,
                        requested_by,
                        psycopg2.extras.Json(run_context or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 sync_jobs 失败 (source_id={data_source_id}, key={idempotency_key}): {e}")
        return None


def get_sync_job(
    *,
    sync_job_id: str,
    company_id: str | None = None,
) -> dict | None:
    """按 id 查询同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, job_type, trigger_type, status,
                               idempotency_key, resource_scope, requested_window_start,
                               requested_window_end, requested_cursor, active_attempt_no,
                               requested_by, run_context, error_summary, started_at, finished_at,
                               created_at, updated_at
                        FROM sync_jobs
                        WHERE id = %s AND company_id = %s
                        LIMIT 1
                        """,
                        (sync_job_id, company_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, job_type, trigger_type, status,
                               idempotency_key, resource_scope, requested_window_start,
                               requested_window_end, requested_cursor, active_attempt_no,
                               requested_by, run_context, error_summary, started_at, finished_at,
                               created_at, updated_at
                        FROM sync_jobs
                        WHERE id = %s
                        LIMIT 1
                        """,
                        (sync_job_id,),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 sync_jobs 失败 (id={sync_job_id}, company_id={company_id}): {e}")
        return None


def list_sync_jobs(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """列出同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, job_type, trigger_type, status,
                           idempotency_key, resource_scope, requested_window_start,
                           requested_window_end, requested_cursor, active_attempt_no,
                           requested_by, run_context, error_summary, started_at, finished_at,
                           created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 sync_jobs 列表失败 (company_id={company_id}, source_id={data_source_id}): {e}")
        return []


def update_sync_job_status(
    *,
    sync_job_id: str,
    status: str,
    error_summary: str | None = None,
    active_attempt_no: int | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
) -> dict | None:
    """更新同步任务状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET status = %s,
                        error_summary = COALESCE(%s, error_summary),
                        active_attempt_no = COALESCE(%s, active_attempt_no),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, job_type, trigger_type, status,
                              idempotency_key, resource_scope, requested_window_start,
                              requested_window_end, requested_cursor, active_attempt_no,
                              requested_by, run_context, error_summary, started_at, finished_at,
                              created_at, updated_at
                    """,
                    (
                        status,
                        error_summary,
                        active_attempt_no,
                        mark_started,
                        mark_finished,
                        sync_job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_jobs 状态失败 (id={sync_job_id}, status={status}): {e}")
        return None


def create_sync_job_attempt(
    *,
    company_id: str,
    sync_job_id: str,
    attempt_no: int,
    request_payload: dict[str, Any] | None = None,
) -> dict | None:
    """创建同步尝试。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_job_attempts (
                        company_id, sync_job_id, attempt_no, status, request_payload
                    ) VALUES (%s, %s, %s, 'pending', %s::jsonb)
                    RETURNING id, company_id, sync_job_id, attempt_no, status,
                              request_payload, runtime_summary, error_detail,
                              started_at, finished_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        sync_job_id,
                        attempt_no,
                        psycopg2.extras.Json(request_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 sync_job_attempts 失败 (job_id={sync_job_id}, attempt={attempt_no}): {e}")
        return None


def list_sync_job_attempts(sync_job_id: str) -> list[dict]:
    """列出同步任务的尝试记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, sync_job_id, attempt_no, status,
                           request_payload, runtime_summary, error_detail,
                           started_at, finished_at, created_at, updated_at
                    FROM sync_job_attempts
                    WHERE sync_job_id = %s
                    ORDER BY attempt_no DESC
                    """,
                    (sync_job_id,),
                )
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 sync_job_attempts 失败 (job_id={sync_job_id}): {e}")
        return []


def update_sync_job_attempt_status(
    *,
    sync_attempt_id: str,
    status: str,
    runtime_summary: dict[str, Any] | None = None,
    error_detail: str | None = None,
    mark_started: bool = False,
    mark_finished: bool = False,
) -> dict | None:
    """更新同步尝试状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_job_attempts
                    SET status = %s,
                        runtime_summary = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN runtime_summary
                            ELSE %s::jsonb
                        END,
                        error_detail = COALESCE(%s, error_detail),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, sync_job_id, attempt_no, status,
                              request_payload, runtime_summary, error_detail,
                              started_at, finished_at, created_at, updated_at
                    """,
                    (
                        status,
                        psycopg2.extras.Json(runtime_summary) if runtime_summary is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(runtime_summary) if runtime_summary is not None else psycopg2.extras.Json(None),
                        error_detail,
                        mark_started,
                        mark_finished,
                        sync_attempt_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_job_attempts 状态失败 (id={sync_attempt_id}, status={status}): {e}")
        return None



def upsert_dataset_binding(
    *,
    company_id: str,
    data_source_id: str,
    dataset_code: str,
    consumer_type: str,
    consumer_key: str,
    role_code: str = "source",
    selection_mode: str = "latest_published",
    binding_config: dict[str, Any] | None = None,
    status: str = "active",
) -> dict | None:
    """写入数据集绑定关系。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO dataset_bindings (
                        company_id, data_source_id, dataset_code, consumer_type,
                        consumer_key, role_code, selection_mode, binding_config, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    ON CONFLICT (company_id, consumer_type, consumer_key, role_code)
                    DO UPDATE SET
                        data_source_id = EXCLUDED.data_source_id,
                        dataset_code = EXCLUDED.dataset_code,
                        selection_mode = EXCLUDED.selection_mode,
                        binding_config = EXCLUDED.binding_config,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, dataset_code, consumer_type,
                              consumer_key, role_code, selection_mode, binding_config,
                              status, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        dataset_code,
                        consumer_type,
                        consumer_key,
                        role_code,
                        selection_mode,
                        psycopg2.extras.Json(binding_config or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 dataset_bindings 失败 (consumer={consumer_type}:{consumer_key}, role={role_code}): {e}")
        return None


def list_dataset_bindings(
    *,
    company_id: str,
    consumer_type: str | None = None,
    consumer_key: str | None = None,
) -> list[dict]:
    """列出数据集绑定。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_code, consumer_type,
                           consumer_key, role_code, selection_mode, binding_config,
                           status, created_at, updated_at
                    FROM dataset_bindings
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if consumer_type:
                    sql += " AND consumer_type = %s"
                    params.append(consumer_type)
                if consumer_key:
                    sql += " AND consumer_key = %s"
                    params.append(consumer_key)
                sql += " ORDER BY updated_at DESC"
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询 dataset_bindings 失败 (company_id={company_id}): {e}")
        return []


def create_data_source_event(
    *,
    company_id: str,
    event_type: str,
    data_source_id: str | None = None,
    sync_job_id: str | None = None,
    sync_attempt_id: str | None = None,
    event_level: str = "info",
    event_message: str = "",
    event_payload: dict[str, Any] | None = None,
) -> dict | None:
    """写入数据连接审计事件。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_events (
                        company_id, data_source_id, sync_job_id, sync_attempt_id,
                        event_type, event_level, event_message, event_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    RETURNING id, company_id, data_source_id, sync_job_id, sync_attempt_id,
                              event_type, event_level, event_message, event_payload, created_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        sync_attempt_id,
                        event_type,
                        event_level,
                        event_message,
                        psycopg2.extras.Json(event_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 data_source_events 失败 (event_type={event_type}, source_id={data_source_id}): {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 通用数据连接模型（data_sources / sync_jobs / data_source_datasets）
# ══════════════════════════════════════════════════════════════════════════════


def upsert_unified_data_source(
    *,
    company_id: str,
    code: str,
    name: str,
    source_kind: str,
    domain_type: str,
    provider_code: str,
    execution_mode: str = "deterministic",
    description: str = "",
    status: str = "active",
    is_enabled: bool = True,
    health_status: str | None = None,
    last_checked_at: str | None = None,
    last_error_message: str | None = None,
    meta: dict | None = None,
) -> dict | None:
    """创建或更新数据源。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_sources (
                        company_id, code, name, source_kind, domain_type, provider_code,
                        execution_mode, description, status, is_enabled,
                        health_status, last_checked_at, last_error_message, meta
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        COALESCE(%s, 'unknown'), %s, COALESCE(%s, ''), %s::jsonb
                    )
                    ON CONFLICT (company_id, code)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        source_kind = EXCLUDED.source_kind,
                        domain_type = EXCLUDED.domain_type,
                        provider_code = EXCLUDED.provider_code,
                        execution_mode = EXCLUDED.execution_mode,
                        description = EXCLUDED.description,
                        status = EXCLUDED.status,
                        is_enabled = EXCLUDED.is_enabled,
                        health_status = COALESCE(EXCLUDED.health_status, data_sources.health_status),
                        last_checked_at = COALESCE(EXCLUDED.last_checked_at, data_sources.last_checked_at),
                        last_error_message = CASE
                            WHEN EXCLUDED.last_error_message IS NULL
                                THEN data_sources.last_error_message
                            ELSE EXCLUDED.last_error_message
                        END,
                        meta = EXCLUDED.meta,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                              execution_mode, description, status, is_enabled,
                              health_status, last_checked_at, last_error_message, meta,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        code,
                        name,
                        source_kind,
                        domain_type,
                        provider_code,
                        execution_mode,
                        description,
                        status,
                        is_enabled,
                        health_status,
                        last_checked_at,
                        last_error_message,
                        psycopg2.extras.Json(meta or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"写入 data_sources 失败 (company_id={company_id}, code={code}): {e}")
        return None


def get_unified_data_source_by_id(*, company_id: str, data_source_id: str) -> dict | None:
    """按 id 查询数据源。"""
    conn_manager = get_conn()
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
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, data_source_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_sources 失败 (company_id={company_id}, id={data_source_id}): {e}")
        return None


def list_unified_data_sources(
    *,
    company_id: str,
    source_kind: str | None = None,
    domain_type: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    """查询数据源列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, code, name, source_kind, domain_type, provider_code,
                           execution_mode, description, status, is_enabled,
                           health_status, last_checked_at, last_error_message, meta,
                           created_at, updated_at
                    FROM data_sources
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if source_kind:
                    sql += " AND source_kind = %s"
                    params.append(source_kind)
                if domain_type:
                    sql += " AND domain_type = %s"
                    params.append(domain_type)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                elif not include_deleted:
                    sql += " AND status <> 'deleted'"
                sql += " ORDER BY updated_at DESC, created_at DESC"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 data_sources 列表失败 (company_id={company_id}, source_kind={source_kind}, domain_type={domain_type}, status={status}): {e}"
        )
        return []


def update_unified_data_source_status(
    *,
    data_source_id: str,
    status: str,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新数据源状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_enabled is None:
                    cur.execute(
                        """
                        UPDATE data_sources
                        SET status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                                  execution_mode, description, status, is_enabled,
                                  health_status, last_checked_at, last_error_message, meta,
                                  created_at, updated_at
                        """,
                        (status, data_source_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE data_sources
                        SET status = %s,
                            is_enabled = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                                  execution_mode, description, status, is_enabled,
                                  health_status, last_checked_at, last_error_message, meta,
                                  created_at, updated_at
                        """,
                        (status, is_enabled, data_source_id),
                    )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_sources 状态失败 (id={data_source_id}, status={status}): {e}")
        return None


def update_unified_data_source_health(
    *,
    data_source_id: str,
    health_status: str,
    last_checked_at: str | None = None,
    last_error_message: str = "",
) -> dict | None:
    """更新数据源健康状态。"""
    conn_manager = get_conn()
    checked_at = last_checked_at or datetime.now(timezone.utc).isoformat()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE data_sources
                    SET health_status = %s,
                        last_checked_at = %s,
                        last_error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, code, name, source_kind, domain_type, provider_code,
                              execution_mode, description, status, is_enabled,
                              health_status, last_checked_at, last_error_message, meta,
                              created_at, updated_at
                    """,
                    (health_status, checked_at, last_error_message, data_source_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_sources 健康状态失败 (id={data_source_id}, health_status={health_status}): {e}")
        return None


def upsert_unified_data_source_dataset(
    *,
    company_id: str,
    data_source_id: str,
    dataset_code: str,
    dataset_name: str,
    resource_key: str = "default",
    dataset_kind: str = "table",
    origin_type: str = "manual",
    extract_config: dict | None = None,
    schema_summary: dict | None = None,
    sync_strategy: dict | None = None,
    status: str = "active",
    is_enabled: bool = True,
    health_status: str = "unknown",
    last_checked_at: str | None = None,
    last_sync_at: str | None = None,
    last_error_message: str = "",
    meta: dict | None = None,
    schema_name: str | None = None,
    object_name: str | None = None,
    object_type: str | None = None,
    publish_status: str = "unpublished",
    business_domain: str | None = None,
    business_object_type: str | None = None,
    grain: str | None = None,
    usage_count: int = 0,
    last_used_at: str | None = None,
    search_text: str | None = None,
) -> dict | None:
    """创建或更新数据源下的数据集目录项。"""
    conn_manager = get_conn()
    extract_config = dict(extract_config or {})
    schema_summary = dict(schema_summary or {})
    sync_strategy = dict(sync_strategy or {})
    meta = dict(meta or {})
    resolved_schema_name, resolved_object_name = _infer_schema_and_object_name(resource_key, dataset_name, dataset_code)
    resolved_schema_name = (
        str(schema_name or "").strip()
        or str(extract_config.get("schema") or "").strip()
        or str(schema_summary.get("schema") or "").strip()
        or (resolved_schema_name or "")
    )
    resolved_object_name = (
        str(object_name or "").strip()
        or str(extract_config.get("table") or "").strip()
        or str(extract_config.get("object_name") or "").strip()
        or str(schema_summary.get("table") or "").strip()
        or str(schema_summary.get("object_name") or "").strip()
        or (resolved_object_name or "")
        or str(dataset_code or "").strip()
    )
    resolved_object_type = (
        str(object_type or "").strip().lower()
        or str(extract_config.get("object_type") or "").strip().lower()
        or _infer_object_type(dataset_kind, schema_summary)
    )
    resolved_business_domain = str(business_domain or "").strip()
    resolved_business_object_type = str(business_object_type or "").strip()
    resolved_grain = str(grain or "").strip()
    resolved_publish_status = _normalize_catalog_status(
        publish_status,
        allowed=("unpublished", "published", "deprecated"),
        default="unpublished",
    )
    resolved_search_text = str(search_text or "").strip() or _build_dataset_search_text(
        dataset_name=dataset_name,
        dataset_code=dataset_code,
        resource_key=resource_key,
        schema_name=resolved_schema_name,
        object_name=resolved_object_name,
        object_type=resolved_object_type,
        business_domain=resolved_business_domain,
        business_object_type=resolved_business_object_type,
        grain=resolved_grain,
        meta=meta,
    ).lower()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    INSERT INTO data_source_datasets (
                        company_id, data_source_id, dataset_code, dataset_name,
                        resource_key, dataset_kind, origin_type,
                        schema_name, object_name, object_type,
                        publish_status, business_domain, business_object_type, grain,
                        usage_count, last_used_at, search_text,
                        extract_config, schema_summary, sync_strategy,
                        status, is_enabled, health_status,
                        last_checked_at, last_sync_at, last_error_message, meta
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    ON CONFLICT (company_id, data_source_id, dataset_code)
                    DO UPDATE SET
                        dataset_name = EXCLUDED.dataset_name,
                        resource_key = EXCLUDED.resource_key,
                        dataset_kind = EXCLUDED.dataset_kind,
                        origin_type = EXCLUDED.origin_type,
                        schema_name = EXCLUDED.schema_name,
                        object_name = EXCLUDED.object_name,
                        object_type = EXCLUDED.object_type,
                        publish_status = EXCLUDED.publish_status,
                        business_domain = EXCLUDED.business_domain,
                        business_object_type = EXCLUDED.business_object_type,
                        grain = EXCLUDED.grain,
                        usage_count = GREATEST(data_source_datasets.usage_count, EXCLUDED.usage_count),
                        last_used_at = COALESCE(EXCLUDED.last_used_at, data_source_datasets.last_used_at),
                        search_text = EXCLUDED.search_text,
                        extract_config = EXCLUDED.extract_config,
                        schema_summary = EXCLUDED.schema_summary,
                        sync_strategy = EXCLUDED.sync_strategy,
                        status = EXCLUDED.status,
                        is_enabled = EXCLUDED.is_enabled,
                        health_status = EXCLUDED.health_status,
                        last_checked_at = EXCLUDED.last_checked_at,
                        last_sync_at = EXCLUDED.last_sync_at,
                        last_error_message = EXCLUDED.last_error_message,
                        meta = EXCLUDED.meta,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    """,
                    (
                        company_id,
                        data_source_id,
                        dataset_code,
                        dataset_name,
                        resource_key,
                        dataset_kind,
                        origin_type,
                        resolved_schema_name,
                        resolved_object_name,
                        resolved_object_type,
                        resolved_publish_status,
                        resolved_business_domain,
                        resolved_business_object_type,
                        resolved_grain,
                        max(0, int(usage_count or 0)),
                        last_used_at,
                        resolved_search_text,
                        psycopg2.extras.Json(extract_config),
                        psycopg2.extras.Json(schema_summary),
                        psycopg2.extras.Json(sync_strategy),
                        status,
                        is_enabled,
                        health_status,
                        last_checked_at,
                        last_sync_at,
                        last_error_message,
                        psycopg2.extras.Json(meta),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 data_source_datasets 失败 (company_id={company_id}, data_source_id={data_source_id}, dataset_code={dataset_code}): {e}"
        )
        return None


def get_unified_data_source_dataset_by_id(
    *,
    company_id: str,
    dataset_id: str,
) -> dict | None:
    """按 id 查询数据集目录项。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    FROM data_source_datasets
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, dataset_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 data_source_datasets 失败 (company_id={company_id}, id={dataset_id}): {e}")
        return None


def get_unified_data_source_dataset_by_source_resource(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str = "default",
    status: str | None = None,
) -> dict | None:
    """按 source + resource_key 查询数据集目录项（最新一条）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = f"""
                    SELECT {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    FROM data_source_datasets
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND resource_key = %s
                """
                params: list[Any] = [company_id, data_source_id, resource_key]
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                else:
                    sql += " AND status <> 'deleted'"
                sql += " ORDER BY updated_at DESC, created_at DESC LIMIT 1"
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 data_source_datasets 失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}, status={status}): {e}"
        )
        return None


def query_unified_data_source_datasets(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    limit: int = 500,
    keyword: str = "",
    schema_name: str = "",
    object_type: str = "",
    publish_status: str = "",
    business_object_type: str = "",
    only_published: bool = False,
    page: int = 1,
    page_size: int = 500,
    sort_by: str = "updated_at_desc",
    lightweight: bool = False,
) -> dict[str, Any]:
    """查询数据源下的数据集目录列表，支持海量目录筛选和分页。"""
    conn_manager = get_conn()
    page_size = max(1, min(int(page_size or 50), 200))
    page = max(1, int(page or 1))
    offset = (page - 1) * page_size
    if limit:
        page_size = min(page_size, max(1, min(int(limit), 2000)))
    select_columns = _UNIFIED_DATASET_SELECT_COLUMNS_SQL
    if lightweight:
        select_columns = """
            id, company_id, data_source_id, dataset_code, dataset_name,
            resource_key, dataset_kind, origin_type,
            schema_name, object_name, object_type,
            publish_status, business_domain, business_object_type, grain,
            usage_count, last_used_at, search_text,
            status, is_enabled, health_status,
            last_checked_at, last_sync_at, last_error_message, meta,
            created_at, updated_at
        """.strip()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = f"""
                    SELECT {select_columns}
                    FROM data_source_datasets
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                elif not include_deleted:
                    sql += " AND status <> 'deleted'"
                if only_published:
                    sql += " AND publish_status = 'published'"
                elif publish_status:
                    sql += " AND publish_status = %s"
                    params.append(publish_status)
                if schema_name:
                    sql += " AND schema_name = %s"
                    params.append(schema_name)
                if object_type:
                    sql += " AND object_type = %s"
                    params.append(object_type)
                if business_object_type:
                    sql += " AND business_object_type = %s"
                    params.append(business_object_type)
                if keyword:
                    keyword_pattern = f"%{keyword.strip().lower()}%"
                    sql += """
                        AND (
                            lower(search_text) LIKE %s
                            OR lower(dataset_name) LIKE %s
                            OR lower(dataset_code) LIKE %s
                            OR lower(resource_key) LIKE %s
                            OR lower(object_name) LIKE %s
                        )
                    """
                    params.extend(
                        [
                            keyword_pattern,
                            keyword_pattern,
                            keyword_pattern,
                            keyword_pattern,
                            keyword_pattern,
                        ]
                    )

                count_sql = f"SELECT count(1) AS total FROM ({sql}) q"
                cur.execute(count_sql, tuple(params))
                total_row = cur.fetchone() or {}
                total = int(total_row.get("total") or 0)

                sort_mapping = {
                    "updated_at_desc": "updated_at DESC, created_at DESC",
                    "updated_desc": "updated_at DESC, created_at DESC",
                    "updated_at_asc": "updated_at ASC, created_at ASC",
                    "updated_asc": "updated_at ASC, created_at ASC",
                    "last_sync_desc": "last_sync_at DESC NULLS LAST, updated_at DESC",
                    "last_used_desc": "usage_count DESC, last_used_at DESC NULLS LAST, updated_at DESC",
                    "usage_desc": "usage_count DESC, last_used_at DESC NULLS LAST, updated_at DESC",
                    "name_asc": "COALESCE(NULLIF(lower(object_name), ''), lower(dataset_name)) ASC, updated_at DESC",
                    "name_desc": "COALESCE(NULLIF(lower(object_name), ''), lower(dataset_name)) DESC, updated_at DESC",
                    "schema_object_asc": "lower(schema_name) ASC, lower(object_name) ASC, updated_at DESC",
                }
                normalized_sort_by = str(sort_by or "").strip().lower()
                sql += f" ORDER BY {sort_mapping.get(normalized_sort_by, sort_mapping['updated_at_desc'])} LIMIT %s OFFSET %s"
                params.extend([page_size, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                items = [_normalize_record(dict(row)) for row in rows]
                return {
                    "items": items,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }
    except Exception as e:
        logger.error(
            "查询 data_source_datasets 列表失败 "
            f"(company_id={company_id}, data_source_id={data_source_id}, status={status}, "
            f"publish_status={publish_status}, keyword={keyword!r}): {e}"
        )
        return {"items": [], "total": 0, "page": page, "page_size": page_size}


def list_unified_data_source_datasets(
    *,
    company_id: str,
    data_source_id: str | None = None,
    status: str | None = None,
    include_deleted: bool = False,
    limit: int = 500,
    keyword: str = "",
    schema_name: str = "",
    object_type: str = "",
    publish_status: str = "",
    business_object_type: str = "",
    only_published: bool = False,
    page: int = 1,
    page_size: int = 500,
    sort_by: str = "updated_at_desc",
    lightweight: bool = False,
) -> list[dict]:
    result = query_unified_data_source_datasets(
        company_id=company_id,
        data_source_id=data_source_id,
        status=status,
        include_deleted=include_deleted,
        limit=limit,
        keyword=keyword,
        schema_name=schema_name,
        object_type=object_type,
        publish_status=publish_status,
        business_object_type=business_object_type,
        only_published=only_published,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        lightweight=lightweight,
    )
    return list(result.get("items") or [])


def update_unified_data_source_dataset_status(
    *,
    dataset_id: str,
    status: str,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新数据集目录状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_enabled is None:
                    cur.execute(
                        f"""
                        UPDATE data_source_datasets
                        SET status = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                        """,
                        (status, dataset_id),
                    )
                else:
                    cur.execute(
                        f"""
                        UPDATE data_source_datasets
                        SET status = %s,
                            is_enabled = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                        RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                        """,
                        (status, is_enabled, dataset_id),
                    )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_source_datasets 状态失败 (id={dataset_id}, status={status}): {e}")
        return None


def update_unified_data_source_dataset_health(
    *,
    dataset_id: str,
    health_status: str,
    last_checked_at: str | None = None,
    last_sync_at: str | None = None,
    last_error_message: str = "",
) -> dict | None:
    """更新数据集目录健康状态。"""
    conn_manager = get_conn()
    checked_at = last_checked_at or datetime.now(timezone.utc).isoformat()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE data_source_datasets
                    SET health_status = %s,
                        last_checked_at = %s,
                        last_sync_at = COALESCE(%s, last_sync_at),
                        last_error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    """,
                    (health_status, checked_at, last_sync_at, last_error_message, dataset_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"更新 data_source_datasets 健康状态失败 (id={dataset_id}, health_status={health_status}): {e}"
        )
        return None


def update_unified_data_source_dataset_meta(
    *,
    dataset_id: str,
    meta: dict | None = None,
) -> dict | None:
    """仅更新数据集 meta 字段。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE data_source_datasets
                    SET meta = %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    """,
                    (psycopg2.extras.Json(meta or {}), dataset_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_source_datasets meta 失败 (id={dataset_id}): {e}")
        return None


def update_unified_data_source_dataset_catalog(
    *,
    dataset_id: str,
    publish_status: str | None = None,
    business_domain: str | None = None,
    business_object_type: str | None = None,
    grain: str | None = None,
    schema_name: str | None = None,
    object_name: str | None = None,
    object_type: str | None = None,
    search_text: str | None = None,
    meta: dict | None = None,
) -> dict | None:
    """更新数据集目录业务化字段。"""
    updates: list[str] = []
    params: list[Any] = []
    if publish_status is not None:
        normalized_publish_status = _normalize_catalog_status(
            publish_status,
            allowed=("unpublished", "published", "deprecated"),
            default="unpublished",
        )
        updates.append("publish_status = %s")
        params.append(normalized_publish_status)
    if business_domain is not None:
        updates.append("business_domain = %s")
        params.append(str(business_domain or "").strip())
    if business_object_type is not None:
        updates.append("business_object_type = %s")
        params.append(str(business_object_type or "").strip())
    if grain is not None:
        updates.append("grain = %s")
        params.append(str(grain or "").strip())
    if schema_name is not None:
        updates.append("schema_name = %s")
        params.append(str(schema_name or "").strip())
    if object_name is not None:
        updates.append("object_name = %s")
        params.append(str(object_name or "").strip())
    if object_type is not None:
        updates.append("object_type = %s")
        params.append(str(object_type or "").strip().lower() or "unknown")
    if search_text is not None:
        updates.append("search_text = %s")
        params.append(str(search_text or "").strip())
    if meta is not None:
        updates.append("meta = %s::jsonb")
        params.append(psycopg2.extras.Json(meta))
    if not updates:
        return None

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                params.append(dataset_id)
                cur.execute(
                    f"""
                    UPDATE data_source_datasets
                    SET {", ".join(updates)},
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 data_source_datasets 目录字段失败 (id={dataset_id}): {e}")
        return None


def touch_unified_data_source_dataset_usage(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str,
    increment_by: int = 1,
) -> dict | None:
    """更新数据集最近使用时间与使用次数。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    WITH target AS (
                        SELECT id
                        FROM data_source_datasets
                        WHERE company_id = %s
                          AND data_source_id = %s
                          AND resource_key = %s
                          AND status <> 'deleted'
                        ORDER BY updated_at DESC, created_at DESC
                        LIMIT 1
                    )
                    UPDATE data_source_datasets
                    SET usage_count = usage_count + %s,
                        last_used_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = (SELECT id FROM target)
                    RETURNING {_UNIFIED_DATASET_SELECT_COLUMNS_SQL}
                    """,
                    (company_id, data_source_id, resource_key, max(1, int(increment_by or 1))),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"更新 data_source_datasets 使用统计失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}): {e}"
        )
        return None


def list_unified_rule_binding_requirements(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    status: str | None = "active",
) -> list[dict]:
    """查询规则绑定及其 source/dataset 健康上下文（preflight helper）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT b.id, b.company_id, b.binding_scope, b.binding_code, b.binding_name,
                           b.data_source_id, b.resource_key, b.role_code, b.is_required, b.priority,
                           b.filter_config, b.mapping_config, b.status AS binding_status,
                           b.created_at AS binding_created_at, b.updated_at AS binding_updated_at,
                           s.name AS source_name, s.source_kind, s.provider_code,
                           s.status AS source_status, s.is_enabled AS source_enabled,
                           s.health_status AS source_health_status, s.last_checked_at AS source_last_checked_at,
                           s.last_error_message AS source_last_error_message,
                           d.id AS dataset_id, d.dataset_code, d.dataset_name, d.dataset_kind, d.origin_type,
                           d.status AS dataset_status, d.is_enabled AS dataset_enabled,
                           d.health_status AS dataset_health_status, d.last_checked_at AS dataset_last_checked_at,
                           d.last_sync_at AS dataset_last_sync_at, d.last_error_message AS dataset_last_error_message
                    FROM dataset_bindings b
                    LEFT JOIN data_sources s
                      ON s.id = b.data_source_id
                    LEFT JOIN LATERAL (
                        SELECT id, dataset_code, dataset_name, dataset_kind, origin_type,
                               status, is_enabled, health_status, last_checked_at, last_sync_at, last_error_message
                        FROM data_source_datasets d0
                        WHERE d0.data_source_id = b.data_source_id
                          AND d0.resource_key = b.resource_key
                          AND d0.status <> 'deleted'
                        ORDER BY d0.updated_at DESC, d0.created_at DESC
                        LIMIT 1
                    ) d ON true
                    WHERE b.company_id = %s
                      AND b.binding_scope = %s
                      AND b.binding_code = %s
                """
                params: list[Any] = [company_id, binding_scope, binding_code]
                if status:
                    sql += " AND b.status = %s"
                    params.append(status)
                sql += " ORDER BY b.priority ASC, b.updated_at DESC"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询规则绑定 preflight 上下文失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}, status={status}): {e}"
        )
        return []


def evaluate_unified_rule_binding_preflight(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    stale_after_minutes: int = 24 * 60,
) -> dict[str, Any]:
    """评估规则绑定可用性（preflight helper）。"""
    bindings = list_unified_rule_binding_requirements(
        company_id=company_id,
        binding_scope=binding_scope,
        binding_code=binding_code,
        status="active",
    )
    issues: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for item in bindings:
        role_code = str(item.get("role_code") or "")
        source_id = str(item.get("data_source_id") or "")
        resource_key = str(item.get("resource_key") or "default")
        is_required = bool(item.get("is_required", True))

        source_status = str(item.get("source_status") or "")
        source_enabled = bool(item.get("source_enabled", False))
        source_health_status = str(item.get("source_health_status") or "unknown")
        source_name = str(item.get("source_name") or source_id or "未知数据源")

        dataset_id = str(item.get("dataset_id") or "")
        dataset_name = str(item.get("dataset_name") or item.get("dataset_code") or resource_key)
        dataset_status = str(item.get("dataset_status") or "")
        dataset_enabled = bool(item.get("dataset_enabled", False))
        dataset_health_status = str(item.get("dataset_health_status") or "unknown")

        def _append_issue(code: str, level: str, message: str) -> None:
            issues.append(
                {
                    "code": code,
                    "level": level,
                    "message": message,
                    "binding_scope": binding_scope,
                    "binding_code": binding_code,
                    "role_code": role_code,
                    "is_required": is_required,
                    "data_source_id": source_id,
                    "resource_key": resource_key,
                    "dataset_id": dataset_id,
                }
            )

        if not source_id:
            _append_issue("source_missing", "error", f"角色 {role_code} 未绑定数据源")
            continue

        if source_status != "active" or not source_enabled:
            _append_issue("source_disabled", "error", f"{source_name} 未启用或状态非 active")
            continue

        if source_health_status in {"error", "auth_expired", "disabled"}:
            _append_issue("source_unhealthy", "error", f"{source_name} 当前健康状态为 {source_health_status}")
            continue

        if not dataset_id:
            _append_issue("dataset_missing", "error", f"{source_name} 的资源 {resource_key} 未配置数据集目录")
            continue

        if dataset_status != "active" or not dataset_enabled:
            _append_issue("dataset_disabled", "error", f"数据集 {dataset_name} 未启用或状态非 active")
            continue

        if dataset_health_status in {"error", "auth_expired", "disabled"}:
            _append_issue("dataset_unhealthy", "error", f"数据集 {dataset_name} 当前健康状态为 {dataset_health_status}")
            continue

        last_sync_at = item.get("dataset_last_sync_at")
        if isinstance(last_sync_at, str) and last_sync_at:
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_at.replace("Z", "+00:00"))
                stale_threshold = now - timedelta(minutes=max(1, stale_after_minutes))
                if last_sync_dt.tzinfo is None:
                    last_sync_dt = last_sync_dt.replace(tzinfo=timezone.utc)
                if last_sync_dt < stale_threshold:
                    _append_issue(
                        "dataset_stale",
                        "warn",
                        f"数据集 {dataset_name} 最近同步时间 {last_sync_at}，已超过 {stale_after_minutes} 分钟",
                    )
            except Exception:
                _append_issue("dataset_sync_time_invalid", "warn", f"数据集 {dataset_name} 最近同步时间格式无效")

    blocking_issues = [item for item in issues if item.get("level") == "error"]
    return {
        "ready": len(blocking_issues) == 0,
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking_issues),
        "issues": issues,
        "requirements": bindings,
    }


def upsert_unified_data_source_credentials(
    *,
    company_id: str,
    data_source_id: str,
    credential_type: str = "default",
    credential_payload: dict | None = None,
    extra: dict | None = None,
) -> dict | None:
    """创建或更新数据源凭证（密封存储）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_credentials (
                        company_id, data_source_id, credential_type,
                        secret_payload, secret_version, secret_updated_at, extra
                    ) VALUES (
                        %s, %s, %s,
                        %s, 1, CURRENT_TIMESTAMP, %s::jsonb
                    )
                    ON CONFLICT (data_source_id, credential_type)
                    DO UPDATE SET
                        secret_payload = EXCLUDED.secret_payload,
                        secret_version = data_source_credentials.secret_version + 1,
                        secret_updated_at = CURRENT_TIMESTAMP,
                        extra = EXCLUDED.extra,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, data_source_id, credential_type,
                              secret_payload, secret_version, secret_updated_at, extra,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        credential_type,
                        _seal_json_payload(credential_payload),
                        psycopg2.extras.Json(extra or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                result["credential_payload"] = {}
                return result
    except Exception as e:
        logger.error(
            f"写入 data_source_credentials 失败 (company_id={company_id}, data_source_id={data_source_id}, credential_type={credential_type}): {e}"
        )
        return None


def get_unified_data_source_credentials(
    *,
    data_source_id: str,
    credential_type: str = "default",
    include_secret: bool = False,
) -> dict | None:
    """查询数据源凭证。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, credential_type,
                           secret_payload, secret_version, secret_updated_at, extra,
                           created_at, updated_at
                    FROM data_source_credentials
                    WHERE data_source_id = %s
                      AND credential_type = %s
                    LIMIT 1
                    """,
                    (data_source_id, credential_type),
                )
                row = cur.fetchone()
                if not row:
                    return None
                result = _normalize_record(dict(row))
                if include_secret:
                    result["credential_payload"] = _open_json_payload(str(result.get("secret_payload") or ""))
                else:
                    result["credential_payload"] = {}
                result["secret_payload"] = ""
                return result
    except Exception as e:
        logger.error(
            f"查询 data_source_credentials 失败 (data_source_id={data_source_id}, credential_type={credential_type}): {e}"
        )
        return None


def upsert_unified_data_source_config(
    *,
    company_id: str,
    data_source_id: str,
    config_type: str,
    config: dict | None = None,
    is_active: bool = True,
) -> dict | None:
    """写入数据源配置；当 is_active=true 时将同类型旧配置置为非激活。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if is_active:
                    cur.execute(
                        """
                        UPDATE data_source_configs
                        SET is_active = false,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE data_source_id = %s
                          AND config_type = %s
                          AND is_active = true
                        """,
                        (data_source_id, config_type),
                    )
                cur.execute(
                    """
                    INSERT INTO data_source_configs (
                        company_id, data_source_id, config_type, config, version, is_active
                    ) VALUES (
                        %s, %s, %s, %s::jsonb,
                        COALESCE((
                            SELECT MAX(version) + 1
                            FROM data_source_configs
                            WHERE data_source_id = %s
                              AND config_type = %s
                        ), 1),
                        %s
                    )
                    RETURNING id, company_id, data_source_id, config_type, config, version, is_active,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        config_type,
                        psycopg2.extras.Json(config or {}),
                        data_source_id,
                        config_type,
                        is_active,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 data_source_configs 失败 (company_id={company_id}, data_source_id={data_source_id}, config_type={config_type}): {e}"
        )
        return None


def get_unified_data_source_config(
    *,
    data_source_id: str,
    config_type: str,
    active_only: bool = True,
) -> dict | None:
    """查询数据源配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if active_only:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, config_type, config, version, is_active,
                               created_at, updated_at
                        FROM data_source_configs
                        WHERE data_source_id = %s
                          AND config_type = %s
                          AND is_active = true
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (data_source_id, config_type),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, config_type, config, version, is_active,
                               created_at, updated_at
                        FROM data_source_configs
                        WHERE data_source_id = %s
                          AND config_type = %s
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (data_source_id, config_type),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 data_source_configs 失败 (data_source_id={data_source_id}, config_type={config_type}, active_only={active_only}): {e}"
        )
        return None


def create_unified_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    trigger_mode: str = "manual",
    resource_key: str = "default",
    idempotency_key: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    request_payload: dict | None = None,
    checkpoint_before: dict | None = None,
) -> dict | None:
    """创建同步任务。

    采集任务的幂等在 dataset_collection_records 数据层处理；任务层每次触发都应保留
    一条独立审计记录，避免手动采集/重新对账复用旧任务导致状态不可追踪。
    """
    stored_idempotency_key = str(idempotency_key or "").strip() or None
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_jobs (
                        company_id, data_source_id, trigger_mode, resource_key, idempotency_key,
                        window_start, window_end, request_payload, checkpoint_before
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, trigger_mode, resource_key,
                              window_start, window_end, idempotency_key, job_status,
                              request_payload, checkpoint_before, checkpoint_after,
                              active_snapshot_id, published_snapshot_id, current_attempt,
                              error_message, started_at, completed_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        trigger_mode,
                        resource_key,
                        stored_idempotency_key,
                        window_start,
                        window_end,
                        psycopg2.extras.Json(request_payload or {}),
                        psycopg2.extras.Json(checkpoint_before or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 sync_jobs 失败 (company_id={company_id}, data_source_id={data_source_id}, idempotency_key={stored_idempotency_key}): {e}"
        )
        return None


def get_unified_sync_job_by_id(sync_job_id: str) -> dict | None:
    """按 id 查询同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, next_retry_at, browser_fail_reason, max_attempts,
                           is_verification, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (sync_job_id,),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 sync_jobs 失败 (id={sync_job_id}): {e}")
        return None


def find_unified_sync_job_by_idempotency_key(
    *,
    company_id: str,
    data_source_id: str,
    idempotency_key: str,
) -> dict | None:
    """按幂等键查询同步任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, next_retry_at, browser_fail_reason, max_attempts,
                           is_verification, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND idempotency_key = %s
                    LIMIT 1
                    """,
                    (company_id, data_source_id, idempotency_key),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 sync_jobs 幂等键失败 (company_id={company_id}, data_source_id={data_source_id}, idempotency_key={idempotency_key}): {e}"
        )
        return None


def list_unified_sync_jobs(
    *,
    company_id: str,
    data_source_id: str | None = None,
    job_status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """查询同步任务列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, next_retry_at, browser_fail_reason, max_attempts,
                           is_verification, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if job_status:
                    sql += " AND job_status = %s"
                    params.append(job_status)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 sync_jobs 列表失败 (company_id={company_id}, data_source_id={data_source_id}, job_status={job_status}): {e}"
        )
        return []


def get_latest_unified_sync_job_attempts(
    *,
    company_id: str,
    sync_job_ids: list[str],
) -> dict[str, dict]:
    """按 sync_job_id 查询最近一次任务尝试，返回 sync_job_id -> attempt 的映射。"""
    normalized_ids = [str(item).strip() for item in sync_job_ids if str(item).strip()]
    if not normalized_ids:
        return {}

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (sync_job_id)
                           id, company_id, sync_job_id, attempt_no, attempt_status,
                           started_at, finished_at, error_message, metrics,
                           checkpoint_before, checkpoint_after, created_at, updated_at
                    FROM sync_job_attempts
                    WHERE company_id = %s
                      AND sync_job_id = ANY(%s::uuid[])
                    ORDER BY sync_job_id, attempt_no DESC, created_at DESC
                    """,
                    (company_id, normalized_ids),
                )
                rows = cur.fetchall()
                attempts = [_normalize_record(dict(row)) for row in rows]
                return {str(item.get("sync_job_id") or ""): item for item in attempts if item.get("sync_job_id")}
    except Exception as e:
        logger.error(
            f"查询 sync_job_attempts 最近记录失败 (company_id={company_id}, sync_job_ids={normalized_ids}): {e}"
        )
        return {}


def create_unified_sync_job_attempt(
    *,
    company_id: str,
    sync_job_id: str,
    attempt_no: int,
    checkpoint_before: dict | None = None,
) -> dict | None:
    """创建同步任务尝试记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_job_attempts (
                        company_id, sync_job_id, attempt_no, attempt_status, checkpoint_before
                    ) VALUES (
                        %s, %s, %s, 'running', %s::jsonb
                    )
                    RETURNING id, company_id, sync_job_id, attempt_no, attempt_status,
                              started_at, finished_at, error_message, metrics,
                              checkpoint_before, checkpoint_after, created_at, updated_at
                    """,
                    (
                        company_id,
                        sync_job_id,
                        attempt_no,
                        psycopg2.extras.Json(checkpoint_before or {}),
                    ),
                )
                row = cur.fetchone()
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET current_attempt = %s,
                        job_status = 'running',
                        started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (attempt_no, sync_job_id),
                )
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 sync_job_attempts 失败 (sync_job_id={sync_job_id}, attempt_no={attempt_no}): {e}")
        return None


def update_unified_sync_job_attempt(
    *,
    attempt_id: str,
    attempt_status: str,
    error_message: str = "",
    metrics: dict | None = None,
    checkpoint_after: dict | None = None,
    finish_attempt: bool = True,
) -> dict | None:
    """更新同步任务尝试结果。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_job_attempts
                    SET attempt_status = %s,
                        error_message = %s,
                        metrics = %s::jsonb,
                        checkpoint_after = %s::jsonb,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, sync_job_id, attempt_no, attempt_status,
                              started_at, finished_at, error_message, metrics,
                              checkpoint_before, checkpoint_after, created_at, updated_at
                    """,
                    (
                        attempt_status,
                        error_message,
                        psycopg2.extras.Json(metrics or {}),
                        psycopg2.extras.Json(checkpoint_after or {}),
                        finish_attempt,
                        attempt_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_job_attempts 失败 (attempt_id={attempt_id}, status={attempt_status}): {e}")
        return None


def update_unified_sync_job_status(
    *,
    sync_job_id: str,
    job_status: str,
    error_message: str = "",
    checkpoint_after: dict | None = None,
    finish_job: bool = False,
) -> dict | None:
    """更新同步任务状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET job_status = %s,
                        error_message = %s,
                        checkpoint_after = CASE
                            WHEN %s::jsonb = '{}'::jsonb THEN checkpoint_after
                            ELSE %s::jsonb
                        END,
                        completed_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE completed_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING id, company_id, data_source_id, trigger_mode, resource_key,
                              window_start, window_end, idempotency_key, job_status,
                              request_payload, checkpoint_before, checkpoint_after,
                              active_snapshot_id, published_snapshot_id, current_attempt,
                              error_message, started_at, completed_at, created_at, updated_at
                    """,
                    (
                        job_status,
                        error_message,
                        psycopg2.extras.Json(checkpoint_after or {}),
                        psycopg2.extras.Json(checkpoint_after or {}),
                        finish_job,
                        sync_job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 sync_jobs 状态失败 (sync_job_id={sync_job_id}, status={job_status}): {e}")
        return None


def get_latest_source_dataset_checkpoint(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str,
) -> dict:
    """读取某数据源+资源最近一次成功同步后的 checkpoint。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT checkpoint_after
                    FROM sync_jobs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND resource_key = %s
                      AND job_status = 'success'
                      AND checkpoint_after IS NOT NULL
                      AND checkpoint_after <> '{}'::jsonb
                    ORDER BY completed_at DESC NULLS LAST, updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    (company_id, data_source_id, resource_key),
                )
                row = cur.fetchone()
                if not row:
                    return {}
                checkpoint = row.get("checkpoint_after")
                return checkpoint if isinstance(checkpoint, dict) else {}
    except Exception as e:
        logger.error(
            f"查询最近同步 checkpoint 失败 (company_id={company_id}, data_source_id={data_source_id}, resource_key={resource_key}): {e}"
        )
        return {}


def find_inflight_dataset_collection_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    resource_key: str,
    biz_date: str,
) -> dict | None:
    """查找同一数据集业务日期正在执行的采集任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND resource_key = %s
                      AND job_status IN ('pending', 'running')
                      AND request_payload ->> 'dataset_id' = %s
                      AND request_payload ->> 'biz_date' = %s
                      AND updated_at >= CURRENT_TIMESTAMP - INTERVAL '15 minutes'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (company_id, data_source_id, resource_key, dataset_id, biz_date),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            "查询进行中采集任务失败 "
            f"(company_id={company_id}, data_source_id={data_source_id}, dataset_id={dataset_id}, biz_date={biz_date}): {e}"
        )
        return None


def find_recent_success_dataset_collection_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    resource_key: str,
    biz_date: str,
    ttl_seconds: int,
) -> dict | None:
    """查找 TTL 内同一数据集业务日期最近一次成功采集任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND resource_key = %s
                      AND job_status = 'success'
                      AND request_payload ->> 'dataset_id' = %s
                      AND request_payload ->> 'biz_date' = %s
                      AND completed_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                    ORDER BY completed_at DESC NULLS LAST, updated_at DESC, created_at DESC
                    LIMIT 1
                    """,
                    (
                        company_id,
                        data_source_id,
                        resource_key,
                        dataset_id,
                        biz_date,
                        max(1, int(ttl_seconds or 1)),
                    ),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            "查询 TTL 内成功采集任务失败 "
            f"(company_id={company_id}, data_source_id={data_source_id}, dataset_id={dataset_id}, biz_date={biz_date}): {e}"
        )
        return None


def create_or_reuse_dataset_collection_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    trigger_mode: str,
    resource_key: str,
    dataset_id: str,
    biz_date: str,
    ttl_seconds: int,
    idempotency_key: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    request_payload: dict | None = None,
    checkpoint_before: dict | None = None,
    inflight_ttl_seconds: int = 900,
) -> dict:
    """在同一数据库临界区内复用或创建数据集采集任务。"""
    stored_idempotency_key = str(idempotency_key or "").strip() or None
    lock_key = f"dataset_collection:{company_id}:{data_source_id}:{dataset_id}:{resource_key}:{biz_date}"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (lock_key,))
                cur.execute(
                    """
                    SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                           window_start, window_end, idempotency_key, job_status,
                           request_payload, checkpoint_before, checkpoint_after,
                           active_snapshot_id, published_snapshot_id, current_attempt,
                           error_message, started_at, completed_at, created_at, updated_at
                    FROM sync_jobs
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND resource_key = %s
                      AND job_status IN ('pending', 'running')
                      AND request_payload ->> 'dataset_id' = %s
                      AND request_payload ->> 'biz_date' = %s
                      AND updated_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (
                        company_id,
                        data_source_id,
                        resource_key,
                        dataset_id,
                        biz_date,
                        max(1, int(inflight_ttl_seconds or 1)),
                    ),
                )
                row = cur.fetchone()
                if row:
                    conn.commit()
                    return {
                        "job": _normalize_record(dict(row)),
                        "reused": True,
                        "reuse_reason": "inflight",
                    }

                if int(ttl_seconds or 0) > 0:
                    cur.execute(
                        """
                        SELECT id, company_id, data_source_id, trigger_mode, resource_key,
                               window_start, window_end, idempotency_key, job_status,
                               request_payload, checkpoint_before, checkpoint_after,
                               active_snapshot_id, published_snapshot_id, current_attempt,
                               error_message, started_at, completed_at, created_at, updated_at
                        FROM sync_jobs
                        WHERE company_id = %s
                          AND data_source_id = %s
                          AND resource_key = %s
                          AND job_status = 'success'
                          AND request_payload ->> 'dataset_id' = %s
                          AND request_payload ->> 'biz_date' = %s
                          AND completed_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                        ORDER BY completed_at DESC NULLS LAST, updated_at DESC, created_at DESC
                        LIMIT 1
                        """,
                        (
                            company_id,
                            data_source_id,
                            resource_key,
                            dataset_id,
                            biz_date,
                            max(1, int(ttl_seconds or 1)),
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        conn.commit()
                        return {
                            "job": _normalize_record(dict(row)),
                            "reused": True,
                            "reuse_reason": "recent_success_ttl",
                        }

                cur.execute(
                    """
                    INSERT INTO sync_jobs (
                        company_id, data_source_id, trigger_mode, resource_key, idempotency_key,
                        window_start, window_end, request_payload, checkpoint_before
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, trigger_mode, resource_key,
                              window_start, window_end, idempotency_key, job_status,
                              request_payload, checkpoint_before, checkpoint_after,
                              active_snapshot_id, published_snapshot_id, current_attempt,
                              error_message, started_at, completed_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        trigger_mode,
                        resource_key,
                        stored_idempotency_key,
                        window_start,
                        window_end,
                        psycopg2.extras.Json(request_payload or {}),
                        psycopg2.extras.Json(checkpoint_before or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return {
                    "job": _normalize_record(dict(row)) if row else None,
                    "reused": False,
                    "reuse_reason": "",
                }
    except Exception as e:
        logger.error(
            "复用或创建数据集采集任务失败 "
            f"(company_id={company_id}, data_source_id={data_source_id}, dataset_id={dataset_id}, biz_date={biz_date}): {e}"
        )
        return {"job": None, "reused": False, "reuse_reason": "", "error": str(e)}


def claim_next_browser_sync_job(*, agent_id: str = "", agent_max_concurrency: int = 2) -> dict | None:
    """原子领取下一条待执行的 browser_playbook sync job,带 enrich。

    返回的 dict 在标准 sync_jobs 字段之外,额外携带 browser-agent 执行所需的所有运行时上下文:
    shop_id / playbook_id / playbook_version / playbook_body / runtime_profile_ref /
    egress_group / credential_ref / browser_binding。browser-agent 据此构造 RUN_PLAYBOOK 消息,
    不再依赖 request_payload 自带 shop_id 或 playbook_body。

    过滤条件:
      - sync_job pending
      - data_source.source_kind = 'browser_playbook',且 active + is_enabled
      - shop_runtime_bindings.agent_id = :agent_id
      - verification 允许重新领取登录态异常的 binding,便于人工/凭证重验;
        生产采集要求 profile_status=active 且 playbook_status=ok(健康门下沉到 claim 层)
      - 当前 agent in-flight 浏览器任务数 < agent_max_concurrency(DB 层并发硬保护)
      - 已到 next_retry_at(为 NULL 视为可立即领取)
      - playbook.status='active'(canary 版本路由暂未实现,见 Deferred)
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    WITH running_for_agent AS (
                        SELECT COUNT(*) AS running_count
                        FROM sync_jobs running_jobs
                        JOIN data_sources running_ds ON running_ds.id = running_jobs.data_source_id
                        JOIN shop_runtime_bindings running_srb
                          ON running_srb.company_id = running_jobs.company_id
                         AND running_srb.data_source_id = running_jobs.data_source_id
                        WHERE running_jobs.job_status = 'running'
                          AND running_ds.source_kind = 'browser_playbook'
                          AND running_srb.agent_id = %s
                    ),
                    claimed AS (
                        SELECT sync_jobs.id,
                               jsonb_build_object(
                                   'shop_id', srb.shop_id,
                                   'agent_id', srb.agent_id,
                                   'playbook_id', srb.playbook_id,
                                   'runtime_profile_ref', COALESCE(srb.runtime_profile_ref, ''),
                                   'egress_group', COALESCE(srb.egress_group, ''),
                                   'credential_ref', COALESCE(srb.credential_ref, ''),
                                   'profile_status', srb.profile_status,
                                   'playbook_status', srb.playbook_status
                               ) AS browser_binding,
                               srb.shop_id,
                               srb.playbook_id,
                               COALESCE(srb.runtime_profile_ref, '') AS runtime_profile_ref,
                               COALESCE(srb.egress_group, '') AS egress_group,
                               COALESCE(srb.credential_ref, '') AS credential_ref,
                               p.version AS playbook_version,
                               p.playbook_body
                        FROM sync_jobs
                        CROSS JOIN running_for_agent
                        JOIN data_sources ds ON ds.id = sync_jobs.data_source_id
                        JOIN shop_runtime_bindings srb
                          ON srb.company_id = sync_jobs.company_id
                         AND srb.data_source_id = sync_jobs.data_source_id
                        JOIN playbooks p
                          ON p.company_id = sync_jobs.company_id
                         AND p.playbook_id = srb.playbook_id
                         AND (
                              (sync_jobs.is_verification = TRUE AND p.status IN ('draft', 'active'))
                              OR (sync_jobs.is_verification = FALSE AND p.status = 'active')
                         )
                        WHERE sync_jobs.job_status = 'pending'
                          AND ds.source_kind = 'browser_playbook'
                          AND ds.status = 'active'
                          AND ds.is_enabled = TRUE
                          AND srb.agent_id = %s
                          -- verification dry-run 允许重验登录态异常 binding;
                          -- 生产采集要求 binding 完全健康(profile=active AND playbook=ok)。
                          AND (
                              (sync_jobs.is_verification = TRUE AND srb.profile_status IN ('verifying', 'active', 'needs_reauth', 'risk_blocked'))
                              OR (sync_jobs.is_verification = FALSE AND srb.profile_status = 'active' AND srb.playbook_status = 'ok')
                          )
                          AND running_for_agent.running_count < %s
                          AND (sync_jobs.next_retry_at IS NULL OR sync_jobs.next_retry_at <= CURRENT_TIMESTAMP)
                        ORDER BY sync_jobs.created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE sync_jobs
                    SET job_status = 'running',
                        started_at = CURRENT_TIMESTAMP,
                        current_attempt = COALESCE(current_attempt, 0) + 1,
                        updated_at = CURRENT_TIMESTAMP
                    FROM claimed
                    WHERE sync_jobs.id = claimed.id
                    RETURNING sync_jobs.id, sync_jobs.company_id, sync_jobs.data_source_id,
                              sync_jobs.trigger_mode, sync_jobs.resource_key,
                              sync_jobs.window_start, sync_jobs.window_end,
                              sync_jobs.idempotency_key, sync_jobs.job_status,
                              sync_jobs.request_payload, sync_jobs.checkpoint_before,
                              sync_jobs.checkpoint_after, sync_jobs.active_snapshot_id,
                              sync_jobs.published_snapshot_id, sync_jobs.current_attempt,
                              sync_jobs.error_message, sync_jobs.started_at,
                              sync_jobs.completed_at, sync_jobs.created_at, sync_jobs.updated_at,
                              claimed.browser_binding, claimed.shop_id, claimed.playbook_id,
                              claimed.playbook_version, claimed.playbook_body,
                              claimed.runtime_profile_ref, claimed.egress_group, claimed.credential_ref
                    """,
                    (agent_id, agent_id, agent_max_concurrency),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"领取 browser_playbook sync_job 失败: {e}")
        return None


def insert_browser_verification_sync_job(
    *,
    company_id: str,
    data_source_id: str,
    resource_key: str,
    request_payload: dict,
    idempotency_key: str | None = None,
) -> dict | None:
    """Create a one-off browser verification sync_job for playbook registration.

    Unlike production triggers, this never reuses an inflight or recently-successful job:
    verification is an explicit "run this playbook + credential combo end-to-end before we
    let it go live" action. The resulting sync_job is the same shape as any browser sync_job
    except for ``is_verification=true``, which lets ``claim_next_browser_sync_job`` pull it
    even when the shop binding is still ``profile_status='verifying'``.
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO sync_jobs (
                        company_id, data_source_id, trigger_mode, resource_key, idempotency_key,
                        request_payload, is_verification
                    ) VALUES (
                        %s, %s, 'manual', %s, %s,
                        %s::jsonb, TRUE
                    )
                    RETURNING id, company_id, data_source_id, trigger_mode, resource_key,
                              window_start, window_end, idempotency_key, job_status,
                              request_payload, checkpoint_before, checkpoint_after,
                              active_snapshot_id, published_snapshot_id, current_attempt,
                              error_message, started_at, completed_at, created_at, updated_at,
                              is_verification
                    """,
                    (
                        company_id,
                        data_source_id,
                        resource_key,
                        str(idempotency_key or "").strip() or None,
                        psycopg2.extras.Json(request_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"insert_browser_verification_sync_job 失败: {e}")
        return None


def activate_browser_playbook_and_binding(
    *,
    company_id: str,
    playbook_id: str,
    version: str,
    data_source_id: str,
) -> dict:
    """Atomically flip a draft playbook + verifying binding to fully active.

    Called by ``data_source_finalize_browser_playbook_registration`` after the verification
    sync_job ends in ``success``. Resets ``cron_pause_reason`` so the binding immediately
    becomes eligible for production claim.
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE playbooks
                    SET status = 'active',
                        approved_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND playbook_id = %s
                      AND version = %s
                      AND status IN ('draft', 'replayed', 'approved')
                    RETURNING id, playbook_id, version, status
                    """,
                    (company_id, playbook_id, version),
                )
                playbook_row = cur.fetchone()
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings
                    SET profile_status = 'active',
                        playbook_status = 'ok',
                        cron_pause_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND data_source_id = %s
                      AND profile_status = 'verifying'
                    RETURNING id, company_id, data_source_id, shop_id, profile_status, playbook_status
                    """,
                    (company_id, data_source_id),
                )
                binding_row = cur.fetchone()
                conn.commit()
                return {
                    "playbook": _normalize_record(dict(playbook_row)) if playbook_row else None,
                    "binding": _normalize_record(dict(binding_row)) if binding_row else None,
                }
    except Exception as e:
        logger.error(f"activate_browser_playbook_and_binding 失败: {e}")
        return {"playbook": None, "binding": None}


def get_shop_runtime_binding_for_source(*, company_id: str, data_source_id: str) -> dict:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM shop_runtime_bindings
                    WHERE company_id = %s
                      AND data_source_id = %s
                    LIMIT 1
                    """,
                    (company_id, data_source_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else {}
    except Exception as e:
        logger.error(
            f"查询 shop_runtime_bindings 失败 (company_id={company_id}, data_source_id={data_source_id}): {e}"
        )
        return {}


def get_active_playbook(*, company_id: str, playbook_id: str) -> dict:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM playbooks
                    WHERE company_id = %s
                      AND playbook_id = %s
                      AND status = 'active'
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (company_id, playbook_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else {}
    except Exception as e:
        logger.error(f"查询 playbooks 失败 (company_id={company_id}, playbook_id={playbook_id}): {e}")
        return {}


def mark_browser_sync_job_success(*, sync_job_id: str, summary: dict) -> dict | None:
    row = update_unified_sync_job_status(
        sync_job_id=sync_job_id,
        job_status="success",
        error_message="",
        checkpoint_after={"browser_collection_summary": summary or {}},
        finish_job=True,
    )
    if row:
        mark_browser_binding_collection_seen(sync_job_id=sync_job_id)
    return row


def mark_browser_binding_collection_seen(*, sync_job_id: str) -> int:
    """Record the latest successful browser collection timestamp on the shop binding."""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings b
                    SET last_collection_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    FROM sync_jobs s
                    WHERE s.id = %s
                      AND b.company_id = s.company_id
                      AND b.data_source_id = s.data_source_id
                    """,
                    (sync_job_id,),
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"mark_browser_binding_collection_seen 失败: {e}")
        return 0


def upsert_browser_agent_heartbeat(
    *,
    company_id: str,
    agent_id: str,
    hostname: str = "",
    version: str = "",
    capabilities: dict[str, Any] | None = None,
) -> dict | None:
    """Upsert browser-agent heartbeat, marking the collection node online."""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO agents (
                        company_id, agent_id, hostname, version, status,
                        capabilities, last_heartbeat_at
                    ) VALUES (
                        %s, %s, %s, %s, 'online',
                        %s::jsonb, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (company_id, agent_id)
                    DO UPDATE SET
                        hostname = EXCLUDED.hostname,
                        version = EXCLUDED.version,
                        status = 'online',
                        capabilities = EXCLUDED.capabilities,
                        last_heartbeat_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """,
                    (
                        company_id,
                        agent_id,
                        hostname,
                        version,
                        json.dumps(capabilities or {}, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"upsert_browser_agent_heartbeat 失败 (company_id={company_id}, agent_id={agent_id}): {e}")
        return None


def mark_browser_sync_job_failed(
    *,
    sync_job_id: str,
    error_message: str,
    fail_reason: str,
    retryable: bool = False,
    max_attempts: int = 3,
    retry_delay_seconds: int = 1800,
) -> dict | None:
    """Terminal or transient browser sync_job failure handler.

    Behavior:
    - Always writes browser_fail_reason as the canonical code (AUTH_EXPIRED, etc.).
    - Normalizes error_message to ``"{fail_reason}: {body}"`` exactly once. If the incoming
      message already has the correct prefix, no double prefix is added.
    - If retryable=True AND current_attempt < max_attempts: job goes back to ``pending`` with
      ``next_retry_at = now + retry_delay_seconds`` and ``completed_at`` cleared. This lets the
      claim SQL pick it up after the backoff.
    - Otherwise the job is terminal ``failed`` and ``apply_browser_binding_failure_transition``
      is called to flip shop_runtime_bindings into the right pause state.
    - Binding transition is NOT triggered for transient retries — the binding stays healthy and
      the shop continues to receive cron triggers.
    """
    canonical = str(fail_reason or "OTHER").strip().upper() or "OTHER"
    raw_message = str(error_message or "").strip()
    prefix = f"{canonical}: "
    if raw_message.startswith(prefix):
        prefixed_error = raw_message
    elif raw_message:
        prefixed_error = f"{canonical}: {raw_message}"
    else:
        prefixed_error = canonical

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET job_status = CASE
                            WHEN %s = TRUE AND COALESCE(current_attempt, 0) < %s THEN 'pending'
                            ELSE 'failed'
                        END,
                        browser_fail_reason = %s,
                        error_message = %s,
                        max_attempts = GREATEST(COALESCE(max_attempts, 3), %s),
                        next_retry_at = CASE
                            WHEN %s = TRUE AND COALESCE(current_attempt, 0) < %s THEN CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                            ELSE NULL
                        END,
                        completed_at = CASE
                            WHEN %s = TRUE AND COALESCE(current_attempt, 0) < %s THEN NULL
                            ELSE CURRENT_TIMESTAMP
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        bool(retryable), int(max_attempts),
                        canonical,
                        prefixed_error,
                        int(max_attempts),
                        bool(retryable), int(max_attempts), int(retry_delay_seconds),
                        bool(retryable), int(max_attempts),
                        sync_job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
    except Exception as e:
        logger.error(f"mark_browser_sync_job_failed 失败: {e}")
        return None

    normalized = _normalize_record(dict(row)) if row else None
    if normalized and str(normalized.get("job_status") or "") == "failed":
        try:
            apply_browser_binding_failure_transition(
                sync_job_id=sync_job_id, fail_reason=canonical
            )
        except Exception as e:
            logger.error(f"apply_browser_binding_failure_transition 调用失败: {e}")
    return normalized


def apply_browser_binding_failure_transition(*, sync_job_id: str, fail_reason: str) -> int:
    """根据 fail_reason 切换 shop_runtime_bindings 的状态字段。

    映射:
      - AUTH_EXPIRED -> profile_status='needs_reauth', cron_pause_reason='AUTH_EXPIRED'
      - RISK_VERIFICATION -> profile_status='risk_blocked', cron_pause_reason='RISK_VERIFICATION'
      - PAGE_CHANGED -> playbook_status='stale', cron_pause_reason='PAGE_CHANGED'
      - 其他 fail_reason 不动 binding

    仅在 sync_job 进入最终 failed 状态时由 ``mark_browser_sync_job_failed`` 调用,
    transient retry(reschedule 到 pending)不调用。
    """
    canonical = str(fail_reason or "").strip().upper()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings b
                    SET profile_status = CASE
                            WHEN %s = 'AUTH_EXPIRED' THEN 'needs_reauth'
                            WHEN %s = 'RISK_VERIFICATION' THEN 'risk_blocked'
                            ELSE b.profile_status
                        END,
                        playbook_status = CASE
                            WHEN %s = 'PAGE_CHANGED' THEN 'stale'
                            ELSE b.playbook_status
                        END,
                        cron_pause_reason = CASE
                            WHEN %s IN ('AUTH_EXPIRED', 'RISK_VERIFICATION', 'PAGE_CHANGED') THEN %s
                            ELSE b.cron_pause_reason
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    FROM sync_jobs s
                    WHERE s.id = %s
                      AND b.company_id = s.company_id
                      AND b.data_source_id = s.data_source_id
                    """,
                    (canonical, canonical, canonical, canonical, canonical, sync_job_id),
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"apply_browser_binding_failure_transition 失败: {e}")
        return 0


def upsert_playbook(
    *,
    company_id: str,
    playbook_id: str,
    version: str,
    title: str,
    playbook_body: dict,
    description: str = "",
    target: dict | None = None,
    params_schema: dict | None = None,
    status: str = "active",
    schema_check_result: dict | None = None,
    replay_result: dict | None = None,
    sample_data_path: str = "",
    transcript_path: str = "",
    canary_shop_ids: list | None = None,
    emergency_page_changed: bool = False,
    bypass_canary_reason: str = "",
    created_by: str | None = None,
    approved_by: str | None = None,
) -> dict | None:
    body = dict(playbook_body or {})
    resolved_target = dict(target or body.get("target") or {})
    resolved_params_schema = dict(params_schema or body.get("params_schema") or {})
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO playbooks (
                        company_id, playbook_id, version, title, description,
                        target, params_schema, playbook_body,
                        schema_check_result, replay_result, sample_data_path, transcript_path,
                        canary_shop_ids, emergency_page_changed, bypass_canary_reason,
                        created_by, approved_by, approved_at, status
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s, %s,
                        %s::jsonb, %s, %s,
                        %s, %s, CASE WHEN %s IS NULL THEN NULL ELSE CURRENT_TIMESTAMP END, %s
                    )
                    ON CONFLICT (company_id, playbook_id, version)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        description = EXCLUDED.description,
                        target = EXCLUDED.target,
                        params_schema = EXCLUDED.params_schema,
                        playbook_body = EXCLUDED.playbook_body,
                        schema_check_result = EXCLUDED.schema_check_result,
                        replay_result = EXCLUDED.replay_result,
                        sample_data_path = EXCLUDED.sample_data_path,
                        transcript_path = EXCLUDED.transcript_path,
                        canary_shop_ids = EXCLUDED.canary_shop_ids,
                        emergency_page_changed = EXCLUDED.emergency_page_changed,
                        bypass_canary_reason = EXCLUDED.bypass_canary_reason,
                        approved_by = EXCLUDED.approved_by,
                        approved_at = EXCLUDED.approved_at,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """,
                    (
                        company_id,
                        playbook_id,
                        version,
                        title,
                        description,
                        json.dumps(resolved_target, ensure_ascii=False),
                        json.dumps(resolved_params_schema, ensure_ascii=False),
                        json.dumps(body, ensure_ascii=False),
                        json.dumps(schema_check_result or {}, ensure_ascii=False),
                        json.dumps(replay_result or {}, ensure_ascii=False),
                        sample_data_path,
                        transcript_path,
                        json.dumps(canary_shop_ids or [], ensure_ascii=False),
                        emergency_page_changed,
                        bypass_canary_reason,
                        created_by,
                        approved_by,
                        approved_by,
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"upsert_playbook 失败 (company_id={company_id}, playbook_id={playbook_id}, version={version}): {e}")
        return None


def upsert_shop_runtime_binding(
    *,
    company_id: str,
    data_source_id: str,
    shop_id: str,
    playbook_id: str,
    agent_id: str,
    egress_group: str,
    credential_ref: str,
    profile_status: str = "active",
    playbook_status: str = "ok",
) -> dict | None:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO shop_runtime_bindings (
                        company_id, data_source_id, shop_id, playbook_id, agent_id,
                        egress_group, credential_ref, profile_status, playbook_status, cron_pause_reason
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, NULL
                    )
                    ON CONFLICT (company_id, data_source_id)
                    DO UPDATE SET
                        shop_id = EXCLUDED.shop_id,
                        playbook_id = EXCLUDED.playbook_id,
                        agent_id = EXCLUDED.agent_id,
                        egress_group = EXCLUDED.egress_group,
                        credential_ref = EXCLUDED.credential_ref,
                        profile_status = EXCLUDED.profile_status,
                        playbook_status = EXCLUDED.playbook_status,
                        cron_pause_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """,
                    (
                        company_id,
                        data_source_id,
                        shop_id,
                        playbook_id,
                        agent_id,
                        egress_group,
                        credential_ref,
                        profile_status,
                        playbook_status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"upsert_shop_runtime_binding 失败 (company_id={company_id}, data_source_id={data_source_id}): {e}")
        return None


def clear_page_changed_bindings_for_playbook(*, company_id: str, playbook_id: str) -> int:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings
                    SET playbook_status = 'ok',
                        cron_pause_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND playbook_id = %s
                      AND playbook_status = 'stale'
                      AND cron_pause_reason = 'page_changed'
                    """,
                    (company_id, playbook_id),
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"clear_page_changed_bindings_for_playbook 失败 (company_id={company_id}, playbook_id={playbook_id}): {e}")
        return 0


def mark_recon_run_waiting_data(
    *,
    job_id: str,
    waiting_reason: str,
    waiting_datasets: list[dict],
    collection_job_ids: list[str],
    wait_minutes: int = 90,
) -> dict | None:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'waiting_data',
                        started_at = NULL,
                        next_retry_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes',
                        wait_deadline_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 minute'),
                        waiting_reason = %s,
                        waiting_datasets = %s::jsonb,
                        collection_job_ids = %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                    """,
                    (
                        max(1, int(wait_minutes or 1)),
                        waiting_reason,
                        json.dumps(waiting_datasets or [], ensure_ascii=False),
                        json.dumps(collection_job_ids or [], ensure_ascii=False),
                        job_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_execution_queue.waiting_data 失败 (job_id={job_id}): {e}")
        return None


def requeue_ready_waiting_recon_runs() -> int:
    """Resume waiting-data recon jobs without consuming business retry budget.

    Bumps data_wait_resume_count and last_data_wait_resumed_at so operators can audit how
    many times a recon job had to wait for browser data; current_attempt is left alone so
    retries from real failures stay independent.
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'queued',
                        next_retry_at = NULL,
                        waiting_reason = '',
                        data_wait_resume_count = COALESCE(data_wait_resume_count, 0) + 1,
                        last_data_wait_resumed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'waiting_data'
                      AND next_retry_at <= CURRENT_TIMESTAMP
                      AND jsonb_typeof(collection_job_ids) = 'array'
                      AND jsonb_array_length(collection_job_ids) > 0
                      AND NOT EXISTS (
                          SELECT 1
                          FROM jsonb_array_elements_text(collection_job_ids) job_id
                          JOIN sync_jobs s ON s.id::text = job_id
                          WHERE s.job_status <> 'success'
                      )
                    """
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"requeue_ready_waiting_recon_runs 失败: {e}")
        return 0


def fail_waiting_recon_runs_with_failed_collection_jobs() -> int:
    """Fast-fail waiting_data recon jobs whose referenced browser sync_jobs already failed.

    Without this, a deterministic browser failure (AUTH_EXPIRED / PAGE_CHANGED etc.) would leave
    the recon job in waiting_data until wait_deadline_at (~90min) before surfacing a generic
    "采集未就绪" error. This aggregates the failed sync_jobs' error_message into the recon error
    so operators see the real reason immediately.
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue q
                    SET status = 'failed',
                        finished_at = CURRENT_TIMESTAMP,
                        error = COALESCE(NULLIF(f.failed_error, ''), q.waiting_reason, '浏览器采集失败'),
                        updated_at = CURRENT_TIMESTAMP
                    FROM (
                        SELECT q0.id AS queue_id,
                               string_agg(DISTINCT COALESCE(NULLIF(s.error_message, ''), '浏览器采集失败'), ' / ') AS failed_error
                        FROM recon_execution_queue q0
                        JOIN LATERAL jsonb_array_elements_text(collection_job_ids) job_id ON TRUE
                        JOIN sync_jobs s ON s.id::text = job_id
                        WHERE q0.status = 'waiting_data'
                          AND s.job_status = 'failed'
                        GROUP BY q0.id
                    ) f
                    WHERE q.id = f.queue_id
                      AND q.status = 'waiting_data'
                    """
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"fail_waiting_recon_runs_with_failed_collection_jobs 失败: {e}")
        return 0


def fail_expired_waiting_recon_runs() -> int:
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'failed',
                        finished_at = CURRENT_TIMESTAMP,
                        error = COALESCE(NULLIF(waiting_reason, ''), '采集未就绪'),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE status = 'waiting_data'
                      AND wait_deadline_at <= CURRENT_TIMESTAMP
                    """
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"fail_expired_waiting_recon_runs 失败: {e}")
        return 0


def _clean_decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _clean_timestamp_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text if text else None


_ALIPAY_BILL_SYSTEM_PAYLOAD_FIELDS = {
    "company_id",
    "data_source_id",
    "dataset_id",
    "shop_connection_id",
    "external_shop_id",
    "bill_type",
    "bill_date",
    "source_file_name",
    "source_row_number",
    "source_row_key",
    "platform_code",
    "merchant_display_name",
}
_ALIPAY_DERIVED_BUSINESS_FIELDS = {
    "alipay_trade_no",
    "merchant_order_no",
    "business_order_no",
    "amount",
    "income_amount",
    "expense_amount",
    "trade_time",
}


def _safe_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _first_non_empty_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _fallback_alipay_bill_source_row_key(
    *,
    bill_type: str,
    bill_date: str,
    source_file_name: str,
    source_row_number: int | None,
    payload: dict[str, Any],
) -> str:
    source = {
        "bill_type": bill_type,
        "bill_date": bill_date,
        "source_file_name": source_file_name,
        "source_row_number": source_row_number,
        "payload": _json_safe_value(payload),
    }
    text = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _alipay_bill_payload(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("payload")
    if not isinstance(source, dict):
        source = item.get("raw")
    if not isinstance(source, dict):
        source = item

    result: dict[str, Any] = {}
    for key, value in dict(source).items():
        field_name = str(key or "").strip()
        if not field_name:
            continue
        if field_name in _ALIPAY_BILL_SYSTEM_PAYLOAD_FIELDS or field_name in _ALIPAY_DERIVED_BUSINESS_FIELDS:
            continue
        if field_name == "raw":
            continue
        result[field_name] = _json_safe_value(value)
    return result


def upsert_platform_order_lines(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    shop_connection_id: str,
    platform_code: str,
    external_shop_id: str,
    rows: list[dict] | None = None,
) -> dict:
    """按店铺订单行唯一键 upsert 电商平台订单明细。"""
    items = rows or []
    if not items:
        return {"input_count": 0, "upserted_count": 0, "inserted_count": 0, "updated_count": 0}

    conn_manager = get_conn()
    inserted_count = 0
    updated_count = 0
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for item in items:
                    payload = item.get("payload") if isinstance(item.get("payload"), dict) else dict(item)
                    cur.execute(
                        """
                        INSERT INTO platform_order_lines (
                            company_id, data_source_id, dataset_id, shop_connection_id,
                            platform_code, external_shop_id, biz_date, tid, oid,
                            trade_status, order_status, refund_status,
                            pay_time, modified, end_time, alipay_no,
                            payment, order_payment, total_fee, order_total_fee,
                            discount_fee, order_discount_fee, post_fee, commission_fee,
                            sku_id, outer_sku_id, outer_iid, num_iid,
                            title, sku_properties_name, quantity,
                            payload, source_modified_at
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s::jsonb, %s
                        )
                        ON CONFLICT (company_id, shop_connection_id, tid, oid)
                        DO UPDATE SET
                            data_source_id = EXCLUDED.data_source_id,
                            dataset_id = EXCLUDED.dataset_id,
                            platform_code = EXCLUDED.platform_code,
                            external_shop_id = EXCLUDED.external_shop_id,
                            biz_date = EXCLUDED.biz_date,
                            trade_status = EXCLUDED.trade_status,
                            order_status = EXCLUDED.order_status,
                            refund_status = EXCLUDED.refund_status,
                            pay_time = EXCLUDED.pay_time,
                            modified = EXCLUDED.modified,
                            end_time = EXCLUDED.end_time,
                            alipay_no = EXCLUDED.alipay_no,
                            payment = EXCLUDED.payment,
                            order_payment = EXCLUDED.order_payment,
                            total_fee = EXCLUDED.total_fee,
                            order_total_fee = EXCLUDED.order_total_fee,
                            discount_fee = EXCLUDED.discount_fee,
                            order_discount_fee = EXCLUDED.order_discount_fee,
                            post_fee = EXCLUDED.post_fee,
                            commission_fee = EXCLUDED.commission_fee,
                            sku_id = EXCLUDED.sku_id,
                            outer_sku_id = EXCLUDED.outer_sku_id,
                            outer_iid = EXCLUDED.outer_iid,
                            num_iid = EXCLUDED.num_iid,
                            title = EXCLUDED.title,
                            sku_properties_name = EXCLUDED.sku_properties_name,
                            quantity = EXCLUDED.quantity,
                            payload = EXCLUDED.payload,
                            source_modified_at = EXCLUDED.source_modified_at,
                            latest_seen_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE platform_order_lines.source_modified_at IS NULL
                           OR (
                               EXCLUDED.source_modified_at IS NOT NULL
                               AND EXCLUDED.source_modified_at >= platform_order_lines.source_modified_at
                           )
                        RETURNING (xmax = 0) AS inserted
                        """,
                        (
                            company_id,
                            data_source_id,
                            dataset_id,
                            shop_connection_id,
                            platform_code,
                            external_shop_id,
                            item.get("biz_date"),
                            str(item.get("tid") or ""),
                            str(item.get("oid") or ""),
                            str(item.get("trade_status") or ""),
                            str(item.get("order_status") or ""),
                            str(item.get("refund_status") or ""),
                            _clean_timestamp_text(item.get("pay_time")),
                            _clean_timestamp_text(item.get("modified")),
                            _clean_timestamp_text(item.get("end_time")),
                            str(item.get("alipay_no") or ""),
                            _clean_decimal_text(item.get("payment")),
                            _clean_decimal_text(item.get("order_payment")),
                            _clean_decimal_text(item.get("total_fee")),
                            _clean_decimal_text(item.get("order_total_fee")),
                            _clean_decimal_text(item.get("discount_fee")),
                            _clean_decimal_text(item.get("order_discount_fee")),
                            _clean_decimal_text(item.get("post_fee")),
                            _clean_decimal_text(item.get("commission_fee")),
                            str(item.get("sku_id") or ""),
                            str(item.get("outer_sku_id") or ""),
                            str(item.get("outer_iid") or ""),
                            str(item.get("num_iid") or ""),
                            str(item.get("title") or ""),
                            str(item.get("sku_properties_name") or ""),
                            _clean_decimal_text(item.get("quantity")),
                            psycopg2.extras.Json(_json_safe_payload(payload)),
                            _clean_timestamp_text(item.get("modified")),
                        ),
                    )
                    row = cur.fetchone() or {}
                    if not row:
                        continue
                    if bool(row.get("inserted")):
                        inserted_count += 1
                    else:
                        updated_count += 1
            conn.commit()
            return {
                "input_count": len(items),
                "upserted_count": inserted_count + updated_count,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
            }
    except Exception as e:
        logger.error(
            f"写入 platform_order_lines 失败 (company_id={company_id}, dataset_id={dataset_id}, rows={len(items)}): {e}"
        )
        raise


def list_platform_order_lines(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    shop_connection_id: str | None = None,
    resource_key: str | None = None,
    biz_date: str | None = None,
    filters: dict | None = None,
    limit: int | None = 100,
    offset: int = 0,
) -> list[dict]:
    """查询电商订单明细行，返回结构化字段和 payload。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_id, shop_connection_id,
                           platform_code, external_shop_id, biz_date, tid, oid,
                           trade_status, order_status, refund_status,
                           pay_time, modified, end_time, alipay_no,
                           payment, order_payment, total_fee, order_total_fee,
                           discount_fee, order_discount_fee, post_fee, commission_fee,
                           sku_id, outer_sku_id, outer_iid, num_iid,
                           title, sku_properties_name, quantity, payload,
                           first_seen_at, latest_seen_at, created_at, updated_at
                    FROM platform_order_lines
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(shop_connection_id)
                if resource_key and resource_key.startswith("taobao_order_lines:"):
                    sql += " AND shop_connection_id = %s"
                    params.append(resource_key.split(":", 1)[1])
                if biz_date:
                    sql += " AND biz_date = %s"
                    params.append(biz_date)
                allowed_columns = {
                    "tid",
                    "oid",
                    "trade_status",
                    "order_status",
                    "refund_status",
                    "alipay_no",
                    "sku_id",
                    "outer_sku_id",
                    "outer_iid",
                }
                for field, value in _normalize_payload_filters(filters).items():
                    if field not in allowed_columns:
                        continue
                    if isinstance(value, list):
                        sql += f" AND {field} = ANY(%s)"
                        params.append([str(item) for item in value])
                    else:
                        sql += f" AND {field} = %s"
                        params.append(str(value))
                for field_name, filter_value in _normalize_payload_filters(filters).items():
                    if field_name in allowed_columns:
                        continue
                    if isinstance(filter_value, list):
                        sql += " AND payload ->> %s = ANY(%s)"
                        params.extend([field_name, [str(item) for item in filter_value]])
                    else:
                        sql += " AND payload ->> %s = %s"
                        params.extend([field_name, str(filter_value)])
                sql += " ORDER BY biz_date DESC, updated_at DESC, id DESC OFFSET %s"
                params.append(max(0, offset))
                if limit is not None:
                    sql += " LIMIT %s"
                    params.append(max(1, min(limit, 1000)))
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall() or []]
    except Exception as e:
        logger.error(f"查询 platform_order_lines 失败 (company_id={company_id}, dataset_id={dataset_id}): {e}")
        return []


def get_platform_order_line_stats(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    shop_connection_id: str | None = None,
    biz_date: str | None = None,
) -> dict:
    """统计电商订单明细行。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT COUNT(*)::bigint AS total_count,
                           COUNT(DISTINCT biz_date)::bigint AS biz_date_count,
                           MIN(first_seen_at) AS first_seen_at,
                           MAX(latest_seen_at) AS latest_seen_at
                    FROM platform_order_lines
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(shop_connection_id)
                if biz_date:
                    sql += " AND biz_date = %s"
                    params.append(biz_date)
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else {}
    except Exception as e:
        logger.error(f"统计 platform_order_lines 失败 (company_id={company_id}, dataset_id={dataset_id}): {e}")
        return {}


def upsert_platform_alipay_bill_lines(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    shop_connection_id: str,
    external_shop_id: str,
    bill_type: str,
    bill_date: str,
    rows: list[dict] | None = None,
    replace_bill_scope: bool = False,
) -> dict:
    """按支付宝账单行唯一键 upsert 账单明细。"""
    items = rows or []
    if not items:
        deleted_stale_count = 0
        if replace_bill_scope:
            conn_manager = get_conn()
            with conn_manager as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        """
                        DELETE FROM platform_alipay_bill_lines
                        WHERE company_id = %s
                          AND shop_connection_id = %s
                          AND bill_type = %s
                          AND bill_date = %s
                          AND dataset_id = %s
                        """,
                        (
                            company_id,
                            shop_connection_id,
                            bill_type,
                            bill_date,
                            dataset_id,
                        ),
                    )
                    deleted_stale_count = int(getattr(cur, "rowcount", 0) or 0)
                conn.commit()
        return {
            "input_count": 0,
            "upserted_count": 0,
            "inserted_count": 0,
            "updated_count": 0,
            "deleted_stale_count": deleted_stale_count,
        }

    conn_manager = get_conn()
    inserted_count = 0
    updated_count = 0
    deleted_stale_count = 0
    seen_source_row_keys: list[str] = []
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                for item in items:
                    enriched_item = {
                        **item,
                        "company_id": company_id,
                        "data_source_id": data_source_id,
                        "dataset_id": dataset_id,
                        "shop_connection_id": shop_connection_id,
                        "external_shop_id": external_shop_id,
                        "bill_type": bill_type,
                        "bill_date": bill_date,
                    }
                    payload = _alipay_bill_payload(enriched_item)
                    source_file_name = _first_non_empty_text(
                        item.get("source_file_name"),
                    )
                    source_row_number = _safe_int_or_none(
                        item.get("source_row_number")
                    )
                    source_row_key = _first_non_empty_text(
                        item.get("source_row_key"),
                    )
                    if not source_row_key:
                        source_row_key = _fallback_alipay_bill_source_row_key(
                            bill_type=bill_type,
                            bill_date=bill_date,
                            source_file_name=source_file_name,
                            source_row_number=source_row_number,
                            payload=payload,
                        )
                    if source_row_key and source_row_key not in seen_source_row_keys:
                        seen_source_row_keys.append(source_row_key)
                    cur.execute(
                        """
                        INSERT INTO platform_alipay_bill_lines (
                            company_id, data_source_id, dataset_id, shop_connection_id,
                            external_shop_id, bill_type, bill_date,
                            source_file_name, source_row_number, source_row_key,
                            payload
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s::jsonb
                        )
                        ON CONFLICT (company_id, shop_connection_id, bill_type, bill_date, source_row_key)
                        DO UPDATE SET
                            data_source_id = EXCLUDED.data_source_id,
                            dataset_id = EXCLUDED.dataset_id,
                            external_shop_id = EXCLUDED.external_shop_id,
                            source_file_name = EXCLUDED.source_file_name,
                            source_row_number = EXCLUDED.source_row_number,
                            payload = EXCLUDED.payload,
                            latest_seen_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING (xmax = 0) AS inserted
                        """,
                        (
                            company_id,
                            data_source_id,
                            dataset_id,
                            shop_connection_id,
                            external_shop_id,
                            bill_type,
                            bill_date,
                            source_file_name,
                            source_row_number,
                            source_row_key,
                            psycopg2.extras.Json(_json_safe_payload(payload)),
                        ),
                    )
                    row = cur.fetchone() or {}
                    if not row:
                        continue
                    if bool(row.get("inserted")):
                        inserted_count += 1
                    else:
                        updated_count += 1
                if replace_bill_scope and seen_source_row_keys:
                    cur.execute(
                        """
                        DELETE FROM platform_alipay_bill_lines
                        WHERE company_id = %s
                          AND shop_connection_id = %s
                          AND bill_type = %s
                          AND bill_date = %s
                          AND dataset_id = %s
                          AND source_row_key <> ALL(%s)
                        """,
                        (
                            company_id,
                            shop_connection_id,
                            bill_type,
                            bill_date,
                            dataset_id,
                            seen_source_row_keys,
                        ),
                    )
                    deleted_stale_count = int(getattr(cur, "rowcount", 0) or 0)
            conn.commit()
            return {
                "input_count": len(items),
                "upserted_count": inserted_count + updated_count,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "deleted_stale_count": deleted_stale_count,
            }
    except Exception as e:
        logger.error(
            "写入 platform_alipay_bill_lines 失败 "
            f"(company_id={company_id}, dataset_id={dataset_id}, rows={len(items)}): {e}"
        )
        raise


def list_platform_alipay_bill_lines(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    shop_connection_id: str | None = None,
    resource_key: str | None = None,
    biz_date: str | None = None,
    filters: dict | None = None,
    limit: int | None = 100,
    offset: int = 0,
) -> list[dict]:
    """查询支付宝账单明细行，返回结构化字段和 payload。"""
    resource_bill_type = ""
    resource_shop_connection_id = ""
    if resource_key and resource_key.startswith("alipay_bill:"):
        resource_parts = resource_key.split(":")
        if len(resource_parts) >= 2:
            resource_bill_type = resource_parts[1].strip()
        if len(resource_parts) >= 3:
            resource_shop_connection_id = resource_parts[2].strip()
    if (
        shop_connection_id
        and resource_shop_connection_id
        and str(shop_connection_id).strip() != resource_shop_connection_id
    ):
        return []

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_id, shop_connection_id,
                           external_shop_id, bill_type, bill_date,
                           source_file_name, source_row_number, source_row_key,
                           payload,
                           first_seen_at, latest_seen_at, created_at, updated_at
                    FROM platform_alipay_bill_lines
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)

                if resource_bill_type:
                    sql += " AND bill_type = %s"
                    params.append(resource_bill_type)
                if shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(shop_connection_id)
                elif resource_shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(resource_shop_connection_id)
                if biz_date:
                    sql += " AND bill_date = %s"
                    params.append(biz_date)

                allowed_columns = {
                    "bill_type",
                    "source_row_key",
                }
                for field, value in _normalize_payload_filters(filters).items():
                    if field not in allowed_columns:
                        continue
                    if isinstance(value, list):
                        sql += f" AND {field} = ANY(%s)"
                        params.append([str(item) for item in value])
                    else:
                        sql += f" AND {field} = %s"
                        params.append(str(value))
                for field_name, filter_value in _normalize_payload_filters(filters).items():
                    if field_name in allowed_columns:
                        continue
                    if isinstance(filter_value, list):
                        sql += " AND payload ->> %s = ANY(%s)"
                        params.extend([field_name, [str(item) for item in filter_value]])
                    else:
                        sql += " AND payload ->> %s = %s"
                        params.extend([field_name, str(filter_value)])

                safe_offset = max(0, int(offset or 0))
                sql += " ORDER BY bill_date DESC, updated_at DESC, id DESC OFFSET %s"
                params.append(safe_offset)
                if limit is not None:
                    safe_limit = max(1, min(int(limit or 100), 1000))
                    sql += " LIMIT %s"
                    params.append(safe_limit)
                cur.execute(sql, tuple(params))
                return [_normalize_record(dict(row)) for row in cur.fetchall() or []]
    except Exception as e:
        logger.error(
            f"查询 platform_alipay_bill_lines 失败 (company_id={company_id}, dataset_id={dataset_id}): {e}"
        )
        return []


def get_platform_alipay_bill_line_stats(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    shop_connection_id: str | None = None,
    biz_date: str | None = None,
) -> dict:
    """统计支付宝账单明细行。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT COUNT(*)::bigint AS total_count,
                           COUNT(DISTINCT bill_date)::bigint AS biz_date_count,
                           MIN(first_seen_at) AS first_seen_at,
                           MAX(latest_seen_at) AS latest_seen_at
                    FROM platform_alipay_bill_lines
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if shop_connection_id:
                    sql += " AND shop_connection_id = %s"
                    params.append(shop_connection_id)
                if biz_date:
                    sql += " AND bill_date = %s"
                    params.append(biz_date)
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else {}
    except Exception as e:
        logger.error(
            f"统计 platform_alipay_bill_lines 失败 (company_id={company_id}, dataset_id={dataset_id}): {e}"
        )
        return {}



def upsert_dataset_collection_records(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    dataset_code: str,
    resource_key: str,
    biz_date: str,
    sync_job_id: str | None = None,
    records: list[dict] | None = None,
) -> dict:
    """按数据集业务主键 upsert 采集明细记录。"""
    items = records or []
    if not items:
        return {"input_count": 0, "upserted_count": 0, "inserted_count": 0, "updated_count": 0, "unchanged_count": 0}

    conn_manager = get_conn()
    input_count = len(items)
    values: list[tuple[Any, ...]] = []
    for item in items:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        key_values = item.get("item_key_values") if isinstance(item.get("item_key_values"), dict) else {}
        values.append(
            (
                company_id,
                data_source_id,
                dataset_id,
                dataset_code,
                resource_key or "default",
                biz_date,
                str(item.get("item_key") or ""),
                psycopg2.extras.Json(_json_safe_payload(key_values)),
                str(item.get("item_hash") or ""),
                psycopg2.extras.Json(_json_safe_payload(payload)),
                sync_job_id,
                sync_job_id,
            )
        )
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                rows = psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO dataset_collection_records (
                        company_id, data_source_id, dataset_id, dataset_code, resource_key,
                        biz_date, item_key, item_key_values, item_hash, payload, record_status,
                        first_seen_job_id, latest_seen_job_id
                    ) VALUES %s
                    ON CONFLICT (company_id, dataset_id, biz_date, item_key)
                    DO UPDATE SET
                        data_source_id = EXCLUDED.data_source_id,
                        dataset_code = EXCLUDED.dataset_code,
                        resource_key = EXCLUDED.resource_key,
                        item_key_values = CASE
                            WHEN dataset_collection_records.item_hash = EXCLUDED.item_hash
                            THEN dataset_collection_records.item_key_values
                            ELSE EXCLUDED.item_key_values
                        END,
                        item_hash = EXCLUDED.item_hash,
                        payload = CASE
                            WHEN dataset_collection_records.item_hash = EXCLUDED.item_hash
                            THEN dataset_collection_records.payload
                            ELSE EXCLUDED.payload
                        END,
                        record_status = CASE
                            WHEN dataset_collection_records.item_hash = EXCLUDED.item_hash THEN 'unchanged'
                            ELSE 'updated'
                        END,
                        latest_seen_job_id = EXCLUDED.latest_seen_job_id,
                        latest_seen_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING CASE
                        WHEN (xmax = 0) THEN 'inserted'
                        WHEN record_status = 'unchanged' THEN 'unchanged'
                        ELSE 'updated'
                    END AS action
                    """,
                    values,
                    template=(
                        "(%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, "
                        "'active', %s, %s)"
                    ),
                    page_size=1000,
                    fetch=True,
                )
                inserted_count = sum(
                    1 for row in rows or [] if str(row.get("action") or "") == "inserted"
                )
                unchanged_count = sum(
                    1 for row in rows or [] if str(row.get("action") or "") == "unchanged"
                )
                updated_count = max(0, len(rows or []) - inserted_count - unchanged_count)
            conn.commit()
            return {
                "input_count": input_count,
                "upserted_count": inserted_count + updated_count + unchanged_count,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "unchanged_count": unchanged_count,
            }
    except Exception as e:
        logger.error(
            f"写入 dataset_collection_records 失败 (company_id={company_id}, dataset_id={dataset_id}, biz_date={biz_date}, records={input_count}): {e}"
        )
        raise


def list_dataset_collection_records(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    dataset_code: str | None = None,
    resource_key: str | None = None,
    biz_date: str | None = None,
    item_key: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int | None = 100,
    offset: int = 0,
) -> list[dict]:
    """查询数据资产层采集记录。limit=None 表示不限条数，返回全量。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_id, dataset_code, resource_key,
                           biz_date, item_key, item_key_values, item_hash, payload, record_status,
                           first_seen_job_id, latest_seen_job_id, first_seen_at, latest_seen_at,
                           created_at, updated_at
                    FROM dataset_collection_records
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if dataset_code:
                    sql += " AND dataset_code = %s"
                    params.append(dataset_code)
                if resource_key:
                    sql += " AND resource_key = %s"
                    params.append(resource_key)
                if biz_date:
                    sql += " AND biz_date = %s"
                    params.append(biz_date)
                if item_key:
                    sql += " AND item_key = %s"
                    params.append(item_key)
                for field_name, filter_value in _normalize_payload_filters(filters).items():
                    if isinstance(filter_value, list):
                        sql += " AND payload ->> %s = ANY(%s)"
                        params.extend([field_name, [str(item) for item in filter_value]])
                    else:
                        sql += " AND payload ->> %s = %s"
                        params.extend([field_name, str(filter_value)])
                sql += " ORDER BY biz_date DESC, updated_at DESC, id DESC OFFSET %s"
                params.append(max(0, offset))
                if limit is not None:
                    sql += " LIMIT %s"
                    params.append(max(1, min(limit, 1000)))
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 dataset_collection_records 失败 (company_id={company_id}, dataset_id={dataset_id}, biz_date={biz_date}): {e}"
        )
        return []


def _browser_record_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        _json_safe_payload(payload or {}),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def upsert_browser_collection_records(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    dataset_code: str,
    resource_key: str,
    shop_id: str,
    playbook_id: str,
    biz_date: str,
    sync_job_id: str | None = None,
    captured_at: str | None = None,
    records: list[dict] | None = None,
) -> dict:
    """按浏览器采集数据集主键 upsert 明细记录。"""
    items = records or []
    if not items:
        return {
            "input_count": 0,
            "upserted_count": 0,
            "inserted_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "deleted_count": 0,
        }

    input_count = len(items)
    values: list[tuple[Any, ...]] = []
    for item in items:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        key_values = item.get("item_key_values") if isinstance(item.get("item_key_values"), dict) else {}
        item_key = str(item.get("item_key") or "").strip()
        if not item_key:
            raise ValueError("browser_collection_records item_key 不能为空")
        values.append(
            (
                company_id,
                data_source_id,
                dataset_id,
                dataset_code,
                resource_key or "default",
                shop_id,
                playbook_id,
                biz_date,
                item_key,
                psycopg2.extras.Json(_json_safe_payload(key_values)),
                _browser_record_hash(payload),
                psycopg2.extras.Json(_json_safe_payload(payload)),
                sync_job_id,
                sync_job_id,
                captured_at,
            )
        )

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                rows = psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO browser_collection_records (
                        company_id, data_source_id, dataset_id, dataset_code, resource_key,
                        shop_id, playbook_id, biz_date, item_key, item_key_values,
                        item_hash, payload, record_status, first_seen_job_id,
                        latest_seen_job_id, captured_at
                    ) VALUES %s
                    ON CONFLICT (company_id, dataset_id, biz_date, item_key)
                    DO UPDATE SET
                        data_source_id = EXCLUDED.data_source_id,
                        dataset_code = EXCLUDED.dataset_code,
                        resource_key = EXCLUDED.resource_key,
                        shop_id = EXCLUDED.shop_id,
                        playbook_id = EXCLUDED.playbook_id,
                        item_key_values = CASE
                            WHEN browser_collection_records.item_hash = EXCLUDED.item_hash
                            THEN browser_collection_records.item_key_values
                            ELSE EXCLUDED.item_key_values
                        END,
                        payload = CASE
                            WHEN browser_collection_records.item_hash = EXCLUDED.item_hash
                            THEN browser_collection_records.payload
                            ELSE EXCLUDED.payload
                        END,
                        item_hash = EXCLUDED.item_hash,
                        record_status = CASE
                            WHEN browser_collection_records.item_hash = EXCLUDED.item_hash THEN 'unchanged'
                            ELSE 'updated'
                        END,
                        latest_seen_job_id = EXCLUDED.latest_seen_job_id,
                        latest_seen_at = CURRENT_TIMESTAMP,
                        captured_at = EXCLUDED.captured_at,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING CASE
                        WHEN (xmax = 0) THEN 'inserted'
                        WHEN record_status = 'unchanged' THEN 'unchanged'
                        ELSE 'updated'
                    END AS action
                    """,
                    values,
                    template=(
                        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, "
                        "%s, %s::jsonb, 'active', %s, %s, COALESCE(%s::timestamptz, CURRENT_TIMESTAMP))"
                    ),
                    page_size=1000,
                    fetch=True,
                )
                inserted_count = sum(
                    1 for row in rows or [] if str(row.get("action") or "") == "inserted"
                )
                unchanged_count = sum(
                    1 for row in rows or [] if str(row.get("action") or "") == "unchanged"
                )
                updated_count = max(0, len(rows or []) - inserted_count - unchanged_count)
            conn.commit()
            return {
                "input_count": input_count,
                "upserted_count": inserted_count + updated_count + unchanged_count,
                "inserted_count": inserted_count,
                "updated_count": updated_count,
                "unchanged_count": unchanged_count,
                "deleted_count": 0,
            }
    except Exception as e:
        logger.error(
            f"写入 browser_collection_records 失败 (company_id={company_id}, dataset_id={dataset_id}, biz_date={biz_date}, records={input_count}): {e}"
        )
        raise


def insert_browser_capture_files(
    *,
    company_id: str,
    data_source_id: str,
    dataset_id: str,
    sync_job_id: str,
    resource_key: str,
    shop_id: str,
    playbook_id: str,
    biz_date: str,
    capture_files: list[dict],
) -> dict:
    """Persist browser-agent capture file metadata as audit artifacts.

    Original downloaded files (CSV / Excel) are referenced by storage_path; this table only
    stores metadata + checksum so operators can audit "what file was downloaded for which
    sync_job on which biz_date".
    """
    files = list(capture_files or [])
    if not files:
        return {"inserted_count": 0}

    rows: list[tuple] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        storage_path = str(entry.get("storage_path") or "").strip()
        if not storage_path:
            continue
        rows.append(
            (
                company_id,
                data_source_id,
                dataset_id or None,
                sync_job_id or None,
                resource_key,
                shop_id,
                playbook_id,
                biz_date or None,
                storage_path,
                str(entry.get("encoding") or ""),
                str(entry.get("checksum") or ""),
                int(entry.get("row_count") or 0),
            )
        )
    if not rows:
        return {"inserted_count": 0}

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO browser_capture_files (
                        company_id, data_source_id, dataset_id, sync_job_id, resource_key,
                        shop_id, playbook_id, biz_date, storage_path, encoding, checksum, row_count
                    ) VALUES %s
                    """,
                    rows,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s)",
                )
                conn.commit()
        return {"inserted_count": len(rows)}
    except Exception as e:
        logger.error(f"insert_browser_capture_files 失败: {e}")
        raise


def list_browser_collection_records(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    dataset_code: str | None = None,
    resource_key: str | None = None,
    biz_date: str | None = None,
    item_key: str | None = None,
    filters: dict[str, Any] | None = None,
    limit: int | None = 100,
    offset: int = 0,
) -> list[dict]:
    """查询浏览器采集明细记录。limit=None 表示不限条数，返回全量。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, dataset_id, dataset_code, resource_key,
                           shop_id, playbook_id, biz_date, item_key, item_key_values,
                           item_hash, payload, record_status, first_seen_job_id,
                           latest_seen_job_id, first_seen_at, latest_seen_at,
                           captured_at, created_at, updated_at
                    FROM browser_collection_records
                    WHERE company_id = %s
                      AND record_status <> 'deleted'
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if dataset_code:
                    sql += " AND dataset_code = %s"
                    params.append(dataset_code)
                if resource_key:
                    sql += " AND resource_key = %s"
                    params.append(resource_key)
                if biz_date:
                    sql += " AND biz_date = %s"
                    params.append(biz_date)
                if item_key:
                    sql += " AND item_key = %s"
                    params.append(item_key)
                for field_name, filter_value in _normalize_payload_filters(filters).items():
                    if isinstance(filter_value, list):
                        sql += " AND payload ->> %s = ANY(%s)"
                        params.extend([field_name, [str(item) for item in filter_value]])
                    else:
                        sql += " AND payload ->> %s = %s"
                        params.extend([field_name, str(filter_value)])
                sql += " ORDER BY biz_date DESC, captured_at DESC, id DESC OFFSET %s"
                params.append(max(0, offset))
                if limit is not None:
                    sql += " LIMIT %s"
                    params.append(max(1, min(limit, 1000)))
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 browser_collection_records 失败 (company_id={company_id}, dataset_id={dataset_id}, biz_date={biz_date}): {e}"
        )
        return []


def _normalize_payload_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}
    normalized: dict[str, Any] = {}
    for raw_field, raw_value in filters.items():
        field_name = str(raw_field or "").strip()
        if not _is_safe_payload_filter_field(field_name):
            continue
        if raw_value is None or raw_value == "":
            continue
        if isinstance(raw_value, (list, tuple, set)):
            values = [
                item
                for item in list(raw_value)[:50]
                if item not in {None, ""}
                and isinstance(item, (str, int, float, bool))
            ]
            if values:
                normalized[field_name] = values
            continue
        if isinstance(raw_value, (str, int, float, bool)):
            normalized[field_name] = raw_value
    return normalized


def _is_safe_payload_filter_field(field_name: str) -> bool:
    if not field_name or len(field_name) > 128:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_\-\u4e00-\u9fff（）()＋+\s]+", field_name))


def get_dataset_collection_record_stats(
    *,
    company_id: str,
    data_source_id: str | None = None,
    dataset_id: str | None = None,
    dataset_code: str | None = None,
    resource_key: str | None = None,
    biz_date: str | None = None,
) -> dict:
    """统计数据资产层采集记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT COUNT(*)::bigint AS total_count,
                           COUNT(*) FILTER (WHERE record_status = 'active')::bigint AS active_count,
                           COUNT(*) FILTER (WHERE record_status = 'updated')::bigint AS updated_count,
                           COUNT(*) FILTER (WHERE record_status = 'unchanged')::bigint AS unchanged_count,
                           COUNT(DISTINCT biz_date)::bigint AS biz_date_count,
                           MIN(first_seen_at) AS first_seen_at,
                           MAX(latest_seen_at) AS latest_seen_at
                    FROM dataset_collection_records
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if dataset_id:
                    sql += " AND dataset_id = %s"
                    params.append(dataset_id)
                if dataset_code:
                    sql += " AND dataset_code = %s"
                    params.append(dataset_code)
                if resource_key:
                    sql += " AND resource_key = %s"
                    params.append(resource_key)
                if biz_date:
                    sql += " AND biz_date = %s"
                    params.append(biz_date)
                cur.execute(sql, tuple(params))
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else {}
    except Exception as e:
        logger.error(
            f"统计 dataset_collection_records 失败 (company_id={company_id}, dataset_id={dataset_id}, biz_date={biz_date}): {e}"
        )
        return {}


def upsert_unified_dataset_binding(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    data_source_id: str,
    resource_key: str = "default",
    role_code: str = "source",
    binding_name: str = "",
    is_required: bool = True,
    priority: int = 100,
    filter_config: dict | None = None,
    mapping_config: dict | None = None,
    status: str = "active",
) -> dict | None:
    """写入数据集绑定关系。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO dataset_bindings (
                        company_id, binding_scope, binding_code, binding_name,
                        data_source_id, resource_key, role_code, is_required, priority,
                        filter_config, mapping_config, status
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s
                    )
                    ON CONFLICT (company_id, binding_scope, binding_code, role_code, data_source_id, resource_key)
                    DO UPDATE SET
                        binding_name = EXCLUDED.binding_name,
                        is_required = EXCLUDED.is_required,
                        priority = EXCLUDED.priority,
                        filter_config = EXCLUDED.filter_config,
                        mapping_config = EXCLUDED.mapping_config,
                        status = EXCLUDED.status,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, binding_scope, binding_code, binding_name,
                              data_source_id, resource_key, role_code, is_required, priority,
                              filter_config, mapping_config, status, created_at, updated_at
                    """,
                    (
                        company_id,
                        binding_scope,
                        binding_code,
                        binding_name,
                        data_source_id,
                        resource_key,
                        role_code,
                        is_required,
                        priority,
                        psycopg2.extras.Json(filter_config or {}),
                        psycopg2.extras.Json(mapping_config or {}),
                        status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 dataset_bindings 失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}, data_source_id={data_source_id}): {e}"
        )
        return None


def list_unified_dataset_bindings(
    *,
    company_id: str,
    binding_scope: str | None = None,
    binding_code: str | None = None,
    status: str | None = "active",
) -> list[dict]:
    """查询数据集绑定关系。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, binding_scope, binding_code, binding_name,
                           data_source_id, resource_key, role_code, is_required, priority,
                           filter_config, mapping_config, status, created_at, updated_at
                    FROM dataset_bindings
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if binding_scope:
                    sql += " AND binding_scope = %s"
                    params.append(binding_scope)
                if binding_code:
                    sql += " AND binding_code = %s"
                    params.append(binding_code)
                if status:
                    sql += " AND status = %s"
                    params.append(status)
                sql += " ORDER BY priority ASC, updated_at DESC"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 dataset_bindings 列表失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}, status={status}): {e}"
        )
        return []


def replace_unified_dataset_bindings(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    binding_name: str = "",
    bindings: list[dict[str, Any]] | None = None,
) -> list[dict]:
    """覆盖写入数据集绑定关系，并禁用旧绑定。"""
    normalized_bindings = [dict(item) for item in (bindings or []) if isinstance(item, dict)]
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE dataset_bindings
                    SET status = 'disabled',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND binding_scope = %s
                      AND binding_code = %s
                    """,
                    (company_id, binding_scope, binding_code),
                )
                rows: list[dict] = []
                for index, binding in enumerate(normalized_bindings):
                    cur.execute(
                        """
                        INSERT INTO dataset_bindings (
                            company_id, binding_scope, binding_code, binding_name,
                            data_source_id, resource_key, role_code, is_required, priority,
                            filter_config, mapping_config, status
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s::jsonb, %s::jsonb, 'active'
                        )
                        ON CONFLICT (company_id, binding_scope, binding_code, role_code, data_source_id, resource_key)
                        DO UPDATE SET
                            binding_name = EXCLUDED.binding_name,
                            is_required = EXCLUDED.is_required,
                            priority = EXCLUDED.priority,
                            filter_config = EXCLUDED.filter_config,
                            mapping_config = EXCLUDED.mapping_config,
                            status = 'active',
                            updated_at = CURRENT_TIMESTAMP
                        RETURNING id, company_id, binding_scope, binding_code, binding_name,
                                  data_source_id, resource_key, role_code, is_required, priority,
                                  filter_config, mapping_config, status, created_at, updated_at
                        """,
                        (
                            company_id,
                            binding_scope,
                            binding_code,
                            str(binding.get("binding_name") or binding_name or "").strip(),
                            str(binding.get("data_source_id") or "").strip(),
                            str(binding.get("resource_key") or "default").strip() or "default",
                            str(binding.get("role_code") or "source").strip() or "source",
                            bool(binding.get("is_required", True)),
                            int(binding.get("priority") or ((index + 1) * 10)),
                            psycopg2.extras.Json(dict(binding.get("filter_config") or {})),
                            psycopg2.extras.Json(dict(binding.get("mapping_config") or {})),
                        ),
                    )
                    row = cur.fetchone()
                    if row:
                        rows.append(_normalize_record(dict(row)))
                conn.commit()
                return rows
    except Exception as e:
        logger.error(
            f"覆盖写入 dataset_bindings 失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}): {e}"
        )
        return []


def disable_stale_unified_dataset_bindings(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    keep_bindings: list[dict[str, Any]] | None = None,
    disabled_status: str = "disabled",
) -> int:
    """禁用不在 keep_bindings 内的旧绑定。"""
    normalized = [dict(item) for item in (keep_bindings or []) if isinstance(item, dict)]
    keep_keys: list[tuple[str, str, str]] = []
    for item in normalized:
        keep_keys.append(
            (
                str(item.get("role_code") or "source").strip() or "source",
                str(item.get("data_source_id") or "").strip(),
                str(item.get("resource_key") or "default").strip() or "default",
            )
        )

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                sql = """
                    UPDATE dataset_bindings
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND binding_scope = %s
                      AND binding_code = %s
                      AND status <> 'deleted'
                """
                params: list[Any] = [disabled_status, company_id, binding_scope, binding_code]
                if keep_keys:
                    predicates: list[str] = []
                    for role_code, data_source_id, resource_key in keep_keys:
                        predicates.append("(role_code = %s AND data_source_id = %s AND resource_key = %s)")
                        params.extend([role_code, data_source_id, resource_key])
                    sql += f" AND NOT ({' OR '.join(predicates)})"
                cur.execute(sql, tuple(params))
                changed = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
                conn.commit()
                return changed
    except Exception as e:
        logger.error(
            f"禁用陈旧 dataset_bindings 失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}): {e}"
        )
        return 0


def touch_unified_dataset_usage_by_binding(
    *,
    company_id: str,
    binding_scope: str,
    binding_code: str,
    binding_status: str | None = "active",
    increment_by: int = 1,
    used_at: str | None = None,
) -> int:
    """按绑定关系批量回写 usage_count/last_used_at。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                sql = """
                    WITH target_datasets AS (
                        SELECT DISTINCT ON (b.role_code, b.data_source_id, b.resource_key)
                               d.id AS dataset_id
                        FROM dataset_bindings b
                        JOIN LATERAL (
                            SELECT d0.id
                            FROM data_source_datasets d0
                            WHERE d0.company_id = b.company_id
                              AND d0.data_source_id = b.data_source_id
                              AND d0.resource_key = b.resource_key
                              AND d0.status <> 'deleted'
                            ORDER BY d0.updated_at DESC, d0.created_at DESC
                            LIMIT 1
                        ) d ON true
                        WHERE b.company_id = %s
                          AND b.binding_scope = %s
                          AND b.binding_code = %s
                """
                params: list[Any] = [company_id, binding_scope, binding_code]
                if binding_status:
                    sql += " AND b.status = %s"
                    params.append(binding_status)
                sql += """
                    )
                    UPDATE data_source_datasets x
                    SET usage_count = GREATEST(0, x.usage_count + %s),
                        last_used_at = COALESCE(%s::timestamptz, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE x.id IN (SELECT dataset_id FROM target_datasets)
                """
                params.extend([max(1, int(increment_by or 1)), used_at])
                cur.execute(sql, tuple(params))
                changed = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
                conn.commit()
                return changed
    except Exception as e:
        logger.error(
            f"批量回写 data_source_datasets 使用统计失败 (company_id={company_id}, binding_scope={binding_scope}, binding_code={binding_code}): {e}"
        )
        return 0


def create_unified_data_source_event(
    *,
    company_id: str,
    data_source_id: str,
    event_type: str,
    event_level: str = "info",
    event_message: str = "",
    event_payload: dict | None = None,
    sync_job_id: str | None = None,
) -> dict | None:
    """写入数据源事件。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO data_source_events (
                        company_id, data_source_id, sync_job_id,
                        event_type, event_level, event_message, event_payload
                    ) VALUES (
                        %s, %s, %s,
                        %s, %s, %s, %s::jsonb
                    )
                    RETURNING id, company_id, data_source_id, sync_job_id,
                              event_type, event_level, event_message, event_payload, created_at
                    """,
                    (
                        company_id,
                        data_source_id,
                        sync_job_id,
                        event_type,
                        event_level,
                        event_message,
                        psycopg2.extras.Json(event_payload or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"写入 data_source_events 失败 (company_id={company_id}, data_source_id={data_source_id}, event_type={event_type}): {e}"
        )
        return None


def list_unified_data_source_events(
    *,
    company_id: str,
    data_source_id: str | None = None,
    sync_job_id: str | None = None,
    event_level: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """查询数据源事件。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, data_source_id, sync_job_id,
                           event_type, event_level, event_message, event_payload, created_at
                    FROM data_source_events
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if data_source_id:
                    sql += " AND data_source_id = %s"
                    params.append(data_source_id)
                if sync_job_id:
                    sql += " AND sync_job_id = %s"
                    params.append(sync_job_id)
                if event_level:
                    sql += " AND event_level = %s"
                    params.append(event_level)
                sql += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 data_source_events 列表失败 (company_id={company_id}, data_source_id={data_source_id}, sync_job_id={sync_job_id}, event_level={event_level}): {e}"
        )
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 自动对账任务与异常闭环（recon_auto_tasks / recon_auto_runs / recon_exception_tasks）
# ══════════════════════════════════════════════════════════════════════════════

def create_recon_auto_task(
    *,
    company_id: str,
    task_name: str,
    rule_code: str,
    rule_id: str = "",
    is_enabled: bool = True,
    schedule_type: str = "daily",
    schedule_expr: str = "",
    biz_date_offset: str = "T-1",
    max_wait_until: str = "",
    retry_policy_json: dict | None = None,
    input_mode: str = "bound_source",
    bound_data_source_ids: list[str] | None = None,
    completeness_policy_json: dict | None = None,
    auto_create_exceptions: bool = True,
    auto_remind: bool = False,
    channel_config_id: str | None = None,
    reminder_policy_json: dict | None = None,
    owner_mapping_json: dict | None = None,
    task_meta_json: dict | None = None,
) -> dict | None:
    """创建自动运行任务配置。"""
    import uuid as _uuid

    conn_manager = get_conn()
    try:
        task_code = f"task_{_uuid.uuid4().hex[:10]}"
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_auto_tasks (
                        company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                        schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                        retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                        auto_create_exceptions, auto_remind, channel_config_id,
                        reminder_policy_json, owner_mapping_json, task_meta_json
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::jsonb, %s, %s::jsonb, %s::jsonb,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    RETURNING id, company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                              schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                              retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                              auto_create_exceptions, auto_remind, channel_config_id,
                              reminder_policy_json, owner_mapping_json, task_meta_json,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        task_code,
                        task_name,
                        rule_code,
                        rule_id,
                        is_enabled,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        max_wait_until,
                        psycopg2.extras.Json(retry_policy_json or {}),
                        input_mode,
                        psycopg2.extras.Json(bound_data_source_ids or []),
                        psycopg2.extras.Json(completeness_policy_json or {}),
                        auto_create_exceptions,
                        auto_remind,
                        channel_config_id,
                        psycopg2.extras.Json(reminder_policy_json or {}),
                        psycopg2.extras.Json(owner_mapping_json or {}),
                        psycopg2.extras.Json(task_meta_json or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 recon_auto_tasks 失败 (company_id={company_id}, rule_code={rule_code}): {e}")
        return None


def update_recon_auto_task(
    *,
    company_id: str,
    auto_task_id: str,
    task_name: str | None = None,
    rule_code: str | None = None,
    rule_id: str | None = None,
    is_enabled: bool | None = None,
    schedule_type: str | None = None,
    schedule_expr: str | None = None,
    biz_date_offset: str | None = None,
    max_wait_until: str | None = None,
    retry_policy_json: dict | None = None,
    input_mode: str | None = None,
    bound_data_source_ids: list[str] | None = None,
    completeness_policy_json: dict | None = None,
    auto_create_exceptions: bool | None = None,
    auto_remind: bool | None = None,
    channel_config_id: str | None = None,
    reminder_policy_json: dict | None = None,
    owner_mapping_json: dict | None = None,
    task_meta_json: dict | None = None,
) -> dict | None:
    """更新自动运行任务配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_auto_tasks
                    SET task_name = COALESCE(%s, task_name),
                        rule_code = COALESCE(%s, rule_code),
                        rule_id = COALESCE(%s, rule_id),
                        is_enabled = COALESCE(%s, is_enabled),
                        schedule_type = COALESCE(%s, schedule_type),
                        schedule_expr = COALESCE(%s, schedule_expr),
                        biz_date_offset = COALESCE(%s, biz_date_offset),
                        max_wait_until = COALESCE(%s, max_wait_until),
                        retry_policy_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN retry_policy_json
                            ELSE %s::jsonb
                        END,
                        input_mode = COALESCE(%s, input_mode),
                        bound_data_source_ids = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN bound_data_source_ids
                            ELSE %s::jsonb
                        END,
                        completeness_policy_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN completeness_policy_json
                            ELSE %s::jsonb
                        END,
                        auto_create_exceptions = COALESCE(%s, auto_create_exceptions),
                        auto_remind = COALESCE(%s, auto_remind),
                        channel_config_id = COALESCE(%s, channel_config_id),
                        reminder_policy_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN reminder_policy_json
                            ELSE %s::jsonb
                        END,
                        owner_mapping_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_mapping_json
                            ELSE %s::jsonb
                        END,
                        task_meta_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN task_meta_json
                            ELSE %s::jsonb
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                              schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                              retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                              auto_create_exceptions, auto_remind, channel_config_id,
                              reminder_policy_json, owner_mapping_json, task_meta_json,
                              created_at, updated_at
                    """,
                    (
                        task_name,
                        rule_code,
                        rule_id,
                        is_enabled,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        max_wait_until,
                        psycopg2.extras.Json(retry_policy_json) if retry_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(retry_policy_json) if retry_policy_json is not None else psycopg2.extras.Json(None),
                        input_mode,
                        psycopg2.extras.Json(bound_data_source_ids) if bound_data_source_ids is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(bound_data_source_ids) if bound_data_source_ids is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(completeness_policy_json) if completeness_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(completeness_policy_json) if completeness_policy_json is not None else psycopg2.extras.Json(None),
                        auto_create_exceptions,
                        auto_remind,
                        channel_config_id,
                        psycopg2.extras.Json(reminder_policy_json) if reminder_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(reminder_policy_json) if reminder_policy_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(task_meta_json) if task_meta_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(task_meta_json) if task_meta_json is not None else psycopg2.extras.Json(None),
                        auto_task_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_auto_tasks 失败 (company_id={company_id}, id={auto_task_id}): {e}")
        return None


def get_recon_auto_task(*, company_id: str, auto_task_id: str) -> dict | None:
    """查询单个自动运行任务配置。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, task_code, task_name, rule_code, is_enabled,
                           rule_id,
                           schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                           retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                           auto_create_exceptions, auto_remind, channel_config_id,
                           reminder_policy_json, owner_mapping_json, task_meta_json,
                           created_at, updated_at
                    FROM recon_auto_tasks
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, auto_task_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 recon_auto_tasks 失败 (company_id={company_id}, id={auto_task_id}): {e}")
        return None


def list_recon_auto_tasks(
    *,
    company_id: str,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询自动运行任务配置列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, task_code, task_name, rule_code, rule_id, is_enabled,
                           schedule_type, schedule_expr, biz_date_offset, max_wait_until,
                           retry_policy_json, input_mode, bound_data_source_ids, completeness_policy_json,
                           auto_create_exceptions, auto_remind, channel_config_id,
                           reminder_policy_json, owner_mapping_json, task_meta_json,
                           created_at, updated_at
                    FROM recon_auto_tasks
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if not include_disabled:
                    sql += " AND is_enabled = true"
                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 recon_auto_tasks 列表失败 (company_id={company_id}): {e}")
        return []


def disable_recon_auto_task(*, company_id: str, auto_task_id: str) -> dict | None:
    """停用自动运行任务配置（逻辑删除）。"""
    return update_recon_auto_task(company_id=company_id, auto_task_id=auto_task_id, is_enabled=False)


def create_recon_auto_run(
    *,
    company_id: str,
    auto_task_id: str,
    biz_date: str,
    trigger_mode: str = "cron",
    run_status: str = "scheduled",
    readiness_status: str = "waiting_data",
    closure_status: str = "open",
    run_no: int | None = None,
    task_snapshot_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    anomaly_count: int = 0,
    error_message: str = "",
) -> dict | None:
    """创建自动运行批次记录（run）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if run_no is None:
                    cur.execute(
                        """
                        SELECT COALESCE(MAX(run_no), 0) + 1 AS next_run_no
                        FROM recon_auto_runs
                        WHERE auto_task_id = %s
                          AND biz_date = %s
                        """,
                        (auto_task_id, biz_date),
                    )
                    row = cur.fetchone()
                    run_no = int((row or {}).get("next_run_no") or 1)

                cur.execute(
                    """
                    INSERT INTO recon_auto_runs (
                        company_id, auto_task_id, biz_date, run_status, readiness_status, closure_status,
                        trigger_mode, run_no, task_snapshot_json, source_snapshot_json,
                        recon_result_summary_json, anomaly_count, error_message
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s, %s
                    )
                    RETURNING id, company_id, auto_task_id, biz_date, run_status, readiness_status, closure_status,
                              trigger_mode, run_no, task_snapshot_json, source_snapshot_json,
                              recon_result_summary_json, anomaly_count, started_at, finished_at, error_message,
                              created_at, updated_at
                    """,
                    (
                        company_id,
                        auto_task_id,
                        biz_date,
                        run_status,
                        readiness_status,
                        closure_status,
                        trigger_mode,
                        run_no,
                        psycopg2.extras.Json(task_snapshot_json or {}),
                        psycopg2.extras.Json(source_snapshot_json or {}),
                        psycopg2.extras.Json(recon_result_summary_json or {}),
                        anomaly_count,
                        error_message,
                    ),
                )
                created = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(created)) if created else None
    except Exception as e:
        logger.error(f"创建 recon_auto_runs 失败 (company_id={company_id}, auto_task_id={auto_task_id}, biz_date={biz_date}): {e}")
        return None


def get_recon_auto_run(*, company_id: str, auto_run_id: str) -> dict | None:
    """查询单个运行批次记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT r.id, r.company_id, r.auto_task_id, r.biz_date,
                           r.run_status, r.readiness_status, r.closure_status,
                           r.trigger_mode, r.run_no, r.task_snapshot_json, r.source_snapshot_json,
                           r.recon_result_summary_json, r.anomaly_count, r.started_at, r.finished_at,
                           r.error_message, r.created_at, r.updated_at,
                           t.task_name, t.rule_code
                    FROM recon_auto_runs r
                    JOIN recon_auto_tasks t ON t.id = r.auto_task_id
                    WHERE r.company_id = %s
                      AND r.id = %s
                    LIMIT 1
                    """,
                    (company_id, auto_run_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 recon_auto_runs 失败 (company_id={company_id}, id={auto_run_id}): {e}")
        return None


def list_recon_auto_runs(
    *,
    company_id: str,
    auto_task_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询运行批次记录列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT r.id, r.company_id, r.auto_task_id, r.biz_date,
                           r.run_status, r.readiness_status, r.closure_status,
                           r.trigger_mode, r.run_no, r.task_snapshot_json, r.source_snapshot_json,
                           r.recon_result_summary_json, r.anomaly_count, r.started_at, r.finished_at,
                           r.error_message, r.created_at, r.updated_at,
                           t.task_name, t.rule_code
                    FROM recon_auto_runs r
                    JOIN recon_auto_tasks t ON t.id = r.auto_task_id
                    WHERE r.company_id = %s
                """
                params: list[Any] = [company_id]
                if auto_task_id:
                    sql += " AND r.auto_task_id = %s"
                    params.append(auto_task_id)
                sql += " ORDER BY r.created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 recon_auto_runs 列表失败 (company_id={company_id}, auto_task_id={auto_task_id}): {e}")
        return []


def update_recon_auto_run_status(
    *,
    company_id: str,
    auto_run_id: str,
    run_status: str | None = None,
    readiness_status: str | None = None,
    closure_status: str | None = None,
    recon_result_summary_json: dict | None = None,
    anomaly_count: int | None = None,
    error_message: str | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
) -> dict | None:
    """更新运行批次状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_auto_runs
                    SET run_status = COALESCE(%s, run_status),
                        readiness_status = COALESCE(%s, readiness_status),
                        closure_status = COALESCE(%s, closure_status),
                        recon_result_summary_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN recon_result_summary_json
                            ELSE %s::jsonb
                        END,
                        anomaly_count = COALESCE(%s, anomaly_count),
                        error_message = COALESCE(%s, error_message),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, auto_task_id, biz_date, run_status, readiness_status, closure_status,
                              trigger_mode, run_no, task_snapshot_json, source_snapshot_json,
                              recon_result_summary_json, anomaly_count, started_at, finished_at, error_message,
                              created_at, updated_at
                    """,
                    (
                        run_status,
                        readiness_status,
                        closure_status,
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        anomaly_count,
                        error_message,
                        started_at_now,
                        finished_at_now,
                        auto_run_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_auto_runs 失败 (company_id={company_id}, id={auto_run_id}): {e}")
        return None


def create_recon_run_job(
    *,
    company_id: str,
    auto_run_id: str,
    job_type: str,
    job_status: str = "queued",
    attempt_no: int = 1,
    idempotency_key: str = "",
    input_json: dict | None = None,
    output_json: dict | None = None,
    error_message: str = "",
) -> dict | None:
    """创建 run 下的短动作执行记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_run_jobs (
                        company_id, auto_run_id, job_type, job_status, attempt_no,
                        idempotency_key, input_json, output_json, error_message
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s::jsonb, %s::jsonb, %s
                    )
                    RETURNING id, company_id, auto_run_id, job_type, job_status, attempt_no,
                              idempotency_key, started_at, finished_at, input_json, output_json,
                              error_message, created_at, updated_at
                    """,
                    (
                        company_id,
                        auto_run_id,
                        job_type,
                        job_status,
                        attempt_no,
                        idempotency_key,
                        psycopg2.extras.Json(input_json or {}),
                        psycopg2.extras.Json(output_json or {}),
                        error_message,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 recon_run_jobs 失败 (company_id={company_id}, auto_run_id={auto_run_id}, job_type={job_type}): {e}")
        return None


def update_recon_run_job(
    *,
    company_id: str,
    run_job_id: str,
    job_status: str | None = None,
    output_json: dict | None = None,
    error_message: str | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
) -> dict | None:
    """更新 run_job 状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_run_jobs
                    SET job_status = COALESCE(%s, job_status),
                        output_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN output_json
                            ELSE %s::jsonb
                        END,
                        error_message = COALESCE(%s, error_message),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, auto_run_id, job_type, job_status, attempt_no,
                              idempotency_key, started_at, finished_at, input_json, output_json,
                              error_message, created_at, updated_at
                    """,
                    (
                        job_status,
                        psycopg2.extras.Json(output_json) if output_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(output_json) if output_json is not None else psycopg2.extras.Json(None),
                        error_message,
                        started_at_now,
                        finished_at_now,
                        run_job_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_run_jobs 失败 (company_id={company_id}, id={run_job_id}): {e}")
        return None


def create_recon_exception_task(
    *,
    company_id: str,
    auto_task_id: str,
    auto_run_id: str,
    anomaly_key: str,
    anomaly_type: str,
    summary: str,
    detail_json: dict | None = None,
    owner_name: str = "",
    owner_identifier: str = "",
    owner_contact_json: dict | None = None,
    reminder_status: str = "pending",
    processing_status: str = "pending",
    fix_status: str = "pending",
    latest_feedback: str = "",
    feedback_json: dict | None = None,
    verify_required: bool = False,
    verify_run_id: str | None = None,
    is_closed: bool = False,
) -> dict | None:
    """创建或幂等更新异常任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_exception_tasks (
                        company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                        summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                        reminder_status, processing_status, fix_status, latest_feedback,
                        feedback_json, verify_required, verify_run_id, is_closed
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s::jsonb, %s, %s, %s::jsonb,
                        %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (auto_run_id, anomaly_key)
                    DO UPDATE SET
                        anomaly_type = EXCLUDED.anomaly_type,
                        summary = EXCLUDED.summary,
                        detail_json = EXCLUDED.detail_json,
                        owner_name = CASE
                            WHEN EXCLUDED.owner_name <> '' THEN EXCLUDED.owner_name
                            ELSE recon_exception_tasks.owner_name
                        END,
                        owner_identifier = CASE
                            WHEN EXCLUDED.owner_identifier <> '' THEN EXCLUDED.owner_identifier
                            ELSE recon_exception_tasks.owner_identifier
                        END,
                        owner_contact_json = CASE
                            WHEN EXCLUDED.owner_contact_json <> '{}'::jsonb THEN EXCLUDED.owner_contact_json
                            ELSE recon_exception_tasks.owner_contact_json
                        END,
                        reminder_status = EXCLUDED.reminder_status,
                        processing_status = EXCLUDED.processing_status,
                        fix_status = EXCLUDED.fix_status,
                        latest_feedback = CASE
                            WHEN EXCLUDED.latest_feedback <> '' THEN EXCLUDED.latest_feedback
                            ELSE recon_exception_tasks.latest_feedback
                        END,
                        feedback_json = CASE
                            WHEN EXCLUDED.feedback_json <> '{}'::jsonb THEN EXCLUDED.feedback_json
                            ELSE recon_exception_tasks.feedback_json
                        END,
                        verify_required = EXCLUDED.verify_required,
                        verify_run_id = COALESCE(EXCLUDED.verify_run_id, recon_exception_tasks.verify_run_id),
                        is_closed = EXCLUDED.is_closed,
                        closed_at = CASE
                            WHEN EXCLUDED.is_closed THEN COALESCE(recon_exception_tasks.closed_at, CURRENT_TIMESTAMP)
                            ELSE NULL
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                              summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status, latest_feedback,
                              feedback_json, verify_required, verify_run_id, last_verified_at,
                              is_closed, closed_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        auto_task_id,
                        auto_run_id,
                        anomaly_key,
                        anomaly_type,
                        summary,
                        psycopg2.extras.Json(detail_json or {}),
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json or {}),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json or {}),
                        verify_required,
                        verify_run_id,
                        is_closed,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 recon_exception_tasks 失败 (company_id={company_id}, auto_run_id={auto_run_id}, anomaly_key={anomaly_key}): {e}"
        )
        return None


def get_recon_exception_task(*, company_id: str, exception_id: str) -> dict | None:
    """查询单个异常任务。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                           summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status, latest_feedback,
                           feedback_json, verify_required, verify_run_id, last_verified_at,
                           is_closed, closed_at, created_at, updated_at
                    FROM recon_exception_tasks
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, exception_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 recon_exception_tasks 失败 (company_id={company_id}, id={exception_id}): {e}")
        return None


def list_recon_exception_tasks(
    *,
    company_id: str,
    auto_run_id: str,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """按运行批次查询异常任务列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                           summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status, latest_feedback,
                           feedback_json, verify_required, verify_run_id, last_verified_at,
                           is_closed, closed_at, created_at, updated_at
                    FROM recon_exception_tasks
                    WHERE company_id = %s
                      AND auto_run_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (company_id, auto_run_id, limit, offset),
                )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 recon_exception_tasks 失败 (company_id={company_id}, auto_run_id={auto_run_id}): {e}")
        return []


def update_recon_exception_task(
    *,
    company_id: str,
    exception_id: str,
    owner_name: str | None = None,
    owner_identifier: str | None = None,
    owner_contact_json: dict | None = None,
    reminder_status: str | None = None,
    processing_status: str | None = None,
    fix_status: str | None = None,
    latest_feedback: str | None = None,
    feedback_json: dict | None = None,
    verify_required: bool | None = None,
    verify_run_id: str | None = None,
    is_closed: bool | None = None,
) -> dict | None:
    """更新异常任务状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_exception_tasks
                    SET owner_name = COALESCE(%s, owner_name),
                        owner_identifier = COALESCE(%s, owner_identifier),
                        owner_contact_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_contact_json
                            ELSE %s::jsonb
                        END,
                        reminder_status = COALESCE(%s, reminder_status),
                        processing_status = COALESCE(%s, processing_status),
                        fix_status = COALESCE(%s, fix_status),
                        latest_feedback = COALESCE(%s, latest_feedback),
                        feedback_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN feedback_json
                            ELSE %s::jsonb
                        END,
                        verify_required = COALESCE(%s, verify_required),
                        verify_run_id = COALESCE(%s, verify_run_id),
                        last_verified_at = CASE WHEN %s IS NOT NULL THEN CURRENT_TIMESTAMP ELSE last_verified_at END,
                        is_closed = COALESCE(%s, is_closed),
                        closed_at = CASE
                            WHEN COALESCE(%s, false) THEN COALESCE(closed_at, CURRENT_TIMESTAMP)
                            ELSE NULL
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, auto_task_id, auto_run_id, anomaly_key, anomaly_type,
                              summary, detail_json, owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status, latest_feedback,
                              feedback_json, verify_required, verify_run_id, last_verified_at,
                              is_closed, closed_at, created_at, updated_at
                    """,
                    (
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        verify_required,
                        verify_run_id,
                        verify_run_id,
                        is_closed,
                        is_closed,
                        exception_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 recon_exception_tasks 失败 (company_id={company_id}, id={exception_id}): {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 执行模型（execution_schemes / execution_run_plans / execution_runs / execution_run_exceptions）
# ══════════════════════════════════════════════════════════════════════════════

def _generate_execution_code(prefix: str) -> str:
    import uuid as _uuid

    return f"{prefix}_{_uuid.uuid4().hex[:12]}"


def create_execution_scheme(
    *,
    company_id: str,
    scheme_name: str,
    scheme_code: str = "",
    scheme_type: str = "recon",
    description: str = "",
    file_rule_code: str = "",
    proc_rule_code: str = "",
    recon_rule_code: str = "",
    scheme_meta_json: dict | None = None,
    is_enabled: bool = True,
    created_by: str | None = None,
) -> dict | None:
    """创建执行方案。"""
    conn_manager = get_conn()
    try:
        resolved_scheme_code = str(scheme_code or "").strip() or _generate_execution_code("scheme")
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_schemes (
                        company_id, scheme_code, scheme_name, scheme_type, description,
                        file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                        is_enabled, created_by
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb,
                        %s, %s
                    )
                    RETURNING id, company_id, scheme_code, scheme_name, scheme_type, description,
                              file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        resolved_scheme_code,
                        scheme_name,
                        scheme_type,
                        description,
                        file_rule_code,
                        proc_rule_code,
                        recon_rule_code,
                        psycopg2.extras.Json(scheme_meta_json or {}),
                        is_enabled,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 execution_schemes 失败 (company_id={company_id}, scheme_name={scheme_name}): {e}")
        return None


def update_execution_scheme(
    *,
    company_id: str,
    scheme_id: str,
    scheme_name: str | None = None,
    scheme_type: str | None = None,
    description: str | None = None,
    file_rule_code: str | None = None,
    proc_rule_code: str | None = None,
    recon_rule_code: str | None = None,
    scheme_meta_json: dict | None = None,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新执行方案。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_schemes
                    SET scheme_name = COALESCE(%s, scheme_name),
                        scheme_type = COALESCE(%s, scheme_type),
                        description = COALESCE(%s, description),
                        file_rule_code = COALESCE(%s, file_rule_code),
                        proc_rule_code = COALESCE(%s, proc_rule_code),
                        recon_rule_code = COALESCE(%s, recon_rule_code),
                        scheme_meta_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN scheme_meta_json
                            ELSE %s::jsonb
                        END,
                        is_enabled = COALESCE(%s, is_enabled),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, scheme_code, scheme_name, scheme_type, description,
                              file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        scheme_name,
                        scheme_type,
                        description,
                        file_rule_code,
                        proc_rule_code,
                        recon_rule_code,
                        psycopg2.extras.Json(scheme_meta_json) if scheme_meta_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(scheme_meta_json) if scheme_meta_json is not None else psycopg2.extras.Json(None),
                        is_enabled,
                        scheme_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 execution_schemes 失败 (company_id={company_id}, scheme_id={scheme_id}): {e}")
        return None


def disable_execution_scheme(*, company_id: str, scheme_id: str) -> dict | None:
    """停用执行方案。"""
    return update_execution_scheme(company_id=company_id, scheme_id=scheme_id, is_enabled=False)


def get_execution_scheme(*, company_id: str, scheme_id: str | None = None, scheme_code: str | None = None) -> dict | None:
    """查询单个执行方案（按 id 或 scheme_code）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if scheme_id:
                    cur.execute(
                        """
                        SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                               file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_schemes
                        WHERE company_id = %s
                          AND id = %s
                        LIMIT 1
                        """,
                        (company_id, scheme_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                               file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_schemes
                        WHERE company_id = %s
                          AND scheme_code = %s
                        LIMIT 1
                        """,
                        (company_id, str(scheme_code or "").strip()),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 execution_schemes 失败 (company_id={company_id}, scheme_id={scheme_id}, scheme_code={scheme_code}): {e}"
        )
        return None


def list_execution_schemes(
    *,
    company_id: str,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询执行方案列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                           file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                           is_enabled, created_by, created_at, updated_at
                    FROM execution_schemes
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if not include_disabled:
                    sql += " AND is_enabled = true"
                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 execution_schemes 列表失败 (company_id={company_id}): {e}")
        return []


def create_execution_run_plan(
    *,
    company_id: str,
    plan_name: str,
    scheme_code: str,
    plan_code: str = "",
    schedule_type: str = "daily",
    schedule_expr: str = "",
    biz_date_offset: str = "previous_day",
    input_bindings_json: list[dict] | None = None,
    channel_config_id: str | None = None,
    owner_mapping_json: dict | None = None,
    plan_meta_json: dict | None = None,
    is_enabled: bool = True,
    created_by: str | None = None,
) -> dict | None:
    """创建执行运行计划。"""
    conn_manager = get_conn()
    try:
        resolved_plan_code = str(plan_code or "").strip() or _generate_execution_code("plan")
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_run_plans (
                        company_id, plan_code, plan_name, scheme_code,
                        schedule_type, schedule_expr, biz_date_offset,
                        input_bindings_json, channel_config_id,
                        owner_mapping_json, plan_meta_json,
                        is_enabled, created_by
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s,
                        %s::jsonb, %s::jsonb,
                        %s, %s
                    )
                    RETURNING id, company_id, plan_code, plan_name, scheme_code,
                              schedule_type, schedule_expr, biz_date_offset,
                              input_bindings_json, channel_config_id,
                              owner_mapping_json, plan_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        company_id,
                        resolved_plan_code,
                        plan_name,
                        scheme_code,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        psycopg2.extras.Json(input_bindings_json or []),
                        channel_config_id,
                        psycopg2.extras.Json(owner_mapping_json or {}),
                        psycopg2.extras.Json(plan_meta_json or {}),
                        is_enabled,
                        created_by,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 execution_run_plans 失败 (company_id={company_id}, plan_name={plan_name}): {e}")
        return None


def update_execution_run_plan(
    *,
    company_id: str,
    plan_id: str,
    plan_name: str | None = None,
    scheme_code: str | None = None,
    schedule_type: str | None = None,
    schedule_expr: str | None = None,
    biz_date_offset: str | None = None,
    input_bindings_json: list[dict] | None = None,
    channel_config_id: str | None = None,
    owner_mapping_json: dict | None = None,
    plan_meta_json: dict | None = None,
    is_enabled: bool | None = None,
) -> dict | None:
    """更新执行运行计划。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_run_plans
                    SET plan_name = COALESCE(%s, plan_name),
                        scheme_code = COALESCE(%s, scheme_code),
                        schedule_type = COALESCE(%s, schedule_type),
                        schedule_expr = COALESCE(%s, schedule_expr),
                        biz_date_offset = COALESCE(%s, biz_date_offset),
                        input_bindings_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN input_bindings_json
                            ELSE %s::jsonb
                        END,
                        channel_config_id = COALESCE(%s, channel_config_id),
                        owner_mapping_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_mapping_json
                            ELSE %s::jsonb
                        END,
                        plan_meta_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN plan_meta_json
                            ELSE %s::jsonb
                        END,
                        is_enabled = COALESCE(%s, is_enabled),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, plan_code, plan_name, scheme_code,
                              schedule_type, schedule_expr, biz_date_offset,
                              input_bindings_json, channel_config_id,
                              owner_mapping_json, plan_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (
                        plan_name,
                        scheme_code,
                        schedule_type,
                        schedule_expr,
                        biz_date_offset,
                        psycopg2.extras.Json(input_bindings_json) if input_bindings_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(input_bindings_json) if input_bindings_json is not None else psycopg2.extras.Json(None),
                        channel_config_id,
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_mapping_json) if owner_mapping_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(plan_meta_json) if plan_meta_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(plan_meta_json) if plan_meta_json is not None else psycopg2.extras.Json(None),
                        is_enabled,
                        plan_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 execution_run_plans 失败 (company_id={company_id}, plan_id={plan_id}): {e}")
        return None


def disable_execution_run_plan(*, company_id: str, plan_id: str) -> dict | None:
    """停用执行运行计划。"""
    return update_execution_run_plan(company_id=company_id, plan_id=plan_id, is_enabled=False)


def delete_execution_run_plan(*, company_id: str, plan_id: str) -> dict | None:
    """删除执行运行计划。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    DELETE FROM execution_run_plans
                    WHERE company_id = %s
                      AND id = %s
                    RETURNING id, company_id, plan_code, plan_name, scheme_code,
                              schedule_type, schedule_expr, biz_date_offset,
                              input_bindings_json, channel_config_id,
                              owner_mapping_json, plan_meta_json,
                              is_enabled, created_by, created_at, updated_at
                    """,
                    (company_id, plan_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"删除 execution_run_plans 失败 (company_id={company_id}, plan_id={plan_id}): {e}")
        return None


def get_execution_run_plan(*, company_id: str, plan_id: str | None = None, plan_code: str | None = None) -> dict | None:
    """查询单个执行运行计划（按 id 或 plan_code）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if plan_id:
                    cur.execute(
                        """
                        SELECT id, company_id, plan_code, plan_name, scheme_code,
                               schedule_type, schedule_expr, biz_date_offset,
                               input_bindings_json, channel_config_id,
                               owner_mapping_json, plan_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_run_plans
                        WHERE company_id = %s
                          AND id = %s
                        LIMIT 1
                        """,
                        (company_id, plan_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, plan_code, plan_name, scheme_code,
                               schedule_type, schedule_expr, biz_date_offset,
                               input_bindings_json, channel_config_id,
                               owner_mapping_json, plan_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_run_plans
                        WHERE company_id = %s
                          AND plan_code = %s
                        LIMIT 1
                        """,
                        (company_id, str(plan_code or "").strip()),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"查询 execution_run_plans 失败 (company_id={company_id}, plan_id={plan_id}, plan_code={plan_code}): {e}"
        )
        return None


def list_execution_run_plans(
    *,
    company_id: str,
    scheme_code: str | None = None,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询执行运行计划列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, plan_code, plan_name, scheme_code,
                           schedule_type, schedule_expr, biz_date_offset,
                           input_bindings_json, channel_config_id,
                           owner_mapping_json, plan_meta_json,
                           is_enabled, created_by, created_at, updated_at
                    FROM execution_run_plans
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if scheme_code:
                    sql += " AND scheme_code = %s"
                    params.append(scheme_code)
                if not include_disabled:
                    sql += " AND is_enabled = true"
                sql += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 execution_run_plans 列表失败 (company_id={company_id}, scheme_code={scheme_code}): {e}")
        return []


def list_enabled_execution_run_plans_for_scheduler(
    *,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    """供后台调度器查询全部启用中的运行计划。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, plan_code, plan_name, scheme_code,
                           schedule_type, schedule_expr, biz_date_offset,
                           input_bindings_json, channel_config_id,
                           owner_mapping_json, plan_meta_json,
                           is_enabled, created_by, created_at, updated_at
                    FROM execution_run_plans
                    WHERE is_enabled = true
                    ORDER BY updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询启用中的 execution_run_plans 失败 (limit={limit}, offset={offset}): {e}")
        return []


def get_execution_run_by_schedule_slot(
    *,
    company_id: str,
    plan_code: str,
    schedule_slot: str,
) -> dict | None:
    """按计划编码 + 调度窗口查询已触发的执行记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                           trigger_type, entry_mode, execution_status,
                           failed_stage, failed_reason,
                           run_context_json, source_snapshot_json, subtasks_json,
                           proc_result_json, recon_result_summary_json, artifacts_json,
                           anomaly_count, started_at, finished_at, created_at, updated_at
                    FROM execution_runs
                    WHERE company_id = %s
                      AND plan_code = %s
                      AND trigger_type = 'schedule'
                      AND COALESCE(run_context_json ->> 'schedule_slot', '') = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (company_id, plan_code, schedule_slot),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            "查询 execution_runs 调度窗口失败 "
            f"(company_id={company_id}, plan_code={plan_code}, schedule_slot={schedule_slot}): {e}"
        )
        return None


def create_execution_run(
    *,
    company_id: str,
    scheme_code: str,
    run_code: str = "",
    plan_code: str | None = None,
    scheme_type: str = "recon",
    trigger_type: str = "chat",
    entry_mode: str = "file",
    execution_status: str = "running",
    failed_stage: str = "",
    failed_reason: str = "",
    run_context_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    subtasks_json: list[dict] | None = None,
    proc_result_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    artifacts_json: dict | None = None,
    anomaly_count: int = 0,
    started_at_now: bool = True,
    finished_at_now: bool = False,
) -> dict | None:
    """创建执行记录。"""
    conn_manager = get_conn()
    try:
        resolved_run_code = str(run_code or "").strip() or _generate_execution_code("run")
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_runs (
                        company_id, run_code, scheme_code, plan_code, scheme_type,
                        trigger_type, entry_mode, execution_status,
                        failed_stage, failed_reason,
                        run_context_json, source_snapshot_json, subtasks_json,
                        proc_result_json, recon_result_summary_json, artifacts_json,
                        anomaly_count, started_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s,
                        CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                        CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END
                    )
                    RETURNING id, company_id, run_code, scheme_code, plan_code, scheme_type,
                              trigger_type, entry_mode, execution_status,
                              failed_stage, failed_reason,
                              run_context_json, source_snapshot_json, subtasks_json,
                              proc_result_json, recon_result_summary_json, artifacts_json,
                              anomaly_count, started_at, finished_at, created_at, updated_at
                    """,
                    (
                        company_id,
                        resolved_run_code,
                        scheme_code,
                        plan_code,
                        scheme_type,
                        trigger_type,
                        entry_mode,
                        execution_status,
                        failed_stage,
                        failed_reason,
                        psycopg2.extras.Json(run_context_json or {}),
                        psycopg2.extras.Json(source_snapshot_json or {}),
                        psycopg2.extras.Json(subtasks_json or []),
                        psycopg2.extras.Json(proc_result_json or {}),
                        psycopg2.extras.Json(recon_result_summary_json or {}),
                        psycopg2.extras.Json(artifacts_json or {}),
                        max(0, int(anomaly_count)),
                        started_at_now,
                        finished_at_now,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"创建 execution_runs 失败 (company_id={company_id}, scheme_code={scheme_code}): {e}")
        return None


def update_execution_run(
    *,
    company_id: str,
    run_id: str,
    execution_status: str | None = None,
    failed_stage: str | None = None,
    failed_reason: str | None = None,
    run_context_json: dict | None = None,
    source_snapshot_json: dict | None = None,
    subtasks_json: list[dict] | None = None,
    proc_result_json: dict | None = None,
    recon_result_summary_json: dict | None = None,
    artifacts_json: dict | None = None,
    anomaly_count: int | None = None,
    started_at_now: bool = False,
    finished_at_now: bool = False,
) -> dict | None:
    """更新执行记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_runs
                    SET execution_status = COALESCE(%s, execution_status),
                        failed_stage = COALESCE(%s, failed_stage),
                        failed_reason = COALESCE(%s, failed_reason),
                        run_context_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN run_context_json
                            ELSE %s::jsonb
                        END,
                        source_snapshot_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN source_snapshot_json
                            ELSE %s::jsonb
                        END,
                        subtasks_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN subtasks_json
                            ELSE %s::jsonb
                        END,
                        proc_result_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN proc_result_json
                            ELSE %s::jsonb
                        END,
                        recon_result_summary_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN recon_result_summary_json
                            ELSE %s::jsonb
                        END,
                        artifacts_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN artifacts_json
                            ELSE %s::jsonb
                        END,
                        anomaly_count = COALESCE(%s, anomaly_count),
                        started_at = CASE WHEN %s THEN COALESCE(started_at, CURRENT_TIMESTAMP) ELSE started_at END,
                        finished_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE finished_at END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, run_code, scheme_code, plan_code, scheme_type,
                              trigger_type, entry_mode, execution_status,
                              failed_stage, failed_reason,
                              run_context_json, source_snapshot_json, subtasks_json,
                              proc_result_json, recon_result_summary_json, artifacts_json,
                              anomaly_count, started_at, finished_at, created_at, updated_at
                    """,
                    (
                        execution_status,
                        failed_stage,
                        failed_reason,
                        psycopg2.extras.Json(run_context_json) if run_context_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(run_context_json) if run_context_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(source_snapshot_json) if source_snapshot_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(source_snapshot_json) if source_snapshot_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(subtasks_json) if subtasks_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(subtasks_json) if subtasks_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(proc_result_json) if proc_result_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(proc_result_json) if proc_result_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(recon_result_summary_json) if recon_result_summary_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(artifacts_json) if artifacts_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(artifacts_json) if artifacts_json is not None else psycopg2.extras.Json(None),
                        anomaly_count,
                        started_at_now,
                        finished_at_now,
                        run_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"更新 execution_runs 失败 (company_id={company_id}, run_id={run_id}): {e}")
        return None


def get_execution_run(*, company_id: str, run_id: str | None = None, run_code: str | None = None) -> dict | None:
    """查询单个执行记录（按 id 或 run_code）。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if run_id:
                    cur.execute(
                        """
                        SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                               trigger_type, entry_mode, execution_status,
                               failed_stage, failed_reason,
                               run_context_json, source_snapshot_json, subtasks_json,
                               proc_result_json, recon_result_summary_json, artifacts_json,
                               anomaly_count, started_at, finished_at, created_at, updated_at
                        FROM execution_runs
                        WHERE company_id = %s
                          AND id = %s
                        LIMIT 1
                        """,
                        (company_id, run_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                               trigger_type, entry_mode, execution_status,
                               failed_stage, failed_reason,
                               run_context_json, source_snapshot_json, subtasks_json,
                               proc_result_json, recon_result_summary_json, artifacts_json,
                               anomaly_count, started_at, finished_at, created_at, updated_at
                        FROM execution_runs
                        WHERE company_id = %s
                          AND run_code = %s
                        LIMIT 1
                        """,
                        (company_id, str(run_code or "").strip()),
                    )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 execution_runs 失败 (company_id={company_id}, run_id={run_id}, run_code={run_code}): {e}")
        return None


def list_execution_runs(
    *,
    company_id: str,
    scheme_code: str | None = None,
    plan_code: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询执行记录列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                           trigger_type, entry_mode, execution_status,
                           failed_stage, failed_reason,
                           run_context_json, source_snapshot_json, subtasks_json,
                           proc_result_json, recon_result_summary_json, artifacts_json,
                           anomaly_count, started_at, finished_at, created_at, updated_at
                    FROM execution_runs
                    WHERE company_id = %s
                """
                params: list[Any] = [company_id]
                if scheme_code:
                    sql += " AND scheme_code = %s"
                    params.append(scheme_code)
                if plan_code:
                    sql += " AND plan_code = %s"
                    params.append(plan_code)
                sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            f"查询 execution_runs 列表失败 (company_id={company_id}, scheme_code={scheme_code}, plan_code={plan_code}): {e}"
        )
        return []


def delete_execution_run(*, company_id: str, run_id: str) -> dict | None:
    """删除执行记录。

    execution_run_exceptions.run_id 使用 ON DELETE CASCADE，删除运行记录会同步清理异常。
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    DELETE FROM execution_runs
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, run_code, scheme_code, plan_code, scheme_type,
                              trigger_type, entry_mode, execution_status,
                              failed_stage, failed_reason,
                              run_context_json, source_snapshot_json, subtasks_json,
                              proc_result_json, recon_result_summary_json, artifacts_json,
                              anomaly_count, started_at, finished_at, created_at, updated_at
                    """,
                    (run_id, company_id),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"删除 execution_runs 失败 (company_id={company_id}, run_id={run_id}): {e}")
        return None


def create_execution_run_exception(
    *,
    company_id: str,
    run_id: str,
    scheme_code: str,
    anomaly_key: str,
    anomaly_type: str,
    summary: str,
    detail_json: dict | None = None,
    owner_name: str = "",
    owner_identifier: str = "",
    owner_contact_json: dict | None = None,
    reminder_status: str = "pending",
    processing_status: str = "pending",
    fix_status: str = "pending",
    latest_feedback: str = "",
    feedback_json: dict | None = None,
    is_closed: bool = False,
) -> dict | None:
    """创建或幂等更新执行异常。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO execution_run_exceptions (
                        company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                        summary, detail_json,
                        owner_name, owner_identifier, owner_contact_json,
                        reminder_status, processing_status, fix_status,
                        latest_feedback, feedback_json, is_closed
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s::jsonb,
                        %s, %s, %s::jsonb,
                        %s, %s, %s,
                        %s, %s::jsonb, %s
                    )
                    ON CONFLICT (run_id, anomaly_key)
                    DO UPDATE SET
                        anomaly_type = EXCLUDED.anomaly_type,
                        summary = EXCLUDED.summary,
                        detail_json = EXCLUDED.detail_json,
                        owner_name = CASE
                            WHEN EXCLUDED.owner_name <> '' THEN EXCLUDED.owner_name
                            ELSE execution_run_exceptions.owner_name
                        END,
                        owner_identifier = CASE
                            WHEN EXCLUDED.owner_identifier <> '' THEN EXCLUDED.owner_identifier
                            ELSE execution_run_exceptions.owner_identifier
                        END,
                        owner_contact_json = CASE
                            WHEN EXCLUDED.owner_contact_json <> '{}'::jsonb THEN EXCLUDED.owner_contact_json
                            ELSE execution_run_exceptions.owner_contact_json
                        END,
                        reminder_status = EXCLUDED.reminder_status,
                        processing_status = EXCLUDED.processing_status,
                        fix_status = EXCLUDED.fix_status,
                        latest_feedback = CASE
                            WHEN EXCLUDED.latest_feedback <> '' THEN EXCLUDED.latest_feedback
                            ELSE execution_run_exceptions.latest_feedback
                        END,
                        feedback_json = CASE
                            WHEN EXCLUDED.feedback_json <> '{}'::jsonb THEN EXCLUDED.feedback_json
                            ELSE execution_run_exceptions.feedback_json
                        END,
                        is_closed = EXCLUDED.is_closed,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                              summary, detail_json,
                              owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status,
                              latest_feedback, feedback_json, is_closed, created_at, updated_at
                    """,
                    (
                        company_id,
                        run_id,
                        scheme_code,
                        anomaly_key,
                        anomaly_type,
                        summary,
                        psycopg2.extras.Json(detail_json or {}),
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json or {}),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json or {}),
                        is_closed,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"创建 execution_run_exceptions 失败 (company_id={company_id}, run_id={run_id}, anomaly_key={anomaly_key}): {e}"
        )
        return None


def get_execution_run_exception(*, company_id: str, exception_id: str) -> dict | None:
    """查询单个执行异常。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                           summary, detail_json,
                           owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status,
                           latest_feedback, feedback_json, is_closed, created_at, updated_at
                    FROM execution_run_exceptions
                    WHERE company_id = %s
                      AND id = %s
                    LIMIT 1
                    """,
                    (company_id, exception_id),
                )
                row = cur.fetchone()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"查询 execution_run_exceptions 失败 (company_id={company_id}, exception_id={exception_id}): {e}")
        return None


def list_execution_run_exceptions(
    *,
    company_id: str,
    run_id: str,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    """按执行记录查询异常列表。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                           summary, detail_json,
                           owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status,
                           latest_feedback, feedback_json, is_closed, created_at, updated_at
                    FROM execution_run_exceptions
                    WHERE company_id = %s
                      AND run_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (company_id, run_id, limit, offset),
                )
                rows = cur.fetchall()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(f"查询 execution_run_exceptions 列表失败 (company_id={company_id}, run_id={run_id}): {e}")
        return []


def get_public_execution_run_exception_bundle(
    *,
    run_id: str,
    owner_identifier: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict | None:
    """公开只读查询一次执行运行及其异常明细。

    第一版公开分享链接依赖不可猜的 run UUID，不要求登录；因此这里只返回
    展示异常详情必要的方案、运行计划和异常数据，不返回任何授权密钥。
    """
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return None

    safe_limit = max(1, min(int(limit or 100), 500))
    safe_offset = max(0, int(offset or 0))
    normalized_owner = str(owner_identifier or "").strip()
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, company_id, run_code, scheme_code, plan_code, scheme_type,
                           trigger_type, entry_mode, execution_status,
                           failed_stage, failed_reason,
                           run_context_json, source_snapshot_json, subtasks_json,
                           proc_result_json, recon_result_summary_json, artifacts_json,
                           anomaly_count, started_at, finished_at, created_at, updated_at
                    FROM execution_runs
                    WHERE id = %s
                    LIMIT 1
                    """,
                    (normalized_run_id,),
                )
                run_row = cur.fetchone()
                if not run_row:
                    return None
                run = _normalize_record(dict(run_row))
                company_id = str(run.get("company_id") or "")
                scheme_code = str(run.get("scheme_code") or "")
                plan_code = str(run.get("plan_code") or "")

                scheme: dict = {}
                if scheme_code:
                    cur.execute(
                        """
                        SELECT id, company_id, scheme_code, scheme_name, scheme_type, description,
                               file_rule_code, proc_rule_code, recon_rule_code, scheme_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_schemes
                        WHERE company_id = %s
                          AND scheme_code = %s
                        LIMIT 1
                        """,
                        (company_id, scheme_code),
                    )
                    scheme_row = cur.fetchone()
                    scheme = _normalize_record(dict(scheme_row)) if scheme_row else {}

                run_plan: dict = {}
                if plan_code:
                    cur.execute(
                        """
                        SELECT id, company_id, plan_code, plan_name, scheme_code,
                               schedule_type, schedule_expr, biz_date_offset,
                               input_bindings_json, channel_config_id,
                               owner_mapping_json, plan_meta_json,
                               is_enabled, created_by, created_at, updated_at
                        FROM execution_run_plans
                        WHERE company_id = %s
                          AND plan_code = %s
                        LIMIT 1
                        """,
                        (company_id, plan_code),
                    )
                    plan_row = cur.fetchone()
                    run_plan = _normalize_record(dict(plan_row)) if plan_row else {}

                cur.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM execution_run_exceptions
                    WHERE run_id = %s
                      AND (%s = '' OR owner_identifier = %s)
                    """,
                    (normalized_run_id, normalized_owner, normalized_owner),
                )
                total_row = cur.fetchone() or {}
                total = int(total_row.get("total") or 0)

                cur.execute(
                    """
                    SELECT id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                           summary, detail_json,
                           owner_name, owner_identifier, owner_contact_json,
                           reminder_status, processing_status, fix_status,
                           latest_feedback, feedback_json, is_closed, created_at, updated_at
                    FROM execution_run_exceptions
                    WHERE run_id = %s
                      AND (%s = '' OR owner_identifier = %s)
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (normalized_run_id, normalized_owner, normalized_owner, safe_limit, safe_offset),
                )
                exception_rows = cur.fetchall()
                exceptions = [_normalize_record(dict(row)) for row in exception_rows]

                return {
                    "run": run,
                    "scheme": scheme,
                    "run_plan": run_plan,
                    "exceptions": exceptions,
                    "count": len(exceptions),
                    "total": total,
                    "limit": safe_limit,
                    "offset": safe_offset,
                }
    except Exception as e:
        logger.error(f"公开查询 execution_run_exceptions 失败 (run_id={run_id}): {e}")
        return None


def bulk_update_execution_run_exceptions_by_owner(
    *,
    company_id: str,
    run_id: str,
    owner_identifier: str = "",
    reminder_status: str | None = None,
    processing_status: str | None = None,
    fix_status: str | None = None,
    latest_feedback: str | None = None,
    feedback_patch_json: dict | None = None,
) -> list[dict]:
    """按运行批次和责任人批量更新异常状态。"""
    normalized_company_id = str(company_id or "").strip()
    normalized_run_id = str(run_id or "").strip()
    normalized_owner = str(owner_identifier or "").strip()
    if not normalized_company_id or not normalized_run_id:
        return []

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                owner_clause = ""
                params: list[Any] = [
                    reminder_status,
                    processing_status,
                    fix_status,
                    latest_feedback,
                    psycopg2.extras.Json(feedback_patch_json or {}),
                    psycopg2.extras.Json(feedback_patch_json or {}),
                    normalized_company_id,
                    normalized_run_id,
                ]
                if normalized_owner:
                    owner_clause = " AND owner_identifier = %s"
                    params.append(normalized_owner)

                cur.execute(
                    f"""
                    UPDATE execution_run_exceptions
                    SET reminder_status = COALESCE(%s, reminder_status),
                        processing_status = COALESCE(%s, processing_status),
                        fix_status = COALESCE(%s, fix_status),
                        latest_feedback = COALESCE(%s, latest_feedback),
                        feedback_json = CASE
                            WHEN %s::jsonb = '{{}}'::jsonb THEN feedback_json
                            ELSE COALESCE(feedback_json, '{{}}'::jsonb) || %s::jsonb
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND run_id = %s
                      {owner_clause}
                    RETURNING id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                              summary, detail_json,
                              owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status,
                              latest_feedback, feedback_json, is_closed, created_at, updated_at
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                conn.commit()
                return [_normalize_record(dict(row)) for row in rows]
    except Exception as e:
        logger.error(
            "批量更新 execution_run_exceptions 失败 "
            f"(company_id={company_id}, run_id={run_id}, owner_identifier={owner_identifier}): {e}"
        )
        return []


def update_execution_run_exception(
    *,
    company_id: str,
    exception_id: str,
    owner_name: str | None = None,
    owner_identifier: str | None = None,
    owner_contact_json: dict | None = None,
    reminder_status: str | None = None,
    processing_status: str | None = None,
    fix_status: str | None = None,
    latest_feedback: str | None = None,
    feedback_json: dict | None = None,
    is_closed: bool | None = None,
) -> dict | None:
    """更新执行异常状态。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE execution_run_exceptions
                    SET owner_name = COALESCE(%s, owner_name),
                        owner_identifier = COALESCE(%s, owner_identifier),
                        owner_contact_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN owner_contact_json
                            ELSE %s::jsonb
                        END,
                        reminder_status = COALESCE(%s, reminder_status),
                        processing_status = COALESCE(%s, processing_status),
                        fix_status = COALESCE(%s, fix_status),
                        latest_feedback = COALESCE(%s, latest_feedback),
                        feedback_json = CASE
                            WHEN %s::jsonb = 'null'::jsonb THEN feedback_json
                            ELSE %s::jsonb
                        END,
                        is_closed = COALESCE(%s, is_closed),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                      AND company_id = %s
                    RETURNING id, company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                              summary, detail_json,
                              owner_name, owner_identifier, owner_contact_json,
                              reminder_status, processing_status, fix_status,
                              latest_feedback, feedback_json, is_closed, created_at, updated_at
                    """,
                    (
                        owner_name,
                        owner_identifier,
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(owner_contact_json) if owner_contact_json is not None else psycopg2.extras.Json(None),
                        reminder_status,
                        processing_status,
                        fix_status,
                        latest_feedback,
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        psycopg2.extras.Json(feedback_json) if feedback_json is not None else psycopg2.extras.Json(None),
                        is_closed,
                        exception_id,
                        company_id,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(
            f"更新 execution_run_exceptions 失败 (company_id={company_id}, exception_id={exception_id}): {e}"
        )
        return None


# ──────────────────────────────────────────────────────────────────────────────
# recon_execution_queue  （持久化对账执行队列）
# ──────────────────────────────────────────────────────────────────────────────

def enqueue_recon_run(
    *,
    company_id: str,
    run_plan_code: str,
    biz_date: str = "",
    trigger_mode: str = "schedule",
    run_context: dict | None = None,
) -> dict:
    """把一次对账执行请求写入队列，返回创建的 job 记录。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO recon_execution_queue
                        (company_id, run_plan_code, biz_date, trigger_mode, run_context, status)
                    VALUES (%s, %s, %s, %s, %s::jsonb, 'queued')
                    RETURNING *
                    """,
                    (
                        company_id,
                        run_plan_code,
                        biz_date or "",
                        trigger_mode or "schedule",
                        json.dumps(run_context or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row))
    except Exception as e:
        logger.error(f"enqueue_recon_run 失败 (run_plan_code={run_plan_code}): {e}")
        raise


def dequeue_recon_run() -> dict | None:
    """原子地取出并锁定一条 queued job（SKIP LOCKED），置为 running 后返回。
    无可用任务时返回 None。
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'running',
                        started_at = CURRENT_TIMESTAMP,
                        attempt = attempt + 1
                    WHERE id = (
                        SELECT id FROM recon_execution_queue
                        WHERE status = 'queued'
                        ORDER BY created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING *
                    """
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"dequeue_recon_run 失败: {e}")
        return None


def complete_recon_run(job_id: str) -> dict | None:
    """将 job 标记为 done。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'done', finished_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    RETURNING *
                    """,
                    (job_id,),
                )
                row = cur.fetchone()
                conn.commit()
                return _normalize_record(dict(row)) if row else None
    except Exception as e:
        logger.error(f"complete_recon_run 失败 (job_id={job_id}): {e}")
        return None


def fail_recon_run(job_id: str, error: str = "") -> None:
    """将 job 标记为 failed 并记录错误信息。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'failed', finished_at = CURRENT_TIMESTAMP, error = %s
                    WHERE id = %s
                    """,
                    (str(error or "")[:4000], job_id),
                )
                conn.commit()
    except Exception as e:
        logger.error(f"fail_recon_run 失败 (job_id={job_id}): {e}")


def reclaim_stale_recon_runs(timeout_minutes: int = 15) -> int:
    """把卡在 running 超过 timeout_minutes 的 job 重置回 queued，返回重置数量。"""
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE recon_execution_queue
                    SET status = 'queued', started_at = NULL
                    WHERE status = 'running'
                      AND started_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
                    """,
                    (max(1, timeout_minutes),),
                )
                count = cur.rowcount
                conn.commit()
                return count
    except Exception as e:
        logger.error(f"reclaim_stale_recon_runs 失败: {e}")
        return 0

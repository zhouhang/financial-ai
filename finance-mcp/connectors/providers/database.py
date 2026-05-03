"""Database source connector."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, timedelta
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2 import sql as pg_sql

from connectors.base import BaseDataSourceConnector

logger = logging.getLogger(__name__)

_DATASET_CODE_PATTERN = re.compile(r"[^a-z0-9_]+")
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_POSTGRES_DISCOVER_RELKINDS = ("r", "v", "m", "f", "p")
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
_DATE_FILTER_MARKER = "__collection_date_filter__"


def _normalize_db_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"hologres", "holo"}:
        return "postgresql"
    if normalized in {"postgres", "postgresql", "pg"}:
        return "postgresql"
    if normalized in {"mysql", "mariadb"}:
        return "mysql"
    if normalized in {"sqlite", "sqlite3"}:
        return "sqlite"
    return normalized or "postgresql"


def _sanitize_dataset_code(*parts: str) -> str:
    text = "_".join(part.strip().lower() for part in parts if part and part.strip())
    text = _DATASET_CODE_PATTERN.sub("_", text).strip("_")
    if not text:
        return "dataset"
    return text[:120]


def _split_identifier_text(raw: str) -> list[str]:
    parts = re.split(r"[\n,]+", str(raw or ""))
    return [part.strip() for part in parts if part and part.strip()]


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_target_resource_keys(value: Any) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, str):
        raw_items.extend(_split_identifier_text(value))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                raw_items.extend(_split_identifier_text(item))
            else:
                text = str(item or "").strip()
                if text:
                    raw_items.append(text)
    else:
        text = str(value or "").strip()
        if text:
            raw_items.append(text)

    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        text = item.strip().strip("`").strip('"').strip("'")
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
    return normalized


def _compact_error_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _friendly_database_error(exc: Exception) -> str:
    detail = _compact_error_text(exc)
    lowered = detail.lower()

    if "password authentication failed" in lowered or "authentication failed" in lowered:
        return "数据库认证失败：用户名或密码错误"
    if "timeout expired" in lowered or "timed out" in lowered or "connect timeout" in lowered:
        return "数据库连接超时，请检查网络、白名单和端口配置"
    if "connection refused" in lowered or "could not connect to server" in lowered:
        return "数据库连接失败：无法连接到数据库主机或端口"
    if "no pg_hba.conf entry" in lowered or "not allowed to connect" in lowered:
        return "数据库连接被拒绝，请检查白名单或访问控制配置"

    return detail or "数据库连接失败"


def _is_hologres_source(provider_code: Any, db_type: Any) -> bool:
    normalized_provider = str(provider_code or "").strip().lower()
    normalized_db_type = str(db_type or "").strip().lower()
    return normalized_provider in {"hologres", "holo"} or normalized_db_type in {"hologres", "holo"}


def _is_hologres_worker_info_permission_error(exc: Exception) -> bool:
    detail = _compact_error_text(exc).lower()
    return "hg_get_worker_info" in detail and (
        "must be superuser" in detail or "insufficientprivilege" in detail or "permission denied" in detail
    )


def _parse_requested_objects(resource_keys: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for resource_key in resource_keys:
        text = str(resource_key or "").strip()
        if not text:
            continue
        if "." in text:
            schema_name, table_name = text.split(".", 1)
            parsed.append(
                {
                    "schema_name": schema_name.strip(),
                    "table_name": table_name.strip(),
                    "resource_key": f"{schema_name.strip()}.{table_name.strip()}".strip("."),
                }
            )
        else:
            parsed.append(
                {
                    "schema_name": "",
                    "table_name": text,
                    "resource_key": text,
                }
            )
    return parsed


def _build_sync_strategy(columns: list[dict[str, Any]]) -> dict[str, Any]:
    cursor_candidates = {
        "updated_at",
        "modified_at",
        "last_updated_at",
        "update_time",
        "modified_time",
        "updated_time",
    }
    for item in columns:
        column_name = str(item.get("name") or "").strip().lower()
        if column_name in cursor_candidates:
            return {"mode": "incremental", "cursor_field": column_name}
    return {"mode": "full"}


def _postgres_relkind_to_dataset_kind(relkind: str) -> str:
    normalized = str(relkind or "").strip().lower()
    if normalized in {"v", "m"}:
        return "view"
    return "table"


def _postgres_relkind_to_object_type(relkind: str) -> str:
    normalized = str(relkind or "").strip().lower()
    if normalized == "v":
        return "view"
    if normalized == "m":
        return "materialized_view"
    if normalized == "f":
        return "foreign_table"
    if normalized == "p":
        return "partitioned_table"
    return "table"


class DatabaseConnector(BaseDataSourceConnector):
    source_kind = "database"
    execution_mode = "deterministic"

    @property
    def capabilities(self) -> list[str]:
        return ["test", "discover_datasets", "list_datasets", "list_events", "sync", "preview"]

    def _resolved_connection_config(self) -> dict[str, Any]:
        connection_config = dict(self.ctx.config.get("connection_config") or {})
        auth_config = dict(self.ctx.config.get("auth_config") or {})

        if not connection_config.get("username"):
            connection_config["username"] = (
                auth_config.get("username")
                or auth_config.get("user")
                or auth_config.get("account")
                or ""
            )
        if not connection_config.get("password"):
            connection_config["password"] = (
                auth_config.get("password")
                or auth_config.get("pass")
                or auth_config.get("passwd")
                or auth_config.get("token")
                or ""
            )
        if not connection_config.get("db_type"):
            connection_config["db_type"] = self.ctx.provider_code or "postgresql"

        return connection_config

    def _validate_connection_config(self, cfg: dict[str, Any]) -> list[str]:
        db_type = _normalize_db_type(cfg.get("db_type"))
        if db_type in {"postgresql", "mysql"}:
            required = ["host", "port", "database", "username", "password"]
        elif db_type == "sqlite":
            required = ["database"]
        else:
            required = ["db_type"]
        return [key for key in required if not str(cfg.get(key) or "").strip()]

    def _connect_postgresql(self, cfg: dict[str, Any]):
        connect_kwargs: dict[str, Any] = {
            "host": str(cfg.get("host") or ""),
            "port": _to_int(cfg.get("port"), 5432),
            "dbname": str(cfg.get("database") or ""),
            "user": str(cfg.get("username") or ""),
            "password": str(cfg.get("password") or ""),
            # 连接超时不再开放配置，统一固定为 5 秒。
            "connect_timeout": DEFAULT_CONNECT_TIMEOUT_SECONDS,
        }
        ssl_mode = str(cfg.get("ssl_mode") or "").strip().lower()
        if ssl_mode:
            connect_kwargs["sslmode"] = ssl_mode
        return psycopg2.connect(**connect_kwargs)

    def _connect_mysql(self, cfg: dict[str, Any]):
        try:
            import pymysql  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "mysql 连接需要安装 pymysql 依赖"
            ) from exc

        connect_kwargs: dict[str, Any] = {
            "host": str(cfg.get("host") or ""),
            "port": _to_int(cfg.get("port"), 3306),
            "user": str(cfg.get("username") or ""),
            "password": str(cfg.get("password") or ""),
            "database": str(cfg.get("database") or ""),
            "connect_timeout": DEFAULT_CONNECT_TIMEOUT_SECONDS,
            "read_timeout": _to_int(cfg.get("read_timeout"), 10),
            "write_timeout": _to_int(cfg.get("write_timeout"), 10),
            "cursorclass": pymysql.cursors.DictCursor,
        }
        ssl_mode = str(cfg.get("ssl_mode") or "").strip().lower()
        if ssl_mode and ssl_mode not in {"disable", "disabled", "off", "false", "0"}:
            # PyMySQL 不支持 PostgreSQL 风格 sslmode，这里按“开启 SSL”做最小映射。
            connect_kwargs["ssl"] = {}
        return pymysql.connect(**connect_kwargs)

    def _connect_sqlite(self, cfg: dict[str, Any]):
        database_path = str(cfg.get("database") or cfg.get("path") or "").strip()
        if not database_path:
            raise RuntimeError("sqlite 配置缺失: database")
        return sqlite3.connect(database_path, timeout=DEFAULT_CONNECT_TIMEOUT_SECONDS)

    def _open_connection(self, cfg: dict[str, Any]):
        db_type = _normalize_db_type(cfg.get("db_type"))
        if db_type == "postgresql":
            return self._connect_postgresql(cfg)
        if db_type == "mysql":
            return self._connect_mysql(cfg)
        if db_type == "sqlite":
            return self._connect_sqlite(cfg)
        raise RuntimeError(f"暂不支持的 db_type: {db_type}")

    def _extract_schema_whitelist(
        self,
        arguments: dict[str, Any],
        cfg: dict[str, Any],
    ) -> list[str]:
        raw = arguments.get("schema_whitelist")
        if raw is None:
            raw = cfg.get("schema_whitelist")
        if isinstance(raw, str):
            items = [item.strip() for item in raw.split(",")]
            return [item for item in items if item]
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return []

    def test_connection(self, arguments):
        cfg = self._resolved_connection_config()
        db_type = _normalize_db_type(cfg.get("db_type"))
        missing = self._validate_connection_config(cfg)
        if missing:
            return {"success": False, "error": f"database 配置缺失: {', '.join(missing)}"}

        conn = None
        cur = None
        try:
            conn = self._open_connection(cfg)
            if db_type == "sqlite":
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
            else:
                cur = conn.cursor()
                cur.execute("SELECT 1")
                cur.fetchone()
            message = "数据库连接成功"
        except Exception as exc:
            logger.error("database test connection failed: %s", exc, exc_info=True)
            detail = _friendly_database_error(exc)
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "error": detail,
                "message": detail,
            }
        finally:
            try:
                if cur is not None:
                    cur.close()
            except Exception:
                pass
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "db_type": db_type,
            "message": message,
        }

    def trigger_sync(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cfg = self._resolved_connection_config()
        db_type = _normalize_db_type(cfg.get("db_type"))
        missing = self._validate_connection_config(cfg)
        if missing:
            return {"success": False, "error": f"database 配置缺失: {', '.join(missing)}"}

        schema_name, table_name, filters = self._resolve_sync_target(arguments)
        if not table_name:
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "error": "missing_table",
                "message": "同步数据需要提供 resource_key 或表名",
            }

        try:
            if db_type == "postgresql":
                rows = self._sync_postgresql(cfg, schema_name or "public", table_name, filters)
            elif db_type == "mysql":
                rows = self._sync_mysql(cfg, schema_name or str(cfg.get("database") or ""), table_name, filters)
            elif db_type == "sqlite":
                rows = self._sync_sqlite(cfg, table_name, filters)
            else:
                return {
                    "success": False,
                    "source_id": self.ctx.source_id,
                    "error": f"unsupported_db_type:{db_type}",
                    "message": f"暂不支持 {db_type} 的同步",
                }
        except Exception as exc:
            logger.error("database trigger sync failed: %s", exc, exc_info=True)
            detail = _friendly_database_error(exc)
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "error": detail,
                "message": detail,
            }

        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "rows_ingested": len(rows),
            "rows": rows,
            "message": f"已同步 {len(rows)} 行数据库数据",
        }

    def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cfg = self._resolved_connection_config()
        db_type = _normalize_db_type(cfg.get("db_type"))
        missing = self._validate_connection_config(cfg)
        if missing:
            return {"success": False, "error": f"database 配置缺失: {', '.join(missing)}"}

        schema_whitelist = self._extract_schema_whitelist(arguments, cfg)
        limit = max(1, min(_to_int(arguments.get("limit"), 300), 1000))
        offset = max(0, _to_int(arguments.get("offset"), 0))
        target_resource_keys = _normalize_target_resource_keys(arguments.get("target_resource_keys"))

        try:
            if db_type == "postgresql":
                discover_payload = self._discover_postgresql(
                    cfg,
                    schema_whitelist=schema_whitelist,
                    limit=limit,
                    offset=offset,
                    target_resource_keys=target_resource_keys,
                )
            elif db_type == "mysql":
                discover_payload = self._discover_mysql(
                    cfg,
                    limit=limit,
                    offset=offset,
                    target_resource_keys=target_resource_keys,
                )
            elif db_type == "sqlite":
                discover_payload = self._discover_sqlite(
                    cfg,
                    limit=limit,
                    offset=offset,
                    target_resource_keys=target_resource_keys,
                )
            else:
                return {"success": False, "error": f"暂不支持的 db_type: {db_type}"}
        except Exception as exc:
            logger.error("database discover datasets failed: %s", exc, exc_info=True)
            detail = _friendly_database_error(exc)
            return {
                "success": False,
                "source_id": self.ctx.source_id,
                "provider_code": self.ctx.provider_code,
                "datasets": [],
                "dataset_count": 0,
                "error": detail,
                "message": detail,
            }

        datasets = [item for item in discover_payload.get("datasets") or [] if isinstance(item, dict)]
        scan_summary = (
            discover_payload.get("scan_summary")
            if isinstance(discover_payload.get("scan_summary"), dict)
            else {}
        )
        message = str(discover_payload.get("message") or "").strip()
        if not message:
            if scan_summary.get("mode") == "targeted":
                requested_count = int(scan_summary.get("requested_count") or len(target_resource_keys))
                message = f"已更新 {len(datasets)} / {requested_count} 个指定对象"
            else:
                scanned_count = int(scan_summary.get("scanned_count") or len(datasets))
                total_count = int(scan_summary.get("total_count") or scanned_count)
                message = f"本次扫描 {scanned_count} / {total_count} 个数据库对象"

        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "datasets": datasets,
            "dataset_count": len(datasets),
            "scan_summary": scan_summary,
            "message": message,
        }

    def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cfg = self._resolved_connection_config()
        db_type = _normalize_db_type(cfg.get("db_type"))
        is_hologres = _is_hologres_source(self.ctx.provider_code, cfg.get("db_type"))
        resource_key = str(arguments.get("resource_key") or "").strip()
        dataset = arguments.get("dataset") if isinstance(arguments.get("dataset"), dict) else {}
        extract_config = dataset.get("extract_config") if isinstance(dataset.get("extract_config"), dict) else {}
        limit = max(1, min(_to_int(arguments.get("limit"), 10), 200))

        schema_name = str(arguments.get("schema") or extract_config.get("schema") or "").strip()
        table_name = str(arguments.get("table") or extract_config.get("table") or "").strip()

        if not table_name and resource_key:
            if "." in resource_key:
                schema_name, table_name = resource_key.split(".", 1)
            else:
                table_name = resource_key

        if not table_name:
            return {
                "success": False,
                "error": "missing_table",
                "message": "预览数据需要提供 resource_key 或表名",
                "rows": [],
            }

        rows: list[dict[str, Any]] = []
        try:
            if db_type == "postgresql":
                rows = self._preview_postgresql(cfg, schema_name or "public", table_name, limit)
            elif db_type == "mysql":
                rows = self._preview_mysql(cfg, schema_name or str(cfg.get("database") or ""), table_name, limit)
            elif db_type == "sqlite":
                rows = self._preview_sqlite(cfg, table_name, limit)
            else:
                return {
                    "success": False,
                    "error": f"unsupported_db_type:{db_type}",
                    "message": f"暂不支持 {db_type} 的预览",
                    "rows": [],
                }
        except Exception as exc:
            if is_hologres and _is_hologres_worker_info_permission_error(exc):
                logger.warning("hologres preview skipped due to insufficient privilege: %s", exc)
                return {
                    "success": True,
                    "source_id": self.ctx.source_id,
                    "provider_code": self.ctx.provider_code,
                    "rows": [],
                    "count": 0,
                    "message": "当前 Hologres 账号无权读取样例数据，已跳过样例预览",
                }
            logger.error("database preview failed: %s", exc, exc_info=True)
            return {
                "success": False,
                "error": str(exc),
                "message": "查询样例数据失败",
                "rows": [],
            }

        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "rows": rows,
            "count": len(rows),
            "message": f"已返回 {len(rows)} 行样例数据",
        }

    def _resolve_sync_target(
        self,
        arguments: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any]]:
        params = arguments.get("params") if isinstance(arguments.get("params"), dict) else {}
        query = params.get("query") if isinstance(params.get("query"), dict) else {}
        dataset = arguments.get("dataset") if isinstance(arguments.get("dataset"), dict) else {}
        extract_config = dataset.get("extract_config") if isinstance(dataset.get("extract_config"), dict) else {}

        resource_key = str(
            arguments.get("resource_key")
            or query.get("resource_key")
            or arguments.get("table_name")
            or dataset.get("resource_key")
            or dataset.get("dataset_code")
            or ""
        ).strip()
        schema_name = str(arguments.get("schema") or extract_config.get("schema") or "").strip()
        table_name = str(arguments.get("table") or extract_config.get("table") or "").strip()

        if not table_name and resource_key:
            if "." in resource_key:
                schema_name, table_name = resource_key.split(".", 1)
            else:
                table_name = resource_key

        filters = {
            str(key): value
            for key, value in dict(query.get("filters") or {}).items()
            if str(key).strip()
        }
        biz_date = str(params.get("biz_date") or arguments.get("biz_date") or "").strip()
        date_field = str(query.get("date_field") or "").strip()
        date_format = str(
            query.get("date_format")
            or params.get("date_format")
            or query.get("date_value_format")
            or params.get("date_value_format")
            or ""
        ).strip()
        if date_field and biz_date and date_field not in filters:
            filters[date_field] = {
                _DATE_FILTER_MARKER: True,
                "value": biz_date,
                "date_format": date_format,
            }
        return schema_name, table_name, filters

    def _sync_postgresql(
        self,
        cfg: dict[str, Any],
        schema_name: str,
        table_name: str,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conn = self._connect_postgresql(cfg)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = pg_sql.SQL("SELECT * FROM {}.{}").format(
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table_name),
                )
                where_sql, params = self._build_postgresql_filter_sql(filters)
                if where_sql is not None:
                    query += pg_sql.SQL(" WHERE ") + where_sql
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall() or []]
        finally:
            conn.close()

    def _build_postgresql_filter_sql(
        self,
        filters: dict[str, Any],
    ) -> tuple[pg_sql.Composed | None, list[Any]]:
        if not filters:
            return None, []
        clauses: list[pg_sql.Composed] = []
        params: list[Any] = []
        for field_name, value in filters.items():
            filter_value, date_format = self._extract_date_filter_value(field_name, value)
            if self._is_date_only_filter_value(filter_value):
                if date_format == "compact_date":
                    clauses.append(pg_sql.SQL("{} = %s").format(pg_sql.Identifier(field_name)))
                    params.append(self._compact_date_value(filter_value))
                elif date_format == "compact_datetime":
                    start, end = self._compact_datetime_filter_bounds(filter_value)
                    clauses.append(
                        pg_sql.SQL("{} >= %s AND {} < %s").format(
                            pg_sql.Identifier(field_name),
                            pg_sql.Identifier(field_name),
                        )
                    )
                    params.extend([start, end])
                elif date_format == "slash_date":
                    start, end = self._slash_date_filter_bounds(filter_value)
                    clauses.append(
                        pg_sql.SQL("{} >= %s AND {} < %s").format(
                            pg_sql.Identifier(field_name),
                            pg_sql.Identifier(field_name),
                        )
                    )
                    params.extend([start, end])
                elif date_format == "slash_datetime":
                    start, end = self._slash_datetime_filter_bounds(filter_value)
                    clauses.append(
                        pg_sql.SQL("{} >= %s AND {} < %s").format(
                            pg_sql.Identifier(field_name),
                            pg_sql.Identifier(field_name),
                        )
                    )
                    params.extend([start, end])
                elif date_format in {"unix_seconds", "unix_millis"}:
                    start, end = self._unix_filter_bounds(filter_value, date_format=date_format)
                    clauses.append(
                        pg_sql.SQL("{} >= %s AND {} < %s").format(
                            pg_sql.Identifier(field_name),
                            pg_sql.Identifier(field_name),
                        )
                    )
                    params.extend([start, end])
                else:
                    start, end = self._date_filter_bounds(filter_value)
                    clauses.append(
                        pg_sql.SQL("{} >= %s AND {} < %s").format(
                            pg_sql.Identifier(field_name),
                            pg_sql.Identifier(field_name),
                        )
                    )
                    params.extend([start, end])
            else:
                clauses.append(pg_sql.SQL("{} = %s").format(pg_sql.Identifier(field_name)))
                params.append(filter_value)
        return pg_sql.SQL(" AND ").join(clauses), params

    def _sync_mysql(
        self,
        cfg: dict[str, Any],
        schema_name: str,
        table_name: str,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conn = self._connect_mysql(cfg)
        safe_schema = schema_name.replace("`", "``") or str(cfg.get("database") or "")
        safe_table = table_name.replace("`", "``")
        try:
            with conn.cursor() as cur:
                sql = f"SELECT * FROM `{safe_schema}`.`{safe_table}`"
                params: list[Any] = []
                if filters:
                    clauses: list[str] = []
                    for field_name, value in filters.items():
                        safe_field = field_name.replace("`", "``")
                        filter_value, date_format = self._extract_date_filter_value(field_name, value)
                        if self._is_date_only_filter_value(filter_value):
                            if date_format == "compact_date":
                                clauses.append(f"`{safe_field}` = %s")
                                params.append(self._compact_date_value(filter_value))
                            elif date_format == "compact_datetime":
                                start, end = self._compact_datetime_filter_bounds(filter_value)
                                clauses.append(f"`{safe_field}` >= %s AND `{safe_field}` < %s")
                                params.extend([start, end])
                            elif date_format == "slash_date":
                                start, end = self._slash_date_filter_bounds(filter_value)
                                clauses.append(f"`{safe_field}` >= %s AND `{safe_field}` < %s")
                                params.extend([start, end])
                            elif date_format == "slash_datetime":
                                start, end = self._slash_datetime_filter_bounds(filter_value)
                                clauses.append(f"`{safe_field}` >= %s AND `{safe_field}` < %s")
                                params.extend([start, end])
                            elif date_format in {"unix_seconds", "unix_millis"}:
                                start, end = self._unix_filter_bounds(filter_value, date_format=date_format)
                                clauses.append(f"`{safe_field}` >= %s AND `{safe_field}` < %s")
                                params.extend([start, end])
                            else:
                                start, end = self._date_filter_bounds(filter_value)
                                clauses.append(f"`{safe_field}` >= %s AND `{safe_field}` < %s")
                                params.extend([start, end])
                        else:
                            clauses.append(f"`{safe_field}` = %s")
                            params.append(filter_value)
                    sql += f" WHERE {' AND '.join(clauses)}"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall() or []
                return [dict(row) for row in rows]
        finally:
            conn.close()

    def _sync_sqlite(
        self,
        cfg: dict[str, Any],
        table_name: str,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conn = self._connect_sqlite(cfg)
        conn.row_factory = sqlite3.Row
        safe_table = table_name.replace('"', '""')
        try:
            cur = conn.cursor()
            try:
                sql = f'SELECT * FROM "{safe_table}"'
                params: list[Any] = []
                if filters:
                    clauses: list[str] = []
                    for field_name, value in filters.items():
                        safe_field = field_name.replace('"', '""')
                        filter_value, date_format = self._extract_date_filter_value(field_name, value)
                        if self._is_date_only_filter_value(filter_value):
                            if date_format == "compact_date":
                                clauses.append(f'"{safe_field}" = ?')
                                params.append(self._compact_date_value(filter_value))
                            elif date_format == "compact_datetime":
                                start, end = self._compact_datetime_filter_bounds(filter_value)
                                clauses.append(f'"{safe_field}" >= ? AND "{safe_field}" < ?')
                                params.extend([start, end])
                            elif date_format == "slash_date":
                                start, end = self._slash_date_filter_bounds(filter_value)
                                clauses.append(f'"{safe_field}" >= ? AND "{safe_field}" < ?')
                                params.extend([start, end])
                            elif date_format == "slash_datetime":
                                start, end = self._slash_datetime_filter_bounds(filter_value)
                                clauses.append(f'"{safe_field}" >= ? AND "{safe_field}" < ?')
                                params.extend([start, end])
                            elif date_format in {"unix_seconds", "unix_millis"}:
                                start, end = self._unix_filter_bounds(filter_value, date_format=date_format)
                                clauses.append(f'"{safe_field}" >= ? AND "{safe_field}" < ?')
                                params.extend([start, end])
                            else:
                                start, end = self._date_filter_bounds(filter_value)
                                clauses.append(f'datetime("{safe_field}") >= datetime(?) AND datetime("{safe_field}") < datetime(?)')
                                params.extend([start, end])
                        else:
                            clauses.append(f'"{safe_field}" = ?')
                            params.append(filter_value)
                    sql += f" WHERE {' AND '.join(clauses)}"
                cur.execute(sql, tuple(params))
                rows = cur.fetchall() or []
                return [dict(row) for row in rows]
            finally:
                cur.close()
        finally:
            conn.close()

    def _is_date_only_filter_value(self, value: Any) -> bool:
        return bool(_DATE_ONLY_PATTERN.match(str(value or "").strip()))

    def _is_compact_date_partition_field(self, field_name: Any) -> bool:
        normalized = str(field_name or "").strip().lower()
        return normalized in {"pt", "dt", "biz_dt", "bizdate", "biz_date_yyyymmdd", "date_key"}

    def _extract_date_filter_value(self, field_name: Any, value: Any) -> tuple[Any, str]:
        if isinstance(value, dict) and value.get(_DATE_FILTER_MARKER) is True:
            filter_value = value.get("value")
            date_format = self._normalize_date_format(value.get("date_format"), field_name=field_name)
            return filter_value, date_format
        return value, self._normalize_date_format("", field_name=field_name)

    def _normalize_date_format(self, value: Any, *, field_name: Any = "") -> str:
        normalized = str(value or "").strip().lower().replace("-", "_")
        aliases = {
            "auto": "",
            "native": "native",
            "date": "native",
            "datetime": "native",
            "timestamp": "native",
            "iso": "native",
            "iso_date": "native",
            "iso_datetime": "native",
            "yyyy_mm_dd": "native",
            "yyyy_mm_dd_hh_mm_ss": "native",
            "yyyymmdd": "compact_date",
            "compact": "compact_date",
            "compact_date": "compact_date",
            "partition_date": "compact_date",
            "yyyymmddhhmmss": "compact_datetime",
            "compact_datetime": "compact_datetime",
            "yyyy/mm/dd": "slash_date",
            "slash_date": "slash_date",
            "yyyy/mm/dd hh:mm:ss": "slash_datetime",
            "slash_datetime": "slash_datetime",
            "unix": "unix_seconds",
            "unix_seconds": "unix_seconds",
            "unix_second": "unix_seconds",
            "epoch_seconds": "unix_seconds",
            "unix_millis": "unix_millis",
            "unix_milliseconds": "unix_millis",
            "epoch_millis": "unix_millis",
        }
        resolved = aliases.get(normalized, normalized)
        if resolved in {
            "native",
            "compact_date",
            "compact_datetime",
            "slash_date",
            "slash_datetime",
            "unix_seconds",
            "unix_millis",
        }:
            return resolved
        if self._is_compact_date_partition_field(field_name):
            return "compact_date"
        return "native"

    def _compact_date_value(self, value: Any) -> str:
        return date.fromisoformat(str(value or "").strip()).strftime("%Y%m%d")

    def _compact_datetime_filter_bounds(self, value: Any) -> tuple[str, str]:
        start_date = date.fromisoformat(str(value or "").strip())
        return start_date.strftime("%Y%m%d000000"), (start_date + timedelta(days=1)).strftime("%Y%m%d000000")

    def _slash_date_filter_bounds(self, value: Any) -> tuple[str, str]:
        start_date = date.fromisoformat(str(value or "").strip())
        return start_date.strftime("%Y/%m/%d"), (start_date + timedelta(days=1)).strftime("%Y/%m/%d")

    def _slash_datetime_filter_bounds(self, value: Any) -> tuple[str, str]:
        start_date = date.fromisoformat(str(value or "").strip())
        return start_date.strftime("%Y/%m/%d 00:00:00"), (start_date + timedelta(days=1)).strftime("%Y/%m/%d 00:00:00")

    def _unix_filter_bounds(self, value: Any, *, date_format: str) -> tuple[int, int]:
        from datetime import datetime, timezone

        start_date = date.fromisoformat(str(value or "").strip())
        start_ts = int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
        end_ts = int(datetime.combine(start_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
        if date_format == "unix_millis":
            return start_ts * 1000, end_ts * 1000
        return start_ts, end_ts

    def _date_filter_bounds(self, value: Any) -> tuple[str, str]:
        start_date = date.fromisoformat(str(value or "").strip())
        return start_date.isoformat(), (start_date + timedelta(days=1)).isoformat()

    def _discover_postgresql(
        self,
        cfg: dict[str, Any],
        *,
        schema_whitelist: list[str],
        limit: int,
        offset: int,
        target_resource_keys: list[str],
    ) -> dict[str, Any]:
        conn = self._connect_postgresql(cfg)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                requested_objects = _parse_requested_objects(target_resource_keys)
                count_sql = """
                    SELECT COUNT(*) AS total_count
                    FROM pg_class AS c
                    JOIN pg_namespace AS n
                      ON n.oid = c.relnamespace
                    WHERE n.nspname <> %s
                      AND n.nspname NOT LIKE %s
                      AND c.relkind = ANY(%s)
                """
                count_params: list[Any] = ["information_schema", "pg_%", list(_POSTGRES_DISCOVER_RELKINDS)]
                if schema_whitelist:
                    count_sql += " AND n.nspname = ANY(%s)"
                    count_params.append(schema_whitelist)
                if requested_objects:
                    requested_clauses: list[str] = []
                    for item in requested_objects:
                        schema_name = str(item.get("schema_name") or "").strip()
                        table_name = str(item.get("table_name") or "").strip()
                        if schema_name:
                            requested_clauses.append("(n.nspname = %s AND c.relname = %s)")
                            count_params.extend([schema_name, table_name])
                        else:
                            requested_clauses.append("(c.relname = %s)")
                            count_params.append(table_name)
                    count_sql += f" AND ({' OR '.join(requested_clauses)})"
                cur.execute(count_sql, tuple(count_params))
                count_row = cur.fetchone() or {}
                total_count = int(count_row.get("total_count") or 0)

                table_sql = """
                    SELECT n.nspname AS table_schema,
                           c.relname AS table_name,
                           c.relkind AS relkind
                    FROM pg_class AS c
                    JOIN pg_namespace AS n
                      ON n.oid = c.relnamespace
                    WHERE n.nspname <> %s
                      AND n.nspname NOT LIKE %s
                      AND c.relkind = ANY(%s)
                """
                params: list[Any] = ["information_schema", "pg_%", list(_POSTGRES_DISCOVER_RELKINDS)]
                if schema_whitelist:
                    table_sql += " AND n.nspname = ANY(%s)"
                    params.append(schema_whitelist)
                if requested_objects:
                    requested_clauses = []
                    for item in requested_objects:
                        schema_name = str(item.get("schema_name") or "").strip()
                        table_name = str(item.get("table_name") or "").strip()
                        if schema_name:
                            requested_clauses.append("(n.nspname = %s AND c.relname = %s)")
                            params.extend([schema_name, table_name])
                        else:
                            requested_clauses.append("(c.relname = %s)")
                            params.append(table_name)
                    table_sql += f" AND ({' OR '.join(requested_clauses)}) ORDER BY n.nspname, c.relname"
                else:
                    table_sql += " ORDER BY n.nspname, c.relname LIMIT %s OFFSET %s"
                    params.extend([limit, offset])
                cur.execute(table_sql, tuple(params))
                table_rows = [dict(row) for row in (cur.fetchall() or [])]

                if not table_rows:
                    scan_summary: dict[str, Any]
                    if requested_objects:
                        scan_summary = {
                            "mode": "targeted",
                            "requested_count": len(requested_objects),
                            "matched_count": 0,
                            "missing_targets": [str(item.get("resource_key") or "") for item in requested_objects],
                            "scanned_count": 0,
                            "total_count": len(requested_objects),
                            "has_more": False,
                            "next_offset": None,
                            "offset": 0,
                            "requested_limit": len(requested_objects),
                        }
                    else:
                        next_offset = offset + len(table_rows)
                        scan_summary = {
                            "mode": "batch",
                            "scanned_count": 0,
                            "total_count": total_count,
                            "offset": offset,
                            "requested_limit": limit,
                            "has_more": next_offset < total_count,
                            "next_offset": next_offset if next_offset < total_count else None,
                        }
                    return {
                        "datasets": [],
                        "scan_summary": scan_summary,
                    }

                selected_schemas = sorted({str(row.get("table_schema") or "") for row in table_rows if str(row.get("table_schema") or "")})
                selected_tables = sorted({str(row.get("table_name") or "") for row in table_rows if str(row.get("table_name") or "")})

                column_sql = """
                    SELECT table_schema, table_name, column_name, data_type, is_nullable,
                           ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = ANY(%s)
                      AND table_name = ANY(%s)
                """
                column_params: list[Any] = [selected_schemas, selected_tables]
                column_sql += " ORDER BY table_schema, table_name, ordinal_position"
                cur.execute(column_sql, tuple(column_params))
                column_rows = [dict(row) for row in (cur.fetchall() or [])]

                pk_sql = """
                    SELECT kcu.table_schema, kcu.table_name, kcu.column_name, kcu.ordinal_position
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                      ON tc.constraint_name = kcu.constraint_name
                     AND tc.table_schema = kcu.table_schema
                     AND tc.table_name = kcu.table_name
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND kcu.table_schema = ANY(%s)
                      AND kcu.table_name = ANY(%s)
                """
                pk_params: list[Any] = [selected_schemas, selected_tables]
                pk_sql += " ORDER BY kcu.table_schema, kcu.table_name, kcu.ordinal_position"
                cur.execute(pk_sql, tuple(pk_params))
                pk_rows = [dict(row) for row in (cur.fetchall() or [])]
        finally:
            conn.close()

        columns_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in column_rows:
            key = (str(row.get("table_schema") or ""), str(row.get("table_name") or ""))
            columns_by_key.setdefault(key, []).append(
                {
                    "name": str(row.get("column_name") or ""),
                    "data_type": str(row.get("data_type") or ""),
                    "nullable": str(row.get("is_nullable") or "").upper() == "YES",
                }
            )

        primary_keys_by_key: dict[tuple[str, str], list[str]] = {}
        for row in pk_rows:
            key = (str(row.get("table_schema") or ""), str(row.get("table_name") or ""))
            primary_keys_by_key.setdefault(key, []).append(str(row.get("column_name") or ""))

        datasets: list[dict[str, Any]] = []
        for table_row in table_rows:
            schema_name = str(table_row.get("table_schema") or "")
            table_name = str(table_row.get("table_name") or "")
            key = (schema_name, table_name)
            relkind = str(table_row.get("relkind") or "")
            dataset_kind = _postgres_relkind_to_dataset_kind(relkind)
            object_kind = _postgres_relkind_to_object_type(relkind)
            columns = columns_by_key.get(key, [])
            primary_keys = primary_keys_by_key.get(key, [])
            resource_key = f"{schema_name}.{table_name}"
            datasets.append(
                {
                    "dataset_code": _sanitize_dataset_code(schema_name, table_name),
                    "dataset_name": resource_key,
                    "resource_key": resource_key,
                    "dataset_kind": dataset_kind,
                    "origin_type": "discovered",
                    "extract_config": {
                        "db_type": "postgresql",
                        "schema": schema_name,
                        "table": table_name,
                        "object_type": object_kind,
                    },
                    "schema_summary": {
                        "object_type": object_kind,
                        "columns": columns,
                        "primary_keys": primary_keys,
                    },
                    "sync_strategy": _build_sync_strategy(columns),
                    "meta": {"discovered_by": "database_connector"},
                }
            )
        if requested_objects:
            matched_resource_keys = {str(item.get("resource_key") or "").lower() for item in datasets}
            matched_table_names = {
                str(item.get("extract_config", {}).get("table") or "").lower()
                for item in datasets
                if isinstance(item.get("extract_config"), dict)
            }
            missing_targets: list[str] = []
            for requested in requested_objects:
                requested_resource_key = str(requested.get("resource_key") or "").strip()
                requested_table_name = str(requested.get("table_name") or "").strip().lower()
                if "." in requested_resource_key:
                    if requested_resource_key.lower() not in matched_resource_keys:
                        missing_targets.append(requested_resource_key)
                elif requested_table_name and requested_table_name not in matched_table_names:
                    missing_targets.append(requested_resource_key)
            scan_summary = {
                "mode": "targeted",
                "requested_count": len(requested_objects),
                "matched_count": len(datasets),
                "missing_targets": missing_targets,
                "scanned_count": len(datasets),
                "total_count": len(requested_objects),
                "has_more": False,
                "next_offset": None,
                "offset": 0,
                "requested_limit": len(requested_objects),
            }
            message = f"已更新 {len(datasets)} / {len(requested_objects)} 个指定对象"
        else:
            next_offset = offset + len(datasets)
            scan_summary = {
                "mode": "batch",
                "scanned_count": len(datasets),
                "total_count": total_count,
                "offset": offset,
                "requested_limit": limit,
                "has_more": next_offset < total_count,
                "next_offset": next_offset if next_offset < total_count else None,
            }
            message = f"本次扫描 {len(datasets)} / {total_count} 个数据库对象"
        return {
            "datasets": datasets,
            "scan_summary": scan_summary,
            "message": message,
        }

    def _preview_postgresql(
        self,
        cfg: dict[str, Any],
        schema_name: str,
        table_name: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        conn = self._connect_postgresql(cfg)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                query = pg_sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
                    pg_sql.Identifier(schema_name),
                    pg_sql.Identifier(table_name),
                )
                cur.execute(query, (limit,))
                return [dict(row) for row in cur.fetchall() or []]
        finally:
            conn.close()

    def _preview_mysql(
        self,
        cfg: dict[str, Any],
        schema_name: str,
        table_name: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        conn = self._connect_mysql(cfg)
        safe_schema = schema_name.replace("`", "``") or str(cfg.get("database") or "")
        safe_table = table_name.replace("`", "``")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM `{safe_schema}`.`{safe_table}` LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall() or []
                return [dict(row) for row in rows]
        finally:
            conn.close()

    def _preview_sqlite(
        self,
        cfg: dict[str, Any],
        table_name: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        conn = self._connect_sqlite(cfg)
        conn.row_factory = sqlite3.Row
        safe_table = table_name.replace("'", "''")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM '{safe_table}' LIMIT ?",
                    (limit,),
                )
                rows = cur.fetchall() or []
                return [dict(row) for row in rows]
        finally:
            conn.close()

    def _discover_mysql(
        self,
        cfg: dict[str, Any],
        *,
        limit: int,
        offset: int,
        target_resource_keys: list[str],
    ) -> dict[str, Any]:
        conn = self._connect_mysql(cfg)
        db_name = str(cfg.get("database") or "")
        try:
            with conn.cursor() as cur:
                requested_objects = _parse_requested_objects(target_resource_keys)
                count_sql = """
                    SELECT COUNT(*) AS total_count
                    FROM information_schema.tables
                    WHERE table_schema = %s
                      AND table_type IN ('BASE TABLE', 'VIEW')
                """
                count_params: list[Any] = [db_name]
                if requested_objects:
                    requested_clauses: list[str] = []
                    for item in requested_objects:
                        schema_name = str(item.get("schema_name") or "").strip()
                        table_name = str(item.get("table_name") or "").strip()
                        if schema_name:
                            requested_clauses.append("(table_schema = %s AND table_name = %s)")
                            count_params.extend([schema_name, table_name])
                        else:
                            requested_clauses.append("(table_name = %s)")
                            count_params.append(table_name)
                    count_sql += f" AND ({' OR '.join(requested_clauses)})"
                cur.execute(count_sql, tuple(count_params))
                count_row = cur.fetchone() or {}
                total_count = int(count_row.get("total_count") or 0)

                table_sql = """
                    SELECT table_schema, table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema = %s
                      AND table_type IN ('BASE TABLE', 'VIEW')
                """
                table_params: list[Any] = [db_name]
                if requested_objects:
                    requested_clauses = []
                    for item in requested_objects:
                        schema_name = str(item.get("schema_name") or "").strip()
                        table_name = str(item.get("table_name") or "").strip()
                        if schema_name:
                            requested_clauses.append("(table_schema = %s AND table_name = %s)")
                            table_params.extend([schema_name, table_name])
                        else:
                            requested_clauses.append("(table_name = %s)")
                            table_params.append(table_name)
                    table_sql += f" AND ({' OR '.join(requested_clauses)})"
                    table_sql += " ORDER BY table_schema, table_name"
                else:
                    table_sql += " ORDER BY table_name LIMIT %s OFFSET %s"
                    table_params.extend([limit, offset])
                cur.execute(table_sql, tuple(table_params))
                table_rows = list(cur.fetchall() or [])

                if not table_rows:
                    scan_summary: dict[str, Any]
                    if requested_objects:
                        scan_summary = {
                            "mode": "targeted",
                            "requested_count": len(requested_objects),
                            "matched_count": 0,
                            "missing_targets": [str(item.get("resource_key") or "") for item in requested_objects],
                            "scanned_count": 0,
                            "total_count": len(requested_objects),
                            "has_more": False,
                            "next_offset": None,
                            "offset": 0,
                            "requested_limit": len(requested_objects),
                        }
                    else:
                        next_offset = offset
                        scan_summary = {
                            "mode": "batch",
                            "scanned_count": 0,
                            "total_count": total_count,
                            "offset": offset,
                            "requested_limit": limit,
                            "has_more": next_offset < total_count,
                            "next_offset": next_offset if next_offset < total_count else None,
                        }
                    return {"datasets": [], "scan_summary": scan_summary}

                selected_table_names = sorted({str(row.get("table_name") or "") for row in table_rows if str(row.get("table_name") or "")})
                selected_table_placeholders = ", ".join(["%s"] * len(selected_table_names))
                cur.execute(
                    f"""
                    SELECT table_schema, table_name, column_name, data_type, is_nullable,
                           ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = %s
                      AND table_name IN ({selected_table_placeholders})
                    ORDER BY table_name, ordinal_position
                    """,
                    (db_name, *selected_table_names),
                )
                column_rows = list(cur.fetchall() or [])

                cur.execute(
                    f"""
                    SELECT table_schema, table_name, column_name, ordinal_position
                    FROM information_schema.key_column_usage
                    WHERE table_schema = %s
                      AND table_name IN ({selected_table_placeholders})
                      AND constraint_name = 'PRIMARY'
                    ORDER BY table_name, ordinal_position
                    """,
                    (db_name, *selected_table_names),
                )
                pk_rows = list(cur.fetchall() or [])
        finally:
            conn.close()

        columns_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in column_rows:
            key = (str(row.get("table_schema") or ""), str(row.get("table_name") or ""))
            columns_by_key.setdefault(key, []).append(
                {
                    "name": str(row.get("column_name") or ""),
                    "data_type": str(row.get("data_type") or ""),
                    "nullable": str(row.get("is_nullable") or "").upper() == "YES",
                }
            )

        primary_keys_by_key: dict[tuple[str, str], list[str]] = {}
        for row in pk_rows:
            key = (str(row.get("table_schema") or ""), str(row.get("table_name") or ""))
            primary_keys_by_key.setdefault(key, []).append(str(row.get("column_name") or ""))

        datasets: list[dict[str, Any]] = []
        for table_row in table_rows:
            schema_name = str(table_row.get("table_schema") or db_name)
            table_name = str(table_row.get("table_name") or "")
            key = (schema_name, table_name)
            object_kind = "view" if str(table_row.get("table_type") or "").upper() == "VIEW" else "table"
            columns = columns_by_key.get(key, [])
            primary_keys = primary_keys_by_key.get(key, [])
            resource_key = f"{schema_name}.{table_name}"
            datasets.append(
                {
                    "dataset_code": _sanitize_dataset_code(schema_name, table_name),
                    "dataset_name": resource_key,
                    "resource_key": resource_key,
                    "dataset_kind": object_kind,
                    "origin_type": "discovered",
                    "extract_config": {
                        "db_type": "mysql",
                        "schema": schema_name,
                        "table": table_name,
                        "object_type": object_kind,
                    },
                    "schema_summary": {
                        "object_type": object_kind,
                        "columns": columns,
                        "primary_keys": primary_keys,
                    },
                    "sync_strategy": _build_sync_strategy(columns),
                    "meta": {"discovered_by": "database_connector"},
                }
            )
        if requested_objects:
            matched_resource_keys = {str(item.get("resource_key") or "").lower() for item in datasets}
            matched_table_names = {
                str(item.get("extract_config", {}).get("table") or "").lower()
                for item in datasets
                if isinstance(item.get("extract_config"), dict)
            }
            missing_targets: list[str] = []
            for requested in requested_objects:
                requested_resource_key = str(requested.get("resource_key") or "").strip()
                requested_table_name = str(requested.get("table_name") or "").strip().lower()
                if "." in requested_resource_key:
                    if requested_resource_key.lower() not in matched_resource_keys:
                        missing_targets.append(requested_resource_key)
                elif requested_table_name and requested_table_name not in matched_table_names:
                    missing_targets.append(requested_resource_key)
            scan_summary = {
                "mode": "targeted",
                "requested_count": len(requested_objects),
                "matched_count": len(datasets),
                "missing_targets": missing_targets,
                "scanned_count": len(datasets),
                "total_count": len(requested_objects),
                "has_more": False,
                "next_offset": None,
                "offset": 0,
                "requested_limit": len(requested_objects),
            }
            message = f"已更新 {len(datasets)} / {len(requested_objects)} 个指定对象"
        else:
            next_offset = offset + len(datasets)
            scan_summary = {
                "mode": "batch",
                "scanned_count": len(datasets),
                "total_count": total_count,
                "offset": offset,
                "requested_limit": limit,
                "has_more": next_offset < total_count,
                "next_offset": next_offset if next_offset < total_count else None,
            }
            message = f"本次扫描 {len(datasets)} / {total_count} 个数据库对象"
        return {
            "datasets": datasets,
            "scan_summary": scan_summary,
            "message": message,
        }

    def _discover_sqlite(
        self,
        cfg: dict[str, Any],
        *,
        limit: int,
        offset: int,
        target_resource_keys: list[str],
    ) -> dict[str, Any]:
        conn = self._connect_sqlite(cfg)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            requested_objects = _parse_requested_objects(target_resource_keys)
            count_sql = """
                SELECT COUNT(*) AS total_count
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
            """
            count_params: list[Any] = []
            if requested_objects:
                requested_names = [str(item.get("table_name") or "") for item in requested_objects if str(item.get("table_name") or "")]
                if requested_names:
                    placeholders = ", ".join("?" for _ in requested_names)
                    count_sql += f" AND name IN ({placeholders})"
                    count_params.extend(requested_names)
            cur.execute(count_sql, tuple(count_params))
            count_row = cur.fetchone() or {"total_count": 0}
            total_count = int(count_row["total_count"] or 0)

            table_sql = """
                SELECT name, type
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
            """
            table_params: list[Any] = []
            if requested_objects:
                requested_names = [str(item.get("table_name") or "") for item in requested_objects if str(item.get("table_name") or "")]
                if requested_names:
                    placeholders = ", ".join("?" for _ in requested_names)
                    table_sql += f" AND name IN ({placeholders})"
                    table_params.extend(requested_names)
                table_sql += " ORDER BY name"
            else:
                table_sql += " ORDER BY name LIMIT ? OFFSET ?"
                table_params.extend([limit, offset])
            cur.execute(table_sql, tuple(table_params))
            objects = cur.fetchall() or []

            datasets: list[dict[str, Any]] = []
            for obj in objects:
                object_name = str(obj["name"])
                object_kind = "view" if str(obj["type"]).lower() == "view" else "table"
                escaped_name = object_name.replace("'", "''")
                cur.execute(f"PRAGMA table_info('{escaped_name}')")
                column_rows = cur.fetchall() or []
                columns = [
                    {
                        "name": str(row["name"]),
                        "data_type": str(row["type"] or ""),
                        "nullable": int(row["notnull"] or 0) == 0,
                    }
                    for row in column_rows
                ]
                primary_keys = [str(row["name"]) for row in column_rows if int(row["pk"] or 0) > 0]
                datasets.append(
                    {
                        "dataset_code": _sanitize_dataset_code(object_name),
                        "dataset_name": object_name,
                        "resource_key": object_name,
                        "dataset_kind": object_kind,
                        "origin_type": "discovered",
                        "extract_config": {
                            "db_type": "sqlite",
                            "table": object_name,
                            "object_type": object_kind,
                        },
                        "schema_summary": {
                            "object_type": object_kind,
                            "columns": columns,
                            "primary_keys": primary_keys,
                        },
                        "sync_strategy": _build_sync_strategy(columns),
                        "meta": {"discovered_by": "database_connector"},
                    }
                )
            if requested_objects:
                matched_names = {str(item.get("resource_key") or "").lower() for item in datasets}
                missing_targets = [
                    str(item.get("resource_key") or "")
                    for item in requested_objects
                    if str(item.get("resource_key") or "").lower() not in matched_names
                ]
                scan_summary = {
                    "mode": "targeted",
                    "requested_count": len(requested_objects),
                    "matched_count": len(datasets),
                    "missing_targets": missing_targets,
                    "scanned_count": len(datasets),
                    "total_count": len(requested_objects),
                    "has_more": False,
                    "next_offset": None,
                    "offset": 0,
                    "requested_limit": len(requested_objects),
                }
                message = f"已更新 {len(datasets)} / {len(requested_objects)} 个指定对象"
            else:
                next_offset = offset + len(datasets)
                scan_summary = {
                    "mode": "batch",
                    "scanned_count": len(datasets),
                    "total_count": total_count,
                    "offset": offset,
                    "requested_limit": limit,
                    "has_more": next_offset < total_count,
                    "next_offset": next_offset if next_offset < total_count else None,
                }
                message = f"本次扫描 {len(datasets)} / {total_count} 个数据库对象"
            return {
                "datasets": datasets,
                "scan_summary": scan_summary,
                "message": message,
            }
        finally:
            conn.close()

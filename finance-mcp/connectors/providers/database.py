"""Database source connector."""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2 import sql as pg_sql

from connectors.base import BaseDataSourceConnector

logger = logging.getLogger(__name__)

_DATASET_CODE_PATTERN = re.compile(r"[^a-z0-9_]+")
_PG_SYSTEM_SCHEMAS = {"pg_catalog", "information_schema"}
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5


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


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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


class DatabaseConnector(BaseDataSourceConnector):
    source_kind = "database"
    execution_mode = "deterministic"

    @property
    def capabilities(self) -> list[str]:
        return ["test", "discover_datasets", "list_datasets", "list_events"]

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

    def discover_datasets(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cfg = self._resolved_connection_config()
        db_type = _normalize_db_type(cfg.get("db_type"))
        missing = self._validate_connection_config(cfg)
        if missing:
            return {"success": False, "error": f"database 配置缺失: {', '.join(missing)}"}

        schema_whitelist = self._extract_schema_whitelist(arguments, cfg)
        limit = max(1, min(_to_int(arguments.get("limit"), 300), 1000))

        try:
            if db_type == "postgresql":
                datasets = self._discover_postgresql(cfg, schema_whitelist=schema_whitelist, limit=limit)
            elif db_type == "mysql":
                datasets = self._discover_mysql(cfg, limit=limit)
            elif db_type == "sqlite":
                datasets = self._discover_sqlite(cfg, limit=limit)
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

        return {
            "success": True,
            "source_id": self.ctx.source_id,
            "provider_code": self.ctx.provider_code,
            "datasets": datasets,
            "dataset_count": len(datasets),
            "message": f"已发现 {len(datasets)} 个数据库对象",
        }

    def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        cfg = self._resolved_connection_config()
        db_type = _normalize_db_type(cfg.get("db_type"))
        resource_key = str(arguments.get("resource_key") or "").strip()
        dataset = arguments.get("dataset") if isinstance(arguments.get("dataset"), dict) else {}
        extract_config = dataset.get("extract_config") if isinstance(dataset, dict) else {}
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

    def _discover_postgresql(
        self,
        cfg: dict[str, Any],
        *,
        schema_whitelist: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        conn = self._connect_postgresql(cfg)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                table_sql = """
                    SELECT table_schema, table_name, table_type
                    FROM information_schema.tables
                    WHERE table_type IN ('BASE TABLE', 'VIEW')
                      AND table_schema <> ALL(%s)
                """
                params: list[Any] = [list(_PG_SYSTEM_SCHEMAS)]
                if schema_whitelist:
                    table_sql += " AND table_schema = ANY(%s)"
                    params.append(schema_whitelist)
                table_sql += " ORDER BY table_schema, table_name LIMIT %s"
                params.append(limit)
                cur.execute(table_sql, tuple(params))
                table_rows = [dict(row) for row in (cur.fetchall() or [])]

                if not table_rows:
                    return []

                column_sql = """
                    SELECT table_schema, table_name, column_name, data_type, is_nullable,
                           ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema <> ALL(%s)
                """
                column_params: list[Any] = [list(_PG_SYSTEM_SCHEMAS)]
                if schema_whitelist:
                    column_sql += " AND table_schema = ANY(%s)"
                    column_params.append(schema_whitelist)
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
                      AND kcu.table_schema <> ALL(%s)
                """
                pk_params: list[Any] = [list(_PG_SYSTEM_SCHEMAS)]
                if schema_whitelist:
                    pk_sql += " AND kcu.table_schema = ANY(%s)"
                    pk_params.append(schema_whitelist)
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
        return datasets

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

    def _discover_mysql(self, cfg: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        conn = self._connect_mysql(cfg)
        db_name = str(cfg.get("database") or "")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_schema, table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema = %s
                      AND table_type IN ('BASE TABLE', 'VIEW')
                    ORDER BY table_name
                    LIMIT %s
                    """,
                    (db_name, limit),
                )
                table_rows = list(cur.fetchall() or [])

                if not table_rows:
                    return []

                cur.execute(
                    """
                    SELECT table_schema, table_name, column_name, data_type, is_nullable,
                           ordinal_position
                    FROM information_schema.columns
                    WHERE table_schema = %s
                    ORDER BY table_name, ordinal_position
                    """,
                    (db_name,),
                )
                column_rows = list(cur.fetchall() or [])

                cur.execute(
                    """
                    SELECT table_schema, table_name, column_name, ordinal_position
                    FROM information_schema.key_column_usage
                    WHERE table_schema = %s
                      AND constraint_name = 'PRIMARY'
                    ORDER BY table_name, ordinal_position
                    """,
                    (db_name,),
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
        return datasets

    def _discover_sqlite(self, cfg: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
        conn = self._connect_sqlite(cfg)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT name, type
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                LIMIT ?
                """,
                (limit,),
            )
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
            return datasets
        finally:
            conn.close()

"""Database access for company-scoped notification channel configs."""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.extras

from config import DATABASE_URL, NOTIFICATION_DEFAULT_CHANNEL_CODE, NOTIFICATION_PROVIDER

from .models import NotificationChannelConfig, NotificationProvider

logger = logging.getLogger(__name__)


def _normalize_channel_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": str(row.get("id") or ""),
        "company_id": str(row.get("company_id") or ""),
        "provider": str(row.get("provider") or ""),
        "channel_code": str(row.get("channel_code") or NOTIFICATION_DEFAULT_CHANNEL_CODE),
        "name": str(row.get("name") or ""),
        "client_id": str(row.get("client_id") or ""),
        "client_secret": str(row.get("client_secret") or ""),
        "robot_code": str(row.get("robot_code") or ""),
        "is_default": bool(row.get("is_default")),
        "is_enabled": bool(row.get("is_enabled")),
        "extra": dict(row.get("extra") or {}),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def load_company_channel_config(
    *,
    company_id: str | None = None,
    provider: str | NotificationProvider | None = None,
    channel_code: str | None = None,
) -> NotificationChannelConfig | None:
    """Load one enabled notification channel config from PostgreSQL."""
    provider_value = _normalize_provider(provider)
    channel_code_value = (channel_code or NOTIFICATION_DEFAULT_CHANNEL_CODE).strip() or "default"

    if company_id:
        sql = """
            SELECT id, company_id, provider, channel_code, name,
                   client_id, client_secret, robot_code,
                   is_default, is_enabled, extra
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
        """
        params: tuple[Any, ...] = (company_id, provider_value, channel_code_value)
    else:
        sql = """
            SELECT id, company_id, provider, channel_code, name,
                   client_id, client_secret, robot_code,
                   is_default, is_enabled, extra
            FROM company_channel_configs
            WHERE provider = %s
              AND is_enabled = TRUE
            ORDER BY
              is_default DESC,
              (channel_code = %s) DESC,
              updated_at DESC,
              created_at DESC
            LIMIT 1
        """
        params = (provider_value, channel_code_value)

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
    except Exception as exc:
        logger.error("加载 company_channel_configs 失败: %s", exc)
        return None

    if not row:
        return None
    return NotificationChannelConfig(
        id=str(row.get("id") or ""),
        company_id=str(row.get("company_id") or ""),
        provider=str(row.get("provider") or ""),
        channel_code=str(row.get("channel_code") or channel_code_value),
        name=str(row.get("name") or ""),
        client_id=str(row.get("client_id") or ""),
        client_secret=str(row.get("client_secret") or ""),
        robot_code=str(row.get("robot_code") or ""),
        is_default=bool(row.get("is_default")),
        is_enabled=bool(row.get("is_enabled")),
        extra=dict(row.get("extra") or {}),
    )


def list_company_channel_configs(*, company_id: str) -> list[dict[str, Any]]:
    sql = """
        SELECT id, company_id, provider, channel_code, name,
               client_id, client_secret, robot_code,
               is_default, is_enabled, extra,
               created_at, updated_at
        FROM company_channel_configs
        WHERE company_id = %s
        ORDER BY provider ASC, is_default DESC, updated_at DESC, created_at DESC
    """
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (company_id,))
                rows = cur.fetchall() or []
    except Exception as exc:
        logger.error("查询 company_channel_configs 列表失败: %s", exc)
        return []
    return [_normalize_channel_row(dict(row)) for row in rows if row]


def save_company_channel_config(
    *,
    company_id: str,
    provider: str,
    channel_code: str,
    name: str,
    client_id: str,
    client_secret: str,
    robot_code: str,
    extra: dict[str, Any] | None = None,
    is_default: bool,
    is_enabled: bool,
    channel_id: str | None = None,
) -> dict[str, Any] | None:
    provider_value = _normalize_provider(provider)
    channel_code_value = (channel_code or NOTIFICATION_DEFAULT_CHANNEL_CODE).strip() or "default"
    extra_value = dict(extra or {})

    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                existing: dict[str, Any] | None = None
                if channel_id:
                    cur.execute(
                        """
                        SELECT id, client_secret
                        FROM company_channel_configs
                        WHERE id = %s AND company_id = %s
                        LIMIT 1
                        """,
                        (channel_id, company_id),
                    )
                    row = cur.fetchone()
                    if not row:
                        return None
                    existing = dict(row)

                if is_default:
                    cur.execute(
                        """
                        UPDATE company_channel_configs
                        SET is_default = FALSE
                        WHERE company_id = %s
                          AND provider = %s
                          AND (%s::uuid IS NULL OR id <> %s::uuid)
                        """,
                        (company_id, provider_value, channel_id, channel_id),
                    )

                secret_to_save = client_secret.strip()
                if existing and not secret_to_save:
                    secret_to_save = str(existing.get("client_secret") or "")

                if channel_id:
                    cur.execute(
                        """
                        UPDATE company_channel_configs
                        SET provider = %s,
                            channel_code = %s,
                            name = %s,
                            client_id = %s,
                            client_secret = %s,
                            robot_code = %s,
                            extra = %s::jsonb,
                            is_default = %s,
                            is_enabled = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                          AND company_id = %s
                        RETURNING id, company_id, provider, channel_code, name,
                                  client_id, client_secret, robot_code,
                                  is_default, is_enabled, extra,
                                  created_at, updated_at
                        """,
                        (
                            provider_value,
                            channel_code_value,
                            name,
                            client_id,
                            secret_to_save,
                            robot_code,
                            psycopg2.extras.Json(extra_value),
                            is_default,
                            is_enabled,
                            channel_id,
                            company_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO company_channel_configs (
                            company_id, provider, channel_code, name,
                            client_id, client_secret, robot_code, extra,
                            is_default, is_enabled
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                        RETURNING id, company_id, provider, channel_code, name,
                                  client_id, client_secret, robot_code,
                                  is_default, is_enabled, extra,
                                  created_at, updated_at
                        """,
                        (
                            company_id,
                            provider_value,
                            channel_code_value,
                            name,
                            client_id,
                            secret_to_save,
                            robot_code,
                            psycopg2.extras.Json(extra_value),
                            is_default,
                            is_enabled,
                        ),
                    )

                saved = cur.fetchone()
                conn.commit()
    except Exception as exc:
        logger.error("保存 company_channel_configs 失败: %s", exc)
        return None

    return _normalize_channel_row(dict(saved)) if saved else None


def delete_company_channel_config(*, company_id: str, channel_id: str) -> bool:
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM company_channel_configs
                    WHERE id = %s
                      AND company_id = %s
                    """,
                    (channel_id, company_id),
                )
                deleted = cur.rowcount > 0
                conn.commit()
                return deleted
    except Exception as exc:
        logger.error("删除 company_channel_configs 失败: %s", exc)
        return False


def _normalize_provider(provider: str | NotificationProvider | None) -> str:
    if isinstance(provider, NotificationProvider):
        return provider.value
    value = (provider or NOTIFICATION_PROVIDER).strip()
    return value or NotificationProvider.DINGTALK_DWS.value

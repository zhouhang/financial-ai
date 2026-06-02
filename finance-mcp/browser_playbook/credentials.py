"""Credential updates for browser playbook runtime bindings."""

from __future__ import annotations

import logging
from typing import Any

import psycopg2.extras

from auth import db as auth_db

logger = logging.getLogger(__name__)


def update_browser_playbook_credential(
    *,
    company_id: str,
    data_source_id: str,
    credential_username: str,
    credential_password: str,
) -> dict[str, Any]:
    """Store browser task credentials and move the binding back to verification.

    The plaintext password is only used to build the sealed ``credential_ref``. Returned
    data is a safe summary suitable for UI display.
    """
    username = str(credential_username or "").strip()
    password = str(credential_password or "")
    if not username:
        return {"success": False, "error": "登录账号不能为空"}
    if not password:
        return {"success": False, "error": "密码不能为空"}

    credential_ref = auth_db._seal_json_payload(  # noqa: SLF001 - shared sealed-payload helper
        {"username": username, "password": password}
    )
    conn_manager = auth_db.get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings
                    SET credential_ref = %s,
                        profile_status = 'verifying',
                        playbook_status = 'ok',
                        cron_pause_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND data_source_id = %s
                    RETURNING id, company_id, data_source_id, shop_id, playbook_id,
                              agent_id, egress_group, profile_status, playbook_status,
                              cron_pause_reason, last_collection_at, updated_at
                    """,
                    (credential_ref, company_id, data_source_id),
                )
                row = cur.fetchone()
                conn.commit()
    except Exception as e:
        logger.error(f"更新浏览器任务凭证失败 (data_source_id={data_source_id}): {e}")
        return {"success": False, "error": "更新浏览器任务凭证失败"}

    if not row:
        return {"success": False, "error": "浏览器任务缺少运行时绑定，无法更新凭证"}

    binding = auth_db._normalize_record(dict(row))  # noqa: SLF001 - existing db row normalizer
    return {
        "success": True,
        "source_id": data_source_id,
        "credential": {
            "username": username,
            "password_saved": True,
        },
        "binding": binding,
        "message": "浏览器任务凭证已保存",
    }

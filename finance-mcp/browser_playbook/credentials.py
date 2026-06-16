"""Credential updates for browser playbook runtime bindings."""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

import psycopg2.extras

from auth import db as auth_db

logger = logging.getLogger(__name__)


def registrable_domain(host: str) -> str:
    """Best-effort eTLD+1 of a host, so SSO sibling subdomains map to one login identity.

    e.g. mms.pinduoduo.com & cashier.pinduoduo.com -> pinduoduo.com (PDD orders live on mms,
    bills on cashier, but share one SSO login); myseller.taobao.com -> taobao.com. Handles the
    common ``*.com.cn`` compound suffix; not a full public-suffix list, which is overkill for
    the platforms we collect from.
    """
    labels = [p for p in str(host or "").lower().split(".") if p]
    if len(labels) <= 2:
        return ".".join(labels)
    compound_slds = {"com", "net", "org", "gov", "edu"}
    if labels[-1] == "cn" and labels[-2] in compound_slds and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def browser_login_profile_ref(*, playbook_body: dict[str, Any], username: str) -> str:
    """Derive a stable per-login profile ref = (login domain + username).

    Browser collection shares one persistent Chrome profile per *login identity* (same account
    on the same platform), so datasets authenticating as the same account reuse one session
    instead of each logging in. Keyed on:
      - the *registrable domain* of the first step URL — NOT the full host (PDD orders are on
        mms.pinduoduo.com, bills on cashier.pinduoduo.com but share one SSO login -> both must
        resolve to pinduoduo.com), and NOT the data-page path (differs per dataset);
      - the *username* — NOT the full credential_ref, which is enc(username+password) and
        rotates when the password changes (rotation would orphan the profile -> relogin).
    Returns "" when either part is missing (caller leaves runtime_profile_ref blank -> runner
    falls back to shop_id).
    """
    user = str(username or "").strip()
    if not user:
        return ""
    steps = playbook_body.get("steps") or playbook_body.get("actions") or []
    domain = ""
    for step in steps:
        if not isinstance(step, dict):
            continue
        url = str(
            step.get("url")
            or step.get("target_url")
            or (step.get("params") or {}).get("url")
            or ""
        ).strip()
        if url:
            domain = registrable_domain(urlparse(url).netloc)
            if domain:
                break
    if not domain:
        return ""
    digest = hashlib.sha1(f"{domain}|{user}".encode("utf-8")).hexdigest()[:16]
    return f"login::{domain}::{digest}"


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
                # Derive the per-login profile ref from (playbook login domain + username) so that
                # tasks sharing one account (same username on the same platform) collapse onto one
                # Chrome profile/session. Computed here because this is the first point the username
                # is known. Write it when the ref is empty OR when the username changed and the
                # stored ref is exactly the *old* username's auto-derived value — so correcting a
                # wrong username re-derives a matching ref (and same-account tasks re-share) without
                # ever clobbering a hand-customized ref or churning on an unchanged username.
                cur.execute(
                    """
                    SELECT p.playbook_body, srb.credential_ref AS old_credential_ref
                    FROM shop_runtime_bindings srb
                    JOIN playbooks p
                      ON p.company_id = srb.company_id AND p.playbook_id = srb.playbook_id
                    WHERE srb.company_id = %s AND srb.data_source_id = %s
                    ORDER BY (p.status = 'active') DESC, p.version DESC
                    LIMIT 1
                    """,
                    (company_id, data_source_id),
                )
                pb_row = cur.fetchone() or {}
                playbook_body = dict(pb_row.get("playbook_body") or {})
                computed_profile_ref = browser_login_profile_ref(
                    playbook_body=playbook_body, username=username
                )
                old_username = ""
                old_ref_value = str(pb_row.get("old_credential_ref") or "")
                if old_ref_value:
                    try:
                        old_username = str(
                            (auth_db._open_json_payload(old_ref_value) or {}).get("username") or ""  # noqa: SLF001
                        ).strip()
                    except Exception:
                        old_username = ""
                old_profile_ref = (
                    browser_login_profile_ref(playbook_body=playbook_body, username=old_username)
                    if old_username
                    else ""
                )
                cur.execute(
                    """
                    UPDATE shop_runtime_bindings
                    SET credential_ref = %s,
                        profile_status = 'verifying',
                        playbook_status = 'ok',
                        cron_pause_reason = NULL,
                        runtime_profile_ref = CASE
                            WHEN COALESCE(runtime_profile_ref, '') = '' THEN %s
                            WHEN %s <> '' AND runtime_profile_ref = %s THEN %s
                            ELSE runtime_profile_ref
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND data_source_id = %s
                    RETURNING id, company_id, data_source_id, shop_id, playbook_id,
                              agent_id, egress_group, profile_status, playbook_status,
                              cron_pause_reason, last_collection_at, updated_at, runtime_profile_ref
                    """,
                    (
                        credential_ref,
                        computed_profile_ref,
                        old_profile_ref,
                        old_profile_ref,
                        computed_profile_ref,
                        company_id,
                        data_source_id,
                    ),
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

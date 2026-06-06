"""Browser-agent assignment and migration helpers."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

import psycopg2.extras

from auth.db import get_conn

logger = logging.getLogger(__name__)

DEFAULT_ONLINE_THRESHOLD_SECONDS = 180


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key == "running_sync_job_ids":
            normalized[key] = _normalize_running_sync_job_ids(value)
        else:
            normalized[key] = _normalize_value(value)
    return normalized


def _normalize_running_sync_job_ids(value: Any) -> list[str]:
    if value in (None, "", "{}"):
        return []
    if isinstance(value, str):
        raw_value = value.strip()
        if raw_value in ("", "{}"):
            return []
        if raw_value.startswith("{") and raw_value.endswith("}"):
            raw_value = raw_value[1:-1]
            if not raw_value:
                return []
            return [
                item.strip().strip('"')
                for item in raw_value.split(",")
                if item.strip().strip('"')
            ]
        return [raw_value]
    if isinstance(value, (list, tuple, set)):
        return [str(_normalize_value(item)) for item in value if _normalize_value(item) not in (None, "")]
    return [str(_normalize_value(value))]


def _normalize_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_value(item) for item in value]
    return value


def _is_online(row: dict[str, Any], *, online_threshold_seconds: int) -> bool:
    heartbeat = row.get("last_heartbeat_at")
    if not isinstance(heartbeat, datetime):
        return False
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    elapsed = (_now_utc() - heartbeat.astimezone(timezone.utc)).total_seconds()
    return str(row.get("status") or "") == "online" and elapsed <= online_threshold_seconds


def _target_agent_status(
    cur: Any,
    *,
    company_id: str,
    agent_id: str,
    online_threshold_seconds: int,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT agent_id, hostname, version, status, capabilities, last_heartbeat_at
        FROM agents
        WHERE company_id = %s
          AND agent_id = %s
        LIMIT 1
        """,
        (company_id, agent_id),
    )
    row = cur.fetchone()
    if not row:
        return {"agent_id": agent_id, "is_online": False, "exists": False}
    normalized = _normalize_row(dict(row))
    normalized["exists"] = True
    normalized["is_online"] = _is_online(dict(row), online_threshold_seconds=online_threshold_seconds)
    return normalized


def list_browser_agents(
    *,
    company_id: str,
    online_threshold_seconds: int = DEFAULT_ONLINE_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """List browser agents for a company with computed online status."""
    try:
        conn_manager = get_conn()
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT agent_id, hostname, version, status, capabilities, last_heartbeat_at
                    FROM agents
                    WHERE company_id = %s
                    ORDER BY agent_id ASC
                    """,
                    (company_id,),
                )
                agents = []
                for row in cur.fetchall():
                    raw_row = dict(row)
                    normalized = _normalize_row(raw_row)
                    normalized["is_online"] = _is_online(
                        raw_row,
                        online_threshold_seconds=online_threshold_seconds,
                    )
                    agents.append(normalized)
                return {"success": True, "count": len(agents), "agents": agents}
    except Exception as e:
        logger.error(f"查询 browser agents 失败 (company_id={company_id}): {e}")
        return {"success": False, "error": str(e), "error_code": "database_error"}


def _binding_filters_sql(
    *,
    agent_id: str = "",
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
) -> tuple[str, list[Any]]:
    filters: list[str] = []
    params: list[Any] = []

    if agent_id:
        filters.append("srb.agent_id = %s")
        params.append(agent_id)
    if data_source_id:
        filters.append("srb.data_source_id = %s")
        params.append(data_source_id)
    if shop_id:
        filters.append("srb.shop_id = %s")
        params.append(shop_id)
    if playbook_id:
        filters.append("srb.playbook_id = %s")
        params.append(playbook_id)

    if not filters:
        return "", []
    return "\n                      AND " + "\n                      AND ".join(filters), params


def _list_browser_bindings_in_cursor(
    cur: Any,
    *,
    company_id: str,
    agent_id: str = "",
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
    lock_rows: bool = False,
) -> list[dict[str, Any]]:
    filters_sql, filter_params = _binding_filters_sql(
        agent_id=agent_id,
        data_source_id=data_source_id,
        shop_id=shop_id,
        playbook_id=playbook_id,
    )
    lock_sql = "FOR UPDATE OF srb" if lock_rows else ""
    cur.execute(
        f"""
        SELECT srb.data_source_id,
               ds.code AS data_source_code,
               ds.name AS data_source_name,
               srb.shop_id,
               srb.playbook_id,
               srb.agent_id,
               srb.profile_status,
               srb.playbook_status,
               srb.cron_pause_reason,
               srb.last_collection_at,
               COALESCE(running_jobs.running_sync_job_ids, ARRAY[]::text[]) AS running_sync_job_ids,
               COALESCE(running_jobs.has_running_job, FALSE) AS has_running_job
        FROM shop_runtime_bindings srb
        JOIN data_sources ds
          ON ds.id = srb.data_source_id
         AND ds.company_id = srb.company_id
        LEFT JOIN LATERAL (
            SELECT array_agg(sj.id::text ORDER BY sj.created_at ASC) AS running_sync_job_ids,
                   COUNT(sj.id) > 0 AS has_running_job
            FROM sync_jobs sj
            WHERE sj.company_id = srb.company_id
              AND sj.data_source_id = srb.data_source_id
              AND sj.job_status = 'running'
        ) running_jobs ON TRUE
        WHERE srb.company_id = %s
          AND ds.source_kind = 'browser_playbook'{filters_sql}
        ORDER BY srb.agent_id ASC, srb.shop_id ASC, srb.playbook_id ASC, srb.data_source_id ASC
        {lock_sql}
        """,
        (company_id, *filter_params),
    )
    return [_normalize_row(dict(row)) for row in cur.fetchall()]


def list_browser_bindings(
    *,
    company_id: str,
    agent_id: str = "",
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
) -> dict[str, Any]:
    """List browser playbook runtime bindings and running-job flags."""
    try:
        conn_manager = get_conn()
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                bindings = _list_browser_bindings_in_cursor(
                    cur,
                    company_id=company_id,
                    agent_id=agent_id,
                    data_source_id=data_source_id,
                    shop_id=shop_id,
                    playbook_id=playbook_id,
                )
                return {"success": True, "count": len(bindings), "bindings": bindings}
    except Exception as e:
        logger.error(f"查询 browser bindings 失败 (company_id={company_id}): {e}")
        return {"success": False, "error": str(e), "error_code": "database_error"}


def _validation_error(error: str, error_code: str) -> dict[str, Any]:
    return {"success": False, "error": error, "error_code": error_code}


def _flatten_running_sync_job_ids(bindings: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for binding in bindings:
        for sync_job_id in binding.get("running_sync_job_ids") or []:
            ids.append(str(sync_job_id))
    return ids


def _running_sync_job_ids_for_data_sources(
    cur: Any,
    *,
    company_id: str,
    data_source_ids: list[str],
) -> list[str]:
    if not data_source_ids:
        return []
    cur.execute(
        """
        SELECT sj.id::text AS id
        FROM sync_jobs sj
        WHERE sj.company_id = %s
          AND sj.data_source_id = ANY(%s::uuid[])
          AND sj.job_status = 'running'
        ORDER BY sj.created_at ASC, sj.id ASC
        """,
        (company_id, data_source_ids),
    )
    return [str(row["id"]) for row in cur.fetchall()]


def reassign_browser_bindings(
    *,
    company_id: str,
    from_agent_id: str,
    to_agent_id: str,
    data_source_id: str = "",
    shop_id: str = "",
    playbook_id: str = "",
    dry_run: bool = True,
    require_online: bool = True,
    force_offline_target: bool = False,
    online_threshold_seconds: int = DEFAULT_ONLINE_THRESHOLD_SECONDS,
) -> dict[str, Any]:
    """Move selected browser runtime bindings from one agent to another."""
    from_agent_id = str(from_agent_id or "").strip()
    to_agent_id = str(to_agent_id or "").strip()
    if not from_agent_id:
        return _validation_error("source agent is required", "missing_from_agent")
    if not to_agent_id:
        return _validation_error("target agent is required", "missing_to_agent")
    if from_agent_id == to_agent_id:
        return _validation_error("source and target agent are the same", "same_agent")

    try:
        conn_manager = get_conn()
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                target_status = _target_agent_status(
                    cur,
                    company_id=company_id,
                    agent_id=to_agent_id,
                    online_threshold_seconds=online_threshold_seconds,
                )
                bindings = _list_browser_bindings_in_cursor(
                    cur,
                    company_id=company_id,
                    agent_id=from_agent_id,
                    data_source_id=data_source_id,
                    shop_id=shop_id,
                    playbook_id=playbook_id,
                    lock_rows=not dry_run,
                )
                base_result: dict[str, Any] = {
                    "success": True,
                    "dry_run": dry_run,
                    "matched_count": len(bindings),
                    "updated_count": 0,
                    "target_agent": target_status,
                    "bindings": bindings,
                }

                target_missing = not target_status.get("exists")
                target_offline = require_online and not target_status.get("is_online")
                if dry_run:
                    if target_missing and not force_offline_target:
                        base_result["would_block"] = True
                        base_result["blocked_reason"] = "target_agent_missing"
                    elif target_offline and not force_offline_target:
                        base_result["would_block"] = True
                        base_result["blocked_reason"] = "target_agent_offline"
                    return base_result

                if target_missing and not force_offline_target:
                    return {
                        **base_result,
                        "success": False,
                        "error": "target agent does not exist",
                        "error_code": "target_agent_missing",
                    }

                if target_offline and not force_offline_target:
                    return {
                        **base_result,
                        "success": False,
                        "error": "target agent is offline",
                        "error_code": "target_agent_offline",
                    }

                running_sync_job_ids = _flatten_running_sync_job_ids(bindings)
                if running_sync_job_ids:
                    return {
                        **base_result,
                        "success": False,
                        "error": "matched bindings have running jobs",
                        "error_code": "running_jobs_present",
                        "running_sync_job_ids": running_sync_job_ids,
                    }

                data_source_ids = [str(binding["data_source_id"]) for binding in bindings]
                if not data_source_ids:
                    return base_result

                running_sync_job_ids = _running_sync_job_ids_for_data_sources(
                    cur,
                    company_id=company_id,
                    data_source_ids=data_source_ids,
                )
                if running_sync_job_ids:
                    return {
                        **base_result,
                        "success": False,
                        "error": "matched bindings have running jobs",
                        "error_code": "running_jobs_present",
                        "running_sync_job_ids": running_sync_job_ids,
                    }

                cur.execute(
                    """
                    UPDATE shop_runtime_bindings
                    SET agent_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE company_id = %s
                      AND agent_id = %s
                      AND data_source_id = ANY(%s::uuid[])
                    RETURNING data_source_id, agent_id
                    """,
                    (to_agent_id, company_id, from_agent_id, data_source_ids),
                )
                updated_rows = [_normalize_row(dict(row)) for row in cur.fetchall()]
                conn.commit()
                return {
                    **base_result,
                    "updated_count": len(updated_rows),
                    "updated_bindings": updated_rows,
                }
    except Exception as e:
        logger.error(
            "迁移 browser bindings 失败 "
            f"(company_id={company_id}, from_agent_id={from_agent_id}, to_agent_id={to_agent_id}): {e}"
        )
        return {"success": False, "error": str(e), "error_code": "database_error"}

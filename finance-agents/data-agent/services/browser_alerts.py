"""Browser collection alerting through the existing notification adapter stack."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import psycopg2
import psycopg2.extras

from config import (
    BROWSER_COLLECTION_ALERT_AGENT_GRACE_MINUTES,
    BROWSER_COLLECTION_ALERT_MISSED_SUCCESS_HOURS,
    BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD,
    DATABASE_URL,
)
from services.notifications.dingtalk_dws import DingTalkDwsAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserAlertEvent:
    event_type: str
    company_id: str
    shop_id: str
    data_source_name: str
    biz_date: str = ""
    sync_job_id: str = ""
    agent_id: str = ""
    severity: str = "warning"
    reason: str = ""
    message: str = ""

    @property
    def dedupe_key(self) -> str:
        parts = [
            self.event_type,
            self.company_id,
            self.shop_id or self.agent_id,
            self.biz_date,
            self.sync_job_id,
            self.reason,
        ]
        return ":".join(str(part or "").strip() for part in parts)

    @property
    def source_id(self) -> str:
        stable_id = self.sync_job_id or self.agent_id or self.shop_id or self.company_id
        return f"{self.event_type}:{stable_id}"


class BrowserAlertService:
    def __init__(
        self,
        *,
        adapter_factory: Callable[[], Any] | None = None,
        dedupe_checker: Callable[[str], bool] | None = None,
        alert_recorder: Callable[[str, dict[str, Any]], None] | None = None,
        recipient_keyword: str = BROWSER_COLLECTION_ALERT_RECIPIENT_KEYWORD,
    ) -> None:
        self.adapter_factory = adapter_factory or self._build_adapter
        self.dedupe_checker = dedupe_checker or browser_alert_sent
        self.alert_recorder = alert_recorder or record_browser_alert_sent
        self.recipient_keyword = recipient_keyword or "周行"

    def send_alert(self, event: BrowserAlertEvent) -> dict[str, Any]:
        dedupe_key = event.dedupe_key
        if self.dedupe_checker(dedupe_key):
            return {"status": "skipped", "reason": "deduped", "dedupe_key": dedupe_key}

        adapter = self.adapter_factory()
        title = _compose_alert_title(event)
        content = _compose_alert_content(event)
        resolved = adapter.resolve_user(keyword=self.recipient_keyword)
        if not resolved.success or resolved.resolved_user is None:
            return {
                "status": "failed",
                "reason": resolved.code or "user_resolve_failed",
                "message": resolved.message or "无法定位浏览器采集告警接收人",
                "provider": adapter.provider,
                "dedupe_key": dedupe_key,
            }
        receiver = resolved.resolved_user
        bot_result = adapter.send_bot_message(
            title=title,
            content=content,
            to_user_id=str(receiver.user_id or ""),
            content_type="markdown",
        )
        result = {
            "status": "sent" if bot_result.success else "failed",
            "reason": "" if bot_result.success else (bot_result.code or "send_failed"),
            "message": bot_result.message,
            "provider": bot_result.provider,
            "dedupe_key": dedupe_key,
            "message_id": bot_result.message_id,
            "receiver_user_id": str(receiver.user_id or ""),
        }
        if bot_result.success:
            self.alert_recorder(dedupe_key, result)
        return result

    @staticmethod
    def _build_adapter() -> Any:
        return DingTalkDwsAdapter()


def ensure_browser_alerts_table() -> None:
    sql = """
        CREATE TABLE IF NOT EXISTS browser_alert_events (
            id bigserial PRIMARY KEY,
            dedupe_key text NOT NULL UNIQUE,
            result jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


def browser_alert_sent(dedupe_key: str) -> bool:
    try:
        ensure_browser_alerts_table()
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS (SELECT 1 FROM browser_alert_events WHERE dedupe_key = %s)",
                    (dedupe_key,),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception as exc:
        logger.error("检查浏览器采集告警去重失败: %s", exc)
        return False


def record_browser_alert_sent(dedupe_key: str, result: dict[str, Any]) -> None:
    try:
        ensure_browser_alerts_table()
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO browser_alert_events (dedupe_key, result)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (dedupe_key) DO NOTHING
                    """,
                    (
                        dedupe_key,
                        psycopg2.extras.Json(result or {}),
                    ),
                )
            conn.commit()
    except Exception as exc:
        logger.error("记录浏览器采集告警去重失败: %s", exc)


def collect_browser_alert_events(
    *,
    agent_grace_minutes: int = BROWSER_COLLECTION_ALERT_AGENT_GRACE_MINUTES,
    missed_success_hours: int = BROWSER_COLLECTION_ALERT_MISSED_SUCCESS_HOURS,
) -> list[BrowserAlertEvent]:
    """Collect minimal first-store browser alert events from PostgreSQL state."""
    events: list[BrowserAlertEvent] = []
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT s.id AS sync_job_id, s.company_id, s.data_source_id,
                           s.resource_key, s.window_start, s.browser_fail_reason,
                           s.error_message, ds.name AS data_source_name,
                           COALESCE(b.shop_id, ds.code, '') AS shop_id
                    FROM sync_jobs s
                    JOIN data_sources ds ON ds.id = s.data_source_id
                    LEFT JOIN shop_runtime_bindings b
                      ON b.company_id = s.company_id
                     AND b.data_source_id = s.data_source_id
                    WHERE ds.source_kind = 'browser_playbook'
                      AND ds.status <> 'deleted'
                      AND s.job_status = 'failed'
                      AND COALESCE(s.browser_fail_reason, '') <> ''
                      AND s.completed_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                    ORDER BY s.completed_at DESC
                    LIMIT 100
                    """
                )
                for row in cur.fetchall() or []:
                    reason = str(row.get("browser_fail_reason") or "").strip()
                    events.append(
                        BrowserAlertEvent(
                            event_type="risk_blocked" if reason == "RISK_VERIFICATION" else "browser_sync_failed",
                            company_id=str(row.get("company_id") or ""),
                            shop_id=str(row.get("shop_id") or ""),
                            data_source_name=str(row.get("data_source_name") or row.get("resource_key") or "浏览器采集"),
                            biz_date=str(row.get("window_start") or "")[:10],
                            sync_job_id=str(row.get("sync_job_id") or ""),
                            severity="critical",
                            reason=reason,
                            message=str(row.get("error_message") or ""),
                        )
                    )

                cur.execute(
                    """
                    SELECT a.company_id, a.agent_id, a.hostname, a.status, a.last_heartbeat_at
                    FROM agents a
                    WHERE (
                        a.status <> 'online'
                        OR a.last_heartbeat_at IS NULL
                        OR a.last_heartbeat_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 minute')
                    )
                    ORDER BY a.updated_at DESC
                    LIMIT 100
                    """,
                    (max(1, int(agent_grace_minutes)),),
                )
                for row in cur.fetchall() or []:
                    events.append(
                        BrowserAlertEvent(
                            event_type="browser_agent_offline",
                            company_id=str(row.get("company_id") or ""),
                            shop_id="",
                            data_source_name="浏览器采集机",
                            agent_id=str(row.get("agent_id") or ""),
                            severity="critical",
                            reason="AGENT_OFFLINE",
                            message=(
                                f"agent={row.get('agent_id') or ''} status={row.get('status') or ''} "
                                f"last_heartbeat_at={row.get('last_heartbeat_at') or ''}"
                            ).strip(),
                        )
                    )

                cur.execute(
                    """
                    SELECT b.company_id, b.shop_id, b.agent_id, b.last_collection_at,
                           ds.name AS data_source_name
                    FROM shop_runtime_bindings b
                    JOIN data_sources ds ON ds.id = b.data_source_id
                    WHERE ds.source_kind = 'browser_playbook'
                      AND ds.status <> 'deleted'
                      AND b.profile_status = 'active'
                      AND b.playbook_status = 'ok'
                      AND (
                          b.last_collection_at IS NULL
                          OR b.last_collection_at < CURRENT_TIMESTAMP - (%s * INTERVAL '1 hour')
                      )
                    ORDER BY b.updated_at DESC
                    LIMIT 100
                    """,
                    (max(1, int(missed_success_hours)),),
                )
                for row in cur.fetchall() or []:
                    events.append(
                        BrowserAlertEvent(
                            event_type="browser_collection_missed",
                            company_id=str(row.get("company_id") or ""),
                            shop_id=str(row.get("shop_id") or ""),
                            data_source_name=str(row.get("data_source_name") or "浏览器采集"),
                            agent_id=str(row.get("agent_id") or ""),
                            severity="warning",
                            reason="MISSED_SUCCESS",
                            message=f"最近成功采集时间: {row.get('last_collection_at') or '从未成功采集'}",
                        )
                    )

                cur.execute(
                    """
                    SELECT id, company_id, run_plan_code, biz_date, error
                    FROM recon_execution_queue
                    WHERE status = 'failed'
                      AND finished_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                      AND (
                          error ILIKE '%%浏览器采集%%'
                          OR error ILIKE '%%采集未就绪%%'
                          OR error ILIKE '%%browser%%'
                      )
                    ORDER BY finished_at DESC
                    LIMIT 100
                    """
                )
                for row in cur.fetchall() or []:
                    events.append(
                        BrowserAlertEvent(
                            event_type="browser_recon_data_unavailable",
                            company_id=str(row.get("company_id") or ""),
                            shop_id=str(row.get("run_plan_code") or ""),
                            data_source_name="自动对账任务",
                            biz_date=str(row.get("biz_date") or ""),
                            sync_job_id=str(row.get("id") or ""),
                            severity="critical",
                            reason="RECON_DATA_UNAVAILABLE",
                            message=str(row.get("error") or ""),
                        )
                    )
    except Exception as exc:
        logger.error("采集浏览器告警事件失败: %s", exc)
    return events


def send_pending_browser_alerts(service: BrowserAlertService | None = None) -> list[dict[str, Any]]:
    active_service = service or BrowserAlertService()
    results: list[dict[str, Any]] = []
    for event in collect_browser_alert_events():
        results.append(active_service.send_alert(event))
    return results


def _compose_alert_title(event: BrowserAlertEvent) -> str:
    label = {
        "browser_sync_failed": "浏览器采集失败",
        "risk_blocked": "浏览器采集风控验证",
        "browser_agent_offline": "浏览器采集机离线",
        "browser_collection_missed": "浏览器采集连续未成功",
        "browser_recon_data_unavailable": "浏览器数据未就绪导致对账失败",
    }.get(event.event_type, "浏览器采集告警")
    shop = event.shop_id or event.agent_id or "unknown"
    return f"Tally {label}: {shop}"


def _reason_explanation(event: BrowserAlertEvent) -> str:
    reason = str(event.reason or "").strip().upper()
    if reason == "AGENT_INTERRUPTED":
        return "采集任务运行中，浏览器采集机或本地服务被重启/中断，任务未正常跑完。"
    if reason == "AUTH_EXPIRED":
        return "店铺登录态已失效，需要重新登录后再采集。"
    if reason == "RISK_VERIFICATION":
        return "平台触发安全验证，需要人工完成页面验证后再采集。"
    if reason == "PAGE_CHANGED":
        return "采集页面结构变化，当前 playbook 可能需要更新。"
    if reason:
        return f"浏览器采集失败，原因码: {reason}。"
    return "浏览器采集失败，系统未返回明确原因码。"


def _next_action(event: BrowserAlertEvent) -> str:
    reason = str(event.reason or "").strip().upper()
    if reason == "AGENT_INTERRUPTED":
        return "确认是否刚执行过服务重启/发版；确认采集机在线后，重新采集或重新触发本次对账。"
    if reason == "AUTH_EXPIRED":
        return "打开对应店铺浏览器登录态，完成登录后重新采集/重新对账。"
    if reason == "RISK_VERIFICATION":
        return "进入采集机浏览器完成平台验证，再重新采集/重新对账。"
    if reason == "PAGE_CHANGED":
        return "检查页面是否改版，更新或重放 playbook 后再重新采集。"
    return "检查采集机在线状态、店铺登录态、页面验证和 playbook 状态后重新采集/重新对账。"


def _compose_alert_content(event: BrowserAlertEvent) -> str:
    lines = [
        f"告警类型: {event.event_type}",
        f"严重级别: {event.severity}",
        f"数据源/店铺: {event.data_source_name} / {event.shop_id or '-'}",
    ]
    if event.biz_date:
        lines.append(f"业务日期: {event.biz_date}")
    if event.sync_job_id:
        lines.append(f"sync_job_id: {event.sync_job_id}")
    if event.agent_id:
        lines.append(f"agent_id: {event.agent_id}")
    if event.reason:
        lines.append(f"原因码: {event.reason}")
        lines.append(f"直观原因: {_reason_explanation(event)}")
    if event.message:
        lines.append(f"错误摘要: {event.message}")
    lines.append(f"处理建议: {_next_action(event)}")
    return "\n".join(lines)

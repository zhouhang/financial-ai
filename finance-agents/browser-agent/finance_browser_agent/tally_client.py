"""Browser-agent → Tally Cloud data-agent WS client.

Owns:
- ``BrowserAgentConfig``: env-loaded service configuration (agent id, WS URL, polling,
  concurrency).
- ``create_system_token``: mint a short-lived JWT with ``role="system"`` so the data-agent
  gate accepts the worker.
- ``BrowserAgentTallyClient``: stateful client. ``worker_token`` is a refresh-aware property
  that re-mints the JWT 5 minutes before expiry, so a multi-hour browser-agent process never
  ships expired tokens. Communicates via domain messages over WebSocket to the data-agent.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from finance_browser_agent.data_agent_ws import DataAgentWsClient
from finance_browser_agent.remote_control import RemoteControlCoordinator


JWT_ALGORITHM = "HS256"
_TOKEN_LIFETIME = timedelta(hours=2)
_TOKEN_REFRESH_LEAD_SECONDS = 300  # refresh 5 min before expiry


@dataclass(frozen=True)
class BrowserAgentConfig:
    agent_id: str
    company_id: str
    data_agent_ws_url: str
    poll_interval_seconds: float
    max_concurrency: int
    waiting_poll_interval_seconds: float
    heartbeat_interval_seconds: float

    @classmethod
    def from_env(cls) -> "BrowserAgentConfig":
        hostname = socket.gethostname() or "local"
        return cls(
            agent_id=os.getenv("BROWSER_AGENT_ID", f"browser-agent-{hostname}"),
            company_id=os.getenv("BROWSER_AGENT_COMPANY_ID", "").strip(),
            data_agent_ws_url=os.getenv("DATA_AGENT_WS_URL", "ws://127.0.0.1:8100/browser-agent"),
            poll_interval_seconds=max(
                1.0, float(os.getenv("BROWSER_AGENT_POLL_INTERVAL_SECONDS", "2"))
            ),
            max_concurrency=max(1, int(os.getenv("BROWSER_AGENT_MAX_CONCURRENCY", "2"))),
            waiting_poll_interval_seconds=max(
                5.0, float(os.getenv("BROWSER_AGENT_WAITING_POLL_INTERVAL_SECONDS", "30"))
            ),
            heartbeat_interval_seconds=max(
                10.0, float(os.getenv("BROWSER_AGENT_HEARTBEAT_INTERVAL_SECONDS", "30"))
            ),
        )


def create_system_token(*, agent_id: str) -> str:
    jwt_secret = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"browser-agent:{agent_id}",
        "username": "browser-agent",
        "role": "system",
        "company_id": None,
        "department_id": None,
        "iat": now,
        "exp": now + _TOKEN_LIFETIME,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)


class BrowserAgentTallyClient:
    """Data-agent WS client with self-refreshing system token.

    Communicates with the data-agent over WebSocket using domain message types.
    The data-agent injects ``worker_token`` into outbound messages, except for
    ``heartbeat`` which explicitly carries the current token so the data-agent
    can refresh it.
    """

    def __init__(self, *, config: BrowserAgentConfig, ws_client: "DataAgentWsClient | None" = None) -> None:
        self.config = config
        self._token: str = ""
        self._token_expires_at: float = 0.0

        async def _handoff_unavailable(payload: dict[str, Any]) -> dict[str, Any]:
            return {"success": False, "error": "handoff unavailable"}

        if ws_client is None:
            self.handoff_coordinator = RemoteControlCoordinator(
                send_event=lambda payload: self._client.send_event(payload)
            )
            self._client = DataAgentWsClient(
                ws_url=config.data_agent_ws_url,
                agent_id=config.agent_id,
                max_concurrency=config.max_concurrency,
                token_provider=lambda: self.worker_token,
                event_handler=self.handoff_coordinator.handle_event,
            )
        else:
            send_event = getattr(ws_client, "send_event", None)
            self.handoff_coordinator = RemoteControlCoordinator(
                send_event=send_event if callable(send_event) else _handoff_unavailable
            )
            self._client = ws_client

    @property
    def worker_token(self) -> str:
        now_ts = datetime.now(timezone.utc).timestamp()
        if not self._token or now_ts >= self._token_expires_at - _TOKEN_REFRESH_LEAD_SECONDS:
            self._token = create_system_token(agent_id=self.config.agent_id)
            self._token_expires_at = (
                datetime.now(timezone.utc) + _TOKEN_LIFETIME
            ).timestamp()
        return self._token

    async def claim_browser_job(self) -> dict[str, Any]:
        return await self._client.request("claim", {})

    async def startup_cleanup(self) -> dict[str, Any]:
        return await self._client.request("startup_cleanup", {})

    async def heartbeat(self, *, company_id: str | None = None) -> dict[str, Any]:
        resolved_company_id = (company_id or self.config.company_id or "").strip()
        return await self._client.request("heartbeat", {
            "token": self.worker_token,
            "company_id": resolved_company_id,
            "hostname": socket.gethostname() or "",
            "version": os.getenv("BROWSER_AGENT_VERSION", ""),
            "capabilities": {
                "runner": os.getenv("BROWSER_AGENT_RUNNER_MODE", "playwright"),
                "browser_channel": os.getenv("BROWSER_AGENT_BROWSER_CHANNEL", "chrome"),
                "headless": os.getenv("BROWSER_AGENT_HEADLESS", "0"),
                "max_concurrency": self.config.max_concurrency,
            },
        })

    async def mark_browser_job_success(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._client.request("job_complete", dict(payload))

    async def mark_browser_job_failed(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._client.request("job_fail", dict(payload))

    async def requeue_ready_waiting(self) -> dict[str, Any]:
        return await self._client.request("queue_requeue_ready", {})

    async def fail_failed_waiting(self) -> dict[str, Any]:
        return await self._client.request("queue_fail_failed", {})

    async def fail_expired_waiting(self) -> dict[str, Any]:
        return await self._client.request("queue_fail_expired", {})

    async def report_risk_waiting(self, **kwargs):
        return await self._client.report_risk_waiting(**kwargs)

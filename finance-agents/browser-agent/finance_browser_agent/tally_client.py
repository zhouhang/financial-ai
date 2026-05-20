"""Browser-agent → Tally Cloud MCP client.

Owns:
- ``BrowserAgentConfig``: env-loaded service configuration (agent id, base URL, polling,
  concurrency).
- ``create_system_token``: mint a short-lived JWT with ``role="system"`` so finance-mcp's
  ``_require_system`` gate accepts the worker.
- ``BrowserAgentTallyClient``: stateful client. ``worker_token`` is a refresh-aware property
  that re-mints the JWT 5 minutes before expiry, so a multi-hour browser-agent process never
  ships expired tokens to MCP.

Async MCP tool wrappers (claim / complete / fail / waiting-data reconciler) are added in T7
once the corresponding finance-mcp tools exist.
"""

from __future__ import annotations

import os
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from finance_browser_agent.mcp_session import McpSession


JWT_ALGORITHM = "HS256"
_TOKEN_LIFETIME = timedelta(hours=2)
_TOKEN_REFRESH_LEAD_SECONDS = 300  # refresh 5 min before expiry


@dataclass(frozen=True)
class BrowserAgentConfig:
    agent_id: str
    mcp_base_url: str
    poll_interval_seconds: float
    max_concurrency: int
    waiting_poll_interval_seconds: float

    @classmethod
    def from_env(cls) -> "BrowserAgentConfig":
        hostname = socket.gethostname() or "local"
        return cls(
            agent_id=os.getenv("BROWSER_AGENT_ID", f"browser-agent-{hostname}"),
            mcp_base_url=os.getenv("FINANCE_MCP_BASE_URL", "http://127.0.0.1:3335"),
            poll_interval_seconds=max(
                1.0, float(os.getenv("BROWSER_AGENT_POLL_INTERVAL_SECONDS", "2"))
            ),
            max_concurrency=max(1, int(os.getenv("BROWSER_AGENT_MAX_CONCURRENCY", "2"))),
            waiting_poll_interval_seconds=max(
                5.0, float(os.getenv("BROWSER_AGENT_WAITING_POLL_INTERVAL_SECONDS", "30"))
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
    """MCP client shell with self-refreshing system token.

    Async tool wrappers (``claim_browser_job`` / ``mark_browser_job_success`` /
    ``mark_browser_job_failed`` / waiting-data reconciler tools) are filled in by T7. T6 only
    establishes the config + token-refresh seam so long-running services don't hit a hard 401
    at the 2-hour mark.
    """

    def __init__(self, *, config: BrowserAgentConfig, session: McpSession | None = None) -> None:
        self.config = config
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._session = session or McpSession(base_url=config.mcp_base_url)

    @property
    def worker_token(self) -> str:
        now_ts = datetime.now(timezone.utc).timestamp()
        if not self._token or now_ts >= self._token_expires_at - _TOKEN_REFRESH_LEAD_SECONDS:
            self._token = create_system_token(agent_id=self.config.agent_id)
            self._token_expires_at = (
                datetime.now(timezone.utc) + _TOKEN_LIFETIME
            ).timestamp()
        return self._token

    async def _call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        return await self._session.call_tool(tool_name, args)

    async def claim_browser_job(self) -> dict[str, Any]:
        return await self._call(
            "browser_sync_job_claim",
            {
                "worker_token": self.worker_token,
                "agent_id": self.config.agent_id,
                "max_concurrency": self.config.max_concurrency,
            },
        )

    async def mark_browser_job_success(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "browser_sync_job_complete",
            {"worker_token": self.worker_token, **payload},
        )

    async def mark_browser_job_failed(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._call(
            "browser_sync_job_fail",
            {"worker_token": self.worker_token, **payload},
        )

    async def requeue_ready_waiting(self) -> dict[str, Any]:
        return await self._call(
            "recon_queue_requeue_ready_waiting",
            {"worker_token": self.worker_token},
        )

    async def fail_failed_waiting(self) -> dict[str, Any]:
        return await self._call(
            "recon_queue_fail_failed_collection_waiting",
            {"worker_token": self.worker_token},
        )

    async def fail_expired_waiting(self) -> dict[str, Any]:
        return await self._call(
            "recon_queue_fail_expired_waiting",
            {"worker_token": self.worker_token},
        )

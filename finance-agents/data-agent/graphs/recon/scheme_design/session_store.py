"""In-memory design session store with TTL."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import SchemeDesignSession, SchemeDesignStatus


class InMemorySchemeDesignSessionStore:
    def __init__(self, *, ttl_seconds: int = 2 * 60 * 60):
        self._ttl_seconds = max(60, int(ttl_seconds))
        self._sessions: dict[str, SchemeDesignSession] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _next_expiry(self) -> datetime:
        return self._now() + timedelta(seconds=self._ttl_seconds)

    def _is_expired(self, session: SchemeDesignSession) -> bool:
        return session.expires_at <= self._now()

    async def create(self, session: SchemeDesignSession) -> SchemeDesignSession:
        async with self._lock:
            self._cleanup_expired_locked()
            session.expires_at = self._next_expiry()
            self._sessions[session.session_id] = session.model_copy(deep=True)
            return session.model_copy(deep=True)

    async def get(
        self,
        session_id: str,
        *,
        touch: bool = True,
    ) -> Optional[SchemeDesignSession]:
        async with self._lock:
            self._cleanup_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if self._is_expired(session):
                expired = session.model_copy(deep=True)
                expired.status = SchemeDesignStatus.EXPIRED
                self._sessions.pop(session_id, None)
                return expired
            if touch and session.status in (
                SchemeDesignStatus.DRAFT,
                SchemeDesignStatus.WAITING_CONFIRM,
            ):
                session.updated_at = self._now()
                session.expires_at = self._next_expiry()
                self._sessions[session_id] = session
            return session.model_copy(deep=True)

    async def upsert(self, session: SchemeDesignSession) -> SchemeDesignSession:
        async with self._lock:
            self._cleanup_expired_locked()
            if session.status in (SchemeDesignStatus.DRAFT, SchemeDesignStatus.WAITING_CONFIRM):
                session.expires_at = self._next_expiry()
            self._sessions[session.session_id] = session.model_copy(deep=True)
            return session.model_copy(deep=True)

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def _cleanup_expired_locked(self) -> None:
        now = self._now()
        stale_ids = [sid for sid, s in self._sessions.items() if s.expires_at <= now]
        for sid in stale_ids:
            self._sessions.pop(sid, None)


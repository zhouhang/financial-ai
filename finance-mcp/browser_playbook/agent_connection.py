"""Browser collection agent connection abstractions."""

from __future__ import annotations

from typing import Any, Protocol


class AgentConnectionManager(Protocol):
    def dispatch(self, agent_id: str, message: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        """Dispatch a RUN_PLAYBOOK message and return a TASK_RESULT payload."""
        raise NotImplementedError


class FakeAgentConnectionManager:
    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}
        self.messages: list[dict[str, Any]] = []

    def register_result(self, agent_id: str, result: dict[str, Any]) -> None:
        self._results[agent_id] = result

    def dispatch(self, agent_id: str, message: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        self.messages.append({"agent_id": agent_id, "message": message, "timeout_ms": timeout_ms})
        if agent_id not in self._results:
            return {
                "job_id": message.get("job_id"),
                "status": "failed",
                "fail_reason": "AGENT_OFFLINE",
                "error_info": {"message": "agent offline"},
            }
        return self._results[agent_id]


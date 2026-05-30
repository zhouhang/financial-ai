from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RECON_DIR = ROOT / "graphs" / "recon"

sys.path.insert(0, str(ROOT))


def _ensure_package(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module
    return module


_ensure_package("graphs.recon", RECON_DIR)

auto_run_service = importlib.import_module("graphs.recon.auto_run_service")
auto_run_api = importlib.import_module("graphs.recon.auto_run_api")
notifications_models = importlib.import_module("services.notifications.models")

TodoSyncResult = notifications_models.TodoSyncResult
UnifiedTodoStatus = notifications_models.UnifiedTodoStatus


class _FakeAdapter:
    """模拟通知适配器，返回固定的钉钉待办同步状态。"""

    def __init__(self, *, status: UnifiedTodoStatus) -> None:
        self.provider = "dingtalk_dws"
        self._status = status
        self.synced_todo_ids: list[str] = []

    def sync_todo_status(
        self,
        *,
        todo_id: str,
        max_polls: int = 1,
        poll_interval_seconds: float = 1.0,
    ) -> "TodoSyncResult":
        self.synced_todo_ids.append(todo_id)
        return TodoSyncResult(
            success=True,
            provider=self.provider,
            message="ok",
            todo_id=todo_id,
            status=self._status,
            is_terminal=self._status in notifications_models.TERMINAL_TODO_STATUSES,
            polls=1,
        )


def _patch_common(monkeypatch: pytest.MonkeyPatch, *, adapter: _FakeAdapter, batches: list[dict]) -> dict:
    captured: dict = {"bulk_calls": []}

    async def fake_list_batches(auth_token: str, **kwargs):
        captured["list_auth_token"] = auth_token
        return {"success": True, "batches": batches}

    async def fake_bulk_update(auth_token: str, run_id: str, payload: dict):
        captured["bulk_calls"].append({"run_id": run_id, "payload": payload})
        return {"success": True, "updated_count": 3, "exceptions": []}

    monkeypatch.setattr(
        auto_run_service, "execution_run_exception_list_pending_todo_batches", fake_list_batches
    )
    monkeypatch.setattr(
        auto_run_service, "execution_run_exception_bulk_update_by_owner", fake_bulk_update
    )
    monkeypatch.setattr(
        auto_run_service, "load_company_channel_config_by_id", lambda channel_id: object()
    )
    monkeypatch.setattr(
        auto_run_service, "get_notification_adapter", lambda **kwargs: adapter
    )
    return captured


def test_sync_pending_todo_exceptions_marks_completed_batch_owner_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(status=UnifiedTodoStatus.COMPLETED)
    batches = [
        {
            "company_id": "company-001",
            "run_id": "run-001",
            "owner_identifier": "ding-user-001",
            "todo_id": "todo-001",
            "channel_config_id": "channel-001",
        }
    ]
    captured = _patch_common(monkeypatch, adapter=adapter, batches=batches)

    result = asyncio.run(
        auto_run_service.sync_pending_todo_exceptions(auth_token="scheduler-token")
    )

    assert result["success"] is True
    assert result["completed"] == 1
    assert result["updated_count"] == 3
    assert adapter.synced_todo_ids == ["todo-001"]

    assert len(captured["bulk_calls"]) == 1
    call = captured["bulk_calls"][0]
    assert call["run_id"] == "run-001"
    assert call["payload"]["company_id"] == "company-001"
    assert call["payload"]["processing_status"] == "owner_done"
    assert call["payload"]["fix_status"] == "ready_for_verify"
    assert call["payload"]["reminder_status"] == "completed"
    assert call["payload"]["owner_identifier"] == "ding-user-001"


def test_sync_pending_todo_exceptions_skips_open_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(status=UnifiedTodoStatus.OPEN)
    batches = [
        {
            "company_id": "company-001",
            "run_id": "run-001",
            "owner_identifier": "ding-user-001",
            "todo_id": "todo-001",
            "channel_config_id": "channel-001",
        }
    ]
    captured = _patch_common(monkeypatch, adapter=adapter, batches=batches)

    result = asyncio.run(
        auto_run_service.sync_pending_todo_exceptions(auth_token="scheduler-token")
    )

    assert result["success"] is True
    assert result["completed"] == 0
    assert result["updated_count"] == 0
    assert adapter.synced_todo_ids == ["todo-001"]
    assert captured["bulk_calls"] == []


def test_sync_pending_todos_endpoint_forwards_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_sync(**kwargs):
        captured.update(kwargs)
        return {"success": True, "batch_count": 2, "completed": 1, "updated_count": 3}

    monkeypatch.setattr(auto_run_api, "sync_pending_todo_exceptions", fake_sync)

    body = auto_run_api.PendingTodoSyncRequest(
        limit=50, max_age_days=7, max_polls=2, poll_interval_seconds=1.5
    )
    result = asyncio.run(
        auto_run_api.sync_pending_todo_exceptions_api(body, authorization="Bearer scheduler-token")
    )

    assert result["success"] is True
    assert result["completed"] == 1
    assert captured["auth_token"] == "scheduler-token"
    assert captured["limit"] == 50
    assert captured["max_age_days"] == 7
    assert captured["max_polls"] == 2
    assert captured["poll_interval_seconds"] == 1.5


def test_sync_pending_todos_endpoint_requires_token() -> None:
    body = auto_run_api.PendingTodoSyncRequest()
    with pytest.raises(auto_run_api.HTTPException) as exc:
        asyncio.run(auto_run_api.sync_pending_todo_exceptions_api(body, authorization=None))
    assert exc.value.status_code == 401

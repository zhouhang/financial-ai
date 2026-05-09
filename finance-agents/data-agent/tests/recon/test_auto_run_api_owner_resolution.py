from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

import jwt
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

auto_run_api = importlib.import_module("graphs.recon.auto_run_api")
notifications_models = importlib.import_module("services.notifications.models")

NotificationChannelConfig = notifications_models.NotificationChannelConfig
NotificationUser = notifications_models.NotificationUser
UserResolveResult = notifications_models.UserResolveResult


def _auth_header() -> str:
    token = jwt.encode(
        {
            "sub": "user-001",
            "username": "admin",
            "company_id": "company-001",
        },
        auto_run_api.JWT_SECRET,
        algorithm=auto_run_api.JWT_ALGORITHM,
    )
    return f"Bearer {token}"


class _FakeAdapter:
    def __init__(self, *, users: list[NotificationUser], success: bool = True, message: str = "ok"):
        self.calls: list[dict[str, str]] = []
        self._users = users
        self._success = success
        self._message = message

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        self.calls.append({"user_id": user_id, "mobile": mobile, "keyword": keyword})
        resolved_user = self._users[0] if len(self._users) == 1 else None
        return UserResolveResult(
            success=self._success,
            provider="dingtalk_dws",
            message=self._message,
            users=self._users,
            resolved_user=resolved_user,
        )


def _channel_config() -> NotificationChannelConfig:
    return NotificationChannelConfig(
        id="channel-001",
        company_id="company-001",
        provider="dingtalk_dws",
        channel_code="default",
        name="默认钉钉",
        client_id="cid",
        client_secret="secret",
        robot_code="robot",
        is_default=True,
        is_enabled=True,
    )


def test_delete_execution_run_api_calls_mcp_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_delete(auth_token: str, run_id: str) -> dict[str, object]:
        captured["auth_token"] = auth_token
        captured["run_id"] = run_id
        return {"success": True, "run": {"id": run_id}, "message": "运行记录已删除"}

    monkeypatch.setattr(auto_run_api, "execution_run_delete", fake_delete)

    result = asyncio.run(
        auto_run_api.delete_execution_run_api("run-001", authorization=_auth_header())
    )

    assert result["success"] is True
    assert captured["run_id"] == "run-001"
    assert captured["auth_token"]


def test_create_execution_task_resolves_owner_identifier_before_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def passthrough(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        return payload

    captured: dict[str, object] = {}

    async def fake_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {"success": True, "run_plan": payload}

    adapter = _FakeAdapter(
        users=[NotificationUser(user_id="ding-user-001", display_name="周行", mobile="13800000000")]
    )

    monkeypatch.setattr(auto_run_api, "_normalize_run_plan_payload_date_fields", passthrough)
    monkeypatch.setattr(auto_run_api, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(auto_run_api, "get_notification_adapter", lambda **kwargs: adapter)
    monkeypatch.setattr(auto_run_api, "execution_run_plan_create", fake_create)

    body = auto_run_api.ExecutionTaskCreateRequest(
        plan_name="店铺对账 T-1",
        scheme_code="scheme_001",
        channel_config_id="channel-001",
        summary_recipient={"name": "周行"},
        owner_mapping_json={"default_owner": {"name": "周行"}},
    )

    result = asyncio.run(
        auto_run_api.create_execution_task_api(body, authorization=_auth_header())
    )

    default_owner = captured["owner_mapping_json"]["default_owner"]
    assert result["success"] is True
    assert adapter.calls == [
        {"user_id": "", "mobile": "", "keyword": "周行"},
        {"user_id": "", "mobile": "", "keyword": "周行"},
    ]
    assert default_owner["name"] == "周行"
    assert default_owner["identifier"] == "ding-user-001"
    assert captured["plan_meta_json"]["summary_recipient"]["display_name"] == "周行"
    assert captured["plan_meta_json"]["summary_recipient"]["user_id"] == "ding-user-001"


def test_create_auto_task_resolves_owner_identifier_before_save(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_create(auth_token: str, payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {"success": True, "task": payload}

    adapter = _FakeAdapter(
        users=[NotificationUser(user_id="ding-user-002", display_name="李四", mobile="13900000000")]
    )

    monkeypatch.setattr(auto_run_api, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(auto_run_api, "get_notification_adapter", lambda **kwargs: adapter)
    monkeypatch.setattr(auto_run_api, "recon_auto_task_create", fake_create)

    body = auto_run_api.AutoTaskCreateRequest(
        task_name="自动对账任务",
        rule_code="rule_001",
        channel_config_id="channel-001",
        owner_mapping_json={"default_owner": {"name": "李四"}},
    )

    result = asyncio.run(auto_run_api.create_auto_task(body, authorization=_auth_header()))

    default_owner = captured["owner_mapping_json"]["default_owner"]
    assert result["success"] is True
    assert adapter.calls == [{"user_id": "", "mobile": "", "keyword": "李四"}]
    assert default_owner["name"] == "李四"
    assert default_owner["identifier"] == "ding-user-002"


def test_normalize_owner_mapping_rejects_ambiguous_owner_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(
        users=[
            NotificationUser(user_id="ding-user-001", display_name="周行"),
            NotificationUser(user_id="ding-user-002", display_name="周行"),
        ]
    )

    monkeypatch.setattr(auto_run_api, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(auto_run_api, "get_notification_adapter", lambda **kwargs: adapter)

    with pytest.raises(auto_run_api.HTTPException) as exc:
        asyncio.run(
            auto_run_api._normalize_owner_mapping_identifiers(
                _auth_header().replace("Bearer ", ""),
                {
                    "channel_config_id": "channel-001",
                    "owner_mapping_json": {"default_owner": {"name": "周行"}},
                },
            )
        )

    assert exc.value.status_code == 400
    assert "在“默认钉钉”组织中匹配到 2 个钉钉用户" in str(exc.value.detail)


def test_normalize_owner_mapping_keeps_existing_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(users=[])

    monkeypatch.setattr(auto_run_api, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(auto_run_api, "get_notification_adapter", lambda **kwargs: adapter)

    result = asyncio.run(
        auto_run_api._normalize_owner_mapping_identifiers(
            _auth_header().replace("Bearer ", ""),
            {
                "channel_config_id": "channel-001",
                "owner_mapping_json": {
                    "default_owner": {"name": "周行", "identifier": "ding-user-001"}
                },
            },
        )
    )

    default_owner = result["owner_mapping_json"]["default_owner"]
    assert default_owner["name"] == "周行"
    assert default_owner["identifier"] == "ding-user-001"
    assert adapter.calls == []


def test_search_owner_candidates_returns_masked_disambiguation_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(
        users=[
            NotificationUser(
                user_id="ding-user-001",
                display_name="周行",
                mobile="13800001234",
                organization="华东公司",
                departments=["财务部"],
            ),
            NotificationUser(
                user_id="ding-user-002",
                display_name="周行",
                mobile="13900005678",
                organization="华南公司",
                departments=["结算组"],
            ),
        ]
    )

    monkeypatch.setattr(auto_run_api, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(auto_run_api, "get_notification_adapter", lambda **kwargs: adapter)

    result = asyncio.run(
        auto_run_api.search_owner_candidates(
            auto_run_api.OwnerCandidateSearchRequest(
                query="周行",
                channel_config_id="channel-001",
            ),
            authorization=_auth_header(),
        )
    )

    assert result["success"] is True
    assert adapter.calls == [{"user_id": "", "mobile": "", "keyword": "周行"}]
    assert result["candidates"][0]["display_name"] == "周行"
    assert result["candidates"][0]["identifier"] == "ding-user-001"
    assert result["candidates"][0]["organization"] == "华东公司"
    assert result["candidates"][0]["departments"] == ["财务部"]
    assert result["candidates"][0]["mobile_masked"] == "138****1234"
    assert "ID后6位 er-001" in result["candidates"][0]["disambiguation_label"]


def test_normalize_owner_mapping_rejects_missing_owner_in_organization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _FakeAdapter(users=[], success=False, message="未找到匹配的钉钉用户: 王五")

    monkeypatch.setattr(auto_run_api, "load_company_channel_config_by_id", lambda channel_id: _channel_config())
    monkeypatch.setattr(auto_run_api, "get_notification_adapter", lambda **kwargs: adapter)

    with pytest.raises(auto_run_api.HTTPException) as exc:
        asyncio.run(
            auto_run_api._normalize_owner_mapping_identifiers(
                _auth_header().replace("Bearer ", ""),
                {
                    "channel_config_id": "channel-001",
                    "owner_mapping_json": {"default_owner": {"name": "王五"}},
                },
            )
        )

    assert exc.value.status_code == 400
    assert str(exc.value.detail) == "责任人“王五”不在“默认钉钉”组织中，请检查后重试"

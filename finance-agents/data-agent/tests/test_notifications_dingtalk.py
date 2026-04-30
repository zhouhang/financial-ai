from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications import get_notification_adapter
from services.notifications.cli import CLIExecutionResult, SubprocessCLIExecutor, _parse_payload
from services.notifications.dingtalk_dws import DingTalkDwsAdapter
from services.notifications.models import NotificationChannelConfig, NotificationProvider, UnifiedTodoStatus


class FakeExecutor:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def run(self, args, timeout_seconds, *, env=None):
        self.calls.append(
            {
                "args": list(args),
                "timeout_seconds": timeout_seconds,
                "env": dict(env or {}),
            }
        )
        response = self._responses.pop(0)
        if callable(response):
            return response(args, timeout_seconds, env=env)
        return response


def _result(payload: dict, *, success: bool = True, exit_code: int = 0) -> CLIExecutionResult:
    return CLIExecutionResult(
        success=success,
        exit_code=exit_code,
        stdout="",
        stderr="",
        payload=payload,
        command=[],
    )


def test_resolve_user_by_keyword_queries_search_without_contact_detail_lookup():
    executor = FakeExecutor(
        [
            _result({"userId": ["01205058704740"]}),
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot",
    )

    result = adapter.resolve_user(keyword="周行")

    assert result.success is True
    assert result.resolved_user is not None
    assert result.resolved_user.user_id == "01205058704740"
    assert result.resolved_user.display_name == "周行"
    assert executor.calls[0]["args"] == ["dws", "contact", "user", "search", "--query", "周行", "-f", "json"]
    assert len(executor.calls) == 1
    assert executor.calls[0]["env"]["DWS_CLIENT_ID"] == "cid"
    assert executor.calls[0]["env"]["DWS_CLIENT_SECRET"] == "secret"


def test_resolve_user_by_user_id_does_not_call_contact_get():
    executor = FakeExecutor([])
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot",
    )

    result = adapter.resolve_user(user_id="01205058704740")

    assert result.success is True
    assert result.resolved_user is not None
    assert result.resolved_user.user_id == "01205058704740"
    assert executor.calls == []


def test_resolve_user_by_keyword_enriches_multiple_matches_with_contact_detail():
    executor = FakeExecutor(
        [
            _result({"userId": ["u-001", "u-002"]}),
            _result(
                {
                    "result": [
                        {
                            "orgEmployeeModel": {
                                "orgUserId": "u-001",
                                "orgUserName": "张三",
                                "orgUserMobile": "13800000001",
                                "orgName": "华东公司",
                                "deptNameList": ["财务部"],
                            }
                        },
                        {
                            "orgEmployeeModel": {
                                "orgUserId": "u-002",
                                "orgUserName": "张三",
                                "orgUserMobile": "13900000002",
                                "orgName": "华南公司",
                                "deptNameList": ["结算组"],
                            }
                        },
                    ]
                }
            ),
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot",
    )

    result = adapter.resolve_user(keyword="张三")

    assert result.success is True
    assert result.resolved_user is None
    assert [user.user_id for user in result.users] == ["u-001", "u-002"]
    assert result.users[0].organization == "华东公司"
    assert result.users[0].departments == ["财务部"]
    assert result.users[0].mobile == "13800000001"
    assert executor.calls[1]["args"] == [
        "dws",
        "contact",
        "user",
        "get",
        "--ids",
        "u-001,u-002",
        "-f",
        "json",
    ]


def test_send_bot_message_requires_robot_code():
    adapter = DingTalkDwsAdapter(
        executor=FakeExecutor([]),
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="",
    )

    result = adapter.send_bot_message(content="hello", to_user_id="u1")

    assert result.success is False
    assert result.code == "missing_robot_code"


def test_send_reminder_runs_bot_and_todo_flow():
    executor = FakeExecutor(
        [
            _result({"success": True, "result": {"taskId": "todo-1"}}),
            _result(
                {
                    "success": True,
                    "result": {
                        "todoDetailModel": {
                            "taskId": "todo-1",
                            "subject": "催办标题",
                            "isDone": False,
                            "executorIds": ["u1"],
                        }
                    },
                }
            ),
            _result(
                {
                    "success": True,
                    "errorCode": 0,
                    "result": {"processQueryKey": "msg-1"},
                }
            ),
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot-1",
    )

    result = adapter.send_reminder(
        title="催办标题",
        content="请处理异常",
        assignee_user_id="u1",
    )

    assert result.success is True
    assert result.bot_result is not None and result.bot_result.message_id == "msg-1"
    assert result.todo_result is not None and result.todo_result.todo is not None
    assert result.todo_result.todo.todo_id == "todo-1"
    assert executor.calls[2]["args"][:8] == [
        "dws",
        "chat",
        "message",
        "send-by-bot",
        "--robot-code",
        "robot-1",
        "--title",
        "催办标题",
    ]
    assert executor.calls[2]["args"][-4:] == [
        "--users",
        "u1",
        "-f",
        "json",
    ]


def test_update_todo_maps_completed_status_to_done_flag():
    executor = FakeExecutor(
        [
            _result({"result": {"success": True}}),
            _result(
                {
                    "success": True,
                    "result": {
                        "todoDetailModel": {
                            "taskId": "todo-1",
                            "subject": "任务",
                            "isDone": True,
                            "executorIds": ["u1"],
                        }
                    },
                }
            ),
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot-1",
    )

    result = adapter.update_todo(todo_id="todo-1", status="completed")

    assert result.success is True
    assert executor.calls[0]["args"] == [
        "dws",
        "todo",
        "task",
        "update",
        "--task-id",
        "todo-1",
        "--done",
        "true",
        "-f",
        "json",
    ]


def test_sync_todo_status_returns_terminal_completed():
    executor = FakeExecutor(
        [
            _result(
                {
                    "success": True,
                    "result": {
                        "todoDetailModel": {
                            "taskId": "todo-1",
                            "subject": "任务",
                            "isDone": True,
                            "executorIds": ["u1"],
                        }
                    },
                }
            )
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot-1",
    )

    result = adapter.sync_todo_status(todo_id="todo-1", max_polls=3, poll_interval_seconds=0)

    assert result.success is True
    assert result.status == UnifiedTodoStatus.COMPLETED
    assert result.is_terminal is True
    assert result.history == [UnifiedTodoStatus.COMPLETED]


def test_get_todo_falls_back_to_completed_list_when_detail_is_empty():
    executor = FakeExecutor(
        [
            _result({"success": True, "result": {}}),
            _result(
                {
                    "success": True,
                    "result": {
                        "todoCards": [
                            {
                                "taskId": "todo-1",
                                "subject": "任务",
                                "finalStatusStage": 2,
                            }
                        ]
                    },
                }
            ),
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot-1",
    )

    result = adapter.get_todo(todo_id="todo-1")

    assert result.success is True
    assert result.todo is not None
    assert result.todo.todo_id == "todo-1"
    assert result.todo.status == UnifiedTodoStatus.COMPLETED
    assert executor.calls[1]["args"] == [
        "dws",
        "todo",
        "task",
        "list",
        "--page",
        "1",
        "--size",
        "20",
        "--status",
        "true",
        "-f",
        "json",
    ]


def test_create_todo_fails_when_task_id_is_missing():
    executor = FakeExecutor(
        [
            _result({"success": True, "result": {}}),
        ]
    )
    adapter = DingTalkDwsAdapter(
        executor=executor,
        cli_bin="dws",
        client_id="cid",
        client_secret="secret",
        robot_code="robot-1",
    )

    result = adapter.create_todo(assignee_user_id="u1", title="任务")

    assert result.success is False
    assert result.code == "empty_task_id"


def test_notification_factory_returns_dingtalk_adapter():
    adapter = get_notification_adapter(
        NotificationProvider.DINGTALK_DWS,
        executor=FakeExecutor([]),
        channel_config=NotificationChannelConfig(
            provider=NotificationProvider.DINGTALK_DWS.value,
            client_id="cid",
            client_secret="secret",
            robot_code="robot-1",
        ),
    )

    assert isinstance(adapter, DingTalkDwsAdapter)


def test_notification_factory_prefers_db_channel_config(monkeypatch):
    monkeypatch.setattr(
        "services.notifications.load_company_channel_config",
        lambda **kwargs: NotificationChannelConfig(
            provider=NotificationProvider.DINGTALK_DWS.value,
            client_id="db-cid",
            client_secret="db-secret",
            robot_code="db-robot",
        ),
    )

    adapter = get_notification_adapter(
        NotificationProvider.DINGTALK_DWS,
        executor=FakeExecutor([]),
        company_id="company-1",
    )

    assert isinstance(adapter, DingTalkDwsAdapter)
    assert adapter._client_id == "db-cid"
    assert adapter._client_secret == "db-secret"
    assert adapter._robot_code == "db-robot"


def test_parse_payload_extracts_last_json_object():
    payload = _parse_payload('yes\n{"result":{"success":true}}')

    assert payload == {"result": {"success": True}}


def test_subprocess_executor_handles_generic_oserror(monkeypatch):
    def raise_oserror(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("services.notifications.cli.subprocess.run", raise_oserror)
    executor = SubprocessCLIExecutor()

    result = executor.run(["dws"], 1)

    assert result.success is False
    assert result.exit_code == 126
    assert "permission denied" in result.stderr

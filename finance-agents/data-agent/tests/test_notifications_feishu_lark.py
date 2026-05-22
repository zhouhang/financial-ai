from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications.cli import CLIExecutionResult
from services.notifications.feishu_lark import FeishuLarkCliAdapter


class FakeExecutor:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def run(self, args, timeout_seconds, *, env=None):
        self.calls.append({"args": list(args), "timeout_seconds": timeout_seconds, "env": dict(env or {})})
        return self._responses.pop(0)


def _result(payload, *, success=True, exit_code=0, stderr=""):
    return CLIExecutionResult(success=success, exit_code=exit_code, stdout="", stderr=stderr, payload=payload, command=[])


def _adapter(executor, **kw):
    base = dict(executor=executor, cli_bin="lark-cli", state_dir="/tmp/tally-notify-test",
                company_id="company-A", target_chat="oc_chat")
    base.update(kw)
    return FeishuLarkCliAdapter(**base)


def test_send_bot_message_builds_api_post_command():
    # lark-cli api 信封:成功为 {"ok": true}
    executor = FakeExecutor([_result({"ok": True, "data": {"message_id": "om_x"}})])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is True
    args = executor.calls[0]["args"]
    assert args[0] == "lark-cli"
    assert args[1:4] == ["api", "POST", "/open-apis/im/v1/messages"]
    assert "--as" in args and "bot" in args
    assert args[-2:] == ["--format", "json"]
    # data 里带目标 chat 与文本内容
    data_idx = args.index("--data")
    body = json.loads(args[data_idx + 1])
    assert body["receive_id"] == "oc_chat"
    assert body["msg_type"] == "text"
    assert json.loads(body["content"])["text"] == "hello"
    # 按公司隔离 env
    assert "company-A" in executor.calls[0]["env"]["HOME"]


def test_send_bot_message_missing_chat_returns_invalid_input():
    executor = FakeExecutor([])
    adapter = _adapter(executor, target_chat="")
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "invalid_input"
    assert executor.calls == []


def test_send_bot_message_cli_error_maps_error_message():
    executor = FakeExecutor([_result({"ok": False, "error": {"message": "app no permission"}}, success=True)])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"
    assert "app no permission" in res.message


def test_send_bot_message_cli_not_installed():
    executor = FakeExecutor([_result({}, success=False, exit_code=127, stderr="command not found")])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"
    assert "command not found" in res.message


def test_send_reminder_is_message_only():
    executor = FakeExecutor([_result({"ok": True})])
    adapter = _adapter(executor)
    res = adapter.send_reminder(title="标题", content="正文", assignee_user_id="")
    assert res.success is True
    assert res.todo_result is None
    body = json.loads(executor.calls[0]["args"][executor.calls[0]["args"].index("--data") + 1])
    assert "标题" in json.loads(body["content"])["text"]


def test_resolve_user_passthrough_and_search_unsupported():
    adapter = _adapter(FakeExecutor([]))
    ok = adapter.resolve_user(user_id="ou_1")
    assert ok.success is True and ok.resolved_user.user_id == "ou_1"
    miss = adapter.resolve_user(keyword="张三")
    assert miss.success is False and miss.code == "feishu_lark_unsupported"


def test_todo_methods_unsupported():
    adapter = _adapter(FakeExecutor([]))
    assert adapter.create_todo(assignee_user_id="u1", title="t").code == "feishu_lark_unsupported"
    assert adapter.list_todos().code == "feishu_lark_unsupported"
    assert adapter.sync_todo_status(todo_id="x").code == "feishu_lark_unsupported"


def test_disabled_adapter_short_circuits():
    executor = FakeExecutor([])
    adapter = _adapter(executor, enabled=False)
    res = adapter.send_bot_message(content="hi", to_user_id="")
    assert res.success is False and res.code == "disabled"
    assert executor.calls == []

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

    def run(self, args, timeout_seconds, *, env=None, input_text=None):
        self.calls.append({
            "args": list(args),
            "timeout_seconds": timeout_seconds,
            "env": dict(env or {}),
            "input_text": input_text,
        })
        return self._responses.pop(0)


def _result(payload, *, success=True, exit_code=0, stderr=""):
    return CLIExecutionResult(success=success, exit_code=exit_code, stdout="", stderr=stderr, payload=payload, command=[])


def _mark_provisioned(state_dir, company_id="company-A"):
    """预先创建 lark-cli config.json,使适配器视该公司已初始化(跳过 provision)。"""
    cfg = Path(state_dir) / "feishu" / company_id / ".lark-cli" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('{"appId":"x"}', encoding="utf-8")


def _adapter(executor, state_dir, **kw):
    base = dict(executor=executor, cli_bin="lark-cli", state_dir=str(state_dir),
                company_id="company-A", app_id="cli_app", app_secret="sec", target_chat="oc_chat")
    base.update(kw)
    return FeishuLarkCliAdapter(**base)


def test_send_bot_message_builds_api_post_command(tmp_path):
    _mark_provisioned(tmp_path)
    executor = FakeExecutor([_result({"ok": True, "data": {"message_id": "om_x"}})])
    adapter = _adapter(executor, tmp_path)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is True
    args = executor.calls[0]["args"]
    assert args[0] == "lark-cli"
    assert args[1:4] == ["api", "POST", "/open-apis/im/v1/messages"]
    assert "--as" in args and "bot" in args
    assert args[-2:] == ["--format", "json"]
    data_idx = args.index("--data")
    body = json.loads(args[data_idx + 1])
    assert body["receive_id"] == "oc_chat"
    assert body["msg_type"] == "text"
    assert json.loads(body["content"])["text"] == "hello"
    assert "company-A" in executor.calls[0]["env"]["HOME"]


def test_send_bot_message_missing_chat_returns_invalid_input(tmp_path):
    executor = FakeExecutor([])
    adapter = _adapter(executor, tmp_path, target_chat="")
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "invalid_input"
    assert executor.calls == []


def test_send_bot_message_cli_error_maps_error_message(tmp_path):
    _mark_provisioned(tmp_path)
    executor = FakeExecutor([_result({"ok": False, "error": {"message": "app no permission"}}, success=True)])
    adapter = _adapter(executor, tmp_path)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"
    assert "app no permission" in res.message


def test_send_bot_message_cli_not_installed(tmp_path):
    _mark_provisioned(tmp_path)
    executor = FakeExecutor([_result({}, success=False, exit_code=127, stderr="command not found")])
    adapter = _adapter(executor, tmp_path)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"
    assert "command not found" in res.message


def test_send_reminder_is_message_only(tmp_path):
    _mark_provisioned(tmp_path)
    executor = FakeExecutor([_result({"ok": True})])
    adapter = _adapter(executor, tmp_path)
    res = adapter.send_reminder(title="标题", content="正文", assignee_user_id="")
    assert res.success is True
    assert res.todo_result is None
    body = json.loads(executor.calls[0]["args"][executor.calls[0]["args"].index("--data") + 1])
    assert "标题" in json.loads(body["content"])["text"]


def test_first_send_provisions_via_config_init_then_sends(tmp_path):
    # 未初始化:第一次发送应先 config init(secret 走 stdin),再发消息
    executor = FakeExecutor([
        _result({}, success=True),               # config init
        _result({"ok": True}, success=True),      # send
    ])
    adapter = _adapter(executor, tmp_path)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is True
    assert len(executor.calls) == 2
    init_args = executor.calls[0]["args"]
    assert init_args[1:3] == ["config", "init"]
    assert "--app-id" in init_args and "cli_app" in init_args
    assert "--app-secret-stdin" in init_args
    assert executor.calls[0]["input_text"].strip() == "sec"  # secret 经 stdin,不在 args 里
    assert "sec" not in init_args
    assert executor.calls[1]["args"][1:4] == ["api", "POST", "/open-apis/im/v1/messages"]


def test_provision_fails_without_credentials(tmp_path):
    executor = FakeExecutor([])
    adapter = _adapter(executor, tmp_path, app_secret="")
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "missing_credentials"
    assert executor.calls == []


def test_provision_failure_short_circuits_send(tmp_path):
    executor = FakeExecutor([_result({}, success=False, exit_code=1, stderr="invalid app secret")])
    adapter = _adapter(executor, tmp_path)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "provision_failed"
    assert "invalid app secret" in res.message
    assert len(executor.calls) == 1  # 只跑了 config init,没发消息


def test_resolve_user_passthrough_and_search_unsupported(tmp_path):
    adapter = _adapter(FakeExecutor([]), tmp_path)
    ok = adapter.resolve_user(user_id="ou_1")
    assert ok.success is True and ok.resolved_user.user_id == "ou_1"
    miss = adapter.resolve_user(keyword="张三")
    assert miss.success is False and miss.code == "feishu_lark_unsupported"


def test_todo_methods_unsupported(tmp_path):
    adapter = _adapter(FakeExecutor([]), tmp_path)
    assert adapter.create_todo(assignee_user_id="u1", title="t").code == "feishu_lark_unsupported"
    assert adapter.list_todos().code == "feishu_lark_unsupported"
    assert adapter.sync_todo_status(todo_id="x").code == "feishu_lark_unsupported"


def test_disabled_adapter_short_circuits(tmp_path):
    executor = FakeExecutor([])
    adapter = _adapter(executor, tmp_path, enabled=False)
    res = adapter.send_bot_message(content="hi", to_user_id="")
    assert res.success is False and res.code == "disabled"
    assert executor.calls == []

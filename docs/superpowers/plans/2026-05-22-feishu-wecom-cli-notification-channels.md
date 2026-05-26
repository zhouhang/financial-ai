# 飞书 / 企微 CLI 消息推送渠道接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给运行计划的消息推送新增飞书(`larksuite/cli`)与企微(`wecom-pro`)两个渠道,沿用现有 `NotificationAdapter` 抽象与 `channel_config_id` 管道,凭证按公司隔离。

**Architecture:** 两个新适配器 shell 调各自 CLI(仿 `DingTalkDwsAdapter`),复用 `SubprocessCLIExecutor`;多公司隔离靠"每公司独立配置目录 + 子进程 env 注入"。仅消息推送(`send_bot_message` + 纯消息 `send_reminder`),待办/查人类方法返回 `unsupported`。工厂 `get_notification_adapter` 新增两个 provider 分支。

**Tech Stack:** Python 3.12,FastAPI(data-agent),pytest;外部 CLI:`lark-cli`(Node+Go+Py3)、`wecom-pro`(Rust/npm)。

**关键事实(实现前必读)**
- 适配器目录:`finance-agents/data-agent/services/notifications/`。
- 范式文件:`dingtalk_dws.py`(`DingTalkDwsAdapter`)、`cli.py`(`SubprocessCLIExecutor`/`CLIExecutionResult`)、`models.py`、`base.py`(ABC)、`__init__.py`(工厂 `get_notification_adapter`)、`service.py`(registry)。
- 测试范式:`tests/test_notifications_dingtalk.py`(`FakeExecutor` 记录 `args`/`env`,返回 canned `CLIExecutionResult`)。
- 测试运行:`cd finance-agents/data-agent && python3 -m pytest tests/<file> -v`(测试用 `sys.path.insert(0, parents[1])` 引入 `services`)。
- `config.py` 已有 `NOTIFICATION_CLI_TIMEOUT_SECONDS`、`_get_bool_env`。
- `NotificationProvider` 枚举已含 `feishu` / `wechat_work`。
- `company_channel_configs` 字段:`provider`/`client_id`/`client_secret`/`robot_code`/`company_id`/`extra` 等(`models.py: NotificationChannelConfig`)。

---

## 文件结构(决策锁定)

- Create `services/notifications/cli_isolation.py` — per-company 配置目录与 env 注入 helper(单一职责)。
- Create `services/notifications/wecom_pro.py` — `WecomProCliAdapter`。
- Create `services/notifications/feishu_lark.py` — `FeishuLarkCliAdapter`。
- Modify `config.py` — 新增 `FEISHU_LARK_*` / `WECOM_PRO_*` / `NOTIFY_CLI_STATE_DIR`。
- Modify `services/notifications/__init__.py` — 工厂新增两个分支。
- Modify `services/notifications/service.py` — registry 注册三家。
- Create `tests/test_notifications_cli_isolation.py`、`tests/test_notifications_wecom_pro.py`、`tests/test_notifications_feishu_lark.py`、`tests/test_notifications_factory_providers.py`。
- Create `docs/superpowers/notes/2026-05-22-feishu-wecom-cli-probe.md` — Task 1 探测结论(后续任务的 CLI 契约依据)。

---

## Task 1: CLI 能力探测(GATE,先于写适配器)

这是一个调研/验证任务,不写产品代码,产出一份"CLI 契约"文档供 Task 4/5 据实编码,而非照文档猜。

**Files:**
- Create: `docs/superpowers/notes/2026-05-22-feishu-wecom-cli-probe.md`

- [ ] **Step 1: 安装两个 CLI**

```bash
npm install -g @larksuite/cli @liangdi/wecom-pro 2>&1 | tail -5
command -v lark-cli wecom-pro
```
预期:两个二进制路径都打印出来。若 `lark-cli` 安装需要 Go1.23/Python3 而本机缺失,记录到文档并继续探测 wecom-pro。

- [ ] **Step 2: 抓取两个 CLI 的命令与参数**

```bash
lark-cli --help; lark-cli im --help; lark-cli config --help; lark-cli auth --help
wecom-pro --help; wecom-pro msg --help; wecom-pro init --help
```

- [ ] **Step 3: 把探测结论写进 probe 文档**,逐项回答(每项给出实测命令/输出片段,无法确认的标注"未确认"):

  1. **发消息确切命令与参数**:飞书发到群 chat_id 的命令;企微 `msg send_message` 的 JSON 字段(`chat_type`/`chatid`/`msgtype` 的确切含义,是否为推送而非会话存档)。
  2. **JSON 输出结构**:成功/失败时的字段名(用于判定成功——飞书疑似 `code==0`,企微疑似 `errcode==0`、`errmsg`)。
  3. **凭证/配置存储与隔离**:能否用 `HOME`/`XDG_CONFIG_HOME` 把配置隔离到每公司目录;`wecom-pro init --method manual --bot-id .. --secret ..` 能否非交互注册。
  4. **无头发送**:飞书 `--as bot`(应用身份)能否不弹授权直接发;lark-cli 凭证是否只能进系统钥匙串。
  5. **凭证脱敏**:CLI 的 stdout/stderr 出错时是否回显 secret;若会,则适配器 `_build_cli_error_message` 入库/日志前需脱敏(在对应适配器任务补一条断言)。

- [ ] **Step 4: GATE 决策(写进文档顶部"结论")**

  - 若 **wecom-pro 能非交互发送 + 可按目录隔离** → Task 4 按实测契约实现。否则在文档记录阻塞点并升级给用户。
  - 若 **lark-cli 能 `--as bot` 无头发送 + `HOME`/`XDG` 能隔离** → Task 5 按实测契约实现。
  - 若 **lark-cli 仅钥匙串、无法按公司隔离/无头**(spec 已预警的风险)→ **停在此处升级给用户**,在文档给出退路建议(飞书改 HTTP API,或飞书接受单租户),等用户决策后再做 Task 5。

- [ ] **Step 5: Commit**

```bash
git add -f docs/superpowers/notes/2026-05-22-feishu-wecom-cli-probe.md
git commit -m "docs: feishu/wecom CLI capability probe findings"
```

> Task 4/5 的命令常量与成功判定字段以本文档为准;下文代码为 spec 文档基线,若探测结论不同,**同步改代码常量与对应测试断言**。

---

## Task 2: config.py 新增配置项

**Files:**
- Modify: `finance-agents/data-agent/config.py`(在 `DINGTALK_DEFAULT_TODO_PAGE_SIZE` 行之后,约 line 94)
- Test: `finance-agents/data-agent/tests/test_notifications_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_notifications_config.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


def test_feishu_wecom_config_defaults():
    assert config.FEISHU_LARK_BIN == "lark-cli"
    assert config.WECOM_PRO_BIN == "wecom-pro"
    assert config.FEISHU_LARK_ENABLED is True
    assert config.WECOM_PRO_ENABLED is True
    assert config.NOTIFY_CLI_STATE_DIR  # 非空字符串
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_config.py -v`
Expected: FAIL（`AttributeError: module 'config' has no attribute 'FEISHU_LARK_BIN'`）

- [ ] **Step 3: 实现配置项**

在 `config.py` 的钉钉配置块之后新增:
```python
# ── 飞书 / 企微 CLI 通知 ──────────────────────────────────────────────
FEISHU_LARK_ENABLED: bool = _get_bool_env("FEISHU_LARK_ENABLED", True)
FEISHU_LARK_BIN: str = os.getenv("FEISHU_LARK_BIN", "lark-cli").strip()
WECOM_PRO_ENABLED: bool = _get_bool_env("WECOM_PRO_ENABLED", True)
WECOM_PRO_BIN: str = os.getenv("WECOM_PRO_BIN", "wecom-pro").strip()
# 每公司独立 CLI 配置目录的根,按 <root>/<provider>/<company_id> 隔离凭证
NOTIFY_CLI_STATE_DIR: str = os.getenv(
    "NOTIFY_CLI_STATE_DIR", os.path.expanduser("~/.local/state/tally-notify")
).strip()
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add finance-agents/data-agent/config.py finance-agents/data-agent/tests/test_notifications_config.py
git commit -m "feat(notify): add feishu/wecom CLI config keys"
```

---

## Task 3: per-company 隔离 helper

**Files:**
- Create: `finance-agents/data-agent/services/notifications/cli_isolation.py`
- Test: `finance-agents/data-agent/tests/test_notifications_cli_isolation.py`

- [ ] **Step 1: 写失败测试**

`tests/test_notifications_cli_isolation.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications.cli_isolation import company_cli_env, company_state_dir


def test_company_state_dir_is_isolated_per_company(tmp_path):
    d1 = company_state_dir(str(tmp_path), "wechat_work", "company-A")
    d2 = company_state_dir(str(tmp_path), "wechat_work", "company-B")
    assert d1 != d2
    assert d1.exists() and d2.exists()
    assert "company-A" in str(d1) and "wechat_work" in str(d1)


def test_company_cli_env_points_home_and_xdg_under_company_dir(tmp_path):
    env = company_cli_env(str(tmp_path), "feishu", "company-A")
    assert env["HOME"].startswith(str(tmp_path))
    assert "company-A" in env["HOME"]
    assert env["XDG_CONFIG_HOME"].startswith(env["HOME"])


def test_company_cli_env_blank_company_falls_back_to_default(tmp_path):
    env = company_cli_env(str(tmp_path), "feishu", "")
    assert "default" in env["HOME"]
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_cli_isolation.py -v`
Expected: FAIL（`ModuleNotFoundError: services.notifications.cli_isolation`）

- [ ] **Step 3: 实现 helper**

`services/notifications/cli_isolation.py`:
```python
"""Per-company CLI 配置隔离。

文件型配置的 CLI(lark-cli / wecom-pro)凭证落盘,无法像 dws 那样 per-call env 注入凭证。
改为给每家公司分配独立配置目录,并通过子进程 env(HOME / XDG_CONFIG_HOME)指向它,
使不同公司的 CLI 凭证互不串扰。
"""
from __future__ import annotations

import os
from pathlib import Path


def company_state_dir(base_dir: str, provider: str, company_id: str) -> Path:
    safe_company = (str(company_id or "").strip() or "default")
    path = Path(os.path.expanduser(base_dir)) / provider / safe_company
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def company_cli_env(base_dir: str, provider: str, company_id: str) -> dict[str, str]:
    """返回该公司隔离配置目录对应的子进程 env(HOME + XDG_CONFIG_HOME)。"""
    home = company_state_dir(base_dir, provider, company_id)
    config_home = home / ".config"
    config_home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home), "XDG_CONFIG_HOME": str(config_home)}
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_cli_isolation.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add finance-agents/data-agent/services/notifications/cli_isolation.py finance-agents/data-agent/tests/test_notifications_cli_isolation.py
git commit -m "feat(notify): per-company CLI config isolation helper"
```

---

## Task 4: WecomProCliAdapter(企微)

**Files:**
- Create: `finance-agents/data-agent/services/notifications/wecom_pro.py`
- Test: `finance-agents/data-agent/tests/test_notifications_wecom_pro.py`

> 命令/字段以 Task 1 probe 文档为准。下方为基线:`wecom-pro msg --bot-id <id> send_message '<json>' -o json`。

- [ ] **Step 1: 写失败测试**

`tests/test_notifications_wecom_pro.py`:
```python
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications.cli import CLIExecutionResult
from services.notifications.wecom_pro import WecomProCliAdapter


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
    base = dict(executor=executor, cli_bin="wecom-pro", state_dir="/tmp/tally-notify-test",
                company_id="company-A", bot_id="bot-1", secret="sec", target_chat="chat-x")
    base.update(kw)
    return WecomProCliAdapter(**base)


def test_send_bot_message_builds_send_message_command():
    executor = FakeExecutor([_result({"errcode": 0, "errmsg": "ok"})])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is True
    args = executor.calls[0]["args"]
    assert args[0] == "wecom-pro"
    assert args[1:4] == ["msg", "--bot-id", "bot-1"]
    assert args[4] == "send_message"
    body = json.loads(args[5])
    assert body["chatid"] == "chat-x" and body["msgtype"] == "text" and body["text"]["content"] == "hello"
    assert args[-2:] == ["-o", "json"]
    # per-company 隔离 env
    assert "company-A" in executor.calls[0]["env"]["HOME"]


def test_send_bot_message_missing_chat_returns_invalid_input():
    executor = FakeExecutor([])
    adapter = _adapter(executor, target_chat="")
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "invalid_input"
    assert executor.calls == []


def test_send_bot_message_cli_error_maps_errmsg():
    executor = FakeExecutor([_result({"errcode": 40001, "errmsg": "invalid secret"}, success=True)])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"
    assert "invalid secret" in res.message


def test_send_bot_message_cli_not_installed():
    executor = FakeExecutor([_result({}, success=False, exit_code=127, stderr="not found")])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"


def test_send_reminder_is_message_only():
    executor = FakeExecutor([_result({"errcode": 0, "errmsg": "ok"})])
    adapter = _adapter(executor)
    res = adapter.send_reminder(title="标题", content="正文", assignee_user_id="u1")
    assert res.success is True
    assert res.todo_result is None
    body = json.loads(executor.calls[0]["args"][5])
    assert "标题" in body["text"]["content"]


def test_todo_methods_unsupported():
    adapter = _adapter(FakeExecutor([]))
    assert adapter.create_todo(assignee_user_id="u1", title="t").code == "wecom_pro_unsupported"
    assert adapter.list_todos().code == "wecom_pro_unsupported"
    assert adapter.sync_todo_status(todo_id="x").code == "wecom_pro_unsupported"


def test_disabled_adapter_short_circuits():
    executor = FakeExecutor([])
    adapter = _adapter(executor, enabled=False)
    res = adapter.send_bot_message(content="hi", to_user_id="")
    assert res.success is False and res.code == "disabled"
    assert executor.calls == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_wecom_pro.py -v`
Expected: FAIL（`ModuleNotFoundError: services.notifications.wecom_pro`）

- [ ] **Step 3: 实现适配器**

`services/notifications/wecom_pro.py`:
```python
"""企业微信(企微)通知适配器,基于 wecom-pro CLI。仅消息推送。

多公司隔离:每次调用注入 per-company 配置目录(cli_isolation.company_cli_env)。
待办/查人类方法返回 unsupported,不崩溃。
"""
from __future__ import annotations

import json

from config import (
    NOTIFICATION_CLI_TIMEOUT_SECONDS,
    NOTIFY_CLI_STATE_DIR,
    WECOM_PRO_BIN,
    WECOM_PRO_ENABLED,
)

from .base import NotificationAdapter
from .cli import CLIExecutionResult, SubprocessCLIExecutor
from .cli_isolation import company_cli_env
from .models import (
    BotMessageResult,
    NotificationProvider,
    NotificationUser,
    ReminderResult,
    TodoListResult,
    TodoResult,
    TodoSyncResult,
    UnifiedTodoStatus,
    UserResolveResult,
)

_UNSUPPORTED = "wecom_pro_unsupported"


class WecomProCliAdapter(NotificationAdapter):
    """wecom-pro CLI 适配器,仅消息推送。"""

    provider = NotificationProvider.WECHAT_WORK.value

    def __init__(
        self,
        *,
        executor: SubprocessCLIExecutor | None = None,
        cli_bin: str = WECOM_PRO_BIN,
        timeout_seconds: float = NOTIFICATION_CLI_TIMEOUT_SECONDS,
        enabled: bool = WECOM_PRO_ENABLED,
        state_dir: str = NOTIFY_CLI_STATE_DIR,
        company_id: str = "",
        bot_id: str = "",
        secret: str = "",
        target_chat: str = "",
    ):
        self._executor = executor or SubprocessCLIExecutor()
        self._cli_bin = cli_bin
        self._timeout_seconds = timeout_seconds
        self._enabled = enabled
        self._state_dir = state_dir
        self._company_id = company_id
        self._bot_id = bot_id
        self._secret = secret
        self._target_chat = target_chat

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        if user_id:
            user = NotificationUser(user_id=user_id, display_name=keyword or user_id, mobile=mobile)
            return UserResolveResult(
                success=True, provider=self.provider, message="ok",
                raw={"source": "direct_user_id"}, users=[user], resolved_user=user,
            )
        return UserResolveResult(success=False, provider=self.provider, message="企微适配器仅支持直传 user_id", code=_UNSUPPORTED)

    def send_bot_message(
        self, *, content: str, to_user_id: str, content_type: str = "text",
        title: str = "", bot_id: str = "", conversation_id: str = "",
    ) -> BotMessageResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return BotMessageResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        chat = conversation_id or to_user_id or self._target_chat
        if not chat:
            return BotMessageResult(success=False, provider=self.provider, message="发送企微消息时缺少目标 chatid", code="invalid_input")
        msgtype = "markdown" if content_type == "markdown" else "text"
        body = {"chat_type": 1, "chatid": chat, "msgtype": msgtype, msgtype: {"content": content}}
        result = self._run(["msg", "--bot-id", self._bot_id, "send_message", json.dumps(body, ensure_ascii=False)])
        success = self._is_cli_success(result)
        message = "ok" if success else self._build_cli_error_message("发送企微消息失败", result)
        return BotMessageResult(
            success=success, provider=self.provider, message=message,
            code="" if success else "cli_error", raw=result.payload, receiver_user_id=chat,
        )

    def send_reminder(
        self, *, title: str, content: str, todo_title: str = "", assignee_user_id: str = "",
        mobile: str = "", keyword: str = "", due_time: str = "", source_id: str = "", operator_user_id: str = "",
    ) -> ReminderResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return ReminderResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        text = f"{title}\n\n{content}" if title else content
        chat = assignee_user_id or self._target_chat
        bot_result = self.send_bot_message(content=text, to_user_id=chat, title=title)
        return ReminderResult(
            success=bot_result.success, provider=self.provider, message=bot_result.message,
            code=bot_result.code, raw={"bot": bot_result.raw}, bot_result=bot_result,
            todo_result=None, assignee_user_id=assignee_user_id,
        )

    # ── 待办/轮询:企微无原生待办,统一 unsupported ──
    def create_todo(self, *, assignee_user_id: str, title: str, content: str = "", due_time: str = "",
                    source_id: str = "", operator_user_id: str = "", extra: dict | None = None) -> TodoResult:
        return self._unsupported_todo()

    def get_todo(self, *, todo_id: str, operator_user_id: str = "") -> TodoResult:
        return self._unsupported_todo()

    def list_todos(self, *, assignee_user_id: str = "", status: str = "", page_no: int = 1,
                   page_size: int = 20, operator_user_id: str = "") -> TodoListResult:
        return TodoListResult(success=False, provider=self.provider, message="企微暂不支持待办", code=_UNSUPPORTED)

    def update_todo(self, *, todo_id: str, status: str = "", title: str = "", content: str = "",
                    done: bool | None = None, operator_user_id: str = "", extra: dict | None = None) -> TodoResult:
        return self._unsupported_todo()

    def complete_todo(self, *, todo_id: str, operator_user_id: str = "") -> TodoResult:
        return self._unsupported_todo()

    def sync_todo_status(self, *, todo_id: str, operator_user_id: str = "", max_polls: int = 1,
                         poll_interval_seconds: float = 2.0) -> TodoSyncResult:
        return TodoSyncResult(success=False, provider=self.provider, message="企微暂不支持待办", code=_UNSUPPORTED, todo_id=todo_id)

    # ── helpers ──
    def _unsupported_todo(self) -> TodoResult:
        return TodoResult(success=False, provider=self.provider, message="企微暂不支持待办", code=_UNSUPPORTED)

    def _run(self, args: list[str]) -> CLIExecutionResult:
        return self._executor.run([self._cli_bin, *args, "-o", "json"], self._timeout_seconds, env=self._build_env())

    def _build_env(self) -> dict[str, str]:
        return company_cli_env(self._state_dir, self.provider, self._company_id)

    def _ensure_ready(self) -> UserResolveResult | None:
        if not self._enabled:
            return UserResolveResult(success=False, provider=self.provider, message="企微通知适配器未启用", code="disabled")
        if not self._cli_bin:
            return UserResolveResult(success=False, provider=self.provider, message="未配置 WECOM_PRO_BIN", code="missing_cli_bin")
        if not self._bot_id:
            return UserResolveResult(success=False, provider=self.provider, message="企微渠道缺少 bot-id", code="missing_bot_id")
        return None

    def _is_cli_success(self, result: CLIExecutionResult) -> bool:
        if not result.success:
            return False
        return result.payload.get("errcode", 0) in (0, None)

    def _build_cli_error_message(self, prefix: str, result: CLIExecutionResult) -> str:
        parts = [prefix]
        if result.stderr:
            parts.append(result.stderr)
        elif result.payload.get("errmsg"):
            parts.append(str(result.payload["errmsg"]))
        elif result.stdout:
            parts.append(result.stdout)
        return ": ".join(parts)
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_wecom_pro.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 按 probe 校准**:若 Task 1 probe 文档里 `send_message` 字段名/成功判定字段与基线不同,改 `wecom_pro.py` 常量与测试断言后重跑。

- [ ] **Step 6: Commit**

```bash
git add finance-agents/data-agent/services/notifications/wecom_pro.py finance-agents/data-agent/tests/test_notifications_wecom_pro.py
git commit -m "feat(notify): wecom-pro CLI adapter (message push only)"
```

---

## Task 5: FeishuLarkCliAdapter(飞书)

> **前置 GATE**:仅当 Task 1 probe 判定 lark-cli 可无头 `--as bot` 发送且可按公司隔离时执行;否则按 probe 文档里的退路与用户决策执行(可能改为 HTTP API,届时本任务整体调整)。

**Files:**
- Create: `finance-agents/data-agent/services/notifications/feishu_lark.py`
- Test: `finance-agents/data-agent/tests/test_notifications_feishu_lark.py`

> 命令以 probe 为准。基线:`lark-cli im +messages-send --chat-id <chat> --text <content> --as bot --format json`;成功判定 `code==0`。

- [ ] **Step 1: 写失败测试**

`tests/test_notifications_feishu_lark.py`:
```python
from __future__ import annotations
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


def test_send_bot_message_builds_im_send_command():
    executor = FakeExecutor([_result({"code": 0, "msg": "success"})])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is True
    args = executor.calls[0]["args"]
    assert args[0] == "lark-cli"
    assert "--chat-id" in args and "oc_chat" in args
    assert "--text" in args and "hello" in args
    assert "--as" in args and "bot" in args
    assert args[-2:] == ["--format", "json"]
    assert "company-A" in executor.calls[0]["env"]["HOME"]


def test_send_bot_message_missing_chat_returns_invalid_input():
    executor = FakeExecutor([])
    adapter = _adapter(executor, target_chat="")
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "invalid_input"
    assert executor.calls == []


def test_send_bot_message_cli_error_maps_msg():
    executor = FakeExecutor([_result({"code": 230001, "msg": "app no permission"}, success=True)])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"
    assert "app no permission" in res.message


def test_send_bot_message_cli_not_installed():
    executor = FakeExecutor([_result({}, success=False, exit_code=127, stderr="not found")])
    adapter = _adapter(executor)
    res = adapter.send_bot_message(content="hello", to_user_id="")
    assert res.success is False and res.code == "cli_error"


def test_send_reminder_is_message_only():
    executor = FakeExecutor([_result({"code": 0, "msg": "success"})])
    adapter = _adapter(executor)
    res = adapter.send_reminder(title="标题", content="正文", assignee_user_id="")
    assert res.success is True
    assert res.todo_result is None


def test_todo_methods_unsupported():
    adapter = _adapter(FakeExecutor([]))
    assert adapter.create_todo(assignee_user_id="u1", title="t").code == "feishu_lark_unsupported"
    assert adapter.sync_todo_status(todo_id="x").code == "feishu_lark_unsupported"


def test_disabled_adapter_short_circuits():
    executor = FakeExecutor([])
    adapter = _adapter(executor, enabled=False)
    res = adapter.send_bot_message(content="hi", to_user_id="")
    assert res.success is False and res.code == "disabled"
    assert executor.calls == []
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_feishu_lark.py -v`
Expected: FAIL（`ModuleNotFoundError: services.notifications.feishu_lark`）

- [ ] **Step 3: 实现适配器**

`services/notifications/feishu_lark.py`:
```python
"""飞书通知适配器,基于 larksuite/cli(lark-cli)。仅消息推送。

多公司隔离:每次调用注入 per-company 配置目录(cli_isolation.company_cli_env)。
注:lark-cli 凭证默认进系统钥匙串,HOME/XDG 隔离是否生效以 Task 1 probe 为准。
待办/查人类方法返回 unsupported,不崩溃。
"""
from __future__ import annotations

from config import (
    FEISHU_LARK_BIN,
    FEISHU_LARK_ENABLED,
    NOTIFICATION_CLI_TIMEOUT_SECONDS,
    NOTIFY_CLI_STATE_DIR,
)

from .base import NotificationAdapter
from .cli import CLIExecutionResult, SubprocessCLIExecutor
from .cli_isolation import company_cli_env
from .models import (
    BotMessageResult,
    NotificationProvider,
    NotificationUser,
    ReminderResult,
    TodoListResult,
    TodoResult,
    TodoSyncResult,
    UserResolveResult,
)

_UNSUPPORTED = "feishu_lark_unsupported"


class FeishuLarkCliAdapter(NotificationAdapter):
    """lark-cli 适配器,仅消息推送。"""

    provider = NotificationProvider.FEISHU.value

    def __init__(
        self,
        *,
        executor: SubprocessCLIExecutor | None = None,
        cli_bin: str = FEISHU_LARK_BIN,
        timeout_seconds: float = NOTIFICATION_CLI_TIMEOUT_SECONDS,
        enabled: bool = FEISHU_LARK_ENABLED,
        state_dir: str = NOTIFY_CLI_STATE_DIR,
        company_id: str = "",
        app_id: str = "",
        app_secret: str = "",
        target_chat: str = "",
    ):
        self._executor = executor or SubprocessCLIExecutor()
        self._cli_bin = cli_bin
        self._timeout_seconds = timeout_seconds
        self._enabled = enabled
        self._state_dir = state_dir
        self._company_id = company_id
        self._app_id = app_id
        self._app_secret = app_secret
        self._target_chat = target_chat

    def resolve_user(self, *, user_id: str = "", mobile: str = "", keyword: str = "") -> UserResolveResult:
        if user_id:
            user = NotificationUser(user_id=user_id, display_name=keyword or user_id, mobile=mobile)
            return UserResolveResult(
                success=True, provider=self.provider, message="ok",
                raw={"source": "direct_user_id"}, users=[user], resolved_user=user,
            )
        return UserResolveResult(success=False, provider=self.provider, message="飞书适配器仅支持直传 user_id", code=_UNSUPPORTED)

    def send_bot_message(
        self, *, content: str, to_user_id: str, content_type: str = "text",
        title: str = "", bot_id: str = "", conversation_id: str = "",
    ) -> BotMessageResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return BotMessageResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        chat = conversation_id or to_user_id or self._target_chat
        if not chat:
            return BotMessageResult(success=False, provider=self.provider, message="发送飞书消息时缺少目标 chat-id", code="invalid_input")
        result = self._run(["im", "+messages-send", "--chat-id", chat, "--text", content, "--as", "bot"])
        success = self._is_cli_success(result)
        message = "ok" if success else self._build_cli_error_message("发送飞书消息失败", result)
        return BotMessageResult(
            success=success, provider=self.provider, message=message,
            code="" if success else "cli_error", raw=result.payload, receiver_user_id=chat,
        )

    def send_reminder(
        self, *, title: str, content: str, todo_title: str = "", assignee_user_id: str = "",
        mobile: str = "", keyword: str = "", due_time: str = "", source_id: str = "", operator_user_id: str = "",
    ) -> ReminderResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return ReminderResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        text = f"{title}\n\n{content}" if title else content
        chat = assignee_user_id or self._target_chat
        bot_result = self.send_bot_message(content=text, to_user_id=chat, title=title)
        return ReminderResult(
            success=bot_result.success, provider=self.provider, message=bot_result.message,
            code=bot_result.code, raw={"bot": bot_result.raw}, bot_result=bot_result,
            todo_result=None, assignee_user_id=assignee_user_id,
        )

    # ── 待办/轮询:本次不做飞书 Tasks,统一 unsupported ──
    def create_todo(self, *, assignee_user_id: str, title: str, content: str = "", due_time: str = "",
                    source_id: str = "", operator_user_id: str = "", extra: dict | None = None) -> TodoResult:
        return self._unsupported_todo()

    def get_todo(self, *, todo_id: str, operator_user_id: str = "") -> TodoResult:
        return self._unsupported_todo()

    def list_todos(self, *, assignee_user_id: str = "", status: str = "", page_no: int = 1,
                   page_size: int = 20, operator_user_id: str = "") -> TodoListResult:
        return TodoListResult(success=False, provider=self.provider, message="飞书待办本次未接入", code=_UNSUPPORTED)

    def update_todo(self, *, todo_id: str, status: str = "", title: str = "", content: str = "",
                    done: bool | None = None, operator_user_id: str = "", extra: dict | None = None) -> TodoResult:
        return self._unsupported_todo()

    def complete_todo(self, *, todo_id: str, operator_user_id: str = "") -> TodoResult:
        return self._unsupported_todo()

    def sync_todo_status(self, *, todo_id: str, operator_user_id: str = "", max_polls: int = 1,
                         poll_interval_seconds: float = 2.0) -> TodoSyncResult:
        return TodoSyncResult(success=False, provider=self.provider, message="飞书待办本次未接入", code=_UNSUPPORTED, todo_id=todo_id)

    # ── helpers ──
    def _unsupported_todo(self) -> TodoResult:
        return TodoResult(success=False, provider=self.provider, message="飞书待办本次未接入", code=_UNSUPPORTED)

    def _run(self, args: list[str]) -> CLIExecutionResult:
        return self._executor.run([self._cli_bin, *args, "--format", "json"], self._timeout_seconds, env=self._build_env())

    def _build_env(self) -> dict[str, str]:
        return company_cli_env(self._state_dir, self.provider, self._company_id)

    def _ensure_ready(self) -> UserResolveResult | None:
        if not self._enabled:
            return UserResolveResult(success=False, provider=self.provider, message="飞书通知适配器未启用", code="disabled")
        if not self._cli_bin:
            return UserResolveResult(success=False, provider=self.provider, message="未配置 FEISHU_LARK_BIN", code="missing_cli_bin")
        return None

    def _is_cli_success(self, result: CLIExecutionResult) -> bool:
        if not result.success:
            return False
        return result.payload.get("code", 0) in (0, None)

    def _build_cli_error_message(self, prefix: str, result: CLIExecutionResult) -> str:
        parts = [prefix]
        if result.stderr:
            parts.append(result.stderr)
        elif result.payload.get("msg"):
            parts.append(str(result.payload["msg"]))
        elif result.stdout:
            parts.append(result.stdout)
        return ": ".join(parts)
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_feishu_lark.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: 按 probe 校准**:命令/成功字段与 probe 不一致则同步改代码与测试。

- [ ] **Step 6: Commit**

```bash
git add finance-agents/data-agent/services/notifications/feishu_lark.py finance-agents/data-agent/tests/test_notifications_feishu_lark.py
git commit -m "feat(notify): lark-cli feishu adapter (message push only)"
```

---

## Task 6: 工厂注册 + registry 统一

**Files:**
- Modify: `finance-agents/data-agent/services/notifications/__init__.py`(`get_notification_adapter`,约 line 48-55)
- Modify: `finance-agents/data-agent/services/notifications/service.py`(`create_default_registry`)
- Test: `finance-agents/data-agent/tests/test_notifications_factory_providers.py`

- [ ] **Step 1: 写失败测试**

`tests/test_notifications_factory_providers.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications import get_notification_adapter
from services.notifications.feishu_lark import FeishuLarkCliAdapter
from services.notifications.models import NotificationChannelConfig
from services.notifications.wecom_pro import WecomProCliAdapter


def test_factory_creates_feishu_adapter():
    cfg = NotificationChannelConfig(company_id="c1", provider="feishu",
                                    client_id="app", client_secret="sec", robot_code="oc_chat")
    adapter = get_notification_adapter(provider="feishu", channel_config=cfg)
    assert isinstance(adapter, FeishuLarkCliAdapter)
    assert adapter._company_id == "c1" and adapter._target_chat == "oc_chat"
    assert adapter._app_id == "app"


def test_factory_creates_wechat_work_adapter():
    cfg = NotificationChannelConfig(company_id="c1", provider="wechat_work",
                                    client_id="corp", client_secret="sec", robot_code="bot-1")
    adapter = get_notification_adapter(provider="wechat_work", channel_config=cfg)
    assert isinstance(adapter, WecomProCliAdapter)
    assert adapter._company_id == "c1" and adapter._bot_id == "bot-1"


def test_registry_registers_three_providers():
    from services.notifications.service import create_default_registry
    registry = create_default_registry()
    # 三家都能创建,不抛 Unsupported
    for provider in ("dingtalk_dws", "feishu", "wechat_work"):
        registry.create(provider)
```

> 注:`robot_code` 在企微映射为 bot-id、在飞书映射为目标 chat。`test_factory_creates_wechat_work_adapter` 期望 `bot_id == robot_code`;`bot_id` 也可来自 `client_id`,以 probe 确定后的映射为准,届时同步本测试。

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_factory_providers.py -v`
Expected: FAIL（feishu 分支抛 `ValueError: Unsupported notification provider: feishu`）

- [ ] **Step 3: 实现工厂分支**

在 `services/notifications/__init__.py` 顶部 import 处新增:
```python
from .feishu_lark import FeishuLarkCliAdapter
from .wecom_pro import WecomProCliAdapter
```
在 `get_notification_adapter` 的 `if provider_value == NotificationProvider.DINGTALK_DWS.value:` 分支返回之后、`raise ValueError` 之前新增:
```python
    if provider_value == NotificationProvider.FEISHU.value:
        return FeishuLarkCliAdapter(
            executor=executor,
            company_id=company_id or (resolved_channel_config.company_id if resolved_channel_config else ""),
            app_id=resolved_channel_config.client_id if resolved_channel_config else "",
            app_secret=resolved_channel_config.client_secret if resolved_channel_config else "",
            target_chat=resolved_channel_config.robot_code if resolved_channel_config else "",
        )
    if provider_value == NotificationProvider.WECHAT_WORK.value:
        return WecomProCliAdapter(
            executor=executor,
            company_id=company_id or (resolved_channel_config.company_id if resolved_channel_config else ""),
            bot_id=resolved_channel_config.robot_code if resolved_channel_config else "",
            secret=resolved_channel_config.client_secret if resolved_channel_config else "",
            target_chat=resolved_channel_config.robot_code if resolved_channel_config else "",
        )
```
并在 `__all__` 加入 `"FeishuLarkCliAdapter"`, `"WecomProCliAdapter"`。

- [ ] **Step 4: 统一 service.py registry**

在 `services/notifications/service.py` 顶部 import:
```python
from .feishu_lark import FeishuLarkCliAdapter
from .wecom_pro import WecomProCliAdapter
```
把 `create_default_registry` 改为:
```python
def create_default_registry() -> NotificationAdapterRegistry:
    registry = NotificationAdapterRegistry()
    if DINGTALK_DWS_ENABLED:
        registry.register(NotificationProvider.DINGTALK_DWS.value, DingTalkDWSNotificationAdapter)
    if FEISHU_LARK_ENABLED:
        registry.register(NotificationProvider.FEISHU.value, FeishuLarkCliAdapter)
    if WECOM_PRO_ENABLED:
        registry.register(NotificationProvider.WECHAT_WORK.value, WecomProCliAdapter)
    return registry
```
并在该文件顶部 `from config import ...` 处补 `FEISHU_LARK_ENABLED, WECOM_PRO_ENABLED`。

> 若 `dingtalk_dws.py` 实际导出类名为 `DingTalkDwsAdapter` 而非 `DingTalkDWSNotificationAdapter`,以文件实际为准修正本步导入(service.py 现有 import 已用 `DingTalkDWSNotificationAdapter`,沿用)。

- [ ] **Step 5: 运行,确认通过**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_factory_providers.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 全量通知测试回归**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_dingtalk.py tests/test_notifications_wecom_pro.py tests/test_notifications_feishu_lark.py tests/test_notifications_factory_providers.py tests/test_notifications_cli_isolation.py tests/test_notifications_config.py -v`
Expected: 全部 PASS（钉钉测试无回归)

- [ ] **Step 7: Commit**

```bash
git add finance-agents/data-agent/services/notifications/__init__.py finance-agents/data-agent/services/notifications/service.py finance-agents/data-agent/tests/test_notifications_factory_providers.py
git commit -m "feat(notify): register feishu/wecom adapters in factory + registry"
```

---

## Task 7: 端到端选路验证(无真机)

确认运行计划选择飞书/企微渠道后,recon 路径能据 `channel_config.provider` 构造出新适配器(不真发)。

**Files:**
- Test: `finance-agents/data-agent/tests/test_notifications_provider_routing.py`

- [ ] **Step 1: 写测试**

`tests/test_notifications_provider_routing.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.notifications import get_notification_adapter
from services.notifications.feishu_lark import FeishuLarkCliAdapter
from services.notifications.models import NotificationChannelConfig
from services.notifications.wecom_pro import WecomProCliAdapter


def test_provider_driven_by_channel_config():
    """模拟 recon: provider 来自 channel_config.provider。"""
    for provider, cls in (("feishu", FeishuLarkCliAdapter), ("wechat_work", WecomProCliAdapter)):
        cfg = NotificationChannelConfig(company_id="c1", provider=provider,
                                        client_id="id", client_secret="sec", robot_code="target")
        adapter = get_notification_adapter(provider=cfg.provider, channel_config=cfg)
        assert isinstance(adapter, cls)
        assert adapter.provider == provider
```

- [ ] **Step 2: 运行,确认通过**

Run: `cd finance-agents/data-agent && python3 -m pytest tests/test_notifications_provider_routing.py -v`
Expected: PASS

- [ ] **Step 3: 验证导入不破坏 data-agent 启动**

Run: `cd finance-agents/data-agent && python3 -c "import services.notifications as n; print(sorted(n.__all__))"`
Expected: 打印含 `FeishuLarkCliAdapter`、`WecomProCliAdapter` 的列表,无 ImportError。

- [ ] **Step 4: Commit**

```bash
git add finance-agents/data-agent/tests/test_notifications_provider_routing.py
git commit -m "test(notify): verify provider routing for feishu/wecom"
```

---

## 收尾(全部任务完成后)

- 真机发送验收(用户提供真实凭证 + 目标群)留待后续,不在本计划内。
- 若 Task 1 GATE 判定 lark-cli 不可用,Task 5 与飞书相关断言按用户决策(HTTP API / 单租户)调整,其余任务不受影响。
- 部署文档补充:`lark-cli`(Node+Go1.23+Py3)、`wecom-pro`(Rust/npm)安装步骤,以及每公司 `init` provision 流程。

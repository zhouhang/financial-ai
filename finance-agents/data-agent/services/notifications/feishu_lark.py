"""飞书通知适配器，基于 larksuite/cli(lark-cli)。仅消息推送。

实现要点(以 Task 1 探测为准):
- 发送走通用命令 `lark-cli api POST /open-apis/im/v1/messages --params .. --data .. --as bot --format json`
  (不用 `im +messages-send`,因其不接受 `--format`)。
- 成功判定:lark-cli 自有信封 `payload["ok"] is True`(不是 feishu 的 `code`);错误在 `payload["error"]["message"]`。
- `--as bot` 用 tenant_access_token,无头(不弹 device flow)。
- 多公司隔离:每次调用注入 per-company 配置目录(cli_isolation.company_cli_env);lark-cli 凭证文件级加密存 $HOME 下,故 HOME 隔离有效。

待办/查人类方法返回 unsupported,不崩溃。

provisioning(用 `lark-cli config init --app-id .. --app-secret-stdin` 把每公司应用凭证写入其配置目录)
属于真机/上线流程,本轮不在适配器内自动执行(真机验收后续)。`app_id`/`app_secret` 已保留供该步使用。
"""
from __future__ import annotations

import json
from pathlib import Path

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
    UnifiedTodoStatus,
    UserResolveResult,
)

_UNSUPPORTED = "feishu_lark_unsupported"
_IM_MESSAGES_PATH = "/open-apis/im/v1/messages"


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
        prov_error = self._ensure_provisioned()
        if prov_error is not None:
            return prov_error
        # feishu im/v1/messages: content 为 JSON 字符串;text 类型为 {"text": "..."}
        body = {
            "receive_id": chat,
            "msg_type": "text",
            "content": json.dumps({"text": content}, ensure_ascii=False),
        }
        result = self._run([
            "api", "POST", _IM_MESSAGES_PATH,
            "--params", json.dumps({"receive_id_type": "chat_id"}),
            "--data", json.dumps(body, ensure_ascii=False),
            "--as", "bot",
        ])
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

    # ── 待办/轮询:本次不接入飞书 Tasks,统一 unsupported ──
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

    def _config_path(self) -> Path:
        """该公司隔离配置目录下 lark-cli 的应用配置文件。"""
        return Path(self._build_env()["HOME"]) / ".lark-cli" / "config.json"

    def _ensure_provisioned(self) -> BotMessageResult | None:
        """惰性 provision:该公司配置目录未初始化过应用时,用 DB 凭证跑一次
        `lark-cli config init --app-id .. --app-secret-stdin`(secret 走 stdin,不进进程列表)。
        已初始化则跳过。返回非 None 表示 provision 失败,调用方应短路返回。
        """
        if self._config_path().exists():
            return None
        if not self._app_id or not self._app_secret:
            return BotMessageResult(
                success=False, provider=self.provider,
                message="飞书渠道缺少 app_id/app_secret，无法初始化飞书应用",
                code="missing_credentials",
            )
        result = self._executor.run(
            [self._cli_bin, "config", "init", "--app-id", self._app_id, "--app-secret-stdin", "--brand", "feishu"],
            self._timeout_seconds,
            env=self._build_env(),
            input_text=f"{self._app_secret}\n",
        )
        if not result.success:
            return BotMessageResult(
                success=False, provider=self.provider,
                message=self._build_cli_error_message("初始化飞书应用失败", result),
                code="provision_failed", raw=result.payload,
            )
        return None

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
        return result.payload.get("ok") is True

    def _build_cli_error_message(self, prefix: str, result: CLIExecutionResult) -> str:
        parts = [prefix]
        error = result.payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            parts.append(str(error["message"]))
        elif result.stderr:
            parts.append(result.stderr)
        elif result.stdout:
            parts.append(result.stdout)
        return ": ".join(parts)

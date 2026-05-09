"""DingTalk notification adapter built on top of the local dws CLI."""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Any

from config import (
    DINGTALK_CLIENT_ID,
    DINGTALK_CLIENT_SECRET,
    DINGTALK_DEFAULT_TODO_PAGE_SIZE,
    DINGTALK_DEFAULT_TODO_PRIORITY,
    DINGTALK_DWS_BIN,
    DINGTALK_DWS_ENABLED,
    DINGTALK_ROBOT_CODE,
    NOTIFICATION_CLI_TIMEOUT_SECONDS,
)

from .base import NotificationAdapter
from .cli import CLIExecutionResult, SubprocessCLIExecutor
from .models import (
    BotMessageResult,
    NotificationProvider,
    NotificationUser,
    ReminderResult,
    TERMINAL_TODO_STATUSES,
    TodoListResult,
    TodoRecord,
    TodoResult,
    TodoSyncResult,
    UnifiedTodoStatus,
    UserResolveResult,
)


class DingTalkDwsAdapter(NotificationAdapter):
    """Thin wrapper around the dws CLI with normalized return shapes."""

    provider = NotificationProvider.DINGTALK_DWS.value

    def __init__(
        self,
        *,
        executor: SubprocessCLIExecutor | None = None,
        cli_bin: str = DINGTALK_DWS_BIN,
        timeout_seconds: float = NOTIFICATION_CLI_TIMEOUT_SECONDS,
        client_id: str = DINGTALK_CLIENT_ID,
        client_secret: str = DINGTALK_CLIENT_SECRET,
        robot_code: str = DINGTALK_ROBOT_CODE,
        enabled: bool = DINGTALK_DWS_ENABLED,
        default_todo_priority: str = DINGTALK_DEFAULT_TODO_PRIORITY,
        default_todo_page_size: int = DINGTALK_DEFAULT_TODO_PAGE_SIZE,
    ):
        self._executor = executor or SubprocessCLIExecutor()
        self._cli_bin = cli_bin
        self._timeout_seconds = timeout_seconds
        self._client_id = client_id
        self._client_secret = client_secret
        self._robot_code = robot_code
        self._enabled = enabled
        self._default_todo_priority = default_todo_priority
        self._default_todo_page_size = default_todo_page_size

    def resolve_user(
        self,
        *,
        user_id: str = "",
        mobile: str = "",
        keyword: str = "",
    ) -> UserResolveResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return invalid
        if not any([user_id, mobile, keyword]):
            return self._user_failure("缺少用户定位条件，必须传 user_id、mobile 或 keyword 之一", code="invalid_input")

        if user_id:
            # Newer dws versions require interactive PAT permission for
            # contact.user:get. When callers already provide a DingTalk userId,
            # use it directly so reminder delivery does not depend on contact
            # detail lookup.
            user = NotificationUser(user_id=user_id, display_name=keyword or user_id, mobile=mobile)
            return UserResolveResult(
                success=True,
                provider=self.provider,
                message="ok",
                raw={"userId": [user_id], "source": "direct_user_id"},
                users=[user],
                resolved_user=user,
            )

        if mobile:
            search = self._run(["contact", "user", "search-mobile", "--mobile", mobile])
        else:
            search = self._run(["contact", "user", "search", "--keyword", keyword])
        if not self._is_cli_success(search):
            return self._user_failure(self._build_cli_error_message("查询钉钉用户失败", search), code="cli_error", raw=search.payload)

        user_ids = _extract_user_ids(search.payload)
        if not user_ids:
            query_text = mobile or keyword
            return self._user_failure(f"未找到匹配的钉钉用户: {query_text}", code="not_found", raw=search.payload)
        users = [
            NotificationUser(
                user_id=item,
                display_name=keyword or item,
                mobile=mobile,
                extra={"source": "search_result"},
            )
            for item in user_ids
        ]
        if len(users) > 1:
            detail = self._get_users_by_ids(user_ids)
            if detail.success and detail.users:
                detail_by_id = {user.user_id: user for user in detail.users}
                users = [detail_by_id.get(user.user_id, user) for user in users]
                return UserResolveResult(
                    success=True,
                    provider=self.provider,
                    message=f"命中 {len(users)} 个钉钉用户",
                    raw={"search": search.payload, "detail": detail.raw},
                    users=users,
                    resolved_user=None,
                )
        return UserResolveResult(
            success=True,
            provider=self.provider,
            message="ok" if len(users) == 1 else f"命中 {len(users)} 个钉钉用户",
            raw=search.payload,
            users=users,
            resolved_user=users[0] if len(users) == 1 else None,
        )

    def send_bot_message(
        self,
        *,
        content: str,
        to_user_id: str,
        content_type: str = "text",
        title: str = "",
        bot_id: str = "",
        conversation_id: str = "",
    ) -> BotMessageResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return BotMessageResult(
                success=False,
                provider=self.provider,
                message=invalid.message,
                code=invalid.code,
                raw=invalid.raw,
            )
        if content_type not in {"text", "markdown"}:
            return BotMessageResult(
                success=False,
                provider=self.provider,
                message=f"当前仅支持 text/markdown 消息，收到: {content_type}",
                code="unsupported_content_type",
            )
        robot_code = bot_id or self._robot_code
        if not robot_code:
            return BotMessageResult(
                success=False,
                provider=self.provider,
                message="未配置 DINGTALK_ROBOT_CODE，无法发送机器人消息",
                code="missing_robot_code",
            )
        if not to_user_id and not conversation_id:
            return BotMessageResult(
                success=False,
                provider=self.provider,
                message="发送机器人消息时缺少接收对象",
                code="invalid_input",
            )

        args = [
            "chat",
            "message",
            "send-by-bot",
            "--robot-code",
            robot_code,
            "--title",
            title or "Tally 催办通知",
            "--text",
            content,
        ]
        if conversation_id:
            args.extend(["--group", conversation_id])
        else:
            args.extend(["--users", to_user_id])

        result = self._run(args)
        success = self._is_cli_success(result) and bool(_dig(result.payload, "success", default=True))
        message_id = str(_dig(result.payload, "result", "processQueryKey", default=""))
        message = "ok" if success else self._build_cli_error_message("发送钉钉机器人消息失败", result)
        return BotMessageResult(
            success=success,
            provider=self.provider,
            message=message,
            code="" if success else "cli_error",
            raw=result.payload,
            message_id=message_id,
            receiver_user_id=to_user_id,
        )

    def create_todo(
        self,
        *,
        assignee_user_id: str,
        title: str,
        content: str = "",
        due_time: str = "",
        source_id: str = "",
        operator_user_id: str = "",
        extra: dict | None = None,
    ) -> TodoResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return TodoResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        if not assignee_user_id:
            return self._todo_failure("创建钉钉待办时缺少 assignee_user_id", code="invalid_input")
        if not title:
            return self._todo_failure("创建钉钉待办时缺少标题", code="invalid_input")

        args = [
            "todo",
            "task",
            "create",
            "--title",
            title,
            "--executors",
            assignee_user_id,
            "--priority",
            str((extra or {}).get("priority", self._default_todo_priority)),
        ]
        if due_time:
            args.extend(["--due", due_time])
        recurrence = (extra or {}).get("recurrence")
        if recurrence:
            args.extend(["--recurrence", str(recurrence)])

        result = self._run(args)
        if not self._is_cli_success(result):
            return self._todo_failure(self._build_cli_error_message("创建钉钉待办失败", result), code="cli_error", raw=result.payload)

        todo_id = str(_dig(result.payload, "result", "taskId", default=""))
        if not todo_id:
            return self._todo_failure("创建钉钉待办失败: 返回结果缺少 taskId", code="empty_task_id", raw=result.payload)
        if todo_id:
            fresh = self.get_todo(todo_id=todo_id)
            if fresh.success and fresh.todo:
                fresh.todo.extra.setdefault("requested_assignee_user_id", assignee_user_id)
                fresh.todo.extra.setdefault("source_id", source_id)
                return fresh
        return TodoResult(
            success=True,
            provider=self.provider,
            message="ok",
            raw=result.payload,
            todo=TodoRecord(
                todo_id=todo_id,
                title=title,
                content=content,
                assignee_user_id=assignee_user_id,
                status=UnifiedTodoStatus.OPEN,
                due_time=due_time,
                extra={"source_id": source_id, "raw": result.payload},
            ),
        )

    def get_todo(
        self,
        *,
        todo_id: str,
        operator_user_id: str = "",
    ) -> TodoResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return TodoResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        if not todo_id:
            return self._todo_failure("读取钉钉待办时缺少 todo_id", code="invalid_input")

        result = self._run(["todo", "task", "get", "--task-id", todo_id])
        if not self._is_cli_success(result):
            return self._todo_failure(self._build_cli_error_message("查询钉钉待办失败", result), code="cli_error", raw=result.payload)

        detail = _dig(result.payload, "result", "todoDetailModel", default={}) or {}
        todo = _todo_from_detail(detail)
        if todo.todo_id:
            return TodoResult(success=True, provider=self.provider, message="ok", raw=result.payload, todo=todo)

        # dws 对已完成待办存在 success=true 但 detail 为空的情况，回退到 list 接口兜底。
        for status in ("completed", "open"):
            fallback = self.list_todos(
                status=status,
                page_no=1,
                page_size=max(20, self._default_todo_page_size),
                operator_user_id=operator_user_id,
            )
            if not fallback.success:
                continue
            matched = next((item for item in fallback.todos if item.todo_id == todo_id), None)
            if matched is not None:
                return TodoResult(
                    success=True,
                    provider=self.provider,
                    message="ok",
                    raw=fallback.raw,
                    todo=matched,
                )
        return self._todo_failure("钉钉待办详情返回为空", code="empty_payload", raw=result.payload)

    def list_todos(
        self,
        *,
        assignee_user_id: str = "",
        status: str = "",
        page_no: int = 1,
        page_size: int = 20,
        operator_user_id: str = "",
    ) -> TodoListResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return TodoListResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)

        args = [
            "todo",
            "task",
            "list",
            "--page",
            str(page_no),
            "--size",
            str(page_size or self._default_todo_page_size),
        ]
        mapped_status = _map_list_status(status)
        if mapped_status is not None:
            args.extend(["--status", mapped_status])

        result = self._run(args)
        if not self._is_cli_success(result):
            return TodoListResult(
                success=False,
                provider=self.provider,
                message=self._build_cli_error_message("查询钉钉待办列表失败", result),
                code="cli_error",
                raw=result.payload,
            )

        cards = _dig(result.payload, "result", "todoCards", default=[]) or []
        todos = [_todo_from_card(card) for card in cards]
        todos = [todo for todo in todos if todo.todo_id]
        if assignee_user_id:
            todos = [todo for todo in todos if todo.assignee_user_id == assignee_user_id]
        return TodoListResult(success=True, provider=self.provider, message="ok", raw=result.payload, todos=todos)

    def update_todo(
        self,
        *,
        todo_id: str,
        status: str = "",
        title: str = "",
        content: str = "",
        done: bool | None = None,
        operator_user_id: str = "",
        extra: dict | None = None,
    ) -> TodoResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return TodoResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        if not todo_id:
            return self._todo_failure("更新钉钉待办时缺少 todo_id", code="invalid_input")

        args = ["todo", "task", "update", "--task-id", todo_id]
        if title:
            args.extend(["--title", title])
        if extra and extra.get("priority") is not None:
            args.extend(["--priority", str(extra["priority"])])
        if extra and extra.get("due"):
            args.extend(["--due", str(extra["due"])])
        done_flag = done
        if done_flag is None and status:
            normalized_status = _normalize_status_name(status)
            if normalized_status == UnifiedTodoStatus.COMPLETED:
                done_flag = True
            elif normalized_status in {UnifiedTodoStatus.OPEN, UnifiedTodoStatus.IN_PROGRESS}:
                done_flag = False
            else:
                return self._todo_failure(f"当前钉钉待办不支持更新为状态: {status}", code="unsupported_status")
        if done_flag is not None:
            args.extend(["--done", "true" if done_flag else "false"])
        if len(args) == 4:
            return self.get_todo(todo_id=todo_id)

        result = self._run(args)
        if not self._is_cli_success(result):
            return self._todo_failure(self._build_cli_error_message("更新钉钉待办失败", result), code="cli_error", raw=result.payload)
        fresh = self.get_todo(todo_id=todo_id)
        if fresh.success:
            return fresh
        return TodoResult(success=True, provider=self.provider, message="ok", raw=result.payload)

    def complete_todo(
        self,
        *,
        todo_id: str,
        operator_user_id: str = "",
    ) -> TodoResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return TodoResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)
        if not todo_id:
            return self._todo_failure("完成钉钉待办时缺少 todo_id", code="invalid_input")

        result = self._run(["todo", "task", "done", "--task-id", todo_id, "--status", "true"])
        if not self._is_cli_success(result):
            return self._todo_failure(self._build_cli_error_message("完成钉钉待办失败", result), code="cli_error", raw=result.payload)
        fresh = self.get_todo(todo_id=todo_id)
        if fresh.success:
            return fresh
        return TodoResult(success=True, provider=self.provider, message="ok", raw=result.payload)

    def send_reminder(
        self,
        *,
        title: str,
        content: str,
        todo_title: str = "",
        assignee_user_id: str = "",
        mobile: str = "",
        keyword: str = "",
        due_time: str = "",
        source_id: str = "",
        operator_user_id: str = "",
    ) -> ReminderResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return ReminderResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw)

        resolved = self.resolve_user(user_id=assignee_user_id, mobile=mobile, keyword=keyword)
        if not resolved.success or resolved.resolved_user is None:
            return ReminderResult(
                success=False,
                provider=self.provider,
                message=resolved.message or "无法定位待催办的钉钉用户",
                code=resolved.code or "user_resolve_failed",
                raw=resolved.raw,
            )

        assignee = resolved.resolved_user

        # Default due time: today 18:00 CST so DingTalk sends a reminder
        effective_due = due_time or _default_due_time()

        # Create todo first so we can include the task link in the bot message
        todo_result = self.create_todo(
            assignee_user_id=assignee.user_id,
            title=todo_title or title,
            content=content,
            due_time=effective_due,
            source_id=source_id,
        )

        # Append todo reference so the user can find it in the DingTalk todo list
        bot_content = content
        if todo_result.success and todo_result.todo and todo_result.todo.title:
            bot_content = f"{content}\n\n📋 已创建待办：**{todo_result.todo.title}**\n请在钉钉「待办」中搜索上方标题并处理。"

        bot_result = self.send_bot_message(
            content=bot_content,
            to_user_id=assignee.user_id,
            title=title,
        )

        # Send DING strong notification so the user gets a real push alert
        self._send_ding(user_id=assignee.user_id, content=title or content)

        overall_success = bot_result.success and todo_result.success
        message_parts = []
        if not bot_result.success:
            message_parts.append(f"bot 发送失败: {bot_result.message}")
        if not todo_result.success:
            message_parts.append(f"todo 创建失败: {todo_result.message}")
        if not message_parts:
            message_parts.append("ok")

        return ReminderResult(
            success=overall_success,
            provider=self.provider,
            message="; ".join(message_parts),
            code="" if overall_success else "partial_failure",
            raw={
                "resolve": resolved.raw,
                "bot": bot_result.raw,
                "todo": todo_result.raw,
            },
            bot_result=bot_result,
            todo_result=todo_result,
            assignee_user_id=assignee.user_id,
        )

    def _send_ding(self, *, user_id: str, content: str) -> None:
        """Send a DING strong-notification (app push) so the user gets a real alert."""
        if not user_id or not content:
            return
        args = [
            "ding", "message", "send",
            "--users", user_id,
            "--type", "app",
            "--content", content,
        ]
        if self._robot_code:
            args.extend(["--robot-code", self._robot_code])
        try:
            self._run(args)
        except Exception:
            pass  # DING is best-effort; don't fail the whole reminder

    def sync_todo_status(
        self,
        *,
        todo_id: str,
        operator_user_id: str = "",
        max_polls: int = 1,
        poll_interval_seconds: float = 2.0,
    ) -> TodoSyncResult:
        invalid = self._ensure_ready()
        if invalid is not None:
            return TodoSyncResult(success=False, provider=self.provider, message=invalid.message, code=invalid.code, raw=invalid.raw, todo_id=todo_id)
        max_rounds = max(1, int(max_polls))
        history: list[UnifiedTodoStatus] = []
        last_todo: TodoRecord | None = None
        last_raw: dict[str, Any] = {}
        for index in range(max_rounds):
            todo_result = self.get_todo(todo_id=todo_id, operator_user_id=operator_user_id)
            last_raw = todo_result.raw
            if not todo_result.success or todo_result.todo is None:
                return TodoSyncResult(
                    success=False,
                    provider=self.provider,
                    message=todo_result.message,
                    code=todo_result.code,
                    raw=todo_result.raw,
                    todo_id=todo_id,
                    polls=index + 1,
                    history=history,
                )

            last_todo = todo_result.todo
            history.append(last_todo.status)
            if last_todo.status in TERMINAL_TODO_STATUSES:
                return TodoSyncResult(
                    success=True,
                    provider=self.provider,
                    message="ok",
                    raw=last_raw,
                    todo_id=todo_id,
                    status=last_todo.status,
                    is_terminal=True,
                    polls=index + 1,
                    history=history,
                    todo=last_todo,
                )
            if index < max_rounds - 1:
                time.sleep(max(poll_interval_seconds, 0))

        final_status = last_todo.status if last_todo else UnifiedTodoStatus.UNKNOWN
        return TodoSyncResult(
            success=True,
            provider=self.provider,
            message="ok",
            raw=last_raw,
            todo_id=todo_id,
            status=final_status,
            is_terminal=final_status in TERMINAL_TODO_STATUSES,
            polls=max_rounds,
            history=history,
            todo=last_todo,
        )

    def _run(self, args: list[str]) -> CLIExecutionResult:
        return self._executor.run(
            [self._cli_bin, *args, "-f", "json"],
            self._timeout_seconds,
            env=self._build_env(),
        )

    def _build_env(self) -> dict[str, str]:
        env = {}
        if self._client_id:
            env["DWS_CLIENT_ID"] = self._client_id
        if self._client_secret:
            env["DWS_CLIENT_SECRET"] = self._client_secret
        return env

    def _ensure_ready(self) -> UserResolveResult | None:
        if not self._enabled:
            return self._user_failure("DingTalk DWS 通知适配器未启用", code="disabled")
        if not self._cli_bin:
            return self._user_failure("未配置 DINGTALK_DWS_BIN", code="missing_cli_bin")
        return None

    def _get_users_by_ids(self, user_ids: list[str]) -> UserResolveResult:
        ids = [item for item in user_ids if item]
        if not ids:
            return self._user_failure("未获取到可查询的钉钉 user_id", code="not_found")
        result = self._run(["contact", "user", "get", "--ids", ",".join(ids)])
        if not self._is_cli_success(result):
            return self._user_failure(self._build_cli_error_message("查询钉钉用户详情失败", result), code="cli_error", raw=result.payload)

        users = _users_from_payload(result.payload)
        resolved_user = users[0] if len(users) == 1 else None
        if not users:
            return self._user_failure("钉钉用户详情为空", code="not_found", raw=result.payload)
        message = "ok" if resolved_user else f"命中 {len(users)} 个钉钉用户"
        return UserResolveResult(
            success=True,
            provider=self.provider,
            message=message,
            raw=result.payload,
            users=users,
            resolved_user=resolved_user,
        )

    def _is_cli_success(self, result: CLIExecutionResult) -> bool:
        if not result.success:
            return False
        payload_success = result.payload.get("success")
        error_code = result.payload.get("errorCode")
        return payload_success is not False and error_code in (None, 0)

    def _build_cli_error_message(self, prefix: str, result: CLIExecutionResult) -> str:
        parts = [prefix]
        payload_error = result.payload.get("error")
        if result.stderr:
            parts.append(result.stderr)
        elif isinstance(payload_error, dict) and payload_error.get("message"):
            parts.append(str(payload_error["message"]))
        elif payload_error:
            parts.append(str(payload_error))
        elif result.payload.get("errorMessage"):
            parts.append(str(result.payload["errorMessage"]))
        elif result.stdout:
            parts.append(result.stdout)
        return ": ".join(parts)

    def _user_failure(self, message: str, *, code: str, raw: dict[str, Any] | None = None) -> UserResolveResult:
        return UserResolveResult(success=False, provider=self.provider, message=message, code=code, raw=raw or {})

    def _todo_failure(self, message: str, *, code: str, raw: dict[str, Any] | None = None) -> TodoResult:
        return TodoResult(success=False, provider=self.provider, message=message, code=code, raw=raw or {})


def _extract_user_ids(payload: dict[str, Any]) -> list[str]:
    user_ids: list[str] = []
    seen: set[str] = set()

    def append(value: Any) -> None:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            user_ids.append(text)

    def visit(value: Any) -> None:
        if isinstance(value, str):
            append(value)
            return
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return

        model = value.get("orgEmployeeModel") if isinstance(value.get("orgEmployeeModel"), dict) else value
        for id_key in ("orgUserId", "userId", "userid"):
            raw_id = model.get(id_key)
            if isinstance(raw_id, list):
                for item in raw_id:
                    append(item)
            else:
                append(raw_id)

        for key in ("userId", "userIds", "users", "list", "items", "data", "result"):
            nested = value.get(key)
            if nested is not None and nested is not model:
                visit(nested)

    visit(payload)
    return user_ids


def _users_from_payload(payload: dict[str, Any]) -> list[NotificationUser]:
    users: list[NotificationUser] = []
    result = payload.get("result") or []
    if not isinstance(result, list):
        return users
    for item in result:
        if not isinstance(item, dict):
            continue
        model = item.get("orgEmployeeModel") or item
        user_id = str(model.get("orgUserId") or model.get("userId") or model.get("userid") or "").strip()
        if not user_id:
            continue
        departments = _normalize_departments(
            model.get("deptNameList")
            or model.get("departmentNames")
            or model.get("departments")
            or model.get("department")
            or model.get("deptName")
        )
        users.append(
            NotificationUser(
                user_id=user_id,
                display_name=str(model.get("orgUserName") or model.get("name") or "").strip(),
                mobile=str(model.get("orgUserMobile") or model.get("mobile") or "").strip(),
                organization=str(
                    model.get("organization")
                    or model.get("orgName")
                    or model.get("corpName")
                    or model.get("tenantName")
                    or ""
                ).strip(),
                departments=departments,
                extra={"raw": item},
            )
        )
    return users


def _normalize_departments(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, list):
        values: list[str] = []
        for item in raw:
            if isinstance(item, str):
                value = item.strip()
            elif isinstance(item, dict):
                value = str(item.get("name") or item.get("deptName") or item.get("departmentName") or "").strip()
            else:
                value = str(item or "").strip()
            if value:
                values.append(value)
        return values
    if isinstance(raw, dict):
        value = str(raw.get("name") or raw.get("deptName") or raw.get("departmentName") or "").strip()
        return [value] if value else []
    return []


def _todo_from_detail(detail: dict[str, Any]) -> TodoRecord:
    executor_ids = detail.get("executorIds") or []
    assignee_user_id = str(executor_ids[0]) if executor_ids else ""
    return TodoRecord(
        todo_id=str(detail.get("taskId") or ""),
        title=str(detail.get("subject") or ""),
        assignee_user_id=assignee_user_id,
        status=_map_detail_status(detail),
        due_time=_format_due_time(detail.get("dueTime")),
        extra={"raw": detail},
    )


def _todo_from_card(card: dict[str, Any]) -> TodoRecord:
    task_id = str(card.get("taskId") or card.get("id") or card.get("todoId") or "")
    executor_ids = card.get("executorIds") or card.get("participantIds") or []
    assignee_user_id = str(executor_ids[0]) if executor_ids else ""
    return TodoRecord(
        todo_id=task_id,
        title=str(card.get("subject") or card.get("title") or ""),
        assignee_user_id=assignee_user_id,
        status=_map_detail_status(card),
        due_time=_format_due_time(card.get("dueTime")),
        extra={"raw": card},
    )


def _map_detail_status(detail: dict[str, Any]) -> UnifiedTodoStatus:
    if detail.get("isDone") is True:
        return UnifiedTodoStatus.COMPLETED
    if detail.get("isDone") is False:
        return UnifiedTodoStatus.OPEN
    final_status_stage = detail.get("finalStatusStage")
    if final_status_stage is not None:
        try:
            final_status = int(final_status_stage)
        except (TypeError, ValueError):
            final_status = -1
        if final_status == 0:
            return UnifiedTodoStatus.OPEN
        if final_status == 1:
            return UnifiedTodoStatus.IN_PROGRESS
        if final_status == 2:
            return UnifiedTodoStatus.COMPLETED
        if final_status == 3:
            return UnifiedTodoStatus.CANCELLED
        if final_status == 4:
            return UnifiedTodoStatus.FAILED
    raw_status = str(detail.get("status") or "").strip().lower()
    return _normalize_status_name(raw_status)


def _normalize_status_name(status: str) -> UnifiedTodoStatus:
    value = str(status or "").strip().lower()
    if value in {"", "open", "todo", "pending", "false"}:
        return UnifiedTodoStatus.OPEN
    if value in {"in_progress", "processing", "running"}:
        return UnifiedTodoStatus.IN_PROGRESS
    if value in {"done", "completed", "true"}:
        return UnifiedTodoStatus.COMPLETED
    if value in {"cancelled", "canceled"}:
        return UnifiedTodoStatus.CANCELLED
    if value in {"failed", "error"}:
        return UnifiedTodoStatus.FAILED
    return UnifiedTodoStatus.UNKNOWN


def _map_list_status(status: str) -> str | None:
    normalized = _normalize_status_name(status)
    if normalized == UnifiedTodoStatus.UNKNOWN:
        return None if not status else None
    if normalized == UnifiedTodoStatus.COMPLETED:
        return "true"
    if normalized in {UnifiedTodoStatus.OPEN, UnifiedTodoStatus.IN_PROGRESS}:
        return "false"
    return None


def _default_due_time() -> str:
    """Return today 18:00 CST as ISO-8601, so DingTalk sends a reminder."""
    cst = timezone(timedelta(hours=8))
    now = datetime.now(cst)
    due = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if due <= now:
        due = due + timedelta(days=1)
    return due.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _format_due_time(raw_due_time: Any) -> str:
    if raw_due_time in (None, "", 0, "0"):
        return ""
    return str(raw_due_time)


def _dig(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default

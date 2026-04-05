"""调用 finance-mcp 工具的 HTTP 客户端包装器。

所有规则管理和认证操作均通过 finance-mcp 的 MCP 工具完成，
data-agent 不再直接读取 JSON 配置文件或操作数据库。

MCP SSE 协议说明：
  - POST /messages/?session_id=xxx 投递请求，服务端返回 202 Accepted
  - 实际结果通过持续保持的 SSE 连接（/sse）异步推送回来
  - 使用 request_id 匹配请求与响应
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import httpx

from config import FINANCE_MCP_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_RESULT_WAIT_TIMEOUT = 60.0  # 等待 SSE 结果超时秒数
_PLATFORM_CONNECTION_MODE = os.getenv("PLATFORM_CONNECTION_MODE", "mock").strip().lower() or "mock"


def _get_result_wait_timeout(tool_name: str) -> float:
    """按工具类型返回结果等待超时。

    proc/recon 属于长任务，60 秒对真实文件偏紧，容易误判为失败。
    """
    if tool_name == "proc_execute":
        return 180.0
    if tool_name == "recon_execute":
        return 300.0
    return _RESULT_WAIT_TIMEOUT

# ===========================================================================
# MCP SSE 会话管理
# ===========================================================================

class _McpSession:
    """管理单个 MCP SSE 会话：维持 SSE 长连接并匹配请求/响应。"""

    def __init__(self):
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}  # request_id -> Future
        self._req_counter = 0
        self._sse_task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._connect_lock = asyncio.Lock()

    def _next_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    async def connect(self) -> bool:
        """建立 SSE 长连接，获取 session_id，完成 MCP 游标握手，并启动后台监听任务。"""
        async with self._connect_lock:
            if self._sse_task and not self._sse_task.done():
                return self.session_id is not None

            try:
                logger.info("建立 MCP SSE 长连接...")
                self._client = httpx.AsyncClient(timeout=_TIMEOUT)
                session_ready = asyncio.get_running_loop().create_future()
                self._sse_task = asyncio.create_task(
                    self._sse_listener(session_ready)
                )
                # 等待 session_id 就绪（最多 15 秒）
                await asyncio.wait_for(session_ready, timeout=15.0)
                if not self.session_id:
                    await self._close_failed_connection()
                    return False
                # 完成 MCP 协议握手
                await self._handshake()
                return True
            except asyncio.TimeoutError:
                logger.error("等待 SSE session_id 超时")
                await self._close_failed_connection()
                return False
            except Exception as e:
                logger.error(f"SSE 连接失败: {e}", exc_info=True)
                await self._close_failed_connection()
                return False

    async def _close_failed_connection(self) -> None:
        """清理失败或半初始化的 SSE 连接。"""
        sse_task = self._sse_task
        client = self._client

        self.session_id = None
        self._sse_task = None
        self._client = None

        if sse_task is not None and not sse_task.done():
            sse_task.cancel()
            with suppress(asyncio.CancelledError):
                await sse_task

        if client is not None:
            with suppress(Exception):
                await client.aclose()

    async def _handshake(self):
        """完成 MCP 协议握手：发送 initialize 并等待响应，再发 notifications/initialized。"""
        logger.info("开始 MCP 协议握手...")
        
        # 发送 initialize 请求
        init_id = self._next_id()
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[init_id] = fut
        
        init_body = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "data-agent", "version": "1.0"},
            },
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            r = await c.post(
                f"{FINANCE_MCP_BASE_URL}/messages/?session_id={self.session_id}",
                json=init_body,
            )
        if r.status_code not in (200, 202):
            self._pending.pop(init_id, None)
            raise RuntimeError(f"initialize 失败: {r.status_code} {r.text}")
        
        # 等待 initialize 响应
        try:
            await asyncio.wait_for(fut, timeout=10.0)
        except asyncio.TimeoutError:
            self._pending.pop(init_id, None)
            raise RuntimeError("initialize 响应超时")
        
        # 发送 notifications/initialized
        notif_body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as c:
            await c.post(
                f"{FINANCE_MCP_BASE_URL}/messages/?session_id={self.session_id}",
                json=notif_body,
            )
        
        logger.info("MCP 协议握手完成")

    async def _sse_listener(self, session_ready: asyncio.Future):
        """后台持续监听 SSE 事件流，将结果分发给等待中的 Future。"""
        try:
            async with self._client.stream("GET", f"{FINANCE_MCP_BASE_URL}/sse") as resp:
                if resp.status_code != 200:
                    logger.error(f"SSE 连接失败: {resp.status_code}")
                    if not session_ready.done():
                        session_ready.set_result(None)
                    return

                is_endpoint_event = False
                event_type: str | None = None
                data_lines: list[str] = []

                async for line in resp.aiter_lines():
                    logger.debug(f"SSE 原始行: {line!r}")

                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue

                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                        continue

                    if line == "":  # 空行 = 事件结束
                        data_str = "\n".join(data_lines)
                        data_lines = []

                        if event_type == "endpoint":
                            # 解析 session_id
                            decoded = unquote(data_str)
                            m = re.search(r"session_id=([^&\s]+)", decoded)
                            if m:
                                self.session_id = m.group(1)
                                logger.info(f"MCP session_id 就绪: {self.session_id}")
                                if not session_ready.done():
                                    session_ready.set_result(self.session_id)

                        elif event_type == "message" and data_str:
                            # JSON-RPC 响应，按 id 分发
                            try:
                                msg = json.loads(data_str)
                                req_id = msg.get("id")
                                if req_id is not None and req_id in self._pending:
                                    fut = self._pending.pop(req_id)
                                    if not fut.done():
                                        fut.set_result(msg)
                            except Exception as e:
                                logger.error(f"解析 SSE 消息失败: {e}, data={data_str!r}")

                        event_type = None

        except asyncio.CancelledError:
            logger.info("SSE 监听任务已取消")
        except Exception as e:
            logger.error(f"SSE 监听异常: {e}", exc_info=True)
        finally:
            # 将所有等待中的 Future 标记为错误
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("SSE 连接已断开"))
            self._pending.clear()
            self.session_id = None
            self._sse_task = None
            client = self._client
            self._client = None
            if not session_ready.done():
                session_ready.set_result(None)
            if client is not None:
                with suppress(Exception):
                    await client.aclose()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """发送工具调用请求并等待 SSE 响应。"""
        # 确保连接就绪
        if not self.session_id or (self._sse_task and self._sse_task.done()):
            ok = await self.connect()
            if not ok:
                return {"success": False, "error": "无法建立 MCP SSE 连接"}

        result_wait_timeout = _get_result_wait_timeout(tool_name)
        req_id = self._next_id()
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut

        request_body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as post_client:
                resp = await post_client.post(
                    f"{FINANCE_MCP_BASE_URL}/messages/?session_id={self.session_id}",
                    json=request_body,
                )

            if resp.status_code not in (200, 202):
                self._pending.pop(req_id, None)
                logger.error(f"MCP 投递失败: {resp.status_code}, {resp.text}")
                # session 过期时重置
                if resp.status_code in (400, 404):
                    logger.info("session 可能已过期，重置连接")
                    self.session_id = None
                    if self._sse_task:
                        self._sse_task.cancel()
                return {"success": False, "error": f"MCP 投递失败: {resp.status_code}"}

            logger.info(f"MCP 请求已投递 (id={req_id}, tool={tool_name})，等待 SSE 响应...")

            # 等待 SSE 推送结果
            try:
                jsonrpc_resp = await asyncio.wait_for(fut, timeout=result_wait_timeout)
            except asyncio.TimeoutError:
                self._pending.pop(req_id, None)
                logger.error(
                    "等待 MCP 响应超时: tool=%s timeout=%ss",
                    tool_name,
                    result_wait_timeout,
                )
                return {
                    "success": False,
                    "error": f"等待 MCP 响应超时（{int(result_wait_timeout)}秒）",
                }

            # 提取结果
            if "error" in jsonrpc_resp:
                err = jsonrpc_resp["error"]
                logger.error(f"MCP 工具返回错误: {err}")
                return {"success": False, "error": err.get("message", str(err))}

            result = jsonrpc_resp.get("result", {})
            # result 通常是 {"content": [{"type": "text", "text": "..."}]}
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and content:
                    text = content[0].get("text", "")
                    # 检查 isError 标志——MCP schema 校验失败时 isError=true
                    if result.get("isError"):
                        logger.error(f"MCP 工具执行错误: {text}")
                        return {"success": False, "error": text}
                    try:
                        return json.loads(text)
                    except Exception:
                        return {"success": True, "result": text}
            return result

        except Exception as e:
            self._pending.pop(req_id, None)
            logger.error(f"MCP 调用异常: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


# 全局单例会话
_mcp_session = _McpSession()


# ===========================================================================
# 底层：公共调用入口
# ===========================================================================

async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """调用 finance-mcp 工具。

    通过 MCP SSE 协议调用 finance-mcp 服务：
    - 维持持久 SSE 长连接接收结果
    - POST /messages/ 投递请求（服务端返回 202）
    - 等待 SSE 流推送 JSON-RPC 响应
    """
    return await _mcp_session.call_tool(tool_name, arguments)


# ===========================================================================
# 高级辅助函数 - 认证
# ===========================================================================

async def auth_login(username: str, password: str) -> dict[str, Any]:
    """用户登录"""
    return await call_mcp_tool("auth_login", {
        "username": username,
        "password": password,
    })


async def auth_register(username: str, password: str, **kwargs) -> dict[str, Any]:
    """用户注册"""
    args = {"username": username, "password": password}
    args.update(kwargs)
    return await call_mcp_tool("auth_register", args)


async def auth_me(token: str) -> dict[str, Any]:
    """获取当前用户信息"""
    return await call_mcp_tool("auth_me", {"auth_token": token})


# ===========================================================================
# 高级辅助函数 - 规则选择
# ===========================================================================

async def list_available_rules(auth_token: str) -> list[dict[str, str]]:
    """从任务列表中提取当前用户可用规则。

    Returns:
        [{"rule_code": "...", "name": "...", "task_name": "..."}, ...]
    """
    result = await list_user_tasks(auth_token)
    if not result.get("success"):
        logger.error(f"查询任务列表失败: {result.get('error')}")
        return []

    flattened_rules: list[dict[str, str]] = []
    seen_rule_codes: set[str] = set()
    for task in result.get("tasks", []):
        task_name = str(task.get("task_name") or "").strip()
        for rule in task.get("rules", []):
            rule_code = str(rule.get("rule_code") or "").strip()
            rule_name = str(rule.get("name") or rule_code or task_name).strip()
            if not rule_name or rule_code in seen_rule_codes:
                continue
            seen_rule_codes.add(rule_code)
            flattened_rules.append({
                "rule_code": rule_code,
                "name": rule_name,
                "task_name": task_name,
            })
    return flattened_rules


# ══════════════════════════════════════════════════════════════════════════════
# 管理员功能
# ══════════════════════════════════════════════════════════════════════════════

async def admin_login(username: str, password: str) -> dict[str, Any]:
    """管理员登录"""
    return await call_mcp_tool("admin_login", {
        "username": username,
        "password": password,
    })


async def create_company(admin_token: str, name: str) -> dict[str, Any]:
    """管理员创建公司"""
    return await call_mcp_tool("create_company", {
        "admin_token": admin_token,
        "name": name,
    })


async def create_department(admin_token: str, company_id: str, name: str) -> dict[str, Any]:
    """管理员创建部门"""
    return await call_mcp_tool("create_department", {
        "admin_token": admin_token,
        "company_id": company_id,
        "name": name,
    })


async def list_company(admin_token: str = "") -> dict[str, Any]:
    """获取公司列表。

    - 未传 admin_token: 注册/公开流程
    - 传入 admin_token: 管理员流程
    """
    args: dict[str, Any] = {}
    if admin_token:
        args["admin_token"] = admin_token
    return await call_mcp_tool("list_company", args)


async def get_admin_view(admin_token: str) -> dict[str, Any]:
    """获取管理员视图"""
    return await call_mcp_tool("get_admin_view", {
        "admin_token": admin_token,
    })


async def list_departments(company_id: str) -> dict[str, Any]:
    """获取指定公司的部门列表。"""
    return await call_mcp_tool("list_departments", {
        "company_id": company_id,
    })


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════════════════════

async def create_conversation(auth_token: str, title: str = None) -> dict[str, Any]:
    """创建新会话"""
    args = {"auth_token": auth_token}
    if title:
        args["title"] = title
    return await call_mcp_tool("create_conversation", args)


async def list_conversations(auth_token: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """获取用户的会话列表"""
    return await call_mcp_tool("list_conversations", {
        "auth_token": auth_token,
        "limit": limit,
        "offset": offset,
    })


async def get_conversation(auth_token: str, conversation_id: str) -> dict[str, Any]:
    """获取单个会话详情（包含消息）"""
    return await call_mcp_tool("get_conversation", {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
    })


async def delete_conversation(auth_token: str, conversation_id: str) -> dict[str, Any]:
    """删除会话"""
    return await call_mcp_tool("delete_conversation", {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
    })


async def save_message(auth_token: str, conversation_id: str, role: str, content: str, metadata: dict = None, attachments: list = None) -> dict[str, Any]:
    """保存消息到会话（支持附件）"""
    args = {
        "auth_token": auth_token,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    if metadata:
        args["metadata"] = metadata
    if attachments:
        args["attachments"] = attachments
    return await call_mcp_tool("save_message", args)


# ══════════════════════════════════════════════════════════════════════════════
# 高级辅助函数 - Proc 模块（任务管理）
# ══════════════════════════════════════════════════════════════════════════════

async def list_user_tasks(auth_token: str) -> dict[str, Any]:
    """获取当前用户可用任务列表。
    
    Args:
        auth_token: JWT token（用户登录后获取，必填）
        
    Returns:
        {
            "success": bool,
            "count": int,
            "tasks": list[dict],
            "message": str
        }
    """
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    return await call_mcp_tool("list_user_tasks", {"auth_token": auth_token})


async def get_file_validation_rule(rule_code: str, auth_token: str = "") -> dict[str, Any]:
    """根据 rule_code 获取文件校验规则 JSON（通过 rule_detail 服务，rule_type=file）
    
    Args:
        rule_code: 规则编码
        auth_token: JWT token（可选）
        
    Returns:
        {
            "success": bool,
            "rule_code": str,
            "data": dict,  # 包含 id, user_id, rule_code, rule, rule_type, remark
            "message": str
        }
    """
    args: dict[str, Any] = {"rule_code": rule_code}
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("get_rule", args)


async def validate_files(
    uploaded_files: list[dict[str, Any]],
    rule_code: str,
    auth_token: str = "",
) -> dict[str, Any]:
    """根据规则编码校验上传文件列表，判断每个文件属于哪个预定义的表。
    
    Args:
        uploaded_files: 上传文件列表，格式 [{"file_name": "xxx.xlsx", "columns": ["列1", ...]}]
        rule_code: 文件校验规则编码，用于从数据库查询对应的校验规则配置
        
    Returns:
        {
            "success": bool,
            "matched_results": [{"file_name": str, "table_id": str, "table_name": str}],
            "unmatched_files": [str],
            "message": str,
            # 失败时还包含:
            "error": str,
            "missing_tables": [{"table_id": str, "table_name": str}]
        }
    """
    args = {
        "uploaded_files": uploaded_files,
        "rule_code": rule_code,
    }
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("validate_files", args)


async def execute_proc_rule(
    uploaded_files: list[dict[str, Any]],
    rule_code: str,
    auth_token: str = "",
) -> dict[str, Any]:
    """根据规则编码执行数据整理规则，生成目标 Excel 文件。
    
    Args:
        uploaded_files: 文件校验结果列表，格式 [{"file_name": str, "file_path": str, "table_id": str, "table_name": str}]
        rule_code: 整理规则编码，用于从数据库查询对应的规则 JSON；输出目录由 MCP 服务端的 config 决定
        
    Returns:
        {
            "success": bool,
            "rule_code": str,
            "generated_files": [{"rule_id": str, "target_table": str, "output_file": str, "row_count": int}],
            "generated_count": int,
            "errors": [str],
            "message": str
        }
    """
    args: dict[str, Any] = {
        "uploaded_files": uploaded_files,
        "rule_code": rule_code,
    }
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("proc_execute", args)


async def execute_recon(
    *,
    validated_inputs: list[dict[str, Any]] | None = None,
    validated_files: list[dict[str, Any]] | None = None,
    rule_code: str,
    rule_id: str = "",
    auth_token: str = "",
) -> dict[str, Any]:
    """执行对账任务（支持对账），根据规则对源文件与目标文件进行数据比对。
    
    Args:
        validated_inputs: 统一输入列表。
            - file: {"table_name": str, "input_type": "file", "file_path": str}
            - dataset: {"table_name": str, "input_type": "dataset",
                        "dataset_ref": {"source_type": "db|api", "source_key": str, "query": dict}}
        validated_files: 兼容旧格式的文件输入，格式 [{"file_path": str, "table_name": str}]
        rule_code: 规则编码，用于从 rule_detail 表获取规则定义
        rule_id: 要执行的对账规则 ID（可选）
        
    Returns:
        {
            "success": bool,
            "rule_code": str,
            "rule_type": str,  # "recon" 或 "normal_reconc"
            "total_rules": int,
            "success_count": int,
            "results": [{
                "success": bool,
                "rule_id": str,
                "rule_name": str,
                "source_file": str,
                "target_file": str,
                "source_rows": int,
                "target_rows": int,
                "matched_with_diff": int,
                "source_only": int,
                "target_only": int,
                "matched_exact": int,
                "output_file": str,
                "message": str
            }]
        }
    """
    args: dict[str, Any] = {
        "rule_code": rule_code,
    }
    if validated_inputs is not None:
        args["validated_inputs"] = validated_inputs
    if validated_files is not None:
        args["validated_files"] = validated_files
    if rule_id:
        args["rule_id"] = rule_id
    if auth_token:
        args["auth_token"] = auth_token
    return await call_mcp_tool("recon_execute", args)


# ══════════════════════════════════════════════════════════════════════════════
# 高级辅助函数 - 自动对账与异常闭环
# ══════════════════════════════════════════════════════════════════════════════

async def recon_auto_task_list(
    auth_token: str,
    *,
    include_disabled: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_task_list",
        {
            "auth_token": auth_token,
            "include_disabled": include_disabled,
            "limit": limit,
            "offset": offset,
        },
    )


async def recon_auto_task_get(auth_token: str, auto_task_id: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_task_get",
        {"auth_token": auth_token, "auto_task_id": auto_task_id},
    )


async def recon_auto_task_create(auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("recon_auto_task_create", {"auth_token": auth_token, **(payload or {})})


async def recon_auto_task_update(auth_token: str, auto_task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_task_update",
        {"auth_token": auth_token, "auto_task_id": auto_task_id, **(payload or {})},
    )


async def recon_auto_task_delete(auth_token: str, auto_task_id: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_task_delete",
        {"auth_token": auth_token, "auto_task_id": auto_task_id},
    )


async def recon_auto_run_create(auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("recon_auto_run_create", {"auth_token": auth_token, **(payload or {})})


async def recon_auto_run_update(auth_token: str, auto_run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_run_update",
        {"auth_token": auth_token, "auto_run_id": auto_run_id, **(payload or {})},
    )


async def recon_auto_run_list(
    auth_token: str,
    *,
    auto_task_id: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "auth_token": auth_token,
        "limit": limit,
        "offset": offset,
    }
    if auto_task_id:
        args["auto_task_id"] = auto_task_id
    return await call_mcp_tool("recon_auto_run_list", args)


async def recon_auto_run_get(auth_token: str, auto_run_id: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_run_get",
        {"auth_token": auth_token, "auto_run_id": auto_run_id},
    )


async def recon_auto_run_rerun(auth_token: str, auto_run_id: str, reason: str = "") -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_run_rerun",
        {"auth_token": auth_token, "auto_run_id": auto_run_id, "reason": reason},
    )


async def recon_auto_run_verify(auth_token: str, auto_run_id: str, reason: str = "") -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_run_verify",
        {"auth_token": auth_token, "auto_run_id": auto_run_id, "reason": reason},
    )


async def recon_auto_run_job_create(auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("recon_auto_run_job_create", {"auth_token": auth_token, **(payload or {})})


async def recon_auto_run_job_update(auth_token: str, run_job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_run_job_update",
        {"auth_token": auth_token, "run_job_id": run_job_id, **(payload or {})},
    )


async def recon_auto_run_exceptions(
    auth_token: str,
    auto_run_id: str,
    *,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_auto_run_exceptions",
        {
            "auth_token": auth_token,
            "auto_run_id": auto_run_id,
            "limit": limit,
            "offset": offset,
        },
    )


async def recon_exception_get(auth_token: str, exception_id: str) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_exception_get",
        {"auth_token": auth_token, "exception_id": exception_id},
    )


async def recon_exception_create(auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool("recon_exception_create", {"auth_token": auth_token, **(payload or {})})


async def recon_exception_update(auth_token: str, exception_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return await call_mcp_tool(
        "recon_exception_update",
        {"auth_token": auth_token, "exception_id": exception_id, **(payload or {})},
    )


# ══════════════════════════════════════════════════════════════════════════════
# 高级辅助函数 - Platform 连接中心（店铺授权）
# ══════════════════════════════════════════════════════════════════════════════

_MOCK_PLATFORM_NAME_MAP: dict[str, str] = {
    "taobao": "淘宝",
    "tmall": "天猫",
    "douyin_shop": "抖店",
    "kuaishou": "快手小店",
    "jd": "京东",
}
_MOCK_PLATFORM_ORDER: tuple[str, ...] = ("taobao", "tmall", "douyin_shop", "kuaishou", "jd")
_MOCK_AUTH_SESSIONS: dict[str, dict[str, Any]] = {}
_MOCK_CONNECTIONS_BY_USER: dict[str, list[dict[str, Any]]] = {}


def _platform_name(platform_code: str) -> str:
    return _MOCK_PLATFORM_NAME_MAP.get(platform_code, platform_code)


def _normalize_mode(mode: str = "") -> str:
    normalized = (mode or "").strip().lower()
    if normalized in {"mock", "real"}:
        return normalized
    return _PLATFORM_CONNECTION_MODE if _PLATFORM_CONNECTION_MODE in {"mock", "real"} else "mock"


def _auth_user_key(auth_token: str) -> str:
    if not auth_token:
        return "anonymous"
    return hashlib.sha1(auth_token.encode("utf-8")).hexdigest()[:16]


def _is_unknown_tool_error(error: Any) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    markers = [
        "未知的工具",
        "no such tool",
        "unknown tool",
    ]
    return any(marker in text for marker in markers)


def _mock_seed_connections(user_key: str) -> list[dict[str, Any]]:
    existing = _MOCK_CONNECTIONS_BY_USER.get(user_key)
    if existing is not None:
        return existing

    seeded = [
        {
            "id": "mock-taobao-shop-001",
            "company_id": "",
            "platform_code": "taobao",
            "platform_name": _platform_name("taobao"),
            "external_shop_id": "taobao_shop_001",
            "external_shop_name": "测试淘宝店铺A",
            "status": "authorized",
            "token_status": "active",
            "last_sync_at": None,
            "created_at": None,
            "updated_at": None,
        },
        {
            "id": "mock-douyin-shop-001",
            "company_id": "",
            "platform_code": "douyin_shop",
            "platform_name": _platform_name("douyin_shop"),
            "external_shop_id": "douyin_shop_001",
            "external_shop_name": "测试抖店A",
            "status": "authorized",
            "token_status": "active",
            "last_sync_at": None,
            "created_at": None,
            "updated_at": None,
        },
    ]
    _MOCK_CONNECTIONS_BY_USER[user_key] = seeded
    return seeded


def _mock_group_platforms(connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {
        code: {
            "platform_code": code,
            "platform_name": _platform_name(code),
            "authorized_shop_count": 0,
            "error_shop_count": 0,
            "last_sync_at": None,
            "status": "connected" if code in {"taobao", "tmall", "douyin_shop"} else "planned",
        }
        for code in _MOCK_PLATFORM_ORDER
    }
    for row in connections:
        code = str(row.get("platform_code") or "")
        if not code:
            continue
        if code not in grouped:
            grouped[code] = {
                "platform_code": code,
                "platform_name": _platform_name(code),
                "authorized_shop_count": 0,
                "error_shop_count": 0,
                "last_sync_at": None,
                "status": "connected",
            }
        grouped[code]["authorized_shop_count"] += 1
        if str(row.get("token_status") or "").lower() in {"expired", "error"}:
            grouped[code]["error_shop_count"] += 1
    return [grouped[code] for code in grouped]


def _mock_list_connections(auth_token: str, platform_code: str = "") -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    all_rows = _mock_seed_connections(user_key)
    normalized_platform = str(platform_code or "").strip()
    rows = [row for row in all_rows if not normalized_platform or row.get("platform_code") == normalized_platform]
    platforms = _mock_group_platforms(rows if normalized_platform else all_rows)
    return {
        "success": True,
        "mode": "mock",
        "platforms": platforms,
        "connections": rows,
        "count": len(rows) if normalized_platform else len(platforms),
    }


def _mock_list_shops(auth_token: str, platform_code: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    rows = [
        row for row in _mock_seed_connections(user_key)
        if row.get("platform_code") == platform_code
    ]
    return {
        "success": True,
        "mode": "mock",
        "platform_code": platform_code,
        "platform_name": _platform_name(platform_code),
        "shops": rows,
        "count": len(rows),
    }


def _mock_create_auth_session(
    auth_token: str,
    platform_code: str,
    return_path: str,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    session_id = str(uuid.uuid4())
    state = session_id
    _MOCK_AUTH_SESSIONS[state] = {
        "session_id": session_id,
        "user_key": user_key,
        "platform_code": platform_code,
        "return_path": return_path or "/",
    }
    auth_url = (
        f"/api/platform-auth/callback/{platform_code}"
        f"?state={quote(state)}&code=mock_code_{session_id[:8]}&mode=mock"
    )
    return {
        "success": True,
        "mode": "mock",
        "platform_code": platform_code,
        "session_id": session_id,
        "state": state,
        "auth_url": auth_url,
        "expires_in": 600,
    }


def _mock_handle_auth_callback(
    platform_code: str,
    state: str,
    code: str,
    error: str = "",
    error_description: str = "",
) -> dict[str, Any]:
    if error:
        return {
            "success": False,
            "mode": "mock",
            "platform_code": platform_code,
            "error": error,
            "message": error_description or "授权失败，请重试",
            "return_path": "/",
        }

    session = _MOCK_AUTH_SESSIONS.get(state)
    if not session:
        return {
            "success": False,
            "mode": "mock",
            "platform_code": platform_code,
            "error": "invalid_state",
            "message": "授权会话已失效，请重新发起授权",
            "return_path": "/",
        }

    user_key = str(session.get("user_key") or "anonymous")
    connections = _mock_seed_connections(user_key)
    index = len([r for r in connections if r.get("platform_code") == platform_code]) + 1
    connection_id = f"mock-{platform_code}-shop-{index:03d}"
    new_row = {
        "id": connection_id,
        "company_id": "",
        "platform_code": platform_code,
        "platform_name": _platform_name(platform_code),
        "external_shop_id": f"{platform_code}_shop_{index:03d}",
        "external_shop_name": f"测试{_platform_name(platform_code)}店铺{index}",
        "status": "authorized",
        "token_status": "active",
        "last_sync_at": None,
        "created_at": None,
        "updated_at": None,
    }
    connections.append(new_row)
    _MOCK_CONNECTIONS_BY_USER[user_key] = connections
    return {
        "success": True,
        "mode": "mock",
        "platform_code": platform_code,
        "message": f"{_platform_name(platform_code)}授权成功",
        "return_path": session.get("return_path") or "/",
        "connection": new_row,
        "code": code,
    }


def _mock_disable_shop(auth_token: str, connection_id: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    rows = _mock_seed_connections(user_key)
    for row in rows:
        if row.get("id") == connection_id:
            row["status"] = "disabled"
            row["token_status"] = "disabled"
            return {"success": True, "mode": "mock", "message": "店铺连接已停用", "connection": row}
    return {"success": False, "mode": "mock", "error": "not_found", "message": "店铺连接不存在"}


def _mock_get_shop_detail(auth_token: str, connection_id: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    rows = _mock_seed_connections(user_key)
    for row in rows:
        if row.get("id") == connection_id:
            return {
                "success": True,
                "mode": "mock",
                "connection": row,
                "sync_sources": [],
                "authorization": {
                    "auth_status": "authorized",
                    "token_expires_at": None,
                    "last_refresh_at": None,
                },
            }
    return {"success": False, "mode": "mock", "error": "not_found", "message": "店铺连接不存在"}


async def platform_list_connections(
    auth_token: str,
    *,
    mode: str = "",
    platform_code: str = "",
) -> dict[str, Any]:
    """获取当前用户的平台连接总览（按平台聚合，含连接明细）。"""
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_list_connections(auth_token, platform_code=platform_code)

    args: dict[str, Any] = {"auth_token": auth_token}
    if platform_code:
        args["platform_code"] = platform_code
    args["mode"] = normalized_mode
    result = await call_mcp_tool("platform_list_connections", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_list_connections(auth_token, platform_code=platform_code)
    return result


async def platform_list_shops(
    auth_token: str,
    platform_code: str,
    *,
    mode: str = "",
) -> dict[str, Any]:
    """获取指定平台下的店铺连接列表。"""
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not platform_code:
        return {"success": False, "error": "platform_code 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_list_shops(auth_token, platform_code=platform_code)

    result = await call_mcp_tool(
        "platform_list_connections",
        {"auth_token": auth_token, "platform_code": platform_code, "mode": normalized_mode},
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_list_shops(auth_token, platform_code=platform_code)

    connections = result.get("connections") if isinstance(result.get("connections"), list) else []
    return {
        "success": bool(result.get("success")),
        "mode": result.get("mode", normalized_mode),
        "platform_code": platform_code,
        "platform_name": _platform_name(platform_code),
        "shops": connections,
        "count": len(connections),
        "message": result.get("message", ""),
        "error": result.get("error", ""),
    }


async def platform_create_auth_session(
    auth_token: str,
    platform_code: str,
    *,
    return_path: str = "/",
    mode: str = "",
) -> dict[str, Any]:
    """创建平台授权会话，返回授权 URL。"""
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not platform_code:
        return {"success": False, "error": "platform_code 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_create_auth_session(auth_token, platform_code, return_path)

    result = await call_mcp_tool(
        "platform_create_auth_session",
        {
            "auth_token": auth_token,
            "platform_code": platform_code,
            "return_path": return_path,
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_create_auth_session(auth_token, platform_code, return_path)
    return result


async def platform_handle_auth_callback(
    platform_code: str,
    *,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """处理平台授权回调。"""
    if not platform_code:
        return {"success": False, "error": "platform_code 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_handle_auth_callback(
            platform_code=platform_code,
            state=state,
            code=code,
            error=error,
            error_description=error_description,
        )

    result = await call_mcp_tool(
        "platform_handle_auth_callback",
        {
            "platform_code": platform_code,
            "code": code,
            "state": state,
            "error": error,
            "error_description": error_description,
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_handle_auth_callback(
            platform_code=platform_code,
            state=state,
            code=code,
            error=error,
            error_description=error_description,
        )
    return result


async def platform_reauthorize_shop(
    auth_token: str,
    connection_id: str,
    *,
    return_path: str = "/",
    mode: str = "",
) -> dict[str, Any]:
    """重新发起店铺授权。"""
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not connection_id:
        return {"success": False, "error": "connection_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        # mock 模式下复用授权会话创建逻辑，平台编码由连接 ID 推断
        platform_code = "taobao" if "taobao" in connection_id else "douyin_shop" if "douyin" in connection_id else "taobao"
        return _mock_create_auth_session(auth_token, platform_code, return_path)

    result = await call_mcp_tool(
        "platform_reauthorize_shop",
        {
            "auth_token": auth_token,
            "shop_connection_id": connection_id,
            "return_path": return_path,
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        platform_code = "taobao" if "taobao" in connection_id else "douyin_shop" if "douyin" in connection_id else "taobao"
        return _mock_create_auth_session(auth_token, platform_code, return_path)
    return result


async def platform_disable_shop(
    auth_token: str,
    connection_id: str,
    *,
    reason: str = "",
    mode: str = "",
) -> dict[str, Any]:
    """停用店铺连接。"""
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not connection_id:
        return {"success": False, "error": "connection_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_disable_shop(auth_token, connection_id)

    args = {
        "auth_token": auth_token,
        "shop_connection_id": connection_id,
        "mode": normalized_mode,
    }
    if reason:
        args["reason"] = reason
    result = await call_mcp_tool("platform_disable_shop", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_disable_shop(auth_token, connection_id)
    return result


async def platform_get_shop_detail(
    auth_token: str,
    connection_id: str,
    *,
    mode: str = "",
) -> dict[str, Any]:
    """获取店铺连接详情。"""
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not connection_id:
        return {"success": False, "error": "connection_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_get_shop_detail(auth_token, connection_id)

    result = await call_mcp_tool(
        "platform_get_shop_detail",
        {
            "auth_token": auth_token,
            "shop_connection_id": connection_id,
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_get_shop_detail(auth_token, connection_id)
    return result


# ===========================================================================
# 高级辅助函数 - Unified Data Sources（统一数据连接）
# ===========================================================================

_SUPPORTED_SOURCE_KINDS: tuple[str, ...] = (
    "platform_oauth",
    "database",
    "api",
    "file",
    "browser",
    "desktop_cli",
)
_SUPPORTED_DOMAIN_TYPES: tuple[str, ...] = (
    "ecommerce",
    "bank",
    "finance_mid",
    "erp",
    "supplier",
    "internal_business",
)
_AGENT_ASSISTED_SOURCE_KINDS: set[str] = {"browser", "desktop_cli"}
_DETERMINISTIC_SOURCE_KINDS: set[str] = {"platform_oauth", "database", "api", "file"}
_MOCK_DATA_SOURCES_BY_USER: dict[str, dict[str, dict[str, Any]]] = {}
_MOCK_DATA_SOURCE_AUTH_SESSIONS: dict[str, dict[str, Any]] = {}
_MOCK_SYNC_JOBS_BY_USER: dict[str, dict[str, dict[str, Any]]] = {}
_MOCK_PUBLISHED_SNAPSHOTS_BY_USER: dict[str, dict[str, dict[str, Any]]] = {}
_MOCK_DATA_SOURCE_DATASETS_BY_USER: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
_MOCK_DATA_SOURCE_EVENTS_BY_USER: dict[str, list[dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_source_kind(source_kind: str = "") -> str:
    normalized = str(source_kind or "").strip().lower()
    if normalized in _SUPPORTED_SOURCE_KINDS:
        return normalized
    return "platform_oauth"


def _normalize_domain_type(domain_type: str = "") -> str:
    normalized = str(domain_type or "").strip().lower()
    if normalized in _SUPPORTED_DOMAIN_TYPES:
        return normalized
    return "ecommerce"


def _normalize_execution_mode(execution_mode: str = "", source_kind: str = "") -> str:
    normalized = str(execution_mode or "").strip().lower()
    if normalized in {"deterministic", "agent_assisted"}:
        return normalized
    return "agent_assisted" if source_kind in _AGENT_ASSISTED_SOURCE_KINDS else "deterministic"


def _compute_source_capabilities(source_kind: str) -> list[str]:
    if source_kind == "platform_oauth":
        return [
            "authorize",
            "test",
            "sync",
            "preview",
            "published_snapshot",
            "discover_datasets",
            "list_datasets",
            "list_events",
        ]
    if source_kind in {"database", "api"}:
        return [
            "test",
            "discover_datasets",
            "list_datasets",
            "list_events",
        ]
    if source_kind == "file":
        return [
            "test",
            "list_datasets",
            "list_events",
        ]
    if source_kind in _AGENT_ASSISTED_SOURCE_KINDS:
        return ["test", "preview", "list_events"]
    return ["test"]


def _mock_seed_data_sources(user_key: str) -> dict[str, dict[str, Any]]:
    existing = _MOCK_DATA_SOURCES_BY_USER.get(user_key)
    if existing is not None:
        return existing

    created_at = _now_iso()
    seeded: list[dict[str, Any]] = [
        {
            "id": "mock-source-platform-taobao",
            "name": "淘宝店铺授权连接",
            "source_kind": "platform_oauth",
            "domain_type": "ecommerce",
            "provider_code": "taobao",
            "execution_mode": "deterministic",
            "status": "active",
            "enabled": True,
            "capabilities": _compute_source_capabilities("platform_oauth"),
            "auth_status": "authorized",
            "description": "平台 OAuth 连接（mock）",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": "mock-source-db-hologres",
            "name": "财务中台 Hologres 只读连接",
            "source_kind": "database",
            "domain_type": "finance_mid",
            "provider_code": "hologres",
            "execution_mode": "deterministic",
            "status": "active",
            "enabled": True,
            "capabilities": _compute_source_capabilities("database"),
            "description": "数据库连接（mock）",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": "mock-source-api-bank",
            "name": "银行流水 API 连接",
            "source_kind": "api",
            "domain_type": "bank",
            "provider_code": "bank_openapi",
            "execution_mode": "deterministic",
            "status": "active",
            "enabled": True,
            "capabilities": _compute_source_capabilities("api"),
            "description": "银行 API 连接（mock）",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": "mock-source-file-upload",
            "name": "文件上传连接",
            "source_kind": "file",
            "domain_type": "internal_business",
            "provider_code": "local_upload",
            "execution_mode": "deterministic",
            "status": "active",
            "enabled": True,
            "capabilities": _compute_source_capabilities("file"),
            "description": "文件型连接（mock）",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": "mock-source-browser-reserved",
            "name": "浏览器抓取（预留）",
            "source_kind": "browser",
            "domain_type": "ecommerce",
            "provider_code": "playwright",
            "execution_mode": "agent_assisted",
            "status": "reserved",
            "enabled": False,
            "capabilities": _compute_source_capabilities("browser"),
            "description": "预留：由 agent loop 决策并调用执行器",
            "created_at": created_at,
            "updated_at": created_at,
        },
        {
            "id": "mock-source-cli-reserved",
            "name": "客户端/CLI 抓取（预留）",
            "source_kind": "desktop_cli",
            "domain_type": "internal_business",
            "provider_code": "desktop_cli",
            "execution_mode": "agent_assisted",
            "status": "reserved",
            "enabled": False,
            "capabilities": _compute_source_capabilities("desktop_cli"),
            "description": "预留：由 agent loop 决策并调用执行器",
            "created_at": created_at,
            "updated_at": created_at,
        },
    ]
    source_map = {item["id"]: item for item in seeded}
    _MOCK_DATA_SOURCES_BY_USER[user_key] = source_map
    _MOCK_SYNC_JOBS_BY_USER[user_key] = {}
    _MOCK_PUBLISHED_SNAPSHOTS_BY_USER[user_key] = {}
    return source_map


def _mock_dataset_id(source_id: str, dataset_code: str) -> str:
    raw = f"{source_id}:{dataset_code}".encode("utf-8")
    return f"mock-dataset-{hashlib.sha1(raw).hexdigest()[:12]}"


def _mock_build_dataset(
    *,
    source_id: str,
    dataset_code: str,
    dataset_name: str,
    resource_key: str,
    dataset_kind: str = "table",
    origin_type: str = "fixed",
    extract_config: dict[str, Any] | None = None,
    schema_summary: dict[str, Any] | None = None,
    sync_strategy: dict[str, Any] | None = None,
    status: str = "active",
    enabled: bool = True,
    health_status: str = "healthy",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": _mock_dataset_id(source_id, dataset_code),
        "data_source_id": source_id,
        "dataset_code": dataset_code,
        "dataset_name": dataset_name,
        "resource_key": resource_key,
        "dataset_kind": dataset_kind,
        "origin_type": origin_type,
        "extract_config": dict(extract_config or {}),
        "schema_summary": dict(schema_summary or {}),
        "sync_strategy": dict(sync_strategy or {"mode": "manual"}),
        "status": status,
        "enabled": enabled,
        "health_status": health_status,
        "last_checked_at": now,
        "last_sync_at": None,
        "last_error_message": "",
        "meta": dict(meta or {}),
        "created_at": now,
        "updated_at": now,
    }


def _mock_seed_source_dataset_rows(source: dict[str, Any]) -> list[dict[str, Any]]:
    source_id = str(source.get("id") or "")
    source_kind = str(source.get("source_kind") or "")
    provider_code = str(source.get("provider_code") or "")
    if source_kind == "platform_oauth":
        return [
            _mock_build_dataset(
                source_id=source_id,
                dataset_code="orders",
                dataset_name="订单数据集",
                resource_key="orders",
                dataset_kind="api_endpoint",
                origin_type="fixed",
                extract_config={"endpoint": "/orders/list", "method": "GET"},
                schema_summary={"fields": ["order_id", "shop_id", "amount", "pay_time"]},
                sync_strategy={"mode": "window", "window_unit": "day"},
                meta={"provider_code": provider_code},
            ),
            _mock_build_dataset(
                source_id=source_id,
                dataset_code="refunds",
                dataset_name="退款数据集",
                resource_key="refunds",
                dataset_kind="api_endpoint",
                origin_type="fixed",
                extract_config={"endpoint": "/refund/list", "method": "GET"},
                schema_summary={"fields": ["refund_id", "order_id", "refund_amount", "refund_time"]},
                sync_strategy={"mode": "window", "window_unit": "day"},
                meta={"provider_code": provider_code},
            ),
        ]
    if source_kind == "database":
        return [
            _mock_build_dataset(
                source_id=source_id,
                dataset_code="public_orders",
                dataset_name="订单表",
                resource_key="public.orders",
                dataset_kind="table",
                origin_type="discovered",
                extract_config={"schema": "public", "table": "orders"},
                schema_summary={"fields": ["order_id", "biz_date", "amount"]},
                sync_strategy={"mode": "full"},
            ),
            _mock_build_dataset(
                source_id=source_id,
                dataset_code="public_payment_flow",
                dataset_name="流水表",
                resource_key="public.payment_flow",
                dataset_kind="table",
                origin_type="discovered",
                extract_config={"schema": "public", "table": "payment_flow"},
                schema_summary={"fields": ["trade_no", "channel", "amount", "trade_time"]},
                sync_strategy={"mode": "incremental", "cursor_field": "trade_time"},
            ),
        ]
    if source_kind == "api":
        return [
            _mock_build_dataset(
                source_id=source_id,
                dataset_code="transactions",
                dataset_name="交易流水接口",
                resource_key="/v1/transactions",
                dataset_kind="api_endpoint",
                origin_type="imported_openapi",
                extract_config={"endpoint": "/v1/transactions", "method": "GET"},
                schema_summary={"fields": ["txn_id", "biz_date", "amount", "status"]},
                sync_strategy={"mode": "incremental", "cursor_field": "updated_at"},
            )
        ]
    if source_kind == "file":
        return [
            _mock_build_dataset(
                source_id=source_id,
                dataset_code="uploaded_sheet",
                dataset_name="上传文件数据集",
                resource_key="uploaded_sheet",
                dataset_kind="file",
                origin_type="manual",
                extract_config={"file_type": "xlsx"},
                schema_summary={"fields": ["col_a", "col_b"]},
                sync_strategy={"mode": "manual"},
            )
        ]
    return [
        _mock_build_dataset(
            source_id=source_id,
            dataset_code="default_dataset",
            dataset_name="默认数据集",
            resource_key="default",
            origin_type="manual",
            sync_strategy={"mode": "manual"},
        )
    ]


def _mock_emit_data_source_event(
    user_key: str,
    *,
    source_id: str,
    event_type: str,
    event_level: str,
    event_message: str,
    event_payload: dict[str, Any] | None = None,
    sync_job_id: str = "",
) -> None:
    events = _MOCK_DATA_SOURCE_EVENTS_BY_USER.setdefault(user_key, [])
    events.append(
        {
            "id": f"mock-event-{uuid.uuid4()}",
            "data_source_id": source_id,
            "sync_job_id": sync_job_id,
            "event_type": event_type,
            "event_level": event_level,
            "event_message": event_message,
            "event_payload": dict(event_payload or {}),
            "created_at": _now_iso(),
        }
    )
    if len(events) > 500:
        del events[:-500]


def _mock_ensure_data_source_context(user_key: str) -> tuple[dict[str, dict[str, dict[str, Any]]], list[dict[str, Any]]]:
    source_map = _mock_seed_data_sources(user_key)
    dataset_map = _MOCK_DATA_SOURCE_DATASETS_BY_USER.setdefault(user_key, {})
    events = _MOCK_DATA_SOURCE_EVENTS_BY_USER.setdefault(user_key, [])

    if not dataset_map:
        for source in source_map.values():
            source_id = str(source.get("id") or "")
            rows = _mock_seed_source_dataset_rows(source)
            dataset_map[source_id] = {str(item["id"]): item for item in rows}

    if not events:
        for source in source_map.values():
            source_id = str(source.get("id") or "")
            _mock_emit_data_source_event(
                user_key,
                source_id=source_id,
                event_type="data_source_seeded",
                event_level="info",
                event_message="数据源已初始化（mock）",
            )

    return dataset_map, events


def _mock_collect_source_datasets(user_key: str, source_id: str) -> list[dict[str, Any]]:
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    return list(dataset_map.setdefault(source_id, {}).values())


def _mock_list_data_sources(
    auth_token: str,
    *,
    source_kind: str = "",
    domain_type: str = "",
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    values = list(source_map.values())
    normalized_kind = str(source_kind or "").strip().lower()
    normalized_domain = str(domain_type or "").strip().lower()
    if normalized_kind:
        values = [item for item in values if str(item.get("source_kind")) == normalized_kind]
    if normalized_domain:
        values = [item for item in values if str(item.get("domain_type")) == normalized_domain]
    return {
        "success": True,
        "mode": "mock",
        "count": len(values),
        "sources": values,
    }


def _mock_get_data_source(auth_token: str, source_id: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    source = source_map.get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}
    published = _MOCK_PUBLISHED_SNAPSHOTS_BY_USER.get(user_key, {}).get(source_id)
    return {
        "success": True,
        "mode": "mock",
        "source": source,
        "published_snapshot": published,
    }


def _mock_resolve_provider_code(source_kind: str, payload: dict[str, Any]) -> str:
    explicit = str(payload.get("provider_code") or "").strip().lower()
    if explicit:
        return explicit

    connection_config = dict(payload.get("connection_config") or {})
    if source_kind == "database":
        return str(connection_config.get("db_type") or "database").strip().lower() or "database"
    if source_kind == "api":
        return "custom_api"
    if source_kind == "file":
        return "manual_file"
    return source_kind


def _mock_create_data_source(auth_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    source_kind = _normalize_source_kind(str(payload.get("source_kind") or ""))
    domain_type = _normalize_domain_type(str(payload.get("domain_type") or ""))
    execution_mode = _normalize_execution_mode(str(payload.get("execution_mode") or ""), source_kind)
    now = _now_iso()
    source_id = f"mock-source-{uuid.uuid4()}"
    provider_code = _mock_resolve_provider_code(source_kind, payload)
    source = {
        "id": source_id,
        "name": str(payload.get("name") or f"{source_kind}-source"),
        "source_kind": source_kind,
        "domain_type": domain_type,
        "provider_code": provider_code,
        "execution_mode": execution_mode,
        "status": "reserved" if source_kind in _AGENT_ASSISTED_SOURCE_KINDS else "active",
        "enabled": False if source_kind in _AGENT_ASSISTED_SOURCE_KINDS else True,
        "capabilities": _compute_source_capabilities(source_kind),
        "auth_status": "unauthorized" if source_kind == "platform_oauth" else "",
        "description": str(payload.get("description") or ""),
        "connection_config": dict(payload.get("connection_config") or {}),
        "extract_config": dict(payload.get("extract_config") or {}),
        "mapping_config": dict(payload.get("mapping_config") or {}),
        "runtime_config": dict(payload.get("runtime_config") or {}),
        "created_at": now,
        "updated_at": now,
    }
    source_map[source_id] = source
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    dataset_map[source_id] = {}
    _mock_emit_data_source_event(
        user_key,
        source_id=source_id,
        event_type="data_source_created",
        event_level="info",
        event_message="数据源已创建（mock）",
    )
    return {"success": True, "mode": "mock", "source": source}


def _mock_update_data_source(auth_token: str, source_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    source = source_map.get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}

    mutable_fields = {
        "name",
        "description",
        "provider_code",
        "domain_type",
        "connection_config",
        "extract_config",
        "mapping_config",
        "runtime_config",
        "enabled",
    }
    for field in mutable_fields:
        if field in payload:
            source[field] = payload[field]

    if "provider_code" not in payload:
        source["provider_code"] = _mock_resolve_provider_code(str(source.get("source_kind") or ""), source)

    source["updated_at"] = _now_iso()
    return {"success": True, "mode": "mock", "source": source}


def _mock_disable_data_source(auth_token: str, source_id: str, reason: str = "") -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    source = source_map.get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}
    source["status"] = "disabled"
    source["enabled"] = False
    source["updated_at"] = _now_iso()
    if reason:
        source["last_disable_reason"] = reason
    for dataset in dataset_map.setdefault(source_id, {}).values():
        dataset["status"] = "disabled"
        dataset["enabled"] = False
        dataset["health_status"] = "disabled"
        dataset["updated_at"] = _now_iso()
        dataset["last_error_message"] = reason or "所属数据源已停用"
    _mock_emit_data_source_event(
        user_key,
        source_id=source_id,
        event_type="data_source_disabled",
        event_level="warn",
        event_message=reason or "数据源已停用",
    )
    return {"success": True, "mode": "mock", "source": source, "message": "数据源已停用"}


def _mock_test_data_source(auth_token: str, source_id: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source = _mock_seed_data_sources(user_key).get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}

    source_kind = str(source.get("source_kind") or "")
    if source_kind in _AGENT_ASSISTED_SOURCE_KINDS:
        return {
            "success": True,
            "mode": "mock",
            "source_id": source_id,
            "result": {
                "status": "reserved",
                "execution_mode": "agent_assisted",
                "message": "该类型为预留能力，需由 agent loop 决策执行。",
            },
        }
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "result": {"status": "ok", "message": "连接测试通过（mock）"},
    }


def _mock_authorize_data_source(auth_token: str, source_id: str, return_path: str = "/") -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source = _mock_seed_data_sources(user_key).get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}
    if source.get("source_kind") != "platform_oauth":
        return {"success": False, "mode": "mock", "error": "not_supported", "message": "当前数据源无需授权"}

    session_id = str(uuid.uuid4())
    state = session_id
    _MOCK_DATA_SOURCE_AUTH_SESSIONS[state] = {
        "session_id": session_id,
        "user_key": user_key,
        "source_id": source_id,
        "return_path": return_path or "/",
    }
    auth_url = (
        f"/api/data-sources/auth/callback/{quote(source_id)}"
        f"?state={quote(state)}&code=mock_code_{session_id[:8]}"
    )
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "session_id": session_id,
        "state": state,
        "auth_url": auth_url,
        "expires_in": 600,
        "message": "已生成授权链接",
    }


def _mock_handle_data_source_callback(
    source_id: str,
    *,
    state: str,
    code: str = "",
    error: str = "",
    error_description: str = "",
) -> dict[str, Any]:
    if error:
        return {
            "success": False,
            "mode": "mock",
            "source_id": source_id,
            "error": error,
            "message": error_description or "授权失败，请重试",
            "return_path": "/",
        }

    session = _MOCK_DATA_SOURCE_AUTH_SESSIONS.get(state)
    if not session or str(session.get("source_id") or "") != source_id:
        return {
            "success": False,
            "mode": "mock",
            "source_id": source_id,
            "error": "invalid_state",
            "message": "授权会话已失效，请重新发起授权",
            "return_path": "/",
        }

    user_key = str(session.get("user_key") or "anonymous")
    source = _mock_seed_data_sources(user_key).get(source_id)
    if not source:
        return {
            "success": False,
            "mode": "mock",
            "source_id": source_id,
            "error": "not_found",
            "message": "数据源不存在",
            "return_path": str(session.get("return_path") or "/"),
        }

    source["auth_status"] = "authorized"
    source["enabled"] = True
    source["status"] = "active"
    source["updated_at"] = _now_iso()
    source["last_authorized_at"] = _now_iso()
    source["last_auth_code"] = code
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "message": "数据源授权成功",
        "return_path": str(session.get("return_path") or "/"),
        "source": source,
    }


def _mock_trigger_sync(
    auth_token: str,
    source_id: str,
    *,
    idempotency_key: str = "",
    window_start: str = "",
    window_end: str = "",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    source = source_map.get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}

    source_kind = str(source.get("source_kind") or "")
    if source_kind in _AGENT_ASSISTED_SOURCE_KINDS:
        return {
            "success": False,
            "mode": "mock",
            "error": "agent_assisted_only",
            "message": "该数据源为预留能力，需由 agent loop 决策执行。",
            "source_id": source_id,
        }

    jobs = _MOCK_SYNC_JOBS_BY_USER.setdefault(user_key, {})
    snapshots = _MOCK_PUBLISHED_SNAPSHOTS_BY_USER.setdefault(user_key, {})
    payload_params = dict(params or {})
    resolved_idempotency_key = str(idempotency_key or "").strip() or hashlib.sha1(
        json.dumps(
            {
                "source_id": source_id,
                "window_start": window_start or "",
                "window_end": window_end or "",
                "params": payload_params,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    existing_job = next(
        (
            item
            for item in jobs.values()
            if str(item.get("source_id") or "") == source_id
            and str(item.get("idempotency_key") or "") == resolved_idempotency_key
        ),
        None,
    )
    if existing_job:
        return {
            "success": True,
            "mode": "mock",
            "source_id": source_id,
            "job": existing_job,
            "reused": True,
            "published_snapshot": snapshots.get(source_id),
        }

    sync_job_id = f"sync_{uuid.uuid4()}"
    snapshot_id = f"snapshot_{uuid.uuid4()}"
    now = _now_iso()
    existing_snapshot = snapshots.get(source_id)
    version = int(existing_snapshot.get("version") or 0) + 1 if existing_snapshot else 1
    row_count = 120 + (abs(hash(source_id + now)) % 40)
    source_datasets = list(dataset_map.setdefault(source_id, {}).values())
    first_dataset = source_datasets[0] if source_datasets else None
    dataset_code = str((first_dataset or {}).get("dataset_code") or f"{source_kind}_dataset")

    snapshot = {
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "dataset_code": dataset_code,
        "status": "published",
        "version": version,
        "row_count": row_count,
        "published_at": now,
        "window_start": window_start or "",
        "window_end": window_end or "",
    }
    snapshots[source_id] = snapshot

    job = {
        "sync_job_id": sync_job_id,
        "source_id": source_id,
        "status": "success",
        "idempotency_key": resolved_idempotency_key,
        "window_start": window_start or "",
        "window_end": window_end or "",
        "params": payload_params,
        "started_at": now,
        "finished_at": now,
        "published_snapshot_id": snapshot_id,
    }
    jobs[sync_job_id] = job

    source["last_sync_at"] = now
    source["last_sync_job_id"] = sync_job_id
    source["published_snapshot_id"] = snapshot_id
    source["updated_at"] = now
    source["health_status"] = "healthy"
    if first_dataset:
        first_dataset["last_sync_at"] = now
        first_dataset["last_checked_at"] = now
        first_dataset["health_status"] = "healthy"
        first_dataset["last_error_message"] = ""
        first_dataset["updated_at"] = now
    _mock_emit_data_source_event(
        user_key,
        source_id=source_id,
        sync_job_id=sync_job_id,
        event_type="sync_completed",
        event_level="info",
        event_message="同步任务执行成功（mock）",
        event_payload={"snapshot_id": snapshot_id, "dataset_code": dataset_code},
    )
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "job": job,
        "published_snapshot": snapshot,
        "reused": False,
    }


def _mock_get_sync_job(auth_token: str, sync_job_id: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    job = _MOCK_SYNC_JOBS_BY_USER.setdefault(user_key, {}).get(sync_job_id)
    if not job:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "同步任务不存在"}
    return {"success": True, "mode": "mock", "job": job}


def _mock_list_sync_jobs(
    auth_token: str,
    *,
    source_id: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    jobs = list(_MOCK_SYNC_JOBS_BY_USER.setdefault(user_key, {}).values())
    if source_id:
        jobs = [job for job in jobs if str(job.get("source_id") or "") == source_id]
    jobs = sorted(jobs, key=lambda item: str(item.get("started_at") or ""), reverse=True)
    limited = jobs[: max(1, min(limit, 100))]
    return {"success": True, "mode": "mock", "count": len(limited), "jobs": limited}


def _mock_preview_data_source(auth_token: str, source_id: str, limit: int = 20) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source = _mock_seed_data_sources(user_key).get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}
    preview_limit = max(1, min(limit, 100))
    rows = [
        {
            "record_id": idx + 1,
            "source_id": source_id,
            "biz_key": f"{source_id[-6:]}_{idx + 1}",
            "amount": round(100 + idx * 1.23, 2),
            "event_time": _now_iso(),
        }
        for idx in range(preview_limit)
    ]
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "rows": rows,
        "count": len(rows),
    }


def _mock_get_published_snapshot(auth_token: str, source_id: str) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    snapshot = _MOCK_PUBLISHED_SNAPSHOTS_BY_USER.setdefault(user_key, {}).get(source_id)
    if not snapshot:
        return {
            "success": True,
            "mode": "mock",
            "source_id": source_id,
            "published_snapshot": None,
            "message": "暂无已发布快照",
        }
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "published_snapshot": snapshot,
    }


def _mock_discover_data_source_datasets(
    auth_token: str,
    source_id: str,
    *,
    persist: bool = True,
    discover_mode: str = "",
    openapi_url: str = "",
    openapi_spec: Any = None,
    manual_endpoints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source = _mock_seed_data_sources(user_key).get(source_id)
    if not source:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}

    source_kind = str(source.get("source_kind") or "")
    provider_code = str(source.get("provider_code") or "")
    discovered_rows = _mock_seed_source_dataset_rows(source)
    normalized_discover_mode = str(discover_mode or "").strip().lower()
    if source_kind == "api" and normalized_discover_mode == "openapi":
        if not openapi_url and not openapi_spec:
            return {
                "success": False,
                "mode": "mock",
                "error": "openapi_missing",
                "message": "请提供 OpenAPI 文档地址或文档内容",
            }
        extra_rows: list[dict[str, Any]] = []
        for idx, endpoint in enumerate(manual_endpoints or []):
            path = str((endpoint or {}).get("path") or "").strip()
            if not path:
                continue
            code = f"openapi_{idx + 1}"
            extra_rows.append(
                _mock_build_dataset(
                    source_id=source_id,
                    dataset_code=code,
                    dataset_name=f"OpenAPI {path}",
                    resource_key=path,
                    dataset_kind="api_endpoint",
                    origin_type="imported_openapi",
                    extract_config={
                        "endpoint": path,
                        "method": str((endpoint or {}).get("method") or "GET").upper(),
                    },
                    schema_summary={"fields": []},
                    sync_strategy={"mode": "manual"},
                    meta={"from_openapi": True},
                )
            )
        if extra_rows:
            discovered_rows.extend(extra_rows)

    datasets = discovered_rows
    persisted_count = 0
    if persist:
        dataset_map, _ = _mock_ensure_data_source_context(user_key)
        source_dataset_map = dataset_map.setdefault(source_id, {})
        for row in discovered_rows:
            row = dict(row)
            row["updated_at"] = _now_iso()
            source_dataset_map[str(row["id"])] = row
            persisted_count += 1
        datasets = list(source_dataset_map.values())

    _mock_emit_data_source_event(
        user_key,
        source_id=source_id,
        event_type="datasets_discovered",
        event_level="info",
        event_message=f"发现 {len(discovered_rows)} 个数据集（mock）",
        event_payload={"persist": persist, "discover_mode": normalized_discover_mode or "auto"},
    )
    return {
        "success": True,
        "mode": "mock",
        "source_id": source_id,
        "provider_code": provider_code,
        "datasets": datasets,
        "dataset_count": len(datasets),
        "persist": persist,
        "persisted_count": persisted_count,
        "message": f"发现 {len(discovered_rows)} 个数据集",
    }


def _mock_list_data_source_datasets(
    auth_token: str,
    *,
    source_id: str = "",
    status: str = "",
    include_deleted: bool = False,
    limit: int = 500,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    normalized_status = str(status or "").strip().lower()

    if source_id and source_id not in source_map:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}

    all_rows: list[dict[str, Any]] = []
    source_ids = [source_id] if source_id else list(dataset_map.keys())
    for sid in source_ids:
        rows = list(dataset_map.get(sid, {}).values())
        all_rows.extend(rows)

    if normalized_status:
        all_rows = [row for row in all_rows if str(row.get("status") or "").lower() == normalized_status]
    if not include_deleted:
        all_rows = [row for row in all_rows if str(row.get("status") or "").lower() != "deleted"]

    limited = all_rows[: max(1, min(limit, 2000))]
    return {
        "success": True,
        "mode": "mock",
        "count": len(limited),
        "datasets": limited,
    }


def _mock_get_data_source_dataset(
    auth_token: str,
    *,
    dataset_id: str = "",
    source_id: str = "",
    dataset_code: str = "",
    resource_key: str = "",
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    target: dict[str, Any] | None = None

    if dataset_id:
        for rows in dataset_map.values():
            if dataset_id in rows:
                target = rows[dataset_id]
                break
    else:
        if not source_id:
            return {"success": False, "mode": "mock", "error": "bad_request", "message": "缺少 dataset_id 或 source_id"}
        rows = list(dataset_map.get(source_id, {}).values())
        if dataset_code:
            target = next((item for item in rows if str(item.get("dataset_code") or "") == dataset_code), None)
        elif resource_key:
            target = next((item for item in rows if str(item.get("resource_key") or "") == resource_key), None)

    if not target:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据集不存在"}

    target_source_id = str(target.get("data_source_id") or "")
    source = source_map.get(target_source_id, {})
    return {
        "success": True,
        "mode": "mock",
        "dataset": target,
        "source_summary": {
            "id": target_source_id,
            "name": source.get("name") or "",
            "source_kind": source.get("source_kind") or "",
            "provider_code": source.get("provider_code") or "",
            "health_status": source.get("health_status") or "unknown",
        },
        "health_summary": {
            "source_health_status": source.get("health_status") or "unknown",
            "dataset_health_status": target.get("health_status") or "unknown",
        },
    }


def _mock_upsert_data_source_dataset(
    auth_token: str,
    source_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    if source_id not in source_map:
        return {"success": False, "mode": "mock", "error": "not_found", "message": "数据源不存在"}

    dataset_code = str(payload.get("dataset_code") or "").strip()
    if not dataset_code:
        return {"success": False, "mode": "mock", "error": "bad_request", "message": "dataset_code 不能为空"}

    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    source_dataset_map = dataset_map.setdefault(source_id, {})
    existing = next(
        (
            row for row in source_dataset_map.values()
            if str(row.get("dataset_code") or "") == dataset_code
        ),
        None,
    )
    now = _now_iso()
    if existing:
        row = dict(existing)
        row.update(payload)
        row["updated_at"] = now
    else:
        row = _mock_build_dataset(
            source_id=source_id,
            dataset_code=dataset_code,
            dataset_name=str(payload.get("dataset_name") or dataset_code),
            resource_key=str(payload.get("resource_key") or dataset_code),
            dataset_kind=str(payload.get("dataset_kind") or "table"),
            origin_type=str(payload.get("origin_type") or "manual"),
            extract_config=dict(payload.get("extract_config") or {}),
            schema_summary=dict(payload.get("schema_summary") or {}),
            sync_strategy=dict(payload.get("sync_strategy") or {}),
            status=str(payload.get("status") or "active"),
            enabled=bool(payload.get("enabled", True)),
            health_status=str(payload.get("health_status") or "unknown"),
            meta=dict(payload.get("meta") or {}),
        )
        row["created_at"] = now
        row["updated_at"] = now
    source_dataset_map[str(row["id"])] = row

    _mock_emit_data_source_event(
        user_key,
        source_id=source_id,
        event_type="dataset_upserted",
        event_level="info",
        event_message=f"数据集 {row.get('dataset_name') or dataset_code} 已更新（mock）",
        event_payload={"dataset_id": row.get("id"), "dataset_code": dataset_code},
    )
    source = source_map[source_id]
    return {
        "success": True,
        "mode": "mock",
        "dataset": row,
        "source_summary": {
            "id": source_id,
            "name": source.get("name") or "",
            "source_kind": source.get("source_kind") or "",
            "provider_code": source.get("provider_code") or "",
        },
        "message": "数据集已更新",
    }


def _mock_disable_data_source_dataset(
    auth_token: str,
    dataset_id: str,
    *,
    reason: str = "",
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    dataset_map, _ = _mock_ensure_data_source_context(user_key)
    for source_id, source_dataset_map in dataset_map.items():
        row = source_dataset_map.get(dataset_id)
        if not row:
            continue
        row["status"] = "disabled"
        row["enabled"] = False
        row["health_status"] = "disabled"
        row["last_error_message"] = reason or "数据集已停用"
        row["updated_at"] = _now_iso()
        _mock_emit_data_source_event(
            user_key,
            source_id=source_id,
            event_type="dataset_disabled",
            event_level="warn",
            event_message=row["last_error_message"],
            event_payload={"dataset_id": dataset_id},
        )
        return {"success": True, "mode": "mock", "dataset": row, "message": "数据集已停用"}
    return {"success": False, "mode": "mock", "error": "not_found", "message": "数据集不存在"}


def _mock_list_data_source_events(
    auth_token: str,
    *,
    source_id: str = "",
    sync_job_id: str = "",
    event_level: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    _mock_ensure_data_source_context(user_key)
    events = list(_MOCK_DATA_SOURCE_EVENTS_BY_USER.setdefault(user_key, []))

    if source_id:
        events = [event for event in events if str(event.get("data_source_id") or "") == source_id]
    if sync_job_id:
        events = [event for event in events if str(event.get("sync_job_id") or "") == sync_job_id]
    if event_level:
        expected_level = str(event_level).strip().lower()
        events = [event for event in events if str(event.get("event_level") or "").lower() == expected_level]

    events = sorted(events, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    limited = events[: max(1, min(limit, 1000))]
    return {
        "success": True,
        "mode": "mock",
        "count": len(limited),
        "events": limited,
    }


def _mock_preflight_rule_binding(
    auth_token: str,
    *,
    binding_scope: str,
    binding_code: str,
    stale_after_minutes: int = 24 * 60,
) -> dict[str, Any]:
    user_key = _auth_user_key(auth_token)
    source_map = _mock_seed_data_sources(user_key)
    _mock_ensure_data_source_context(user_key)
    issues: list[dict[str, Any]] = []
    normalized_scope = str(binding_scope or "").strip().lower()
    normalized_code = str(binding_code or "").strip()
    now = datetime.now(timezone.utc)

    def append_issue(code: str, level: str, message: str) -> None:
        issues.append(
            {
                "code": code,
                "level": level,
                "message": message,
                "binding_scope": normalized_scope,
                "binding_code": normalized_code,
            }
        )

    if not normalized_scope or normalized_scope not in {"proc", "recon"}:
        append_issue("binding_scope_invalid", "error", "任务类型无效，无法执行数据预检")
    if not normalized_code:
        append_issue("binding_code_missing", "error", "规则编码为空，无法执行数据预检")

    sample_source = next(iter(source_map.values()), None)
    if not sample_source:
        append_issue("source_missing", "error", "当前账号下未找到可用数据源")
    else:
        source_id = str(sample_source.get("id") or "")
        datasets = _mock_collect_source_datasets(user_key, source_id)
        if not datasets:
            append_issue("dataset_missing", "error", "当前规则未绑定可用数据集")
        else:
            first_dataset = datasets[0]
            sync_time = first_dataset.get("last_sync_at")
            if isinstance(sync_time, str) and sync_time:
                try:
                    sync_dt = datetime.fromisoformat(sync_time.replace("Z", "+00:00"))
                    if sync_dt.tzinfo is None:
                        sync_dt = sync_dt.replace(tzinfo=timezone.utc)
                    stale_threshold = now.timestamp() - max(1, stale_after_minutes) * 60
                    if sync_dt.timestamp() < stale_threshold:
                        append_issue(
                            "dataset_stale",
                            "warn",
                            f"数据集 {first_dataset.get('dataset_name') or first_dataset.get('dataset_code')} 最近快照时间过旧",
                        )
                except Exception:
                    append_issue("dataset_sync_time_invalid", "warn", "数据集最近同步时间格式无效")

    blocking = [item for item in issues if str(item.get("level") or "") == "error"]
    summary = {
        "issue_count": len(issues),
        "blocking_issue_count": len(blocking),
        "requirement_count": 0,
        "issue_level_count": {
            "error": len(blocking),
            "warn": len([item for item in issues if str(item.get("level") or "") == "warn"]),
        },
        "issue_code_count": {
            str(item.get("code") or "unknown"): len(
                [issue for issue in issues if str(issue.get("code") or "unknown") == str(item.get("code") or "unknown")]
            )
            for item in issues
        },
    }
    return {
        "success": True,
        "mode": "mock",
        "ready": len(blocking) == 0,
        "binding_scope": normalized_scope,
        "binding_code": normalized_code,
        "summary": summary,
        "preflight": {
            "ready": len(blocking) == 0,
            "issue_count": len(issues),
            "blocking_issue_count": len(blocking),
            "issues": issues,
            "requirements": [],
        },
    }


async def data_source_list(
    auth_token: str,
    *,
    mode: str = "",
    source_kind: str = "",
    domain_type: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_list_data_sources(auth_token, source_kind=source_kind, domain_type=domain_type)

    args: dict[str, Any] = {"auth_token": auth_token, "mode": normalized_mode}
    if source_kind:
        args["source_kind"] = source_kind
    if domain_type:
        args["domain_type"] = domain_type
    result = await call_mcp_tool("data_source_list", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_list_data_sources(auth_token, source_kind=source_kind, domain_type=domain_type)
    return result


async def data_source_get(
    auth_token: str,
    source_id: str,
    *,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_get_data_source(auth_token, source_id)

    result = await call_mcp_tool(
        "data_source_get",
        {"auth_token": auth_token, "source_id": source_id, "mode": normalized_mode},
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_get_data_source(auth_token, source_id)
    return result


async def data_source_create(
    auth_token: str,
    payload: dict[str, Any],
    *,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_create_data_source(auth_token, payload)

    result = await call_mcp_tool(
        "data_source_create",
        {"auth_token": auth_token, "mode": normalized_mode, **payload},
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_create_data_source(auth_token, payload)
    return result


async def data_source_update(
    auth_token: str,
    source_id: str,
    payload: dict[str, Any],
    *,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_update_data_source(auth_token, source_id, payload)

    result = await call_mcp_tool(
        "data_source_update",
        {
            "auth_token": auth_token,
            "source_id": source_id,
            "mode": normalized_mode,
            **payload,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_update_data_source(auth_token, source_id, payload)
    return result


async def data_source_disable(
    auth_token: str,
    source_id: str,
    *,
    reason: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_disable_data_source(auth_token, source_id, reason=reason)

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "source_id": source_id,
        "mode": normalized_mode,
    }
    if reason:
        args["reason"] = reason
    result = await call_mcp_tool("data_source_disable", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_disable_data_source(auth_token, source_id, reason=reason)
    return result


async def data_source_test(
    auth_token: str,
    source_id: str,
    *,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_test_data_source(auth_token, source_id)

    result = await call_mcp_tool(
        "data_source_test",
        {"auth_token": auth_token, "source_id": source_id, "mode": normalized_mode},
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_test_data_source(auth_token, source_id)
    return result


async def data_source_authorize(
    auth_token: str,
    source_id: str,
    *,
    return_path: str = "/",
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_authorize_data_source(auth_token, source_id, return_path=return_path)

    result = await call_mcp_tool(
        "data_source_authorize",
        {
            "auth_token": auth_token,
            "source_id": source_id,
            "return_path": return_path,
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_authorize_data_source(auth_token, source_id, return_path=return_path)
    return result


async def data_source_handle_callback(
    source_id: str,
    *,
    state: str = "",
    code: str = "",
    error: str = "",
    error_description: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_handle_data_source_callback(
            source_id,
            state=state,
            code=code,
            error=error,
            error_description=error_description,
        )

    result = await call_mcp_tool(
        "data_source_handle_callback",
        {
            "source_id": source_id,
            "state": state,
            "code": code,
            "error": error,
            "error_description": error_description,
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_handle_data_source_callback(
            source_id,
            state=state,
            code=code,
            error=error,
            error_description=error_description,
        )
    return result


async def data_source_trigger_sync(
    auth_token: str,
    source_id: str,
    *,
    idempotency_key: str = "",
    window_start: str = "",
    window_end: str = "",
    params: dict[str, Any] | None = None,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_trigger_sync(
            auth_token,
            source_id,
            idempotency_key=idempotency_key,
            window_start=window_start,
            window_end=window_end,
            params=params,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "source_id": source_id,
        "mode": normalized_mode,
    }
    if idempotency_key:
        args["idempotency_key"] = idempotency_key
    if window_start:
        args["window_start"] = window_start
    if window_end:
        args["window_end"] = window_end
    if params:
        args["params"] = params
    result = await call_mcp_tool("data_source_trigger_sync", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_trigger_sync(
            auth_token,
            source_id,
            idempotency_key=idempotency_key,
            window_start=window_start,
            window_end=window_end,
            params=params,
        )
    return result


async def data_source_get_sync_job(
    auth_token: str,
    sync_job_id: str,
    *,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not sync_job_id:
        return {"success": False, "error": "sync_job_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_get_sync_job(auth_token, sync_job_id)

    result = await call_mcp_tool(
        "data_source_get_sync_job",
        {"auth_token": auth_token, "sync_job_id": sync_job_id, "mode": normalized_mode},
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_get_sync_job(auth_token, sync_job_id)
    return result


async def data_source_list_sync_jobs(
    auth_token: str,
    *,
    source_id: str = "",
    limit: int = 20,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_list_sync_jobs(auth_token, source_id=source_id, limit=limit)

    args: dict[str, Any] = {"auth_token": auth_token, "limit": max(1, min(limit, 100)), "mode": normalized_mode}
    if source_id:
        args["source_id"] = source_id
    result = await call_mcp_tool("data_source_list_sync_jobs", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_list_sync_jobs(auth_token, source_id=source_id, limit=limit)
    return result


async def data_source_preview(
    auth_token: str,
    source_id: str,
    *,
    limit: int = 20,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_preview_data_source(auth_token, source_id, limit=limit)

    result = await call_mcp_tool(
        "data_source_preview",
        {
            "auth_token": auth_token,
            "source_id": source_id,
            "limit": max(1, min(limit, 100)),
            "mode": normalized_mode,
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_preview_data_source(auth_token, source_id, limit=limit)
    return result


async def data_source_get_published_snapshot(
    auth_token: str,
    source_id: str,
    *,
    mode: str = "",
    resource_key: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_get_published_snapshot(auth_token, source_id)

    result = await call_mcp_tool(
        "data_source_get_published_snapshot",
        {
            "auth_token": auth_token,
            "source_id": source_id,
            "mode": normalized_mode,
            **({"resource_key": resource_key} if resource_key else {}),
        },
    )
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_get_published_snapshot(auth_token, source_id)
    return result


async def data_source_discover_datasets(
    auth_token: str,
    source_id: str,
    *,
    persist: bool = True,
    limit: int = 500,
    schema_whitelist: list[str] | None = None,
    discover_mode: str = "",
    openapi_url: str = "",
    openapi_spec: Any = None,
    manual_endpoints: list[dict[str, Any]] | None = None,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_discover_data_source_datasets(
            auth_token,
            source_id,
            persist=persist,
            discover_mode=discover_mode,
            openapi_url=openapi_url,
            openapi_spec=openapi_spec,
            manual_endpoints=manual_endpoints,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "source_id": source_id,
        "persist": bool(persist),
        "limit": max(1, min(limit, 2000)),
        "mode": normalized_mode,
    }
    if schema_whitelist:
        args["schema_whitelist"] = [str(item).strip() for item in schema_whitelist if str(item).strip()]
    if discover_mode:
        args["discover_mode"] = discover_mode
    if openapi_url:
        args["openapi_url"] = openapi_url
    if openapi_spec is not None:
        args["openapi_spec"] = openapi_spec
    if manual_endpoints:
        args["manual_endpoints"] = manual_endpoints

    result = await call_mcp_tool("data_source_discover_datasets", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_discover_data_source_datasets(
            auth_token,
            source_id,
            persist=persist,
            discover_mode=discover_mode,
            openapi_url=openapi_url,
            openapi_spec=openapi_spec,
            manual_endpoints=manual_endpoints,
        )
    return result


async def data_source_list_datasets(
    auth_token: str,
    *,
    source_id: str = "",
    status: str = "",
    include_deleted: bool = False,
    limit: int = 500,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_list_data_source_datasets(
            auth_token,
            source_id=source_id,
            status=status,
            include_deleted=include_deleted,
            limit=limit,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "include_deleted": bool(include_deleted),
        "limit": max(1, min(limit, 2000)),
        "mode": normalized_mode,
    }
    if source_id:
        args["source_id"] = source_id
    if status:
        args["status"] = status
    result = await call_mcp_tool("data_source_list_datasets", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_list_data_source_datasets(
            auth_token,
            source_id=source_id,
            status=status,
            include_deleted=include_deleted,
            limit=limit,
        )
    return result


async def data_source_get_dataset(
    auth_token: str,
    *,
    dataset_id: str = "",
    source_id: str = "",
    dataset_code: str = "",
    resource_key: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not dataset_id and not source_id:
        return {"success": False, "error": "dataset_id 或 source_id 至少提供一个"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_get_data_source_dataset(
            auth_token,
            dataset_id=dataset_id,
            source_id=source_id,
            dataset_code=dataset_code,
            resource_key=resource_key,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "mode": normalized_mode,
    }
    if dataset_id:
        args["dataset_id"] = dataset_id
    if source_id:
        args["source_id"] = source_id
    if dataset_code:
        args["dataset_code"] = dataset_code
    if resource_key:
        args["resource_key"] = resource_key
    result = await call_mcp_tool("data_source_get_dataset", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_get_data_source_dataset(
            auth_token,
            dataset_id=dataset_id,
            source_id=source_id,
            dataset_code=dataset_code,
            resource_key=resource_key,
        )
    return result


async def data_source_upsert_dataset(
    auth_token: str,
    source_id: str,
    payload: dict[str, Any],
    *,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_upsert_data_source_dataset(auth_token, source_id, payload)

    args: dict[str, Any] = {"auth_token": auth_token, "source_id": source_id, "mode": normalized_mode}
    args.update(payload or {})
    result = await call_mcp_tool("data_source_upsert_dataset", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_upsert_data_source_dataset(auth_token, source_id, payload)
    return result


async def data_source_disable_dataset(
    auth_token: str,
    dataset_id: str,
    *,
    reason: str = "",
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not dataset_id:
        return {"success": False, "error": "dataset_id 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_disable_data_source_dataset(auth_token, dataset_id, reason=reason)

    args: dict[str, Any] = {"auth_token": auth_token, "dataset_id": dataset_id, "mode": normalized_mode}
    if reason:
        args["reason"] = reason
    result = await call_mcp_tool("data_source_disable_dataset", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_disable_data_source_dataset(auth_token, dataset_id, reason=reason)
    return result


async def data_source_import_openapi(
    auth_token: str,
    source_id: str,
    *,
    openapi_url: str = "",
    openapi_spec: Any = None,
    persist: bool = True,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not source_id:
        return {"success": False, "error": "source_id 不能为空"}
    if not openapi_url and openapi_spec is None:
        return {"success": False, "error": "请提供 OpenAPI 文档地址或文档内容"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_discover_data_source_datasets(
            auth_token,
            source_id,
            persist=persist,
            discover_mode="openapi",
            openapi_url=openapi_url,
            openapi_spec=openapi_spec,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "source_id": source_id,
        "persist": bool(persist),
        "mode": normalized_mode,
    }
    if openapi_url:
        args["openapi_url"] = openapi_url
    if openapi_spec is not None:
        args["openapi_spec"] = openapi_spec
    result = await call_mcp_tool("data_source_import_openapi", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_discover_data_source_datasets(
            auth_token,
            source_id,
            persist=persist,
            discover_mode="openapi",
            openapi_url=openapi_url,
            openapi_spec=openapi_spec,
        )
    return result


async def data_source_list_events(
    auth_token: str,
    *,
    source_id: str = "",
    sync_job_id: str = "",
    event_level: str = "",
    limit: int = 200,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_list_data_source_events(
            auth_token,
            source_id=source_id,
            sync_job_id=sync_job_id,
            event_level=event_level,
            limit=limit,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "limit": max(1, min(limit, 1000)),
        "mode": normalized_mode,
    }
    if source_id:
        args["source_id"] = source_id
    if sync_job_id:
        args["sync_job_id"] = sync_job_id
    if event_level:
        args["event_level"] = event_level
    result = await call_mcp_tool("data_source_list_events", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return _mock_list_data_source_events(
            auth_token,
            source_id=source_id,
            sync_job_id=sync_job_id,
            event_level=event_level,
            limit=limit,
        )
    return result


async def data_source_preflight_rule_binding(
    auth_token: str,
    *,
    binding_scope: str,
    binding_code: str,
    stale_after_minutes: int = 24 * 60,
    mode: str = "",
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not binding_scope:
        return {"success": False, "error": "binding_scope 不能为空"}
    if not binding_code:
        return {"success": False, "error": "binding_code 不能为空"}

    normalized_mode = _normalize_mode(mode)
    if normalized_mode == "mock":
        return _mock_preflight_rule_binding(
            auth_token,
            binding_scope=binding_scope,
            binding_code=binding_code,
            stale_after_minutes=stale_after_minutes,
        )

    args: dict[str, Any] = {
        "auth_token": auth_token,
        "binding_scope": binding_scope,
        "binding_code": binding_code,
        "stale_after_minutes": max(1, min(stale_after_minutes, 30 * 24 * 60)),
        "mode": normalized_mode,
    }
    result = await call_mcp_tool("data_source_preflight_rule_binding", args)
    if not result.get("success") and _is_unknown_tool_error(result.get("error")):
        return {
            "success": False,
            "error": "任务前检查能力暂不可用，请联系管理员检查数据连接服务",
        }
    return result

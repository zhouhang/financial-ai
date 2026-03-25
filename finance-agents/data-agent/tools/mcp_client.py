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
import json
import logging
import re
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

from config import FINANCE_MCP_BASE_URL

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_RESULT_WAIT_TIMEOUT = 60.0  # 等待 SSE 结果超时秒数

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
                jsonrpc_resp = await asyncio.wait_for(fut, timeout=_RESULT_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                self._pending.pop(req_id, None)
                logger.error(f"等待 MCP 响应超时: tool={tool_name}")
                return {"success": False, "error": "等待 MCP 响应超时"}

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

"""Minimal MCP SSE session client for browser-agent.

Mirrors the SSE handshake/dispatch logic in
``finance-agents/data-agent/tools/mcp_client.py``. Kept self-contained inside the browser-agent
package so the collection machine deployment does not pull in the data-agent project.

Lifecycle:
  1. ``connect()`` opens GET /sse, reads the ``endpoint`` event for ``session_id``, performs the
     MCP initialize handshake, and starts a background task reading further SSE events.
  2. ``call_tool(name, args)`` posts a ``tools/call`` JSON-RPC request, awaits the matching
     response via a per-request ``asyncio.Future`` keyed on request_id, and returns the parsed
     result.
  3. The background SSE listener routes incoming JSON-RPC responses to the right Future and
     fails all pending Futures with ``RuntimeError`` when the connection drops.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import suppress
from typing import Any
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_SSE_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=None)
_RESULT_WAIT_TIMEOUT = 180.0


class McpSession:
    """One MCP SSE session bound to a single finance-mcp base URL."""

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._req_counter = 0
        self._sse_task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._connect_lock = asyncio.Lock()

    def _next_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self._sse_task and not self._sse_task.done():
                return self.session_id is not None
            try:
                logger.info("建立 MCP SSE 长连接: %s", self.base_url)
                self._client = httpx.AsyncClient(timeout=_SSE_TIMEOUT)
                session_ready = asyncio.get_running_loop().create_future()
                self._sse_task = asyncio.create_task(self._sse_listener(session_ready))
                await asyncio.wait_for(session_ready, timeout=15.0)
                if not self.session_id:
                    await self._close_failed_connection()
                    return False
                await self._handshake()
                return True
            except asyncio.TimeoutError:
                logger.error("等待 SSE session_id 超时")
                await self._close_failed_connection()
                return False
            except Exception as e:
                logger.error("SSE 连接失败: %s", e, exc_info=True)
                await self._close_failed_connection()
                return False

    async def _close_failed_connection(self) -> None:
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

    async def _handshake(self) -> None:
        init_id = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[init_id] = fut
        init_body = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "browser-agent", "version": "1.0"},
            },
        }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            r = await c.post(
                f"{self.base_url}/messages/?session_id={self.session_id}",
                json=init_body,
            )
        if r.status_code not in (200, 202):
            self._pending.pop(init_id, None)
            raise RuntimeError(f"initialize 失败: {r.status_code} {r.text}")
        try:
            await asyncio.wait_for(fut, timeout=10.0)
        except asyncio.TimeoutError:
            self._pending.pop(init_id, None)
            raise RuntimeError("initialize 响应超时")
        notif_body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as c:
            await c.post(
                f"{self.base_url}/messages/?session_id={self.session_id}",
                json=notif_body,
            )

    async def _sse_listener(self, session_ready: asyncio.Future) -> None:
        try:
            assert self._client is not None
            async with self._client.stream("GET", f"{self.base_url}/sse") as resp:
                if resp.status_code != 200:
                    logger.error("SSE 连接失败: %s", resp.status_code)
                    if not session_ready.done():
                        session_ready.set_result(None)
                    return
                event_type: str | None = None
                data_lines: list[str] = []
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                        continue
                    if line == "":
                        data_str = "\n".join(data_lines)
                        data_lines = []
                        if event_type == "endpoint":
                            decoded = unquote(data_str)
                            m = re.search(r"session_id=([^&\s]+)", decoded)
                            if m:
                                self.session_id = m.group(1)
                                if not session_ready.done():
                                    session_ready.set_result(self.session_id)
                        elif event_type == "message" and data_str:
                            try:
                                msg = json.loads(data_str)
                                req_id = msg.get("id")
                                if req_id is not None and req_id in self._pending:
                                    fut = self._pending.pop(req_id)
                                    if not fut.done():
                                        fut.set_result(msg)
                            except Exception as e:
                                logger.error("解析 SSE 消息失败: %s", e)
                        event_type = None
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("SSE 监听异常: %s", e, exc_info=True)
        finally:
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
        if not self.session_id or (self._sse_task and self._sse_task.done()):
            if not await self.connect():
                return {"success": False, "error": "无法建立 MCP SSE 连接"}
        req_id = self._next_id()
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        request_body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as post_client:
                resp = await post_client.post(
                    f"{self.base_url}/messages/?session_id={self.session_id}",
                    json=request_body,
                )
            if resp.status_code not in (200, 202):
                self._pending.pop(req_id, None)
                logger.error("MCP 投递失败: %s %s", resp.status_code, resp.text[:200])
                if resp.status_code in (400, 404):
                    self.session_id = None
                    if self._sse_task:
                        self._sse_task.cancel()
                return {"success": False, "error": f"MCP 投递失败: {resp.status_code}"}
            try:
                jsonrpc_resp = await asyncio.wait_for(fut, timeout=_RESULT_WAIT_TIMEOUT)
            except asyncio.TimeoutError:
                self._pending.pop(req_id, None)
                return {"success": False, "error": "等待 MCP 响应超时"}
            if "error" in jsonrpc_resp:
                err = jsonrpc_resp["error"]
                return {"success": False, "error": err.get("message", str(err))}
            result = jsonrpc_resp.get("result", {})
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and content:
                    text = content[0].get("text", "")
                    if result.get("isError"):
                        return {"success": False, "error": text}
                    try:
                        return json.loads(text)
                    except Exception:
                        return {"success": True, "result": text}
            return result
        except Exception as e:
            self._pending.pop(req_id, None)
            logger.error("MCP 调用异常: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}

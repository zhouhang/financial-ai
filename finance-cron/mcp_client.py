from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import suppress
from typing import Any
from urllib.parse import unquote

import httpx

logger = logging.getLogger(__name__)
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _finance_mcp_base_url() -> str:
    # 使用 127.0.0.1 避免本机代理/安全软件拦截 localhost 导致的 502。
    return os.getenv("FINANCE_MCP_BASE_URL", "http://127.0.0.1:3335").rstrip("/")


class _McpSession:
    def __init__(self) -> None:
        self.session_id: str | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._req_counter = 0
        self._sse_task: asyncio.Task[Any] | None = None
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
                self._client = httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False)
                session_ready = asyncio.get_running_loop().create_future()
                self._sse_task = asyncio.create_task(self._sse_listener(session_ready))
                await asyncio.wait_for(session_ready, timeout=15.0)
                if not self.session_id:
                    await self._close_failed_connection()
                    return False
                await self._handshake()
                return True
            except Exception:
                await self._close_failed_connection()
                return False

    async def aclose(self) -> None:
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

    async def _close_failed_connection(self) -> None:
        await self.aclose()

    async def _handshake(self) -> None:
        init_id = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[init_id] = fut

        init_body = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "finance-cron", "version": "1.0"},
            },
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
            response = await client.post(
                f"{_finance_mcp_base_url()}/messages/?session_id={self.session_id}",
                json=init_body,
            )
        if response.status_code not in (200, 202):
            self._pending.pop(init_id, None)
            raise RuntimeError(f"initialize 失败: {response.status_code} {response.text}")

        await asyncio.wait_for(fut, timeout=10.0)

        async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
            await client.post(
                f"{_finance_mcp_base_url()}/messages/?session_id={self.session_id}",
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )

    async def _sse_listener(self, session_ready: asyncio.Future[Any]) -> None:
        try:
            assert self._client is not None
            async with self._client.stream("GET", f"{_finance_mcp_base_url()}/sse") as response:
                if response.status_code != 200:
                    if not session_ready.done():
                        session_ready.set_result(None)
                    return

                event_type: str | None = None
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                        continue
                    if line != "":
                        continue

                    data_str = "\n".join(data_lines)
                    data_lines = []

                    if event_type == "endpoint":
                        decoded = unquote(data_str)
                        matched = re.search(r"session_id=([^&\\s]+)", decoded)
                        if matched:
                            self.session_id = matched.group(1)
                            if not session_ready.done():
                                session_ready.set_result(self.session_id)
                    elif event_type == "message" and data_str:
                        try:
                            message = json.loads(data_str)
                            req_id = message.get("id")
                            if req_id is not None and req_id in self._pending:
                                fut = self._pending.pop(req_id)
                                if not fut.done():
                                    fut.set_result(message)
                        except Exception as exc:  # noqa: BLE001
                            logger.error("解析 MCP SSE 消息失败: %s", exc)

                    event_type = None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("MCP SSE 监听异常: %s", exc, exc_info=True)
        finally:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("MCP SSE 连接已断开"))
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
            ok = await self.connect()
            if not ok:
                return {"success": False, "error": "无法建立 finance-mcp 连接"}

        req_id = self._next_id()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
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
            async with httpx.AsyncClient(timeout=_TIMEOUT, trust_env=False) as client:
                response = await client.post(
                    f"{_finance_mcp_base_url()}/messages/?session_id={self.session_id}",
                    json=request_body,
                )
            if response.status_code not in (200, 202):
                self._pending.pop(req_id, None)
                return {"success": False, "error": f"MCP 投递失败: {response.status_code}"}

            jsonrpc_resp = await asyncio.wait_for(fut, timeout=60.0)
            if "error" in jsonrpc_resp:
                error = jsonrpc_resp["error"]
                return {"success": False, "error": error.get("message", str(error))}

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
        except Exception as exc:  # noqa: BLE001
            self._pending.pop(req_id, None)
            return {"success": False, "error": str(exc)}


_mcp_session = _McpSession()


async def call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return await _mcp_session.call_tool(tool_name, arguments)


async def aclose_mcp_session() -> None:
    await _mcp_session.aclose()


async def execution_scheduler_list_run_plans(
    auth_token: str,
    *,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    return await call_mcp_tool(
        "execution_scheduler_list_run_plans",
        {"auth_token": auth_token, "limit": limit, "offset": offset},
    )


async def execution_scheduler_get_slot_run(
    auth_token: str,
    *,
    company_id: str,
    plan_code: str,
    schedule_slot: str,
) -> dict[str, Any]:
    return await call_mcp_tool(
        "execution_scheduler_get_slot_run",
        {
            "auth_token": auth_token,
            "company_id": company_id,
            "plan_code": plan_code,
            "schedule_slot": schedule_slot,
        },
    )


async def data_source_scheduler_list_collection_plans(
    auth_token: str,
    *,
    company_id: str = "",
    limit: int = 500,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"auth_token": auth_token, "limit": limit}
    if company_id:
        payload["company_id"] = company_id
    return await call_mcp_tool("data_source_scheduler_list_collection_plans", payload)


async def data_source_trigger_dataset_collection(
    auth_token: str,
    *,
    source_id: str,
    dataset_id: str,
    resource_key: str,
    biz_date: str,
    trigger_mode: str = "schedule",
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "auth_token": auth_token,
        "source_id": source_id,
        "dataset_id": dataset_id,
        "resource_key": resource_key,
        "biz_date": biz_date,
        "trigger_mode": trigger_mode,
    }
    if params:
        payload["params"] = params
    return await call_mcp_tool("data_source_trigger_dataset_collection", payload)

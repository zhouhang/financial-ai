"""Browser-agent → data-agent WebSocket 传输。

单条主动出站 WS:connect 时发 hello 帧(system JWT + agent_id)鉴权;之后发"领域消息"
(客户端生成 id),等待匹配的 result 帧。后台 reader 解析响应并兑现挂起的 future,event 帧
本轮忽略(handoff 用)。断线时挂起请求以异常结束,下次 request 自动重连。
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable

import websockets

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 120.0
_CONNECT_TIMEOUT = 10.0


async def _default_connector(url: str):
    return await websockets.connect(url, max_size=None)


class DataAgentWsClient:
    def __init__(
        self,
        *,
        ws_url: str,
        agent_id: str,
        max_concurrency: int,
        token_provider: Callable[[], str],
        connector: Callable[[str], Awaitable[Any]] = _default_connector,
    ) -> None:
        self._ws_url = ws_url
        self._agent_id = agent_id
        self._max_concurrency = max_concurrency
        self._token_provider = token_provider
        self._connector = connector
        self._ws: Any = None
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self._ws is not None and self._reader_task and not self._reader_task.done():
                return True
            try:
                self._ws = await asyncio.wait_for(self._connector(self._ws_url), timeout=_CONNECT_TIMEOUT)
                await self._ws.send(json.dumps({
                    "type": "hello",
                    "token": self._token_provider(),
                    "agent_id": self._agent_id,
                    "max_concurrency": self._max_concurrency,
                }))
                ack = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=_CONNECT_TIMEOUT))
                if ack.get("type") != "hello_ack" or not ack.get("ok"):
                    logger.error("data-agent WS 鉴权失败: %s", ack)
                    await self._close()
                    return False
                self._reader_task = asyncio.create_task(self._reader())
                logger.info("data-agent WS 已连接: %s", self._ws_url)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.error("data-agent WS 连接失败: %s", exc)
                await self._close()
                return False

    async def _close(self) -> None:
        ws, self._ws = self._ws, None
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        self._reader_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("data-agent WS 已断开"))
        self._pending.clear()
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

    async def _reader(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("type") == "result":
                    fut = self._pending.pop(str(msg.get("id") or ""), None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                # 其它类型(event)本轮忽略
        except Exception as exc:  # noqa: BLE001
            logger.warning("data-agent WS 读取中断: %s", exc)
        finally:
            await self._close()

    async def request(self, msg_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._ws is None or (self._reader_task and self._reader_task.done()):
            if not await self.connect():
                return {"success": False, "error": "无法建立 data-agent WS 连接"}
        req_id = str(uuid.uuid4())
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        try:
            await self._ws.send(json.dumps({"type": msg_type, "id": req_id, **payload}))
            result = await asyncio.wait_for(fut, timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            return {"success": False, "error": "等待 data-agent 响应超时"}
        except Exception as exc:  # noqa: BLE001
            self._pending.pop(req_id, None)
            return {"success": False, "error": f"data-agent WS 发送失败: {exc}"}
        if not result.get("ok"):
            return {"success": False, "error": str(result.get("error") or "data-agent 返回失败")}
        data = result.get("data")
        return data if isinstance(data, dict) else {"success": True, "data": data}

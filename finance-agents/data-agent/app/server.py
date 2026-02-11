"""FastAPI 服务器 — 暴露 WebSocket /chat、POST /upload、GET /stream 接口。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.config import HOST, PORT, UPLOAD_DIR, MAX_FILE_SIZE
from app.graphs.main_graph import create_app
from app.utils.db import ensure_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Financial Data Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── LangGraph 实例 ────────────────────────────────────────────────────────────

langgraph_app = create_app()

# 用于跟踪每个 thread 上传的文件
_thread_files: dict[str, list[str]] = {}


# ── 启动时初始化 ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    try:
        ensure_tables()
    except Exception as e:
        logger.warning(f"数据库初始化失败（可稍后重试）: {e}")


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _extract_last_ai_message(messages) -> str | None:
    """从消息列表中提取最后一条 AI 消息。"""
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return m.content
    return None


def _get_interrupt_info(config: dict) -> tuple[bool, Any, str | None]:
    """检查图是否处于中断状态。

    Returns:
        (is_interrupted, interrupt_payload, last_ai_content)
    """
    try:
        snapshot = langgraph_app.get_state(config)
    except Exception:
        return False, None, None

    if not snapshot or not snapshot.next:
        return False, None, None

    # 图处于中断状态 — 提取 interrupt payload
    payload = None
    if hasattr(snapshot, "tasks"):
        for task in snapshot.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                payload = task.interrupts[0].value
                break

    last_ai = _extract_last_ai_message(snapshot.values.get("messages", []))
    return True, payload, last_ai


# ══════════════════════════════════════════════════════════════════════════════
# POST /upload — 文件上传
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    thread_id: str | None = None,
):
    """上传文件到服务器。返回文件路径，供后续对账使用。"""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    now = datetime.now()
    date_dir = Path(UPLOAD_DIR) / str(now.year) / str(now.month) / str(now.day)
    date_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    dest = date_dir / safe_name
    if dest.exists():
        stem = dest.stem
        dest = date_dir / f"{stem}_{now.strftime('%H%M%S')}{ext}"

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "文件过大")

    dest.write_bytes(content)
    file_path = str(dest)

    tid = thread_id or "default"
    _thread_files.setdefault(tid, []).append(file_path)

    logger.info(f"文件已上传: {file_path} (thread={tid})")
    return {"file_path": file_path, "filename": safe_name, "size": len(content)}


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket /chat — 对话
# ══════════════════════════════════════════════════════════════════════════════

@app.websocket("/chat")
async def websocket_chat(ws: WebSocket):
    """WebSocket 对话端点。

    协议：
    - 客户端发送 JSON: {"message": "...", "thread_id": "..."}
    - 服务端返回 JSON: {"type": "message", "content": "..."}
                       {"type": "interrupt", "payload": {...}}
                       {"type": "done"}
    - 当收到 interrupt 时，客户端再次发送:
      {"message": "用户回复", "thread_id": "...", "resume": true}
    """
    await ws.accept()
    logger.info("WebSocket 连接已建立")

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "content": "无效的 JSON"})
                continue

            user_msg = data.get("message", "")
            thread_id = data.get("thread_id", str(uuid.uuid4()))
            is_resume = data.get("resume", False)

            config = {"configurable": {"thread_id": thread_id}}
            files = _thread_files.get(thread_id, [])

            try:
                if is_resume:
                    result = langgraph_app.invoke(
                        Command(resume=user_msg),
                        config=config,
                    )
                else:
                    input_state: dict[str, Any] = {
                        "messages": [HumanMessage(content=user_msg)],
                        "uploaded_files": files,
                    }
                    result = langgraph_app.invoke(input_state, config=config)

                # 检查是否处于中断状态
                is_interrupted, payload, last_ai = _get_interrupt_info(config)

                if is_interrupted:
                    # 发送中断前的 AI 消息
                    if last_ai:
                        await ws.send_json({
                            "type": "message",
                            "content": last_ai,
                            "thread_id": thread_id,
                        })
                    await ws.send_json({
                        "type": "interrupt",
                        "payload": payload or {},
                        "thread_id": thread_id,
                    })
                else:
                    # 正常完成 — 提取最后的 AI 消息
                    messages = result.get("messages", [])
                    last_ai_content = _extract_last_ai_message(messages)
                    if last_ai_content:
                        await ws.send_json({
                            "type": "message",
                            "content": last_ai_content,
                            "thread_id": thread_id,
                        })
                    await ws.send_json({"type": "done", "thread_id": thread_id})

            except Exception as e:
                logger.error(f"图执行异常: {e}", exc_info=True)
                await ws.send_json({
                    "type": "error",
                    "content": f"处理失败: {str(e)}",
                    "thread_id": thread_id,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")


# ══════════════════════════════════════════════════════════════════════════════
# GET /stream — SSE 流式输出
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/stream")
async def stream_chat(
    message: str,
    thread_id: str | None = None,
    resume: bool = False,
):
    """SSE 流式端点。

    参数:
        message: 用户消息
        thread_id: 会话 ID
        resume: 是否恢复中断（为 true 时 message 作为 interrupt 的回复）
    """
    tid = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": tid}}
    files = _thread_files.get(tid, [])

    async def event_generator():
        try:
            if resume:
                invoke_input = Command(resume=message)
            else:
                invoke_input = {
                    "messages": [HumanMessage(content=message)],
                    "uploaded_files": files,
                }

            for event in langgraph_app.stream(invoke_input, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if node_name == "__interrupt__":
                        continue
                    msgs = node_output.get("messages", [])
                    for m in msgs:
                        if isinstance(m, AIMessage):
                            payload = json.dumps(
                                {"type": "message", "content": m.content, "node": node_name},
                                ensure_ascii=False,
                            )
                            yield f"data: {payload}\n\n"

            # 检查是否中断
            is_interrupted, payload, _ = _get_interrupt_info(config)
            if is_interrupted:
                interrupt_data = json.dumps(
                    {"type": "interrupt", "payload": payload or {}, "thread_id": tid},
                    ensure_ascii=False,
                )
                yield f"data: {interrupt_data}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'thread_id': tid})}\n\n"

        except Exception as e:
            logger.error(f"Stream 异常: {e}", exc_info=True)
            error_payload = json.dumps(
                {"type": "error", "content": str(e)},
                ensure_ascii=False,
            )
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# GET /health
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "service": "data-agent"}


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import uvicorn
    uvicorn.run("app.server:app", host=HOST, port=int(PORT), reload=True)


if __name__ == "__main__":
    main()

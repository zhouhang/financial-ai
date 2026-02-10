"""FastAPI 服务器 — 暴露 WebSocket /chat、POST /upload、GET /stream 接口。"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

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

    # 按日期组织目录
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

    # 关联到 thread
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
    - 当收到 interrupt 时，客户端再次发送 {"message": "用户回复", "thread_id": "...", "resume": true}
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

            # 收集已上传文件
            files = _thread_files.get(thread_id, [])

            try:
                if is_resume:
                    # 恢复中断的图执行，将用户回复作为 interrupt 的值
                    result = langgraph_app.invoke(
                        Command(resume=user_msg),
                        config=config,
                    )
                else:
                    # 正常调用
                    input_state: dict[str, Any] = {
                        "messages": [HumanMessage(content=user_msg)],
                        "uploaded_files": files,
                    }
                    result = langgraph_app.invoke(input_state, config=config)

                # 提取最后的 AI 消息
                messages = result.get("messages", [])
                ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
                if ai_msgs:
                    await ws.send_json({
                        "type": "message",
                        "content": ai_msgs[-1].content,
                        "thread_id": thread_id,
                    })

                await ws.send_json({"type": "done", "thread_id": thread_id})

            except Exception as e:
                err_str = str(e)
                # 检查是否是 interrupt（GraphInterrupt）
                if "interrupt" in err_str.lower() or "GraphInterrupt" in err_str:
                    # 获取当前状态以读取中断信息
                    try:
                        snapshot = langgraph_app.get_state(config)
                        # 从 snapshot 中提取 interrupt payload
                        next_tasks = snapshot.next if snapshot else ()
                        interrupt_payload = None
                        if hasattr(snapshot, 'tasks'):
                            for task in snapshot.tasks:
                                if hasattr(task, 'interrupts') and task.interrupts:
                                    interrupt_payload = task.interrupts[0].value
                                    break

                        # 提取最后的 AI 消息
                        state_messages = snapshot.values.get("messages", []) if snapshot else []
                        last_ai = None
                        for m in reversed(state_messages):
                            if isinstance(m, AIMessage):
                                last_ai = m.content
                                break

                        if last_ai:
                            await ws.send_json({
                                "type": "message",
                                "content": last_ai,
                                "thread_id": thread_id,
                            })

                        await ws.send_json({
                            "type": "interrupt",
                            "payload": interrupt_payload if interrupt_payload else {},
                            "thread_id": thread_id,
                        })
                    except Exception as inner_e:
                        logger.error(f"处理 interrupt 异常: {inner_e}")
                        await ws.send_json({
                            "type": "interrupt",
                            "payload": {},
                            "thread_id": thread_id,
                        })
                else:
                    logger.error(f"图执行异常: {e}", exc_info=True)
                    await ws.send_json({
                        "type": "error",
                        "content": f"处理失败: {err_str}",
                        "thread_id": thread_id,
                    })

    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")


# ══════════════════════════════════════════════════════════════════════════════
# GET /stream — SSE 流式输出
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/stream")
async def stream_chat(message: str, thread_id: str | None = None):
    """SSE 流式端点，通过 query 参数传入消息。"""
    tid = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": tid}}
    files = _thread_files.get(tid, [])

    async def event_generator():
        input_state: dict[str, Any] = {
            "messages": [HumanMessage(content=message)],
            "uploaded_files": files,
        }

        try:
            # 使用 stream 获取增量输出
            for event in langgraph_app.stream(input_state, config=config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    msgs = node_output.get("messages", [])
                    for m in msgs:
                        if isinstance(m, AIMessage):
                            payload = json.dumps(
                                {"type": "message", "content": m.content, "node": node_name},
                                ensure_ascii=False,
                            )
                            yield f"data: {payload}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            err_str = str(e)
            if "interrupt" in err_str.lower() or "GraphInterrupt" in err_str:
                # 读取 interrupt 信息
                try:
                    snapshot = langgraph_app.get_state(config)
                    state_messages = snapshot.values.get("messages", []) if snapshot else []
                    last_ai = None
                    for m in reversed(state_messages):
                        if isinstance(m, AIMessage):
                            last_ai = m.content
                            break

                    if last_ai:
                        payload = json.dumps(
                            {"type": "message", "content": last_ai},
                            ensure_ascii=False,
                        )
                        yield f"data: {payload}\n\n"

                    interrupt_data = json.dumps(
                        {"type": "interrupt", "thread_id": tid},
                        ensure_ascii=False,
                    )
                    yield f"data: {interrupt_data}\n\n"
                except Exception:
                    yield f"data: {json.dumps({'type': 'interrupt', 'thread_id': tid})}\n\n"
            else:
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

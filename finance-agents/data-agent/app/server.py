"""FastAPI 服务器 — 暴露 WebSocket /chat、POST /upload、GET /stream 接口。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.config import HOST, PORT, MAX_FILE_SIZE
from app.graphs.main_graph import create_app, register_progress_callback, unregister_progress_callback
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
    thread_id: str = Form("default"),
):
    """上传文件 - 调用 finance-mcp 的 file_upload MCP 工具。"""
    import base64
    from app.tools.mcp_client import call_mcp_tool
    
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    # 读取文件内容
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "文件过大")
    
    # 转换为 base64
    content_b64 = base64.b64encode(content).decode('utf-8')
    
    # 调用 finance-mcp 的 file_upload MCP 工具
    try:
        result = await call_mcp_tool("file_upload", {
            "files": [
                {
                    "filename": file.filename,
                    "content": content_b64
                }
            ]
        })
        
        # 检查上传结果
        if not result.get("success"):
            error_msg = result.get("error", "上传失败")
            if "errors" in result and result["errors"]:
                error_msg = result["errors"][0].get("error", error_msg)
            raise HTTPException(500, error_msg)
        
        # 获取上传的文件信息
        uploaded_files = result.get("uploaded_files", [])
        if not uploaded_files:
            raise HTTPException(500, "上传成功但未返回文件信息")
        
        file_info = uploaded_files[0]
        file_path = file_info.get("file_path", "")
        
        # 保存到线程文件映射
        _thread_files.setdefault(thread_id, []).append(file_path)
        
        logger.info(f"文件已通过 MCP 工具上传: {file_path} (thread={thread_id})")
        return {
            "file_path": file_path,
            "filename": file.filename,
            "size": len(content)
        }
        
    except Exception as e:
        logger.error(f"调用 MCP 工具上传文件失败: {e}", exc_info=True)
        raise HTTPException(500, f"文件上传失败: {str(e)}")


# ══════════════════════════════════════════════════════════════════════════════
# WebSocket /chat — 对话
# ══════════════════════════════════════════════════════════════════════════════

def _send_progress(ws: WebSocket, thread_id: str, message: str):
    """发送进度消息到 WebSocket（同步函数，由轮询线程调用）"""
    import asyncio
    
    try:
        # 在当前事件循环中创建任务
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(
            ws.send_json({
                "type": "stream",
                "content": f"\n\n{message}",
                "thread_id": thread_id,
            }),
            loop
        )
    except Exception as e:
        logger.warning(f"发送进度消息失败: {e}")


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
    
    # 用于跟踪当前连接的 thread_id，以便在连接关闭时注销回调
    current_thread_id = None

    try:
        while True:
            raw = await ws.receive_text()
            logger.info(f"收到 WebSocket 消息: {raw[:200]}")  # 只记录前200个字符
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.error(f"JSON 解析失败: {raw[:100]}")
                await ws.send_json({"type": "error", "content": "无效的 JSON"})
                continue

            user_msg = data.get("message", "")
            thread_id = data.get("thread_id", str(uuid.uuid4()))
            is_resume = data.get("resume", False)
            auth_token = data.get("auth_token", "")
            
            logger.info(f"处理消息: user_msg='{user_msg[:50]}...', thread_id={thread_id}, is_resume={is_resume}, has_token={bool(auth_token)}")

            # 注册进度回调（每次消息都重新注册，确保使用最新的 ws 连接）
            current_thread_id = thread_id
            register_progress_callback(thread_id, lambda msg: _send_progress(ws, thread_id, msg))

            config = {"configurable": {"thread_id": thread_id}}
            files = _thread_files.get(thread_id, [])

            try:
                # 使用 astream_events 捕获 LLM token 级别的流式输出
                if is_resume:
                    # resume 前先更新 state 中的 uploaded_files 和 auth_token
                    update_state: dict[str, Any] = {}
                    if files:
                        update_state["uploaded_files"] = files
                    if auth_token:
                        update_state["auth_token"] = auth_token
                        # 解析 token 获取用户信息
                        from app.tools.mcp_client import auth_me
                        try:
                            me_result = await auth_me(auth_token)
                            if me_result.get("success"):
                                update_state["current_user"] = me_result["user"]
                        except Exception:
                            pass
                    if update_state:
                        langgraph_app.update_state(config, update_state)
                        logger.info(f"resume: 更新 state: {list(update_state.keys())}")
                    input_data = Command(resume=user_msg)
                else:
                    input_data: dict[str, Any] = {
                        "messages": [HumanMessage(content=user_msg)],
                        "uploaded_files": files,
                    }
                    if auth_token:
                        input_data["auth_token"] = auth_token
                        # 解析 token 获取用户信息
                        from app.tools.mcp_client import auth_me
                        try:
                            me_result = await auth_me(auth_token)
                            if me_result.get("success"):
                                input_data["current_user"] = me_result["user"]
                        except Exception:
                            pass
                
                logger.info(f"开始执行 LangGraph: thread_id={thread_id}")
                
                # ── 流式输出策略 ──
                # router: 首 token 检测 JSON → 是则静默，否则流式
                # result_analysis 等: 直接流式
                # task_execution: 手动 AIMessage → message
                # resume 时: 跳过 router 旧消息
                streamed_content = ""
                router_buffer = ""
                router_mode = "detect"  # "detect" | "stream" | "json"
                event_count = 0
                sent_contents: set[str] = set()

                # resume 时，记录已有的 AI 消息内容，避免重发
                if is_resume:
                    try:
                        existing_state = langgraph_app.get_state(config)
                        for msg in (existing_state.values.get("messages") or []):
                            if hasattr(msg, "type") and msg.type == "ai" and hasattr(msg, "content"):
                                sent_contents.add(msg.content.strip())
                        logger.info(f"resume: 已记录 {len(sent_contents)} 条历史 AI 消息用于去重")
                    except Exception as e:
                        logger.warning(f"获取历史消息失败: {e}")
                
                async for event in langgraph_app.astream_events(input_data, config=config, version="v2"):
                    event_count += 1
                    kind = event.get("event")
                    data_obj = event.get("data", {})
                    metadata = event.get("metadata", {})
                    node_name = metadata.get("langgraph_node", "")
                    
                    # ① LLM 流式 token
                    if kind == "on_chat_model_stream" and node_name:
                        chunk = data_obj.get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            token = chunk.content
                            if node_name == "router":
                                # router: 首 token 检测
                                if router_mode == "detect":
                                    router_buffer += token
                                    stripped = router_buffer.strip()
                                    if stripped:
                                        if stripped[0] in ("{", "`"):
                                            router_mode = "json"  # JSON 意图，继续缓冲
                                        else:
                                            router_mode = "stream"  # 普通对话，立即流式
                                            streamed_content += router_buffer
                                            await ws.send_json({"type": "stream", "content": router_buffer, "thread_id": thread_id})
                                            router_buffer = ""
                                elif router_mode == "stream":
                                    streamed_content += token
                                    await ws.send_json({"type": "stream", "content": token, "thread_id": thread_id})
                                else:  # json
                                    router_buffer += token
                            else:
                                # 其他节点：过滤掉 file_analysis 的 LLM 输出（内部字段映射生成）
                                # 只有 result_analysis 等面向用户的节点才流式输出
                                if node_name not in ["file_analysis", "field_mapping", "rule_config", "validation_preview"]:
                                    streamed_content += token
                                    await ws.send_json({"type": "stream", "content": token, "thread_id": thread_id})
                    
                    # ② router LLM 结束
                    elif kind == "on_chat_model_end" and node_name == "router":
                        if router_mode == "json":
                            logger.info(f"过滤 router JSON 意图，长度={len(router_buffer)}")
                        elif router_mode == "stream":
                            sent_contents.add(streamed_content.strip())
                            logger.info(f"router 流式输出完成，长度={len(streamed_content)}")
                        elif router_mode == "detect" and router_buffer.strip():
                            # 只有少量 token，未触发检测，作为 message 发送
                            content = router_buffer.strip()
                            if content not in sent_contents:
                                sent_contents.add(content)
                                await ws.send_json({"type": "message", "content": content, "thread_id": thread_id})
                        router_buffer = ""
                        router_mode = "detect"
                    
                    # ③ 其他 LLM 结束：记录用于去重
                    elif kind == "on_chat_model_end" and node_name and node_name != "router":
                        output = data_obj.get("output")
                        if output and hasattr(output, "content") and output.content:
                            sent_contents.add(output.content.strip())
                    
                    # ④ 节点完成：发送手动 AIMessage + auth_token 更新
                    elif kind == "on_chain_end" and node_name:
                        # resume 时跳过 router 的旧消息
                        if is_resume and node_name == "router":
                            logger.info(f"resume: 跳过 router 的 on_chain_end 消息")
                            continue
                        
                        output = data_obj.get("output", {})
                        if isinstance(output, dict):
                            # 检查是否有新的 auth_token（登录/注册成功）
                            new_token = output.get("auth_token")
                            new_user = output.get("current_user")
                            if new_token:
                                logger.info(f"检测到新 auth_token（登录/注册成功），发送给前端")
                                await ws.send_json({
                                    "type": "auth",
                                    "token": new_token,
                                    "user": new_user,
                                    "thread_id": thread_id,
                                })
                            
                            for msg in output.get("messages", []):
                                if hasattr(msg, "type") and msg.type == "ai":
                                    content = (msg.content if hasattr(msg, "content") else "").strip()
                                    if content and content not in sent_contents:
                                        sent_contents.add(content)
                                        logger.info(f"实时发送 [{node_name}] 手动消息，长度={len(content)}")
                                        await ws.send_json({"type": "message", "content": content, "thread_id": thread_id})
                
                logger.info(f"astream_events 结束，共 {event_count} 个事件，流式发送 {len(streamed_content)} 字符")

                # 检查是否处于中断状态
                is_interrupted, payload, last_ai = _get_interrupt_info(config)

                if is_interrupted:
                    await ws.send_json({
                        "type": "interrupt",
                        "payload": payload or {},
                        "thread_id": thread_id,
                    })
                else:
                    await ws.send_json({"type": "done", "thread_id": thread_id})

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                logger.error(f"图执行异常: {e}\n{tb}")
                print(f"[ERROR] 图执行异常: {e}\n{tb}", flush=True)
                await ws.send_json({
                    "type": "error",
                    "content": f"处理失败: {str(e)}",
                    "thread_id": thread_id,
                })

    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
    finally:
        # 清理：注销进度回调
        if current_thread_id:
            unregister_progress_callback(current_thread_id)
            logger.debug(f"已注销 thread_id={current_thread_id} 的进度回调")


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
    uvicorn.run("app.server:app", host=HOST, port=int(PORT), reload=False)


if __name__ == "__main__":
    main()

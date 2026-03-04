"""FastAPI 服务器 — 暴露 WebSocket /chat、POST /upload、GET /stream 接口。"""

from __future__ import annotations

# 必须在 langchain/langgraph 导入之前加载 .env，否则 LangSmith 会缓存未设置的环境变量，追踪失效
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.config import HOST, PORT, MAX_FILE_SIZE
from app.graphs.main_graph import create_app
from app.models import ReconciliationPhase, UserIntent
from app.utils.db import ensure_tables
from app.tools.mcp_client import (
    auth_login as mcp_auth_login,
    auth_register as mcp_auth_register,
    list_companies_public as mcp_list_companies_public,
    list_departments_public as mcp_list_departments_public,
    create_conversation as mcp_create_conversation,
    save_message as mcp_save_message,
    list_conversations as mcp_list_conversations,
    get_conversation as mcp_get_conversation,
    delete_conversation as mcp_delete_conversation,
    call_mcp_tool,
)

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
_thread_files: dict[str, list[dict]] = {}  # 保存文件信息，包含 file_path 和 original_filename
# ⚠️ 修复：跟踪每个 thread 的上一次文件列表（用于检测文件变化）
_thread_files_snapshot: dict[str, list[str]] = {}  # 保存上一次的文件路径列表快照


# ── 启动时初始化 ──────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    # 启动时打印 LangSmith 追踪配置（便于排查追踪不生效问题）
    import os
    tracing = os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2")
    project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT")
    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if tracing and api_key:
        logger.info(f"LangSmith 追踪已启用: project={project or 'default'}")
    else:
        logger.warning(
            "LangSmith 追踪未启用: LANGSMITH_TRACING=%s, LANGSMITH_API_KEY=%s",
            "未设置" if not tracing else "已设置",
            "未设置" if not api_key else "已设置",
        )
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
    is_first_file: str = Form("0"),  # 改为 str，通过表单传递 "0" 或 "1"
    auth_token: str = Form(""),  # 登录用户的 auth_token
    guest_token: str = Form(""),  # 游客的 guest_token
):
    """上传文件 - 调用 finance-mcp 的 file_upload MCP 工具。

    Args:
        file: 上传的文件
        thread_id: 会话 ID
        is_first_file: 是否是本批上传的第一个文件 ("1"=True, "0"=False)
        auth_token: 登录用户的认证 token（与 guest_token 二选一）
        guest_token: 游客的临时 token（与 auth_token 二选一）
    """
    import base64
    import os
    import sys
    from app.tools.mcp_client import call_mcp_tool
    
    # Add finance-mcp to path to access security utilities
    finance_mcp_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..', 'finance-mcp')
    )
    if finance_mcp_path not in sys.path:
        sys.path.insert(0, finance_mcp_path)
    
    from security_utils import validate_filename

    # Validate thread_id to prevent injection attacks
    if not thread_id or not isinstance(thread_id, str) or len(thread_id) > 100:
        raise HTTPException(400, "无效的 thread_id")
    
    # Prevent path traversal in thread_id
    if '..' in thread_id or '/' in thread_id or '\\' in thread_id:
        raise HTTPException(400, "无效的 thread_id")

    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    # Validate filename to prevent path traversal attacks
    if not validate_filename(file.filename):
        raise HTTPException(400, "非法文件名，可能存在安全风险")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(400, f"不支持的文件类型: {ext}")

    # 读取文件内容
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "文件过大")

    # 转换为 base64
    content_b64 = base64.b64encode(content).decode('utf-8')

    # ⚠️ 修复：正确处理 is_first_file 参数（来自表单的字符串）
    is_first = is_first_file == "1"
    if is_first:
        _thread_files[thread_id] = []
        _thread_files_snapshot[thread_id] = []
        logger.info(f"清空 thread={thread_id} 的历史文件，开始新批次上传")

        # 同时清空 LangGraph state 中的 uploaded_files，确保状态同步
        try:
            config = {"configurable": {"thread_id": thread_id}}
            langgraph_app.update_state(config, {
                "uploaded_files": [],
                "file_analyses": [],
            })
            logger.info(f"已同步清空 state.uploaded_files (thread={thread_id})")
        except Exception as e:
            logger.warning(f"清空 state.uploaded_files 失败: {e}")

    # ⚠️ 如果前端没有传递 token，从 LangGraph state 中获取
    if not auth_token and not guest_token:
        try:
            config = {"configurable": {"thread_id": thread_id}}
            snapshot = langgraph_app.get_state(config)
            state_auth_token = snapshot.values.get("auth_token", "")
            state_guest_token = snapshot.values.get("guest_token", "")
            if state_auth_token:
                auth_token = state_auth_token
                logger.info(f"从 state 获取 auth_token (thread={thread_id})")
            elif state_guest_token:
                guest_token = state_guest_token
                logger.info(f"从 state 获取 guest_token (thread={thread_id})")
        except Exception as e:
            logger.warning(f"无法从 state 获取 token: {e}")

    # 调用 finance-mcp 的 file_upload MCP 工具
    try:
        mcp_args = {
            "files": [
                {
                    "filename": file.filename,
                    "content": content_b64
                }
            ]
        }
        # 传递 token 给 MCP 工具（auth_token 或 guest_token）
        if auth_token:
            mcp_args["auth_token"] = auth_token
        elif guest_token:
            mcp_args["guest_token"] = guest_token

        result = await call_mcp_tool("file_upload", mcp_args)

        # 🔍 临时调试：打印 MCP 返回的完整结果
        logger.info(f"🔍 [DEBUG] MCP file_upload 返回结果: {result}")

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

        # 保存到线程文件映射（包含 file_path 和 original_filename）
        _thread_files.setdefault(thread_id, []).append({
            "file_path": file_path,
            "original_filename": file_info.get("original_filename", file.filename)
        })

        # ⚠️ 修复：更新轻量级快照（只保存文件路径，用于快速比较）
        _thread_files_snapshot[thread_id] = [f.get("file_path", f) if isinstance(f, dict) else f for f in _thread_files[thread_id]]

        current_file_count = len(_thread_files[thread_id])
        logger.info(f"文件已通过 MCP 工具上传: {file_path} (thread={thread_id})")
        logger.info(f"🔍 [DEBUG] 当前 thread={thread_id} 共有 {current_file_count} 个文件: {[f.get('original_filename', 'unknown') for f in _thread_files[thread_id]]}")
        return {
            "file_path": file_path,
            "filename": file.filename,
            "size": len(content)
        }

    except HTTPException:
        raise  # 重新抛出 HTTPException
    except Exception as e:
        logger.error(f"调用 MCP 工具上传文件失败: {e}", exc_info=True)
        raise HTTPException(500, f"文件上传失败: {str(e)}")


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
            msg_attachments = data.get("attachments", [])  # 前端随消息发送的附件（含 path）
            conversation_id = data.get("conversation_id", "")  # 会话 ID
            
            logger.info(f"处理消息: user_msg='{user_msg[:50]}...', thread_id={thread_id}, is_resume={is_resume}, has_token={bool(auth_token)}, attachments={len(msg_attachments)}, conversation_id={conversation_id}")

            # ⚠️ 新增：如果消息为空但有token，这是一个认证验证请求（来自WebSocket连接时）
            if not user_msg and not is_resume and auth_token:
                logger.info(f"收到认证验证请求 (token length={len(auth_token)})")
                from app.tools.mcp_client import auth_me
                try:
                    me_result = await auth_me(auth_token)
                    if me_result.get("success"):
                        logger.info(f"认证验证成功，用户: {me_result.get('user', {}).get('username', 'unknown')}")
                        await ws.send_json({
                            "type": "auth_verify",
                            "success": True,
                            "user": me_result.get("user"),
                        })
                    else:
                        logger.warning(f"认证验证失败: {me_result.get('error', 'unknown')}")
                        await ws.send_json({
                            "type": "auth_verify",
                            "success": False,
                        })
                except Exception as e:
                    logger.error(f"认证验证异常: {str(e)}")
                    await ws.send_json({
                        "type": "auth_verify",
                        "success": False,
                    })
                continue  # 认证验证完成，不继续处理消息

            config = {"configurable": {"thread_id": thread_id}}
            
            # ⚠️ 不再在收到消息时清空 _thread_files：用户可能刚上传完文件再发消息，
            # 若此时 phase=COMPLETED 会误清空刚上传的文件，导致「未检测到文件上传」
            file_infos = _thread_files.get(thread_id, [])
            logger.info(f"🔍 [DEBUG] thread_id={thread_id}, _thread_files keys={list(_thread_files.keys())}, file_infos={len(file_infos)} files")
            # ⚠️ 仅在用户发送新消息（非 resume）且对账已完成时清空旧文件
            # 用户回复「不要」是 resume，表示不采纳规则、返回重新配置，应保留文件
            try:
                snapshot = langgraph_app.get_state(config)
                current_phase = (snapshot.values.get("phase") or "").strip()
                state_uploaded_files = snapshot.values.get("uploaded_files", []) if snapshot else []
                if (
                    not is_resume
                    and current_phase == ReconciliationPhase.COMPLETED.value
                    and not msg_attachments
                ):
                    _thread_files[thread_id] = []
                    _thread_files_snapshot[thread_id] = []
                    file_infos = []
                    logger.info(f"对账已完成且为新消息，清空旧文件 (thread={thread_id})")
                # 文件校验失败后，节点会把 state.uploaded_files 清空并回到 FILE_ANALYSIS。
                # 若此时用户重新上传，优先信任本次消息附件，避免复用 _thread_files 的旧文件。
                if (
                    current_phase == ReconciliationPhase.FILE_ANALYSIS.value
                    and not state_uploaded_files
                    and msg_attachments
                ):
                    _thread_files[thread_id] = []
                    _thread_files_snapshot[thread_id] = []
                    file_infos = []
                    logger.info(f"检测到 FILE_ANALYSIS 且 state 无文件，清空缓存文件以接收新上传 (thread={thread_id})")
            except Exception as e:
                logger.warning(f"获取 phase 失败: {e}")
            # 前端附件字段是 path；兼容 file_path/path 两种键，且优先使用本次附件覆盖缓存
            if msg_attachments:
                attachment_files = [
                    {
                        "file_path": a.get("file_path") or a.get("path", ""),
                        "original_filename": a.get("original_filename", a.get("name", "")),
                    }
                    for a in msg_attachments
                    if (a.get("file_path") or a.get("path"))
                ]
                if attachment_files:
                    cached_paths = [f.get("file_path", f) if isinstance(f, dict) else f for f in file_infos]
                    incoming_paths = [f.get("file_path", "") for f in attachment_files]
                    if set(cached_paths) != set(incoming_paths):
                        logger.info(
                            f"检测到附件文件与缓存不一致，使用附件覆盖缓存 (thread={thread_id}): cached={len(cached_paths)}, incoming={len(incoming_paths)}"
                        )
                    file_infos = attachment_files
                    _thread_files[thread_id] = attachment_files
                    _thread_files_snapshot[thread_id] = incoming_paths
                    logger.info(f"使用消息附带的 {len(file_infos)} 个文件 (thread={thread_id})")
            # 提取文件路径列表（兼容旧代码）
            files = [f.get("file_path", f) if isinstance(f, dict) else f for f in file_infos]
            
            # ⚠️ 修复：检查文件列表是否变化，如果变化则清空 LangGraph 状态中的旧分析结果
            previous_files = _thread_files_snapshot.get(thread_id, [])
            files_changed = set(files) != set(previous_files)
            if files_changed and files:
                logger.info(f"检测到文件列表变化 (thread={thread_id}): 之前={previous_files}, 现在={files}")
                # 清空旧的分析结果，强制重新分析
                try:
                    langgraph_app.update_state(config, {
                        "file_analyses": [],
                        "suggested_mappings": {},
                        "confirmed_mappings": {},
                        "rule_config_items": [],
                        "generated_schema": None,
                        "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                    })
                    logger.info(f"已清空 LangGraph 状态中的旧分析结果 (thread={thread_id})")
                except Exception as e:
                    logger.warning(f"清空 LangGraph 状态失败: {e}")
                # 更新快照
                _thread_files_snapshot[thread_id] = files

            try:
                # 使用 astream_events 捕获 LLM token 级别的流式输出
                if is_resume:
                    # ====== 新增：workflow 中 resume 时先检测意图 ======
                    # 注意：ReconciliationPhase 已在文件顶部全局导入，此处不重复导入以避免 UnboundLocalError
                    from app.utils.workflow_intent import classify_intent_in_workflow, save_workflow_context

                    snapshot = langgraph_app.get_state(config)
                    current_phase = snapshot.values.get("phase", "") if snapshot else ""

                    # 定义所有 workflow 阶段
                    all_workflow_phases = [
                        ReconciliationPhase.FILE_ANALYSIS.value,
                        ReconciliationPhase.FIELD_MAPPING.value,
                        ReconciliationPhase.RULE_RECOMMENDATION.value,
                        ReconciliationPhase.RULE_CONFIG.value,
                        ReconciliationPhase.VALIDATION_PREVIEW.value,
                        ReconciliationPhase.SAVE_RULE.value,
                        ReconciliationPhase.RESULT_EVALUATION.value,
                        ReconciliationPhase.EDIT_FIELD_MAPPING.value,
                        ReconciliationPhase.EDIT_RULE_CONFIG.value,
                        ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
                        ReconciliationPhase.EDIT_SAVE.value,
                    ]

                    # 如果在 workflow 中，检查用户是否想切换意图
                    if current_phase in all_workflow_phases:
                        # 游客模式：跳过 server 层的意图预检测，直接 resume
                        # 游客模式的意图处理由各节点（file_analysis_node 等）负责
                        # 节点中已实现 check_user_intent_after_interrupt_guest + Command(goto=END)
                        if not auth_token:
                            logger.info(f"server: [游客模式] 跳过意图预检测，直接 resume (phase={current_phase})")
                            update_state: dict[str, Any] = {}
                            if file_infos:
                                update_state["uploaded_files"] = file_infos
                            if update_state:
                                langgraph_app.update_state(config, update_state)
                            input_data = Command(resume=user_msg)
                        else:
                            # 登录用户：在 server 层预检测意图
                            # 特殊处理：如果是文件上传提示（系统自动生成），直接认为是继续 workflow
                            import re
                            file_upload_patterns = [
                                r'已上传\s*\d+\s*个文件',
                                r'上传了\s*\d+\s*个文件',
                                r'文件已上传',
                                r'请处理.*文件'
                            ]
                            is_file_upload_msg = any(re.search(p, user_msg.lower()) for p in file_upload_patterns)

                            if is_file_upload_msg:
                                # 文件上传提示，跳过意图检测，直接 resume
                                logger.info(f"server: 检测到文件上传提示，跳过意图检测，直接 resume")
                                intent = UserIntent.RESUME_WORKFLOW.value
                            else:
                                intent = await classify_intent_in_workflow(
                                    user_msg=user_msg,
                                    current_phase=current_phase,
                                    state=snapshot.values
                                )

                            if intent != UserIntent.RESUME_WORKFLOW.value:
                                # 用户想切换意图，保存进度，改为非 resume 模式
                                logger.info(f"server: resume 时检测到意图切换 {current_phase} → {intent}，转为正常消息流程")

                                # 保存 workflow 上下文
                                save_workflow_context(snapshot.values, current_phase)

                                # 更新 state
                                update_state: dict[str, Any] = {
                                    "phase": "",  # 清空 phase，退出 workflow
                                    "user_intent": intent,
                                    "workflow_context": snapshot.values.get("workflow_context"),
                                }
                                if file_infos:
                                    update_state["uploaded_files"] = file_infos
                                if auth_token:
                                    update_state["auth_token"] = auth_token
                                    from app.tools.mcp_client import auth_me
                                    try:
                                        me_result = await auth_me(auth_token)
                                        if me_result.get("success"):
                                            update_state["current_user"] = me_result["user"]
                                    except Exception:
                                        pass

                                langgraph_app.update_state(config, update_state)

                                # 改为正常消息模式，让 router 处理意图
                                is_resume = False
                                input_data: dict[str, Any] = {
                                    "messages": [HumanMessage(content=user_msg)],
                                    "uploaded_files": file_infos,
                                }
                                if auth_token:
                                    input_data["auth_token"] = auth_token
                                    if "current_user" in update_state:
                                        input_data["current_user"] = update_state["current_user"]
                            else:
                                # 用户想继续 workflow，正常 resume
                                logger.info(f"server: resume 继续 workflow (phase={current_phase})")
                                logger.info(f"🔍 [DEBUG] file_infos={file_infos}")
                                update_state: dict[str, Any] = {}
                                if file_infos:
                                    update_state["uploaded_files"] = file_infos
                                    logger.info(f"🔍 [DEBUG] 设置 update_state['uploaded_files'] = {len(file_infos)} 个文件")
                                    logger.info(f"🔍 [DEBUG] 文件详情: {[f.get('original_filename', 'unknown') if isinstance(f, dict) else f for f in file_infos]}")
                                if auth_token:
                                    update_state["auth_token"] = auth_token
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
                                    # 验证更新是否成功
                                    try:
                                        updated_snapshot = langgraph_app.get_state(config)
                                        actual_file_count = len(updated_snapshot.values.get("uploaded_files", []))
                                        logger.info(f"🔍 [DEBUG] state 更新后，实际 uploaded_files 数量: {actual_file_count}")
                                    except Exception as e:
                                        logger.warning(f"验证 state 更新失败: {e}")
                                input_data = Command(resume=user_msg)
                    else:
                        # 不在 workflow 中，正常 resume
                        # 特殊处理：若 phase=completed 且用户发送「已上传X个文件」消息，说明是失败后重传文件，
                        # 应强制回到 FILE_ANALYSIS，而不是继续 completed 状态。
                        import re
                        file_upload_patterns = [
                            r'已上传\s*\d+\s*个文件',
                            r'上传了\s*\d+\s*个文件',
                            r'文件已上传',
                            r'请处理.*文件'
                        ]
                        is_file_upload_msg = any(re.search(p, user_msg.lower()) for p in file_upload_patterns)
                        if is_file_upload_msg and current_phase == ReconciliationPhase.COMPLETED.value and file_infos:
                            logger.info("server: resume 场景检测到 completed 后重传文件，切换到 FILE_ANALYSIS")
                            update_state: dict[str, Any] = {
                                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                                "uploaded_files": file_infos,
                                "file_analyses": [],
                            }
                            if auth_token:
                                update_state["auth_token"] = auth_token
                                from app.tools.mcp_client import auth_me
                                try:
                                    me_result = await auth_me(auth_token)
                                    if me_result.get("success"):
                                        update_state["current_user"] = me_result["user"]
                                except Exception:
                                    pass
                            langgraph_app.update_state(config, update_state)
                            is_resume = False
                            input_data = {
                                "messages": [HumanMessage(content=user_msg)],
                                "uploaded_files": file_infos,
                            }
                        else:
                            update_state = {}
                            if file_infos:
                                update_state["uploaded_files"] = file_infos
                            if auth_token:
                                update_state["auth_token"] = auth_token
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
                    # 非 resume 模式：通常重置 phase，但文件上传消息除外
                    # ⚠️ 检测文件上传消息：即使 resume=false，也应该保持 workflow 状态
                    import re
                    file_upload_patterns = [
                        r'已上传\s*\d+\s*个文件',
                        r'上传了\s*\d+\s*个文件',
                        r'文件已上传',
                        r'请处理.*文件'
                    ]
                    is_file_upload_msg = any(re.search(p, user_msg.lower()) for p in file_upload_patterns)

                    # 获取当前 phase
                    try:
                        snapshot = langgraph_app.get_state(config)
                        current_phase = snapshot.values.get("phase", "") if snapshot else ""
                    except Exception:
                        current_phase = ""

                    # file_analysis 阶段上传文件：这是新一轮校验，必须走正常消息流程（不能 Command(resume)，否则可能无事件并回退旧消息）
                    if is_file_upload_msg and current_phase == ReconciliationPhase.FILE_ANALYSIS.value and file_infos:
                        logger.info("检测到 FILE_ANALYSIS 阶段上传文件，使用正常消息流程重新分析")
                        update_state: dict[str, Any] = {
                            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                            "uploaded_files": file_infos,
                            "file_analyses": [],
                        }
                        if auth_token:
                            update_state["auth_token"] = auth_token
                            from app.tools.mcp_client import auth_me
                            try:
                                me_result = await auth_me(auth_token)
                                if me_result.get("success"):
                                    update_state["current_user"] = me_result["user"]
                            except Exception:
                                pass
                        langgraph_app.update_state(config, update_state)
                        input_data = {
                            "messages": [HumanMessage(content=user_msg)],
                            "uploaded_files": file_infos,
                        }
                        if auth_token:
                            input_data["auth_token"] = auth_token
                            if "current_user" in update_state:
                                input_data["current_user"] = update_state["current_user"]
                    # 其他 workflow 阶段（除 completed）的文件上传提示，保持 phase，改为 resume 模式
                    elif is_file_upload_msg and current_phase and current_phase != ReconciliationPhase.COMPLETED.value:
                        logger.info(f"检测到文件上传消息 (resume=false)，保持 phase={current_phase}，改为 resume 模式")
                        update_state: dict[str, Any] = {}
                        if file_infos:
                            update_state["uploaded_files"] = file_infos
                            logger.info(f"🔍 [DEBUG] (resume=false) 设置 update_state['uploaded_files'] = {len(file_infos)} 个文件")
                            logger.info(f"🔍 [DEBUG] (resume=false) 文件详情: {[f.get('original_filename', 'unknown') if isinstance(f, dict) else f for f in file_infos]}")
                        if auth_token:
                            update_state["auth_token"] = auth_token
                            from app.tools.mcp_client import auth_me
                            try:
                                me_result = await auth_me(auth_token)
                                if me_result.get("success"):
                                    update_state["current_user"] = me_result["user"]
                            except Exception:
                                pass
                        if update_state:
                            langgraph_app.update_state(config, update_state)
                            logger.info(f"更新 state: {list(update_state.keys())}")
                            # 验证更新是否成功
                            try:
                                updated_snapshot = langgraph_app.get_state(config)
                                actual_file_count = len(updated_snapshot.values.get("uploaded_files", []))
                                logger.info(f"🔍 [DEBUG] (resume=false) state 更新后，实际 uploaded_files 数量: {actual_file_count}")
                            except Exception as e:
                                logger.warning(f"验证 state 更新失败: {e}")
                        input_data = Command(resume=user_msg)
                    # 如果是 completed 后重传文件，强制回到 FILE_ANALYSIS 重新校验
                    elif is_file_upload_msg and current_phase == ReconciliationPhase.COMPLETED.value and file_infos:
                        logger.info("检测到 completed 后重传文件，强制 phase=FILE_ANALYSIS")
                        update_state: dict[str, Any] = {
                            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                            "uploaded_files": file_infos,
                            "file_analyses": [],
                        }
                        if auth_token:
                            update_state["auth_token"] = auth_token
                            from app.tools.mcp_client import auth_me
                            try:
                                me_result = await auth_me(auth_token)
                                if me_result.get("success"):
                                    update_state["current_user"] = me_result["user"]
                            except Exception:
                                pass
                        langgraph_app.update_state(config, update_state)
                        input_data = {
                            "messages": [HumanMessage(content=user_msg)],
                            "uploaded_files": file_infos,
                        }
                        if auth_token:
                            input_data["auth_token"] = auth_token
                            if "current_user" in update_state:
                                input_data["current_user"] = update_state["current_user"]
                    else:
                        # 正常的新会话：重置 phase 状态
                        try:
                            langgraph_app.update_state(config, {"phase": ""})
                            logger.info(f"新会话: 已重置 LangGraph state (thread={thread_id})")
                        except Exception as e:
                            logger.warning(f"重置 LangGraph state 失败: {e}")

                        # 构建新会话的 input_data
                        input_data: dict[str, Any] = {
                            "messages": [HumanMessage(content=user_msg)],
                            "uploaded_files": file_infos,  # 传递完整对象（含 file_path、original_filename）
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
                # ⚠️ 修复：添加消息缓冲机制防止分段
                streamed_content = ""
                router_buffer = ""
                router_mode = "detect"  # "detect" | "stream" | "json"
                event_count = 0
                sent_contents: set[str] = set()
                # 消息缓冲（防止每个 token 都单独发送导致分段）
                message_buffer = ""
                BUFFER_SIZE = 100  # 累积 100 字符后发送一次
                current_streaming_node = None  # 跟踪当前流式输出的节点

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
                                        # 过滤 router 探测阶段的单字符噪声（如 "A"），避免误切换到 stream
                                        elif len(stripped) == 1 and stripped.isalpha():
                                            continue
                                        else:
                                            router_mode = "stream"  # 普通对话，立即流式
                                            streamed_content += router_buffer
                                            message_buffer += router_buffer
                                            current_streaming_node = "router"
                                            router_buffer = ""
                                elif router_mode == "stream":
                                    streamed_content += token
                                    message_buffer += token
                                    current_streaming_node = "router"
                                    # ⚠️ 修复：缓冲累积而不是每个 token 都发送
                                    if len(message_buffer) >= BUFFER_SIZE:
                                        await ws.send_json({"type": "stream", "content": message_buffer, "thread_id": thread_id})
                                        message_buffer = ""
                                else:  # json
                                    router_buffer += token
                            else:
                                # 其他节点：过滤掉内部 LLM 输出（字段映射/规则配置的解析，不应显示 raw JSON）
                                # 只有 result_analysis 等面向用户的节点才流式输出
                                _no_stream_nodes = [
                                    "file_analysis", "field_mapping", "rule_config", "validation_preview",
                                    "edit_field_mapping", "edit_rule_config",
                                    "result_analysis",  # 对账结果表格一次性展示，避免逐行渲染生硬
                                ]
                                if node_name not in _no_stream_nodes:
                                    streamed_content += token
                                    message_buffer += token
                                    current_streaming_node = node_name
                                    # ⚠️ 修复：缓冲累积而不是每个 token 都发送
                                    if len(message_buffer) >= BUFFER_SIZE:
                                        await ws.send_json({"type": "stream", "content": message_buffer, "thread_id": thread_id})
                                        message_buffer = ""
                    
                    # ② router LLM 结束
                    elif kind == "on_chat_model_end" and node_name == "router":
                        if router_mode == "json":
                            logger.info(f"过滤 router JSON 意图，长度={len(router_buffer)}")
                        elif router_mode == "stream":
                            # ⚠️ 修复：发送缓冲中还未发送的内容
                            if message_buffer:
                                await ws.send_json({"type": "stream", "content": message_buffer, "thread_id": thread_id})
                                logger.info(f"router 流式输出完成，发送最后缓冲，长度={len(message_buffer)}")
                                message_buffer = ""
                            sent_contents.add(streamed_content.strip())
                            logger.info(f"router 流式输出完成，总长度={len(streamed_content)}")
                        elif router_mode == "detect" and router_buffer.strip():
                            # 只有少量 token，未触发检测，作为 message 发送
                            content = router_buffer.strip()
                            # 过滤无意义的单字符抖动输出（例如偶发的 "A"）
                            if len(content) == 1 and content.isalpha():
                                logger.info(f"忽略 router 单字符输出噪声: {content!r}")
                            elif content not in sent_contents:
                                sent_contents.add(content)
                                await ws.send_json({"type": "message", "content": content, "thread_id": thread_id})
                        router_buffer = ""
                        router_mode = "detect"
                        current_streaming_node = None
                    
                    # ③ 其他 LLM 结束：记录用于去重
                    elif kind == "on_chat_model_end" and node_name and node_name != "router":
                        # ⚠️ 修复：发送缓冲中还未发送的内容
                        if message_buffer and current_streaming_node == node_name:
                            await ws.send_json({"type": "stream", "content": message_buffer, "thread_id": thread_id})
                            logger.info(f"[{node_name}] 流式输出完成，发送最后缓冲，长度={len(message_buffer)}")
                            message_buffer = ""
                            current_streaming_node = None
                        # ⚠️ 只收集面向用户的消息，不收集内部处理的 JSON
                        if node_name not in _no_stream_nodes:
                            output = data_obj.get("output")
                            if output and hasattr(output, "content") and output.content:
                                sent_contents.add(output.content.strip())
                    
                    # ④ 节点完成：发送手动 AIMessage + auth_token 更新
                    elif kind == "on_chain_end" and node_name:
                        # resume 时跳过 router 的旧消息
                        if is_resume and node_name == "router":
                            logger.info(f"resume: 跳过 router 的 on_chain_end 消息")
                            continue
                        
                        # router 节点如果已经通过流式输出发送了内容，就跳过 on_chain_end 的消息
                        if node_name == "router" and streamed_content.strip():
                            logger.info(f"router 节点已通过流式输出发送内容，跳过 on_chain_end 消息")
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

                # Fallback: 补发 on_chain_end 未能捕获的 AI 消息（如 result_evaluation CANCEL）
                try:
                    final_state = langgraph_app.get_state(config)
                    messages = final_state.values.get("messages") or []
                    # 只检查最后一条 AI 消息（避免重发旧消息）
                    last_ai_msg = None
                    for msg in reversed(messages):
                        if hasattr(msg, "type") and msg.type == "ai" and hasattr(msg, "content"):
                            last_ai_msg = msg
                            break

                    if last_ai_msg:
                        content = last_ai_msg.content.strip()
                        if content and content not in sent_contents:
                            sent_contents.add(content)
                            logger.info(f"[fallback] 补发遗漏消息，长度={len(content)}")
                            await ws.send_json({"type": "message", "content": content, "thread_id": thread_id})
                except Exception as e:
                    logger.warning(f"fallback 检查遗漏消息失败: {e}")

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
                
                # ── 会话保存 ──────────────────────────────────────────────
                # 如果用户已登录且有消息内容，保存到数据库
                if auth_token and user_msg and not user_msg.startswith("{"):
                    try:
                        # 如果没有 conversation_id，检查是否需要创建新会话
                        if not conversation_id:
                            # 检查是否已存在该 thread_id 对应的会话（通过查找最新的会话）
                            # 如果不存在，创建新会话
                            title = user_msg[:30] + ("..." if len(user_msg) > 30 else "")
                            conv_result = await mcp_create_conversation(auth_token, title)
                            if conv_result.get("success"):
                                conversation_id = conv_result["conversation"]["id"]
                                # 通知前端新会话 ID
                                await ws.send_json({
                                    "type": "conversation_created",
                                    "conversation_id": conversation_id,
                                    "title": title,
                                    "thread_id": thread_id,
                                })
                                logger.info(f"创建新会话: {conversation_id}")
                        
                        if conversation_id:
                            # 保存用户消息（带附件信息）
                            uploaded_files_info = _thread_files.get(thread_id, [])
                            attachments = [
                                {
                                    "name": f.get("filename"),
                                    "path": f.get("file_path"),
                                    "size": f.get("size", 0)
                                }
                                for f in uploaded_files_info
                            ] if uploaded_files_info else []
                            await mcp_save_message(auth_token, conversation_id, "user", user_msg, attachments=attachments)

                            # 保存 AI 回复（只保存面向用户的消息）
                            if sent_contents:
                                for content in sent_contents:
                                    # 跳过 HTML 表单和进度消息
                                    if (content and
                                        not content.startswith("<") and
                                        "{{SPINNER}}" not in content):
                                        await mcp_save_message(auth_token, conversation_id, "assistant", content)

                            logger.info(f"消息已保存到会话 {conversation_id}")
                    except Exception as e:
                        logger.warning(f"保存消息失败: {e}")

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
    file_infos = _thread_files.get(tid, [])
    # 提取文件路径列表（兼容旧代码）
    files = [f.get("file_path", f) if isinstance(f, dict) else f for f in file_infos]

    async def event_generator():
        try:
            if resume:
                invoke_input = Command(resume=message)
            else:
                # 传递文件信息对象（包含 file_path 和 original_filename）
                uploaded_files_for_state = file_infos if file_infos else files
                invoke_input = {
                    "messages": [HumanMessage(content=message)],
                    "uploaded_files": uploaded_files_for_state,
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
# POST /auth/login — 用户登录
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/login")
async def auth_login(username: str = Form(...), password: str = Form(...)):
    """用户登录，返回 token 和用户信息"""
    try:
        result = await mcp_auth_login(username, password)
        if result.get("success"):
            return result
        raise HTTPException(status_code=401, detail=result.get("error", "登录失败"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"登录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companies")
async def get_companies():
    """获取公司列表（公开，用于注册）"""
    try:
        result = await mcp_list_companies_public()
        return result.get("companies", []) if result.get("success") else []
    except Exception as e:
        logger.error(f"获取公司列表失败: {e}")
        return []


@app.get("/departments")
async def get_departments(company_id: str):
    """获取部门列表（公开，用于注册）"""
    if not company_id:
        return []
    try:
        result = await mcp_list_departments_public(company_id)
        return result.get("departments", []) if result.get("success") else []
    except Exception as e:
        logger.error(f"获取部门列表失败: {e}")
        return []


@app.post("/auth/register")
async def auth_register(
    username: str = Form(...),
    password: str = Form(...),
    company_id: str = Form(...),
    department_id: str = Form(...),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
):
    """用户注册，返回 token 和用户信息"""
    try:
        kwargs = {
            "company_id": company_id.strip(),
            "department_id": department_id.strip(),
        }
        if email and email.strip():
            kwargs["email"] = email.strip()
        if phone and phone.strip():
            kwargs["phone"] = phone.strip()
        result = await mcp_auth_register(username, password, **kwargs)
        if result.get("success"):
            return result
        raise HTTPException(status_code=400, detail=result.get("error", "注册失败"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"注册失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/copy-rule")
async def copy_rule(
    body: dict = Body(...),
    authorization: Optional[str] = Header(None),
):
    """复制对账规则为个人规则（登录后保存游客创建的推荐规则）"""
    logger.info(f"[copy-rule] 收到请求, authorization={authorization[:20] if authorization else None}..., body={body}")
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    logger.info(f"[copy-rule] token长度={len(token)}, token前20={token[:20] if token else None}")
    source_rule_id = body.get("source_rule_id")
    new_rule_name = body.get("new_rule_name")
    if not source_rule_id or not new_rule_name:
        raise HTTPException(status_code=400, detail="缺少 source_rule_id 或 new_rule_name")
    try:
        result = await call_mcp_tool("copy_reconciliation_rule", {
            "auth_token": token,
            "source_rule_id": source_rule_id,
            "new_rule_name": new_rule_name,
        })
        logger.info(f"[copy-rule] MCP返回: {result}")
        return result
    except Exception as e:
        logger.error(f"复制规则失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/save-pending-rule")
async def save_pending_rule(
    body: dict = Body(...),
    authorization: Optional[str] = Header(None),
):
    """从 LangGraph 线程状态恢复并保存新建规则（游客创建规则后登录）"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    thread_id = body.get("thread_id")
    rule_name = body.get("rule_name")
    if not thread_id or not rule_name:
        raise HTTPException(status_code=400, detail="缺少 thread_id 或 rule_name")
    try:
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = langgraph_app.get_state(config)
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail="未找到对应的会话状态，规则可能已过期")
        state = snapshot.values
        schema = state.get("generated_schema")
        if not schema:
            raise HTTPException(status_code=404, detail="会话中无待保存的规则")
        from app.graphs.reconciliation.helpers import (
            _rewrite_schema_transforms_to_mapped_fields,
            _build_field_mapping_text,
            _build_rule_config_text,
            _expand_file_patterns,
            _merge_json_snippets,
            _validate_and_deduplicate_rules,
        )
        schema_to_save = schema.copy()
        schema_to_save["description"] = rule_name
        config_items = state.get("rule_config_items", [])
        if config_items:
            schema_to_save = _merge_json_snippets(schema_to_save, config_items)
            schema_to_save = _validate_and_deduplicate_rules(schema_to_save)
        _rewrite_schema_transforms_to_mapped_fields(schema_to_save)
        mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
        schema_to_save["field_mapping_text"] = _build_field_mapping_text(mappings)
        schema_to_save["rule_config_text"] = _build_rule_config_text(config_items)
        for src in ("business", "finance"):
            patterns = schema_to_save.get("data_sources", {}).get(src, {}).get("file_pattern", [])
            expanded = []
            for p in patterns:
                expanded.extend(_expand_file_patterns(p))
            if "data_sources" not in schema_to_save:
                schema_to_save["data_sources"] = {}
            if src not in schema_to_save["data_sources"]:
                schema_to_save["data_sources"][src] = {}
            schema_to_save["data_sources"][src]["file_pattern"] = list(set(expanded))
        result = await call_mcp_tool("save_reconciliation_rule", {
            "auth_token": token,
            "name": rule_name,
            "description": rule_name,
            "rule_template": schema_to_save,
            "visibility": "private",
        })
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存待处理规则失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理 REST API
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/conversations")
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    authorization: Optional[str] = Header(None),
):
    """获取用户的会话列表"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    
    # 支持 Bearer token 格式
    auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        result = await mcp_list_conversations(auth_token, limit, offset)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "获取会话列表失败"))
        return result
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
):
    """获取单个会话详情（包含消息）"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    
    auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        result = await mcp_get_conversation(auth_token, conversation_id)
        if not result.get("success"):
            raise HTTPException(status_code=404, detail=result.get("error", "会话不存在"))
        return result
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: Optional[str] = Header(None),
):
    """删除会话"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    
    auth_token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    
    try:
        result = await mcp_delete_conversation(auth_token, conversation_id)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "删除会话失败"))
        return result
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════════

def main():
    import uvicorn
    uvicorn.run("app.server:app", host=HOST, port=int(PORT), reload=False)


if __name__ == "__main__":
    main()

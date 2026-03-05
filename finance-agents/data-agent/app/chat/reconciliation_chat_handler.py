"""Reconciliation chat input resolver.

Keep workflow-specific resume/phase transitions out of FastAPI entry.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.models import ReconciliationPhase, UserIntent
from app.utils.workflow_phase_policy import (
    is_file_upload_message,
    is_workflow_phase,
    should_check_intent_switch,
)

logger = logging.getLogger(__name__)


async def _fill_auth_state(update_state: dict[str, Any], auth_token: str) -> dict[str, Any]:
    """Attach auth-related state when token is available."""
    if not auth_token:
        return update_state

    update_state["auth_token"] = auth_token
    from app.tools.mcp_client import auth_me

    try:
        me_result = await auth_me(auth_token)
        if me_result.get("success"):
            update_state["current_user"] = me_result["user"]
    except Exception:
        pass
    return update_state


async def _sync_uploaded_files_state(
    *,
    langgraph_app: Any,
    config: dict[str, Any],
    file_infos: list[dict[str, Any]],
    auth_token: str,
    log_prefix: str,
) -> None:
    update_state: dict[str, Any] = {}
    if file_infos:
        update_state["uploaded_files"] = file_infos
    update_state = await _fill_auth_state(update_state, auth_token)
    if update_state:
        langgraph_app.update_state(config, update_state)
        logger.info(f"{log_prefix}: 更新 state: {list(update_state.keys())}")


async def resolve_graph_input(
    *,
    langgraph_app: Any,
    config: dict[str, Any],
    user_msg: str,
    is_resume: bool,
    auth_token: str,
    file_infos: list[dict[str, Any]],
    has_attachments: bool = False,
) -> tuple[Any, bool]:
    """Resolve graph input payload for reconciliation workflow."""
    from app.utils.workflow_intent import (
        classify_intent_in_workflow_guest,
        classify_intent_in_workflow,
        save_workflow_context,
    )

    if is_resume:
        snapshot = langgraph_app.get_state(config)
        current_phase = snapshot.values.get("phase", "") if snapshot else ""
        state_values = snapshot.values if snapshot else {}
        is_interrupted = bool(snapshot and getattr(snapshot, "next", None))

        # 若图当前处于 interrupt，优先按真正的 resume 处理（即使 phase 为空），
        # 避免被误判为新会话导致从 file_analysis 重跑。
        if is_interrupted:
            if has_attachments:
                await _sync_uploaded_files_state(
                    langgraph_app=langgraph_app,
                    config=config,
                    file_infos=file_infos,
                    auth_token=auth_token,
                    log_prefix="resume[interrupted]",
                )
            return Command(resume=user_msg), True

        # completed 阶段不应继续 resume；非文件重传输入按新消息处理，避免重放旧流程。
        if current_phase == ReconciliationPhase.COMPLETED.value and not is_file_upload_message(user_msg):
            logger.info("resume=true 但当前 phase=completed，按新消息流程处理，避免重放")
            return {
                "messages": [HumanMessage(content=user_msg)],
                "uploaded_files": [],
                **({"auth_token": auth_token} if auth_token else {}),
            }, False

        # workflow 已退出（phase 为空）时，resume 请求按新消息处理，重新走意图识别。
        if not current_phase:
            return {
                "messages": [HumanMessage(content=user_msg)],
                "uploaded_files": file_infos,
                **({"auth_token": auth_token} if auth_token else {}),
            }, False

        # 某些 interrupt/resume 场景下 phase 会停留在 file_analysis，
        # 但映射上下文已就绪；此时应恢复到字段映射而不是重跑文件分析。
        if (
            current_phase == ReconciliationPhase.FILE_ANALYSIS.value
            and not is_file_upload_message(user_msg)
            and state_values.get("file_analyses")
            and (state_values.get("confirmed_mappings") or state_values.get("suggested_mappings"))
        ):
            langgraph_app.update_state(config, {"phase": ReconciliationPhase.FIELD_MAPPING.value})
            current_phase = ReconciliationPhase.FIELD_MAPPING.value
            logger.info("检测到 phase 卡在 file_analysis，已自动纠正为 field_mapping 继续 resume")

        if is_workflow_phase(current_phase):
            is_file_upload_msg = is_file_upload_message(user_msg)
            if not auth_token:
                # 游客模式：对非上传输入始终做意图检测，避免无关输入被当作 workflow 指令继续执行。
                if is_file_upload_msg:
                    intent = UserIntent.RESUME_WORKFLOW.value
                else:
                    intent = await classify_intent_in_workflow_guest(
                        user_msg=user_msg,
                        current_phase=current_phase,
                        state=state_values,
                    )
            else:
                if is_file_upload_msg:
                    intent = UserIntent.RESUME_WORKFLOW.value
                elif should_check_intent_switch(user_msg):
                    intent = await classify_intent_in_workflow(
                        user_msg=user_msg,
                        current_phase=current_phase,
                        state=state_values,
                    )
                else:
                    intent = UserIntent.RESUME_WORKFLOW.value

            if intent != UserIntent.RESUME_WORKFLOW.value:
                logger.info(f"server: resume 时检测到意图切换 {current_phase} → {intent}，转为正常消息流程")
                save_workflow_context(state_values, current_phase)
                update_state: dict[str, Any] = {
                    "phase": "",
                    "user_intent": intent if auth_token else UserIntent.UNKNOWN.value,
                    "workflow_context": state_values.get("workflow_context"),
                }
                if auth_token and file_infos:
                    update_state["uploaded_files"] = file_infos
                if not auth_token:
                    update_state["uploaded_files"] = []
                    update_state["file_analyses"] = []
                update_state = await _fill_auth_state(update_state, auth_token)
                langgraph_app.update_state(config, update_state)
                input_data: dict[str, Any] = {
                    "messages": [HumanMessage(content=user_msg)],
                    "uploaded_files": file_infos if auth_token else [],
                }
                if auth_token:
                    input_data["auth_token"] = auth_token
                    if "current_user" in update_state:
                        input_data["current_user"] = update_state["current_user"]
                return input_data, False

            # 仅在必要时同步 state：有新附件，或 state 中还没有上传文件/token。
            need_sync = (
                has_attachments
                or (not state_values.get("uploaded_files") and bool(file_infos))
                or (auth_token and not state_values.get("auth_token"))
            )
            if need_sync:
                await _sync_uploaded_files_state(
                    langgraph_app=langgraph_app,
                    config=config,
                    file_infos=file_infos,
                    auth_token=auth_token,
                    log_prefix="resume",
                )
            return Command(resume=user_msg), True

        is_file_upload_msg = is_file_upload_message(user_msg)
        if is_file_upload_msg and current_phase == ReconciliationPhase.COMPLETED.value and file_infos:
            logger.info("server: resume 场景检测到 completed 后重传文件，切换到 FILE_ANALYSIS")
            update_state: dict[str, Any] = {
                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "uploaded_files": file_infos,
                "file_analyses": [],
            }
            update_state = await _fill_auth_state(update_state, auth_token)
            langgraph_app.update_state(config, update_state)
            return {
                "messages": [HumanMessage(content=user_msg)],
                "uploaded_files": file_infos,
            }, False

        if has_attachments:
            await _sync_uploaded_files_state(
                langgraph_app=langgraph_app,
                config=config,
                file_infos=file_infos,
                auth_token=auth_token,
                log_prefix="resume",
            )
        return Command(resume=user_msg), True

    # non-resume branch
    is_file_upload_msg = is_file_upload_message(user_msg)
    try:
        snapshot = langgraph_app.get_state(config)
        current_phase = snapshot.values.get("phase", "") if snapshot else ""
        state_values = snapshot.values if snapshot else {}
        is_interrupted = bool(snapshot and getattr(snapshot, "next", None))
    except Exception:
        current_phase = ""
        state_values = {}
        is_interrupted = False

    force_resume_in_workflow = (
        is_workflow_phase(current_phase)
        and is_interrupted
        and not (is_file_upload_msg and current_phase == ReconciliationPhase.FILE_ANALYSIS.value and file_infos)
    )
    if force_resume_in_workflow and not auth_token and not is_file_upload_msg:
        # 游客 + resume=false：先做一次意图检测，避免所有输入都被强制 resume。
        try:
            intent = await classify_intent_in_workflow_guest(
                user_msg=user_msg,
                current_phase=current_phase,
                state=state_values,
            )
        except Exception:
            intent = UserIntent.RESUME_WORKFLOW.value
        if intent != UserIntent.RESUME_WORKFLOW.value:
            logger.info(f"检测到游客 workflow 切换意图 {current_phase} → {intent}，退出 workflow 走主路由")
            langgraph_app.update_state(
                config,
                {
                    "phase": "",
                    "user_intent": UserIntent.UNKNOWN.value,
                    "uploaded_files": [],
                    "file_analyses": [],
                },
            )
            input_data = {
                "messages": [HumanMessage(content=user_msg)],
                "uploaded_files": [],
            }
            return input_data, False

    if force_resume_in_workflow:
        logger.info(f"检测到 workflow 阶段 resume=false，自动按 resume 处理 (phase={current_phase})")
        if has_attachments:
            await _sync_uploaded_files_state(
                langgraph_app=langgraph_app,
                config=config,
                file_infos=file_infos,
                auth_token=auth_token,
                log_prefix="resume=false->resume",
            )
        return Command(resume=user_msg), True

    if is_file_upload_msg and current_phase == ReconciliationPhase.FILE_ANALYSIS.value and file_infos:
        logger.info("检测到 FILE_ANALYSIS 阶段上传文件，使用正常消息流程重新分析")
        update_state: dict[str, Any] = {
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "uploaded_files": file_infos,
            "file_analyses": [],
        }
        update_state = await _fill_auth_state(update_state, auth_token)
        langgraph_app.update_state(config, update_state)
        input_data = {
            "messages": [HumanMessage(content=user_msg)],
            "uploaded_files": file_infos,
        }
        if auth_token:
            input_data["auth_token"] = auth_token
            if "current_user" in update_state:
                input_data["current_user"] = update_state["current_user"]
        return input_data, False

    if is_file_upload_msg and current_phase and current_phase != ReconciliationPhase.COMPLETED.value:
        logger.info(f"检测到文件上传消息 (resume=false)，保持 phase={current_phase}，改为 resume 模式")
        await _sync_uploaded_files_state(
            langgraph_app=langgraph_app,
            config=config,
            file_infos=file_infos,
            auth_token=auth_token,
            log_prefix="resume=false[file-upload]",
        )
        return Command(resume=user_msg), True

    if is_file_upload_msg and current_phase == ReconciliationPhase.COMPLETED.value and file_infos:
        logger.info("检测到 completed 后重传文件，强制 phase=FILE_ANALYSIS")
        update_state = {
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "uploaded_files": file_infos,
            "file_analyses": [],
        }
        update_state = await _fill_auth_state(update_state, auth_token)
        langgraph_app.update_state(config, update_state)
        input_data = {
            "messages": [HumanMessage(content=user_msg)],
            "uploaded_files": file_infos,
        }
        if auth_token:
            input_data["auth_token"] = auth_token
            if "current_user" in update_state:
                input_data["current_user"] = update_state["current_user"]
        return input_data, False

    try:
        langgraph_app.update_state(config, {"phase": ""})
        logger.info("新会话: 已重置 LangGraph state")
    except Exception as e:
        logger.warning(f"重置 LangGraph state 失败: {e}")

    input_data: dict[str, Any] = {
        "messages": [HumanMessage(content=user_msg)],
        "uploaded_files": file_infos,
    }
    if auth_token:
        input_data["auth_token"] = auth_token
        from app.tools.mcp_client import auth_me

        try:
            me_result = await auth_me(auth_token)
            if me_result.get("success"):
                input_data["current_user"] = me_result["user"]
        except Exception:
            pass

    return input_data, False

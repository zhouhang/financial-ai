"""Nodes for shared scheme execution graph."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage

from models import AgentState
from graphs.recon.scheme_rule_registry import ensure_scheme_rule_saved
from graphs.recon.execution_service import (
    build_execution_request,
    build_recon_ctx_update_from_execution,
    build_recon_observation,
    normalize_recon_inputs,
    resolve_recon_inputs,
    run_recon_execution,
)
from graphs.recon.pipeline_service import execute_headless_recon_pipeline
from tools.mcp_client import (
    data_source_export_collection_records,
    execute_proc_rule,
    execution_scheme_update,
)

logger = logging.getLogger(__name__)


def _get_recon_ctx(state: AgentState) -> dict[str, Any]:
    return dict(state.get("recon_ctx") or {})


def decide_prepare_node(state: AgentState) -> dict[str, Any]:
    """Decide whether proc prepare is required before recon."""
    ctx = _get_recon_ctx(state)
    scheme = ctx.get("scheme") if isinstance(ctx.get("scheme"), dict) else {}
    scheme_meta = (
        scheme.get("scheme_meta_json")
        if isinstance(scheme.get("scheme_meta_json"), dict)
        else scheme.get("scheme_meta")
        if isinstance(scheme.get("scheme_meta"), dict)
        else scheme.get("meta")
        if isinstance(scheme.get("meta"), dict)
        else {}
    )
    proc_rule_code = str(
        ctx.get("proc_rule_code")
        or scheme.get("proc_rule_code")
        or "",
    ).strip()
    embedded_proc_rule = scheme_meta.get("proc_rule_json") if isinstance(scheme_meta, dict) else {}
    ctx["should_prepare"] = bool(proc_rule_code or isinstance(embedded_proc_rule, dict) and embedded_proc_rule)
    if proc_rule_code:
        ctx["proc_rule_code"] = proc_rule_code
    return {"recon_ctx": ctx}


async def execute_proc_node(state: AgentState) -> dict[str, Any]:
    """Execute proc for dataset-backed scheme runs and convert outputs into recon file inputs."""
    ctx = _get_recon_ctx(state)
    auth_token = str(state.get("auth_token") or "")
    scheme = ctx.get("scheme") if isinstance(ctx.get("scheme"), dict) else {}
    scheme_meta = (
        scheme.get("scheme_meta_json")
        if isinstance(scheme.get("scheme_meta_json"), dict)
        else scheme.get("scheme_meta")
        if isinstance(scheme.get("scheme_meta"), dict)
        else scheme.get("meta")
        if isinstance(scheme.get("meta"), dict)
        else {}
    )
    proc_rule_code = str(ctx.get("proc_rule_code") or scheme.get("proc_rule_code") or "").strip()
    embedded_proc_rule = scheme_meta.get("proc_rule_json") if isinstance(scheme_meta, dict) else {}

    if not proc_rule_code and isinstance(embedded_proc_rule, dict) and embedded_proc_rule:
        try:
            saved = await ensure_scheme_rule_saved(
                auth_token,
                scheme_name=str(scheme.get("scheme_name") or scheme.get("name") or ctx.get("scheme_code") or "对账方案"),
                rule_type="proc",
                rule_json=embedded_proc_rule,
                preferred_name=str(scheme_meta.get("proc_rule_name") or ""),
                remark="auto scheme run embedded proc rule",
                supported_entry_modes=["dataset"],
            )
            proc_rule_code = str(saved.get("rule_code") or "").strip()
            if proc_rule_code:
                ctx["proc_rule_code"] = proc_rule_code
                scheme["proc_rule_code"] = proc_rule_code
                if scheme.get("id"):
                    next_scheme_meta = dict(scheme_meta) if isinstance(scheme_meta, dict) else {}
                    next_scheme_meta["proc_rule_code"] = proc_rule_code
                    await execution_scheme_update(
                        auth_token,
                        str(scheme.get("id")),
                        {
                            "proc_rule_code": proc_rule_code,
                            "scheme_meta_json": next_scheme_meta,
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            ctx["prepare_status"] = "error"
            ctx["prepare_message"] = f"保存方案 proc 规则失败：{exc}"
            ctx["exec_status"] = "error"
            ctx["exec_error"] = str(exc)
            ctx["failed_stage"] = "prepare"
            return {"recon_ctx": ctx}

    if not proc_rule_code:
        ctx["prepare_status"] = "skipped"
        return {"recon_ctx": ctx}

    raw_recon_inputs = normalize_recon_inputs(list(ctx.get("recon_inputs") or []))
    dataset_inputs = [item for item in raw_recon_inputs if str(item.get("input_type") or "").strip().lower() == "dataset"]
    if not dataset_inputs:
        ctx["prepare_status"] = "skipped"
        ctx["prepare_message"] = "当前运行未提供 dataset 输入，跳过 proc。"
        return {"recon_ctx": ctx}

    uploaded_files: list[dict[str, Any]] = []
    export_records: list[dict[str, Any]] = []
    for item in dataset_inputs:
        table_name = str(item.get("table_name") or "").strip()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        dataset_ref = payload.get("dataset_ref") if isinstance(payload.get("dataset_ref"), dict) else payload
        source_id = str(dataset_ref.get("source_key") or dataset_ref.get("source_id") or "").strip()
        query = dataset_ref.get("query") if isinstance(dataset_ref.get("query"), dict) else {}
        resource_key = str(query.get("resource_key") or "").strip()
        if not source_id or not table_name:
            continue
        export_result = await data_source_export_collection_records(
            auth_token,
            source_id,
            dataset_id=str(query.get("dataset_id") or dataset_ref.get("dataset_id") or ""),
            table_name=table_name,
            resource_key=resource_key,
            biz_date=str(query.get("biz_date") or ctx.get("biz_date") or ""),
            query=query,
        )
        if not bool(export_result.get("success")):
            ctx["prepare_status"] = "error"
            ctx["prepare_message"] = str(export_result.get("error") or f"导出 {table_name} 采集记录失败")
            ctx["exec_status"] = "error"
            ctx["exec_error"] = ctx["prepare_message"]
            ctx["failed_stage"] = "prepare"
            return {"recon_ctx": ctx}
        file_path = str(export_result.get("file_path") or "").strip()
        if not file_path:
            ctx["prepare_status"] = "error"
            ctx["prepare_message"] = f"{table_name} 导出后缺少 file_path"
            ctx["exec_status"] = "error"
            ctx["exec_error"] = ctx["prepare_message"]
            ctx["failed_stage"] = "prepare"
            return {"recon_ctx": ctx}
        uploaded_files.append(
            {
                "file_name": file_path.split("/")[-1],
                "file_path": file_path,
                "table_name": table_name,
                "table_id": table_name,
            }
        )
        export_records.append(
            {
                "table_name": table_name,
                "source_id": source_id,
                "file_path": file_path,
                "dataset_id": str(export_result.get("dataset_id") or query.get("dataset_id") or ""),
                "row_count": export_result.get("row_count"),
            }
        )

    if not uploaded_files:
        ctx["prepare_status"] = "error"
        ctx["prepare_message"] = "未导出到可供 proc 使用的输入文件"
        ctx["exec_status"] = "error"
        ctx["exec_error"] = ctx["prepare_message"]
        ctx["failed_stage"] = "prepare"
        return {"recon_ctx": ctx}

    proc_result = await execute_proc_rule(
        uploaded_files=uploaded_files,
        rule_code=proc_rule_code,
        auth_token=auth_token,
    )
    if not bool(proc_result.get("success")):
        error_parts = [str(proc_result.get("error") or proc_result.get("message") or "proc 执行失败").strip()]
        error_parts.extend(str(item).strip() for item in list(proc_result.get("errors") or []) if str(item).strip())
        ctx["prepare_status"] = "error"
        ctx["prepare_message"] = "\n".join(dict.fromkeys(error_parts))
        ctx["exec_status"] = "error"
        ctx["exec_error"] = ctx["prepare_message"]
        ctx["failed_stage"] = "prepare"
        ctx["proc_result"] = proc_result
        return {"recon_ctx": ctx}

    proc_recon_inputs: list[dict[str, Any]] = []
    for item in list(proc_result.get("generated_files") or []):
        if not isinstance(item, dict):
            continue
        target_table = str(item.get("target_table") or "").strip()
        output_file = str(item.get("output_file") or "").strip()
        if not target_table or not output_file:
            continue
        proc_recon_inputs.append(
            {
                "table_name": target_table,
                "input_type": "file",
                "payload": {
                    "file_path": output_file,
                },
            }
        )

    if not proc_recon_inputs:
        ctx["prepare_status"] = "error"
        ctx["prepare_message"] = "proc 未生成可供 recon 使用的输出文件"
        ctx["exec_status"] = "error"
        ctx["exec_error"] = ctx["prepare_message"]
        ctx["failed_stage"] = "prepare"
        ctx["proc_result"] = proc_result
        return {"recon_ctx": ctx}

    ctx["recon_inputs"] = proc_recon_inputs
    ctx["proc_result"] = proc_result
    ctx["prepare_status"] = "success"
    ctx["prepare_message"] = f"已生成 {len(proc_recon_inputs)} 个整理结果，供后续对账使用。"
    ctx["proc_export_records"] = export_records
    return {"recon_ctx": ctx}


def build_recon_inputs_node(state: AgentState) -> dict[str, Any]:
    """Build recon inputs from explicit inputs or legacy file-match path."""
    ctx = _get_recon_ctx(state)
    raw_inputs = list(ctx.get("recon_inputs") or [])
    recon_inputs = normalize_recon_inputs(raw_inputs)

    if not recon_inputs:
        recon_inputs, ref_map, err = resolve_recon_inputs(state=state, ctx=ctx)
        if err:
            ctx["exec_status"] = "error"
            ctx["exec_error"] = err
            ctx["failed_stage"] = "build_inputs"
            return {"recon_ctx": ctx, "messages": [AIMessage(content=f"对账输入构建失败：{err}")]}
        ctx["ref_to_display_name"] = ref_map
    else:
        ctx["ref_to_display_name"] = dict(ctx.get("ref_to_display_name") or {})

    ctx["recon_inputs"] = recon_inputs
    return {"recon_ctx": ctx}


async def execute_recon_node(state: AgentState) -> dict[str, Any]:
    """Execute recon through the unified headless pipeline."""
    ctx = _get_recon_ctx(state)
    scheme = ctx.get("scheme") if isinstance(ctx.get("scheme"), dict) else {}
    scheme_meta = (
        scheme.get("scheme_meta_json")
        if isinstance(scheme.get("scheme_meta_json"), dict)
        else scheme.get("scheme_meta")
        if isinstance(scheme.get("scheme_meta"), dict)
        else scheme.get("meta")
        if isinstance(scheme.get("meta"), dict)
        else {}
    )
    auth_token = str(state.get("auth_token") or "")
    rule_code = str(ctx.get("rule_code") or "").strip()
    embedded_recon_rule = scheme_meta.get("recon_rule_json") if isinstance(scheme_meta, dict) else {}
    if (
        isinstance(embedded_recon_rule, dict)
        and embedded_recon_rule
        and (not str(scheme.get("recon_rule_code") or "").strip() or rule_code.startswith("embedded:"))
    ):
        try:
            saved = await ensure_scheme_rule_saved(
                auth_token,
                scheme_name=str(scheme.get("scheme_name") or scheme.get("name") or ctx.get("scheme_code") or "对账方案"),
                rule_type="recon",
                rule_json=embedded_recon_rule,
                preferred_name=str(scheme_meta.get("recon_rule_name") or ""),
                remark="auto scheme run embedded recon rule",
                supported_entry_modes=["dataset"],
            )
            saved_rule_code = str(saved.get("rule_code") or "").strip()
            if saved_rule_code:
                rule_code = saved_rule_code
                ctx["rule_code"] = saved_rule_code
                scheme["recon_rule_code"] = saved_rule_code
                if scheme.get("id"):
                    next_scheme_meta = dict(scheme_meta) if isinstance(scheme_meta, dict) else {}
                    next_scheme_meta["recon_rule_code"] = saved_rule_code
                    await execution_scheme_update(
                        auth_token,
                        str(scheme.get("id")),
                        {
                            "recon_rule_code": saved_rule_code,
                            "scheme_meta_json": next_scheme_meta,
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            ctx["exec_status"] = "error"
            ctx["exec_error"] = f"保存方案 recon 规则失败：{exc}"
            ctx["failed_stage"] = "config"
            return {"recon_ctx": ctx, "messages": [AIMessage(content=f"执行失败：{ctx['exec_error']}")]}

    if not rule_code:
        ctx["exec_status"] = "error"
        ctx["exec_error"] = "缺少 recon rule_code"
        ctx["failed_stage"] = "config"
        return {"recon_ctx": ctx, "messages": [AIMessage(content="执行失败：缺少对账规则。")]}

    rule = ctx.get("rule") if isinstance(ctx.get("rule"), dict) else {}
    rule_name = str(ctx.get("rule_name") or rule_code).strip()
    run_context = ctx.get("run_context") if isinstance(ctx.get("run_context"), dict) else {}
    trigger_type = str(run_context.get("trigger_type") or "chat")
    entry_mode = str(run_context.get("entry_mode") or "file")

    pipeline_result = await execute_headless_recon_pipeline(
        rule_code=rule_code,
        rule_id=str(ctx.get("rule_id") or ""),
        rule_name=rule_name,
        rule=rule,
        auth_token=auth_token,
        recon_inputs=list(ctx.get("recon_inputs") or []),
        run_context=run_context,
        run_id=str(ctx.get("run_id") or run_context.get("run_id") or ""),
        trigger_type=trigger_type,
        entry_mode=entry_mode,
        ref_to_display_name=dict(ctx.get("ref_to_display_name") or {}),
        build_execution_request_fn=build_execution_request,
        run_recon_execution_fn=run_recon_execution,
        build_recon_observation_fn=build_recon_observation,
        build_recon_ctx_update_fn=build_recon_ctx_update_from_execution,
    )

    ctx.update(
        {
            "exec_status": str(pipeline_result.get("execution_status") or "error"),
            "exec_error": str(pipeline_result.get("exec_error") or ""),
            "recon_result": pipeline_result.get("execution_result")
            if isinstance(pipeline_result.get("execution_result"), dict)
            else {},
            "execution_result": pipeline_result.get("execution_result")
            if isinstance(pipeline_result.get("execution_result"), dict)
            else {},
            "recon_observation": pipeline_result.get("recon_observation")
            if isinstance(pipeline_result.get("recon_observation"), dict)
            else {},
            "run_context": pipeline_result.get("run_context")
            if isinstance(pipeline_result.get("run_context"), dict)
            else run_context,
        }
    )

    ctx_update = pipeline_result.get("ctx_update")
    if isinstance(ctx_update, dict):
        ctx.update(ctx_update)

    if not bool(pipeline_result.get("ok")):
        failure_stage = str(pipeline_result.get("failure_stage") or "recon").strip() or "recon"
        ctx["failed_stage"] = failure_stage
        if not ctx.get("exec_error"):
            ctx["exec_error"] = "对账执行失败"
        logger.error("[scheme_execution] recon failed stage=%s err=%s", failure_stage, ctx["exec_error"])
        return {
            "recon_ctx": ctx,
            "messages": [AIMessage(content=f"对账执行失败：{ctx['exec_error']}")],
        }

    return {"recon_ctx": ctx}


def build_recon_observation_node(state: AgentState) -> dict[str, Any]:
    """Finalize shared execution output contract."""
    ctx = _get_recon_ctx(state)
    status = str(ctx.get("exec_status") or "error")
    if status in {"success", "partial_success", "skipped"}:
        ctx["phase"] = "completed"
    else:
        ctx["phase"] = "exec_failed"
    return {"recon_ctx": ctx}

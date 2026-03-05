"""对账执行与结果节点模块。"""

from __future__ import annotations

import asyncio
import ast
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langgraph.types import interrupt

from app.models import AgentState, ReconciliationPhase, TaskExecutionStep
from app.tools.mcp_client import (
    get_reconciliation_result,
    get_reconciliation_status,
    list_available_rules,
    start_reconciliation,
)
from app.utils.llm import get_llm

logger = logging.getLogger(__name__)


RESULT_ANALYSIS_PROMPT = """\
你是对账结果分析助手。请用简洁友好的语言描述对账结果。

对账结果数据：
{result_json}

重要要求：
1. 善用 Markdown 排版（**加粗**、- 列表、标题等）增强可读性
2. 使用 Emoji 图标增强可读性
3. 语言言简意赅，简洁直白，易于理解
4. 文件名不要包含时间戳，使用原始上传的文件名
5. 对账概览和异常明细中，必须使用 summary.business_file 和 summary.finance_file 的真实文件名，不要使用「文件1」「文件2」「业务文件」「财务文件」等占位符
6. 【关键】差异/异常的总条数必须使用 summary.unmatched_records（或 issues_count），切勿使用 total_business_records 或 total_finance_records。例如差异列表标题应写「差异 (10条)」而非「差异 (985条)」

示例格式（假设 summary.business_file=销售数据.xlsx, summary.finance_file=财务报表.xlsx）：

✅ 对账完成

**对账概览**
- **销售数据.xlsx:** (100条)
- **财务报表.xlsx:** (98条)
- **匹配成功:** 95条
- **异常记录:** 5条
- **匹配率:** 95%

异常明细（必须用表格展示，表头为「异常订单号」「异常原因」，每行一条数据，异常原因中用真实文件名）：

| 异常订单号 | 异常原因 |
|-----------|----------|
| 订单A001 | 销售数据.xlsx存在，财务报表.xlsx无此订单记录 |
| 订单A002 | 销售数据.xlsx存在，财务报表.xlsx无此订单记录 |
| 订单B001 | 销售数据.xlsx与财务报表.xlsx金额差异（差异0.5元） |
| 订单B002 | 销售数据.xlsx与财务报表.xlsx金额差异（差异1.2元） |

注意：
- 异常明细必须使用 Markdown 表格，表头固定为「异常订单号」「异常原因」
- 每行一条异常记录，从 issues 中按 order_id 和 detail 提取
- 若 issues 的 detail 中有「文件1」「文件2」，必须替换为 summary.business_file 和 summary.finance_file 的真实文件名
- 如果某类型订单数超过20条，只列前20个并在表格后注明「（共N条，仅列前20条）」
"""


def _extract_line_payload(error_detail: str, prefix: str) -> str:
    for raw_line in (error_detail or "").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _build_field_roles_table(field_roles: dict[str, Any]) -> str:
    ordered_roles = ["date", "amount", "order_id", "status"]
    columns: list[str] = []

    for role in ordered_roles:
        if role not in field_roles:
            continue
        role_value = field_roles[role]
        if isinstance(role_value, list):
            valid_cols = [str(x) for x in role_value if str(x).strip()]
            if valid_cols:
                columns.append(" 或 ".join(valid_cols))
        else:
            col_name = str(role_value).strip()
            if col_name:
                columns.append(col_name)

    if not columns:
        for role_value in field_roles.values():
            if isinstance(role_value, list):
                valid_cols = [str(x) for x in role_value if str(x).strip()]
                if valid_cols:
                    columns.append(" 或 ".join(valid_cols))
            else:
                col_name = str(role_value).strip()
                if col_name:
                    columns.append(col_name)

    if not columns:
        return "（未配置列名要求）"

    table_html = ['<table class="text-sm min-w-max">']
    table_html.append("  <thead>")
    table_html.append('    <tr class="bg-gray-50">')
    for col in columns:
        table_html.append(
            f'      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">{col}</th>'
        )
    table_html.append("    </tr>")
    table_html.append("  </thead>")
    table_html.append("</table>")
    return "\n".join(table_html)


def _format_file_mapping_error_message(error_detail: str, rule_name: str) -> str | None:
    if not error_detail:
        return None
    if "business.field_roles:" not in error_detail or "finance.field_roles:" not in error_detail:
        return None

    biz_text = _extract_line_payload(error_detail, "business.field_roles:")
    fin_text = _extract_line_payload(error_detail, "finance.field_roles:")
    unmatched_text = _extract_line_payload(error_detail, "未匹配文件:")

    try:
        biz_roles = ast.literal_eval(biz_text) if biz_text else {}
    except Exception:
        biz_roles = {}
    try:
        fin_roles = ast.literal_eval(fin_text) if fin_text else {}
    except Exception:
        fin_roles = {}
    try:
        unmatched_files = ast.literal_eval(unmatched_text) if unmatched_text else []
    except Exception:
        unmatched_files = []

    if not isinstance(biz_roles, dict) or not isinstance(fin_roles, dict):
        return None
    if not isinstance(unmatched_files, list):
        unmatched_files = []

    biz_table = _build_field_roles_table(biz_roles)
    fin_table = _build_field_roles_table(fin_roles)

    lines = [
        f"### ❌ 上传文件列名未能与「{rule_name}」匹配",
        "",
        f"{rule_name}规则要求文件列名如下",
        "",
        "#### 文件1列名要求",
        biz_table,
        "",
        "#### 文件2列名要求",
        fin_table,
    ]

    if unmatched_files:
        lines.extend(["", "#### 未匹配文件："])
        lines.extend([f"- `{name}`" for name in unmatched_files])

    return "\n".join(lines)


def _is_upload_validation_error(error_detail: str) -> bool:
    if not error_detail:
        return False
    keywords = [
        "未匹配文件",
        "business.field_roles:",
        "finance.field_roles:",
        "上传了",
        "对账只需要2个文件",
        "文件格式验证失败",
        "只有一个文件",
        "不支持的文件格式",
    ]
    return any(k in error_detail for k in keywords)


async def _do_start_task(
    auth_token: str,
    rule_name: str,
    files: list[str],
    guest_token: str = None,
    rule_template: dict = None,
) -> dict[str, Any]:
    if rule_template:
        return await start_reconciliation(
            files=files,
            rule_template=rule_template,
            auth_token=auth_token,
            guest_token=guest_token,
        )
    return await start_reconciliation(
        files=files,
        rule_name=rule_name,
        auth_token=auth_token,
        guest_token=guest_token,
    )


async def _do_poll(
    auth_token: str,
    task_id: str,
    guest_token: str = None,
    progress_callback=None,
    max_polls: int = 60,
    interval: float = 1.0,
) -> dict[str, Any]:
    progress_messages_with_timing = [
        (0, "📊 正在加载数据文件 {{SPINNER}}"),
        (5, "🔍 正在分析数据结构 {{SPINNER}}"),
        (15, "⚙️  正在执行对账规则 {{SPINNER}}"),
        (30, "📈 正在生成对账结果 {{SPINNER}}"),
        (45, "✨ 即将完成 {{SPINNER}}"),
    ]

    collected_progress = []
    last_message_idx = -1

    for poll_count in range(max_polls):
        status = await get_reconciliation_status(task_id, auth_token=auth_token, guest_token=guest_token)
        st = status.get("status", "")

        for idx, (timing, message) in enumerate(progress_messages_with_timing):
            if poll_count >= timing and idx > last_message_idx:
                collected_progress.append(message)
                last_message_idx = idx
                logger.info("对账进度 [%ss]: %s", poll_count, message)

        if st in ("completed", "failed", "error"):
            result = status.copy()
            result["progress_messages"] = collected_progress
            return result

        await asyncio.sleep(interval)

    return {
        "status": "timeout",
        "task_id": task_id,
        "progress_messages": collected_progress,
    }


def _run_async_safe(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


def task_execution_node(state: AgentState) -> dict:
    generated_schema = state.get("generated_schema")
    rule_name = state.get("selected_rule_name") or state.get("saved_rule_name")
    auth_token = state.get("auth_token", "")
    guest_token = state.get("guest_token", "")
    uploaded_files = state.get("uploaded_files", [])

    state.pop("task_id", None)
    state.pop("task_result", None)
    state.pop("task_status", None)

    use_rule_template = bool(generated_schema)
    display_name = rule_name or ("新规则_待确认" if use_rule_template else "")

    if not rule_name and not use_rule_template:
        return {
            "messages": [AIMessage(content="缺少对账规则名称，请先选择或创建一个规则。")],
            "phase": ReconciliationPhase.IDLE.value,
        }

    files = []
    for item in uploaded_files:
        if isinstance(item, dict):
            file_path = item.get("file_path", "")
            if file_path:
                files.append(file_path)
        else:
            files.append(item)

    if not files and use_rule_template:
        analyses = state.get("file_analyses", [])
        for a in analyses:
            fp = a.get("file_path", "")
            if fp:
                files.append(fp)
        if files:
            logger.info("从 file_analyses 恢复文件路径: %s 个", len(files))

    if not files:
        user_response = interrupt({
            "question": "请上传需要对账的文件",
            "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
        })
        response_str = (user_response or "").strip().lower()
        list_rules_keywords = ("规则列表", "看看规则", "有哪些规则", "规则有哪些", "我的规则", "查看规则")
        if any(kw in response_str for kw in list_rules_keywords):
            rules = _run_async_safe(list_available_rules(auth_token or guest_token))
            if rules:
                lines = ["📋 **我的对账规则列表**\n"]
                for r in rules:
                    lines.append(f"• **{r['name']}**")
                msg = "\n".join(lines)
            else:
                msg = "📋 暂无对账规则。\n\n你可以说「创建新规则」来创建第一个对账规则。"
            return {
                "messages": [AIMessage(content=msg)],
                "phase": ReconciliationPhase.COMPLETED.value,
                "selected_rule_name": None,
            }
        return {
            "messages": [],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    if not auth_token and not guest_token:
        return {
            "messages": [AIMessage(content="❌ 缺少认证信息，请先登录或使用游客模式")],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    logger.info("开始执行对账任务: rule=%s, use_template=%s, files=%s个", display_name, use_rule_template, len(files))
    start_result = _run_async_safe(_do_start_task(
        auth_token if auth_token else "",
        rule_name or display_name,
        files,
        guest_token=guest_token if guest_token else None,
        rule_template=generated_schema if use_rule_template else None,
    ))

    if "error" in start_result:
        return {
            "messages": [AIMessage(content=f"❌ 启动对账任务失败：{start_result['error']}")],
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
        }

    task_id = start_result.get("task_id", "")

    file_display_names = []
    if uploaded_files:
        for item in uploaded_files:
            if isinstance(item, dict):
                name = item.get("original_filename") or item.get("file_path", "")
            else:
                name = str(item)
            if name:
                file_display_names.append(name.split("/")[-1].split("\\")[-1])
    elif files:
        for a in state.get("file_analyses", []):
            name = a.get("original_filename") or a.get("file_path", "")
            if name:
                file_display_names.append(name.split("/")[-1].split("\\")[-1])
    if not file_display_names:
        file_display_names = [f.split("/")[-1].split("\\")[-1] for f in files if f]

    detail_lines = [f"- 规则：{display_name}"]
    if file_display_names:
        for fn in file_display_names:
            detail_lines.append(f"- {fn}")
    else:
        detail_lines.append(f"- 文件：{len(files)} 个")

    messages_to_send = [
        AIMessage(content=(
            f"🚀 对账任务已启动\n\n"
            f"{chr(10).join(detail_lines)}\n\n"
            f"⏳ 正在执行对账，预计需要 10-60 秒\n\n"
            f"进度：开始加载数据"
        )),
    ]

    logger.info("开始轮询任务状态: task_id=%s", task_id)
    poll_result = _run_async_safe(_do_poll(auth_token or "", task_id, guest_token=guest_token))

    status = poll_result.get("status", "")
    logger.info("轮询结束: task_id=%s, status=%s", task_id, status)

    if status == "completed":
        try:
            result = _run_async_safe(get_reconciliation_result(task_id, auth_token=auth_token or "", guest_token=guest_token))
            return {
                "messages": messages_to_send,
                "task_id": task_id,
                "task_status": "completed",
                "task_result": result,
                "phase": ReconciliationPhase.TASK_EXECUTION.value,
                "execution_step": TaskExecutionStep.SHOWING_RESULT.value,
            }
        except Exception as e:
            logger.error("获取对账结果出错: task_id=%s, error=%s", task_id, e, exc_info=True)
            messages_to_send.append(AIMessage(content=f"❌ 获取对账结果失败：{str(e)}"))
            return {
                "messages": messages_to_send,
                "task_id": task_id,
                "task_status": "error",
                "phase": ReconciliationPhase.COMPLETED.value,
                "execution_step": TaskExecutionStep.DONE.value,
            }

    if status == "timeout":
        messages_to_send.append(AIMessage(content="⏱️ 对账任务超时，任务可能仍在后台执行，请稍后查询。"))
        return {
            "messages": messages_to_send,
            "task_id": task_id,
            "task_status": status,
            "phase": ReconciliationPhase.COMPLETED.value,
            "execution_step": TaskExecutionStep.DONE.value,
        }

    error_detail = poll_result.get("error", "")
    if _is_upload_validation_error(error_detail):
        formatted_mapping_error = _format_file_mapping_error_message(
            error_detail=error_detail,
            rule_name=display_name,
        )
        err_msg = formatted_mapping_error or f"❌ {error_detail}" if error_detail else "❌ 上传文件不符合要求，请重新上传。"
        messages_to_send.append(AIMessage(content=err_msg))
        return {
            "messages": messages_to_send,
            "task_id": task_id,
            "task_status": status,
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
            "uploaded_files": [],
            "file_analyses": [],
        }

    err_msg = f"❌ 对账任务失败（状态: {status}）"
    if error_detail:
        formatted_mapping_error = _format_file_mapping_error_message(
            error_detail=error_detail,
            rule_name=display_name,
        )
        if formatted_mapping_error:
            err_msg = formatted_mapping_error
        else:
            err_msg += f"\n\n{error_detail}"
    else:
        err_msg += "，请检查日志或重试。"
    messages_to_send.append(AIMessage(content=err_msg))
    return {
        "messages": messages_to_send,
        "task_id": task_id,
        "task_status": status,
        "phase": ReconciliationPhase.COMPLETED.value,
        "execution_step": TaskExecutionStep.DONE.value,
    }


def result_analysis_node(state: AgentState) -> dict:
    task_result = state.get("task_result")
    task_status = state.get("task_status", "")

    if task_status != "completed" or not task_result:
        logger.info("跳过结果分析: task_status=%s", task_status)
        return {
            "phase": state.get("phase", ReconciliationPhase.COMPLETED.value),
            "execution_step": state.get("execution_step", TaskExecutionStep.DONE.value),
            "selected_rule_name": state.get("selected_rule_name"),
        }

    summary = task_result.get("summary", {})
    issues = task_result.get("issues", [])
    unmatched_count = summary.get("unmatched_records", len(issues))

    result_for_llm = {
        "summary": summary,
        "issues_count": len(issues),
        "unmatched_records": unmatched_count,
        "issues": issues[:50],
    }

    result_json = json.dumps(result_for_llm, ensure_ascii=False, indent=2, default=str)
    llm = get_llm()
    prompt = RESULT_ANALYSIS_PROMPT.replace("{result_json}", result_json, 1)
    resp = llm.invoke([SystemMessage(content=prompt)])

    return {
        "messages": [AIMessage(content=resp.content)],
        "phase": ReconciliationPhase.COMPLETED.value,
        "execution_step": TaskExecutionStep.DONE.value,
        "selected_rule_name": None,
    }


def ask_start_now_node(state: AgentState) -> dict:
    user_response = interrupt({
        "question": "是否立即开始对账？",
        "hint": "回复\"开始\"立即执行，或\"稍后\"退出",
    })

    response_str = str(user_response).strip()
    if response_str in ("开始", "是", "yes", "ok", "好", "执行", "立即开始"):
        return {
            "messages": [AIMessage(content="好的，开始执行对账 {{SPINNER}}")],
            "selected_rule_name": state.get("saved_rule_name"),
            "phase": ReconciliationPhase.TASK_EXECUTION.value,
            "execution_step": TaskExecutionStep.NOT_STARTED.value,
            "uploaded_files": state.get("uploaded_files", []),
        }
    return {
        "messages": [AIMessage(content="好的，你可以随时回来执行对账。")],
        "phase": ReconciliationPhase.COMPLETED.value,
    }


__all__ = [
    "_do_start_task",
    "_do_poll",
    "_run_async_safe",
    "task_execution_node",
    "result_analysis_node",
    "ask_start_now_node",
]

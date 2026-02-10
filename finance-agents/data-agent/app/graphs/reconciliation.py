"""对账子图 (Sub-Graph) — 第2层：规则生成工作流

节点流程：
  file_analysis → field_mapping (HITL) → rule_config (HITL) → validation_preview (HITL) → save_rule

每个 HITL 节点通过 interrupt 暂停，等待用户确认后继续。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt, Command

from app.models import AgentState, ReconciliationPhase
from app.utils.file_analysis import analyse_file, analyse_files_with_llm
from app.utils.schema_builder import build_schema
from app.tools.mcp_client import save_schema_to_config, list_available_rules
from app.utils.db import save_rule as db_save_rule

logger = logging.getLogger(__name__)


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _format_field_mappings(mappings: dict[str, Any]) -> str:
    """将字段映射格式化为可读字符串。"""
    lines: list[str] = []
    for source in ("business", "finance"):
        src_map = mappings.get(source, {})
        if not src_map:
            continue
        label = "业务数据" if source == "business" else "财务数据"
        lines.append(f"\n【{label}】")
        for role, col in src_map.items():
            if isinstance(col, list):
                col_str = " / ".join(col)
            else:
                col_str = str(col)
            lines.append(f"  {role} ← {col_str}")
    return "\n".join(lines)


def _guess_field_mappings(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """使用 LLM 智能猜测字段映射：原始列名 → 标准角色。"""
    import json as _json
    from app.utils.llm import get_llm

    mappings: dict[str, dict] = {"business": {}, "finance": {}}

    # 构建文件信息
    files_info = []
    for a in analyses:
        if "error" in a or not a.get("guessed_source"):
            continue
        cols_str = ", ".join(a.get("columns", []))
        sample_str = ""
        for row in a.get("sample_data", [])[:3]:
            sample_str += "  " + str(row) + "\n"
        files_info.append(
            f"文件: {a['filename']} (类型: {a['guessed_source']})\n"
            f"  列名: {cols_str}\n"
            f"  示例数据:\n{sample_str}"
        )

    if not files_info:
        return mappings

    prompt = (
        "你是一个财务数据分析专家。以下是用户上传的对账文件信息。\n"
        "请为每个文件的列名匹配到以下标准角色：\n"
        "- order_id: 订单号/交易号（用于两边数据匹配的关键字段）\n"
        "- amount: 金额\n"
        "- date: 日期/时间\n"
        "- status: 订单状态（可选）\n\n"
        "如果一个角色可能对应多个列名，全部列出。\n"
        "如果某个角色没有对应的列，不要包含。\n\n"
        + "\n".join(files_info)
        + "\n\n请严格按以下 JSON 格式回复，不要添加其他内容：\n"
        '{"business": {"order_id": "列名或[列名1,列名2]", "amount": "...", ...}, '
        '"finance": {"order_id": "...", "amount": "...", ...}}'
    )

    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()

        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)

        parsed = _json.loads(content)
        for source in ("business", "finance"):
            if source in parsed and isinstance(parsed[source], dict):
                mappings[source] = parsed[source]

    except Exception as e:
        logger.warning(f"LLM 字段映射猜测失败: {e}")

    return mappings


# ── 节点函数 ─────────────────────────────────────────────────────────────────

def file_analysis_node(state: AgentState) -> dict:
    """第1步：分析上传的文件，提取列名和样本数据。"""
    uploaded = state.get("uploaded_files", [])
    if not uploaded:
        return {
            "messages": [AIMessage(content="请先上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。")],
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
        }

    analyses: list[dict] = []
    for fp in uploaded:
        result = analyse_file(fp)
        analyses.append(result)

    # 使用 LLM 判断文件类型（business / finance）
    analyses = analyse_files_with_llm(analyses)

    # 使用 LLM 猜测字段映射
    suggested = _guess_field_mappings(analyses)

    # 构建分析摘要
    summary_parts: list[str] = ["文件分析完成：\n"]
    for a in analyses:
        src_label = {"business": "业务数据", "finance": "财务数据"}.get(a.get("guessed_source", ""), "未识别")
        summary_parts.append(f"📄 **{a['filename']}** ({src_label})")
        summary_parts.append(f"   列数: {len(a.get('columns', []))}  行数: {a.get('row_count', 0)}")
        summary_parts.append(f"   列名: {', '.join(a.get('columns', [])[:10])}{'...' if len(a.get('columns', [])) > 10 else ''}")
        summary_parts.append("")

    summary_parts.append("建议的字段映射：")
    summary_parts.append(_format_field_mappings(suggested))
    summary_parts.append('\n这些映射正确吗？（回复"确认"继续，或告诉我需要调整哪个）')

    msg = "\n".join(summary_parts)

    return {
        "messages": [AIMessage(content=msg)],
        "file_analyses": analyses,
        "suggested_mappings": suggested,
        "phase": ReconciliationPhase.FIELD_MAPPING.value,
    }


def field_mapping_node(state: AgentState) -> dict:
    """第2步 (HITL)：等待用户确认或修改字段映射。"""
    suggested = state.get("suggested_mappings", {})
    # interrupt 暂停，等待用户输入
    user_response = interrupt({
        "question": "请确认字段映射",
        "suggested_mappings": suggested,
        "hint": '回复"确认"继续，或描述需要的调整',
    })

    response_str = str(user_response).strip()

    if response_str in ("确认", "ok", "OK", "yes", "确定", "对", "没问题"):
        confirmed = suggested
    else:
        # 用户提供了修改意见，保留原映射但标记需要AI处理
        confirmed = suggested  # 实际场景中可由AI解析用户的修改意见
        return {
            "messages": [AIMessage(content=f"已记录你的调整意见：{response_str}\n我已更新映射。继续进行规则配置。")],
            "confirmed_mappings": confirmed,
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }

    return {
        "messages": [AIMessage(content="字段映射已确认。接下来配置对账规则。")],
        "confirmed_mappings": confirmed,
        "phase": ReconciliationPhase.RULE_CONFIG.value,
    }


def rule_config_node(state: AgentState) -> dict:
    """第3步 (HITL)：引导用户配置规则参数（订单号特征、容差、状态检查）。"""
    questions = [
        {
            "key": "order_id_pattern",
            "text": (
                "订单号有什么特征吗？\n"
                "例如：\n"
                "• 都是104开头\n"
                "• 都是L开头\n"
                "• 没有特殊特征\n\n"
                "请告诉我订单号的特征。"
            ),
        },
        {
            "key": "amount_tolerance",
            "text": (
                "金额差异容差设置为多少？\n"
                "建议：0.1元（即10分钱以内的差异会被忽略）\n\n"
                "你可以：\n"
                "• 回复\"0.1\" - 使用建议值\n"
                "• 回复其他数字 - 自定义"
            ),
        },
        {
            "key": "check_order_status",
            "text": (
                "是否需要检查订单状态？\n"
                "• 回复\"需要\" - 只对比成功的订单\n"
                "• 回复\"不需要\" - 对比所有订单"
            ),
        },
    ]

    # 使用一次 interrupt 收集所有配置
    prompt_text = "\n\n---\n\n".join([q["text"] for q in questions])
    user_response = interrupt({
        "question": "请配置对账规则参数",
        "prompts": questions,
        "hint": "请依次回答以上问题，用换行分隔每个答案",
    })

    response_str = str(user_response).strip()
    lines = [l.strip() for l in response_str.split("\n") if l.strip()]

    # 解析回答
    answers: dict[str, Any] = {}

    # 订单号特征
    if lines:
        pattern = lines[0]
        if pattern in ("没有", "无", "没有特殊特征", "无特征"):
            answers["order_id_pattern"] = None
        else:
            # 提取开头特征
            match = re.search(r"(\d+|[A-Za-z]+)", pattern)
            answers["order_id_pattern"] = match.group(1) if match else None
    else:
        answers["order_id_pattern"] = None

    # 金额容差
    if len(lines) > 1:
        try:
            answers["amount_tolerance"] = float(lines[1])
        except ValueError:
            answers["amount_tolerance"] = 0.1
    else:
        answers["amount_tolerance"] = 0.1

    # 状态检查
    if len(lines) > 2:
        answers["check_order_status"] = lines[2] not in ("不需要", "不用", "no", "否")
    else:
        answers["check_order_status"] = True

    summary = (
        f"规则配置：\n"
        f"• 订单号特征：{answers['order_id_pattern'] or '无特殊特征'}\n"
        f"• 金额容差：{answers['amount_tolerance']}元\n"
        f"• 检查订单状态：{'是' if answers['check_order_status'] else '否'}\n\n"
        f"正在生成规则并预览效果..."
    )

    return {
        "messages": [AIMessage(content=summary)],
        "rule_config_answers": answers,
        "phase": ReconciliationPhase.VALIDATION_PREVIEW.value,
    }


def validation_preview_node(state: AgentState) -> dict:
    """第4步 (HITL)：生成规则 schema，预览对账效果，等待用户确认。"""
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    answers = state.get("rule_config_answers", {})
    analyses = state.get("file_analyses", [])

    # 提取文件模式
    biz_patterns: list[str] = []
    fin_patterns: list[str] = []
    for a in analyses:
        src = a.get("guessed_source")
        fn = a.get("filename", "")
        if src == "business":
            biz_patterns.append(f"*{fn}*" if "*" not in fn else fn)
        elif src == "finance":
            fin_patterns.append(f"*{fn}*" if "*" not in fn else fn)

    if not biz_patterns:
        biz_patterns = ["*.xlsx"]
    if not fin_patterns:
        fin_patterns = ["*.xlsx"]

    biz_field_roles = mappings.get("business", {})
    fin_field_roles = mappings.get("finance", {})

    # 构建 schema
    schema = build_schema(
        description="用户自定义对账规则",
        business_file_patterns=biz_patterns,
        finance_file_patterns=fin_patterns,
        business_field_roles=biz_field_roles,
        finance_field_roles=fin_field_roles,
        order_id_pattern=answers.get("order_id_pattern"),
        amount_tolerance=answers.get("amount_tolerance", 0.1),
        check_order_status=answers.get("check_order_status", True),
    )

    # 简单预览（统计匹配信息）
    preview = _preview_schema(schema, analyses)

    preview_text = (
        f"规则已生成！预览结果（基于上传文件）：\n"
        f"• 业务记录数：{preview.get('biz_count', 'N/A')}\n"
        f"• 财务记录数：{preview.get('fin_count', 'N/A')}\n"
        f"• 预计匹配：{preview.get('estimated_match', 'N/A')}条\n"
        f"• 验证规则数：{len(schema.get('custom_validations', []))}条\n\n"
        f"规则看起来合理吗？（回复\"保存\"继续，或\"调整\"重新配置）"
    )

    user_response = interrupt({
        "question": "请确认规则预览",
        "preview": preview,
        "schema_summary": {
            "validations": len(schema.get("custom_validations", [])),
            "biz_patterns": biz_patterns,
            "fin_patterns": fin_patterns,
        },
        "hint": "回复\"保存\"继续，或\"调整\"重新配置",
    })

    response_str = str(user_response).strip()

    if response_str in ("调整", "重新配置", "重来", "adjust"):
        return {
            "messages": [AIMessage(content="好的，让我们重新配置规则参数。")],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
            "generated_schema": None,
        }

    return {
        "messages": [AIMessage(content="规则确认完毕，准备保存。请为这个规则起个名字（例如：\"直销对账\"）。")],
        "generated_schema": schema,
        "preview_result": preview,
        "phase": ReconciliationPhase.SAVE_RULE.value,
    }


def save_rule_node(state: AgentState) -> dict:
    """第5步 (HITL)：保存规则，询问用户是否立即开始对账。"""
    schema = state.get("generated_schema")
    if not schema:
        return {
            "messages": [AIMessage(content="没有找到已生成的规则，请重新配置。")],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }

    user_response = interrupt({
        "question": "请为这个规则命名",
        "hint": "输入规则名称，例如：直销对账",
    })

    rule_name = str(user_response).strip()
    if not rule_name:
        rule_name = "自定义对账规则"

    # 生成 type_key
    type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name.lower())
    if not type_key or type_key[0].isdigit():
        type_key = "rule_" + type_key

    # 保存到 schema 配置文件
    try:
        save_schema_to_config(rule_name, type_key, schema)
    except Exception as e:
        logger.error(f"保存 schema 到配置失败: {e}")

    # 保存到数据库
    try:
        db_save_rule(rule_name, type_key, schema, description=schema.get("description", ""))
    except Exception as e:
        logger.error(f"保存规则到数据库失败: {e}")

    msg = (
        f"规则 **{rule_name}** 已保存！\n\n"
        f"现在可以用它开始对账了。要立即开始吗？\n"
        f"（回复\"开始\"立即执行对账，或稍后再说）"
    )

    return {
        "messages": [AIMessage(content=msg)],
        "saved_rule_name": rule_name,
        "phase": ReconciliationPhase.COMPLETED.value,
    }


# ── 辅助：预览 ───────────────────────────────────────────────────────────────

def _preview_schema(schema: dict, analyses: list[dict]) -> dict:
    """简单统计预览。"""
    biz_count = 0
    fin_count = 0
    for a in analyses:
        src = a.get("guessed_source")
        cnt = a.get("row_count", 0)
        if src == "business":
            biz_count += cnt
        elif src == "finance":
            fin_count += cnt

    estimated_match = min(biz_count, fin_count)
    return {
        "biz_count": biz_count,
        "fin_count": fin_count,
        "estimated_match": estimated_match,
    }


# ── 路由函数 ─────────────────────────────────────────────────────────────────

def route_after_preview(state: AgentState) -> str:
    """预览后路由：如果用户选择调整则回到 rule_config，否则进入 save_rule。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"
    return "save_rule"


# ── 构建子图 ─────────────────────────────────────────────────────────────────

def build_reconciliation_subgraph() -> StateGraph:
    """构建对账规则生成子图（第2层）。"""
    sg = StateGraph(AgentState)

    sg.add_node("file_analysis", file_analysis_node)
    sg.add_node("field_mapping", field_mapping_node)
    sg.add_node("rule_config", rule_config_node)
    sg.add_node("validation_preview", validation_preview_node)
    sg.add_node("save_rule", save_rule_node)

    sg.set_entry_point("file_analysis")
    sg.add_edge("file_analysis", "field_mapping")
    sg.add_edge("field_mapping", "rule_config")
    sg.add_edge("rule_config", "validation_preview")
    sg.add_conditional_edges("validation_preview", route_after_preview, {
        "rule_config": "rule_config",
        "save_rule": "save_rule",
    })
    sg.add_edge("save_rule", END)

    return sg

"""对账子图 (Sub-Graph) — 第2层：规则生成工作流

节点流程：
  file_analysis → field_mapping (HITL) → rule_config (HITL) → validation_preview (HITL) → save_rule

每个 HITL 节点通过 interrupt 暂停，等待用户确认后继续。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt, Command

from app.models import AgentState, ReconciliationPhase
from app.utils.schema_builder import build_schema
from app.tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _adjust_field_mappings_with_llm(
    current_mappings: dict[str, Any],
    user_instruction: str,
    analyses: list[dict[str, Any]]
) -> dict[str, Any]:
    """使用 LLM 根据用户指令调整字段映射。"""
    import json as _json
    from app.utils.llm import get_llm
    
    # 构建当前映射的描述
    current_desc = []
    for source in ("business", "finance"):
        src_map = current_mappings.get(source, {})
        if src_map:
            label = "文件1" if source == "business" else "文件2"
            filename = ""
            for a in analyses:
                if a.get("guessed_source") == source:
                    filename = a.get("filename", "")
                    break
            current_desc.append(f"{label} ({filename}):")
        for role, col in src_map.items():
            if isinstance(col, list):
                col_str = ", ".join(col)
            else:
                col_str = str(col)
            current_desc.append(f"  {role}: {col_str}")
    
    current_mapping_str = "\n".join(current_desc)
    
    # 构建可用列名
    available_cols = []
    for a in analyses:
        source = a.get("guessed_source", "")
        filename = a.get("filename", "")
        cols = a.get("columns", [])
        available_cols.append(f"{filename}: {', '.join(cols[:20])}")
    
    available_cols_str = "\n".join(available_cols)
    
    prompt = f"""你是一个字段映射调整助手。用户上传了两个文件，当前的字段映射如下：

{current_mapping_str}

可用的列名：
{available_cols_str}

用户的调整指令：
{user_instruction}

请根据用户的指令，调整字段映射。严格按以下 JSON 格式返回，不要添加其他内容：
{{"business": {{"order_id": "列名或[列名1, 列名2]", "amount": "...", "date": "...", "status": "..."}}, 
 "finance": {{"order_id": "...", "amount": "...", "date": "...", "status": "..."}}}}

⚠️ 重要规则：
1. order_id、amount、date 是必需的，status 是可选的
2. 如果用户说"去掉XX"，则从列表中移除该列名（其他字段保持不变）
3. 如果用户说"只保留XX"，则只保留指定的列名（其他字段保持不变）
4. **必须返回完整的映射（包括用户未提到的字段，保持原值）**
5. 如果用户只调整了某个字段，其他字段必须保持当前值不变

示例：
- 当前: {{"business": {{"order_id": ["订单编号", "订单号"], "amount": "金额"}}}}
- 用户: "去掉订单编号"
- 返回: {{"business": {{"order_id": ["订单号"], "amount": "金额"}}}}  ← 注意 amount 保持不变
"""
    
    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()
        
        # 提取 JSON
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)
        
        parsed = _json.loads(content)
        
        # ⚠️ 关键：合并到现有映射，而不是替换，确保未提到的字段不丢失
        new_mappings: dict[str, dict] = {
            "business": current_mappings.get("business", {}).copy(),
            "finance": current_mappings.get("finance", {}).copy(),
        }
        
        # 更新 LLM 返回的字段
        for source in ("business", "finance"):
            if source in parsed and isinstance(parsed[source], dict):
                for role, col in parsed[source].items():
                    new_mappings[source][role] = col
        
        logger.info(f"字段映射合并: LLM解析={parsed}, 合并后={new_mappings}")
        return new_mappings
    
    except Exception as e:
        logger.warning(f"LLM 字段映射调整失败: {e}")
        # 失败则返回原映射
        return current_mappings


def _format_field_mappings(mappings: dict[str, Any], analyses: list[dict[str, Any]]) -> str:
    """将字段映射格式化为用户友好的描述（文件A的XX列 对应 文件B的YY列）。"""
    # 提取文件信息
    business_file = None
    finance_file = None
    for a in analyses:
        if a.get("guessed_source") == "business":
            business_file = a.get("filename", "文件1")
        elif a.get("guessed_source") == "finance":
            finance_file = a.get("filename", "文件2")
    
    # 如果没有识别到类型，使用默认名称
    if not business_file:
        business_file = analyses[0].get("filename", "文件1") if len(analyses) > 0 else "文件1"
    if not finance_file:
        finance_file = analyses[1].get("filename", "文件2") if len(analyses) > 1 else "文件2"
    
    lines: list[str] = []
    business_map = mappings.get("business", {})
    finance_map = mappings.get("finance", {})
    
    # 按角色展示对应关系
    role_labels = {
        "order_id": "订单号",
        "amount": "金额",
        "date": "日期",
        "status": "状态"
    }
    
    for role, label in role_labels.items():
        business_col = business_map.get(role)
        finance_col = finance_map.get(role)
        
        if business_col and finance_col:
            # 处理列表类型的列名
            if isinstance(business_col, list):
                business_col_str = " / ".join(business_col)
            else:
                business_col_str = str(business_col)
            
            if isinstance(finance_col, list):
                finance_col_str = " / ".join(finance_col)
            else:
                finance_col_str = str(finance_col)
            
            lines.append(f"  • **{label}匹配**：`{business_file}` 的 `{business_col_str}` ⇄ `{finance_file}` 的 `{finance_col_str}`")
    
    return "\n" + "\n".join(lines) if lines else "\n  （未找到匹配字段）"


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

async def file_analysis_node(state: AgentState) -> dict:
    """第1步：分析上传的文件，提取列名和样本数据。
    
    ⚠️ 展平到主图后，interrupt/resume 不会 replay 此节点，无需缓存检查。
    """
    uploaded = state.get("uploaded_files", [])
    if not uploaded:
        # 使用 interrupt 等待用户上传文件
        user_response = interrupt({
            "step": "1/4",
            "step_title": "上传文件",
            "question": "📤 **第1步：上传文件**\n\n请上传需要对账的文件（业务数据和财务数据各一个 Excel/CSV 文件）。",
            "hint": "💡 上传文件后，点击发送按钮或直接发送消息",
        })
        # interrupt 返回后，重新检查文件
        uploaded = state.get("uploaded_files", [])
        if not uploaded:
            # 仍然没有文件，返回提示消息
            return {
                "messages": [AIMessage(content="⚠️ 未检测到文件上传，请上传文件后再试。")],
                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "file_analyses": [],  # 空列表，路由函数会返回END
            }

    # 调用 MCP 工具分析文件（包括 LLM 文件类型判断）
    # 提取文件路径和原始文件名映射
    file_paths = []
    original_filenames_map = {}
    
    for item in uploaded:
        if isinstance(item, dict):
            file_path = item.get("file_path", "")
            original_filename = item.get("original_filename", "")
            if file_path:
                file_paths.append(file_path)
                if original_filename:
                    original_filenames_map[file_path] = original_filename
        else:
            # 兼容旧格式（直接是文件路径字符串）
            file_paths.append(item)
    
    try:
        analyze_args = {"file_paths": file_paths}
        if original_filenames_map:
            analyze_args["original_filenames"] = original_filenames_map
        result = await call_mcp_tool("analyze_files", analyze_args)
        if not result.get("success"):
            error_msg = result.get("error", "文件分析失败")
            return {
                "messages": [AIMessage(content=f"❌ {error_msg}")],
                "phase": ReconciliationPhase.FILE_ANALYSIS.value,
                "file_analyses": [],
            }
        
        analyses = result.get("analyses", [])
    except Exception as e:
        logger.error(f"调用 MCP 文件分析工具失败: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content=f"❌ 文件分析失败: {str(e)}")],
            "phase": ReconciliationPhase.FILE_ANALYSIS.value,
            "file_analyses": [],
        }

    # 构建文件分析摘要（只显示文件名和基本信息，不显示业务/财务标签）
    summary_parts: list[str] = ["📊 **第1步：文件分析完成**\n"]
    for a in analyses:
        summary_parts.append(f"📄 **{a['filename']}**")
        summary_parts.append(f"   • 列数: {len(a.get('columns', []))}  行数: {a.get('row_count', 0)}")
        summary_parts.append(f"   • 列名: {', '.join(a.get('columns', [])[:10])}{'...' if len(a.get('columns', [])) > 10 else ''}")
        summary_parts.append("")

    summary_parts.append("正在为你生成字段映射建议...")
    msg = "\n".join(summary_parts)

    # 使用 LLM 猜测字段映射（在后台完成，不显示给用户）
    suggested = _guess_field_mappings(analyses)

    return {
        "messages": [AIMessage(content=msg)],
        "file_analyses": analyses,
        "suggested_mappings": suggested,
        "phase": ReconciliationPhase.FIELD_MAPPING.value,
    }


def field_mapping_node(state: AgentState) -> dict:
    """第2步 (HITL)：等待用户确认或修改字段映射。
    
    ⚠️ 展平到主图后，interrupt/resume 直接恢复到此节点，无需首次进入检查。
    """
    logger.info(f"field_mapping_node 进入，当前 phase={state.get('phase', '')}")
    
    # 优先使用 suggested_mappings（可能已被调整）
    suggested = state.get("suggested_mappings", {})
    confirmed = suggested.copy() if suggested else {}
    analyses = state.get("file_analyses", [])
    
    # 检查是否有待处理的调整意见
    adjustment_feedback = state.get("mapping_adjustment_feedback")
    
    # 构建详细的字段映射展示
    mapping_display = _format_field_mappings(confirmed, analyses)
    
    # 构建问题文本
    if adjustment_feedback:
        # 如果有调整反馈，先显示反馈
        question_text = f"📋 **第2步：确认字段映射**\n\n{adjustment_feedback}\n\n当前字段对应关系：\n{mapping_display}\n\n**请确认是否正确？**"
    else:
        question_text = f"📋 **第2步：确认字段映射**\n\n我已经分析了这两个文件，为你建议了以下字段对应关系：\n{mapping_display}\n\n**这些对应关系是否正确？**"
    
    # interrupt 暂停，等待用户输入
    user_response = interrupt({
        "step": "2/4",
        "step_title": "确认字段映射",
        "question": question_text,
        "suggested_mappings": confirmed,
        "hint": '💡 **操作提示**：\n  • 如果正确，回复"确认"继续\n  • 如果需要调整，请详细描述需要修改的地方（例如："订单号匹配中，去掉订单编号，只保留订单号"）',
    })

    response_str = str(user_response).strip()

    # 忽略文件上传的默认消息或空消息
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        # 清除调整反馈，重新 interrupt
        return {
            "messages": [],
            "mapping_adjustment_feedback": None,
            "phase": ReconciliationPhase.FIELD_MAPPING.value,
        }
    
    response_lower = response_str.lower()

    # 用户确认，进入下一步
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确"):
        return {
            "messages": [AIMessage(content="✅ 字段映射已确认。接下来配置对账规则。")],
            "confirmed_mappings": confirmed,
            "mapping_adjustment_feedback": None,  # 清除反馈
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }

    # 用户需要调整，使用 LLM 解析调整意见并更新映射
    logger.info(f"用户调整意见: {response_str}")
    
    # 使用 LLM 调整映射
    adjusted_mappings = _adjust_field_mappings_with_llm(confirmed, response_str, analyses)
    
    # 检查映射是否有变化
    if adjusted_mappings != confirmed:
        adjustment_msg = f"✅ 已根据你的调整意见更新字段映射：\n\n> {response_str}"
        logger.info("字段映射已更新")
    else:
        adjustment_msg = f"⚠️ 已记录你的调整意见，但未能自动解析。请详细描述需要修改的地方：\n\n> {response_str}"
        logger.warning("字段映射未更新（LLM 解析失败或无变化）")

    return {
        "messages": [AIMessage(content=adjustment_msg)],
        "suggested_mappings": adjusted_mappings,  # 更新映射
        "mapping_adjustment_feedback": adjustment_msg,
        "phase": ReconciliationPhase.FIELD_MAPPING.value,  # 保持在当前阶段
    }


def _parse_rule_config_json_snippet(user_input: str, current_config_items: list[dict] = None) -> dict[str, Any]:
    """使用 LLM 根据 JSON 模板解析用户输入，返回 JSON 片段。
    
    Args:
        user_input: 用户自然语言输入
        current_config_items: 当前已添加的配置项列表
    
    Returns:
        {
            "action": "add" | "delete" | "update",
            "json_snippet": {...},  # 要添加/更新的JSON片段
            "description": "用户友好的描述"
        }
    """
    import json as _json
    from app.utils.llm import get_llm
    from pathlib import Path
    
    # 读取JSON模板
    # 从 finance-agents/data-agent/app/graphs/reconciliation.py 
    # 到 finance-mcp/reconciliation/schemas/direct_sales_schema.json
    template_path = Path(__file__).resolve().parents[3] / "finance-mcp" / "reconciliation" / "schemas" / "direct_sales_schema.json"
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = _json.load(f)
    except Exception as e:
        logger.warning(f"无法读取JSON模板: {e}，使用默认模板")
        template = {}
    
    current_items_desc = ""
    if current_config_items:
        current_items_desc = "\n当前已添加的配置项：\n"
        for i, item in enumerate(current_config_items, 1):
            current_items_desc += f"{i}. {item.get('description', '未知配置')}\n"
    
    prompt = f"""你是一个对账规则配置助手。请根据JSON模板解析用户的自然语言输入，返回JSON片段。

JSON模板结构（参考）：
{_json.dumps(template, ensure_ascii=False, indent=2)[:2000]}

{current_items_desc}

用户的指令：
{user_input}

请判断用户的意图：
1. 如果是**添加配置**（如"金额容差0.1元"、"订单号104开头"、"相同订单号做金额累加"），返回：
   {{
     "action": "add",
     "json_snippet": {{...}},  // 根据模板结构返回对应的JSON片段
     "description": "用户友好的中文描述"
   }}

2. 如果是**删除配置**（如"删除金额容差"、"去掉订单号过滤"），返回：
   {{
     "action": "delete",
     "target": "配置项的描述或关键词",  // 用于匹配要删除的配置
     "description": "删除XXX配置"
   }}

3. 如果是**更新配置**（如"金额容差改为0.2"），返回：
   {{
     "action": "update",
     "target": "要更新的配置项描述",
     "json_snippet": {{...}},
     "description": "更新XXX配置"
   }}

重要规则：
- JSON片段必须符合模板结构
- 金额容差 → {{"tolerance": {{"amount_diff_max": 0.1}}}}
- 订单号特征/过滤 → {{"data_cleaning_rules": {{"finance": {{"row_filters": [...]}}, "business": {{"row_filters": [...]}}}}}}
- 订单号转换 → {{"data_cleaning_rules": {{"finance": {{"field_transforms": [...]}}, "business": {{"field_transforms": [...]}}}}}}
- 金额累加 → {{"data_cleaning_rules": {{"finance": {{"aggregations": [...]}}, "business": {{"aggregations": [...]}}}}}}
- 只返回用户这次明确提到的配置，不要返回其他未提到的配置

示例：
- "金额容差0.1元" → {{"action": "add", "json_snippet": {{"tolerance": {{"amount_diff_max": 0.1}}}}, "description": "金额容差：0.1元"}}
- "订单号104开头" → {{"action": "add", "json_snippet": {{"data_cleaning_rules": {{"finance": {{"row_filters": [{{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "只保留104开头的订单号"}}]}}, "business": {{"row_filters": [{{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "只保留104开头的订单号"}}]}}}}}}, "description": "订单号过滤：104开头"}}
- "相同订单号做金额累加" → {{"action": "add", "json_snippet": {{"data_cleaning_rules": {{"finance": {{"aggregations": [{{"group_by": "order_id", "agg_fields": {{"amount": "sum"}}, "description": "按订单号合并，金额累加"}}]}}, "business": {{"aggregations": [{{"group_by": "order_id", "agg_fields": {{"amount": "sum"}}, "description": "按订单号合并，金额累加"}}]}}}}}}, "description": "金额累加：相同订单号的金额自动累加"}}
- "删除金额容差" → {{"action": "delete", "target": "金额容差", "description": "删除金额容差配置"}}
"""
    
    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()
        
        # 提取 JSON
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)
        
        parsed = _json.loads(content)
        logger.info(f"LLM解析结果: {parsed}")
        return parsed
    
    except Exception as e:
        logger.warning(f"LLM 规则配置解析失败: {e}")
        # 失败则返回空操作
        return {"action": "unknown", "description": f"解析失败: {str(e)}"}


def _parse_rule_config_with_llm(user_input: str, current_config: dict[str, Any] = None) -> dict[str, Any]:
    """使用 LLM 解析用户的自然语言规则配置指令，并合并到当前配置。
    
    ⚠️ 关键：LLM 只返回用户这次提到的字段，然后**合并**到现有配置，避免覆盖之前的设置。
    """
    import json as _json
    from app.utils.llm import get_llm
    
    # 准备当前配置的完整描述
    base_config = current_config or {
        "order_id_pattern": None,
        "order_id_transform": None,
        "amount_tolerance": 0.1,
        "check_order_status": True,
    }
    
    current_desc = f"""
当前配置：
- 订单号特征：{base_config.get('order_id_pattern') or '无特殊特征'}
- 订单号转换：{base_config.get('order_id_transform') or '不转换'}
- 金额容差：{base_config.get('amount_tolerance', 0.1)}元
- 检查订单状态：{'是' if base_config.get('check_order_status', True) else '否'}
"""
    
    prompt = f"""你是一个对账规则配置助手。请解析用户的自然语言指令，提取**用户这次提到的字段**。

{current_desc}

用户的指令：
{user_input}

⚠️ 重要：只返回用户**这次明确提到**的字段，未提到的字段不要包含在 JSON 中。

返回 JSON 格式（只包含用户提到的字段）：
{{
  "order_id_pattern": "订单号特征（如'104'），null表示无特征",  // 仅当用户提到时才返回
  "order_id_transform": "订单号转换规则",  // 仅当用户提到时才返回
  "amount_tolerance": 0.2,  // 仅当用户提到时才返回
  "check_order_status": true  // 仅当用户提到时才返回
}}

解析规则：
1. 订单号特征：用户提到"104开头"、"L开头"等时才返回
2. 订单号转换：用户提到"去掉引号"、"截取X位"等时才返回
3. 金额容差：用户提到"容差"、"差异"、"误差"等时才返回
4. 订单状态检查：用户明确说"需要检查"或"不需要检查"时才返回

示例：
- "金额容差改为0.2" → {{"amount_tolerance": 0.2}}  （只返回容差）
- "订单号去掉开头引号，并截取前21位" → {{"order_id_transform": "去掉开头引号并截取前21位"}}
- "104开头，容差0.2，不检查状态" → {{"order_id_pattern": "104", "amount_tolerance": 0.2, "check_order_status": false}}
"""
    
    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()
        
        # 提取 JSON
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)
        
        parsed = _json.loads(content)
        
        # ⚠️ 关键：合并到现有配置，而不是替换
        merged_config = base_config.copy()
        
        # 只更新 LLM 返回的字段
        if "order_id_pattern" in parsed:
            merged_config["order_id_pattern"] = parsed["order_id_pattern"]
        if "order_id_transform" in parsed:
            merged_config["order_id_transform"] = parsed["order_id_transform"]
        if "amount_tolerance" in parsed:
            merged_config["amount_tolerance"] = float(parsed["amount_tolerance"])
        if "check_order_status" in parsed:
            merged_config["check_order_status"] = bool(parsed["check_order_status"])
        
        logger.info(f"规则配置合并: 原配置={base_config}, LLM解析={parsed}, 合并后={merged_config}")
        return merged_config
    
    except Exception as e:
        logger.warning(f"LLM 规则配置解析失败: {e}")
        # 失败则返回当前配置
        return base_config


def _format_rule_config_items(config_items: list[dict] = None) -> str:
    """格式化已添加的配置项列表为用户友好的文本。"""
    if not config_items or len(config_items) == 0:
        return "（暂无配置，请开始添加配置项）"
    
    lines = []
    for i, item in enumerate(config_items, 1):
        desc = item.get("description", "未知配置")
        lines.append(f"  {i}. {desc}")
    
    return "\n".join(lines)


def _merge_json_snippets(base_schema: dict, snippets: list[dict]) -> dict:
    """将多个JSON片段合并到基础schema中。
    
    Args:
        base_schema: 基础schema（从模板或默认值）
        snippets: JSON片段列表，每个片段包含要合并的配置
    
    Returns:
        合并后的完整schema
    """
    import copy
    import json as _json
    result = copy.deepcopy(base_schema)
    
    for snippet_info in snippets:
        snippet = snippet_info.get("json_snippet", {})
        if not snippet:
            continue
        
        # 深度合并
        def deep_merge(target: dict, source: dict):
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                elif key in target and isinstance(target[key], list) and isinstance(value, list):
                    # 对于列表，追加新项（避免完全重复的项）
                    for item in value:
                        # 简单去重：如果item是dict，检查是否已存在相同的项
                        if isinstance(item, dict):
                            # 通过JSON字符串比较来判断是否重复
                            item_str = _json.dumps(item, sort_keys=True)
                            exists = any(_json.dumps(existing, sort_keys=True) == item_str 
                                       for existing in target[key] if isinstance(existing, dict))
                            if not exists:
                                target[key].append(item)
                        else:
                            if item not in target[key]:
                                target[key].append(item)
                else:
                    # 直接覆盖（如 tolerance.amount_diff_max）
                    target[key] = value
        
        deep_merge(result, snippet)
    
    return result


def rule_config_node(state: AgentState) -> dict:
    """第3步 (HITL)：增量式配置规则参数，支持自然语言添加/删除配置项。
    
    新的配置体验：
    1. 初始配置为空，等待用户输入
    2. 用户输入配置，LLM解析为JSON片段并添加到"当前配置"
    3. 用户可以删除已添加的配置
    4. 用户确认后完成配置
    """
    logger.info(f"rule_config_node 进入，当前 phase={state.get('phase', '')}")
    
    # 获取当前已添加的配置项列表（初始为空）
    config_items = state.get("rule_config_items") or []
    logger.info(f"rule_config_node: 当前配置项数量={len(config_items)}, 配置项={[item.get('description', '未知') for item in config_items]}")
    
    # 区分初始状态和配置中状态
    if len(config_items) == 0:
        # 初始状态：只显示提示，不显示"当前配置"标题
        question_text = """⚙️ **第3步：配置对账规则参数**

请描述对账规则的配置要求，例如：
• "金额容差0.1元"
• "订单号104开头"
• "相同订单号做金额累加"
• "订单号去掉开头引号，并截取前21位"

**请输入你的配置要求：**"""
    else:
        # 有配置项时：显示当前配置列表
        config_display = _format_rule_config_items(config_items)
        question_text = f"""⚙️ **第3步：配置对账规则参数**

当前配置：
{config_display}

你可以：
• 继续添加配置（描述新的配置要求）
• 删除配置（如"删除金额容差"、"去掉订单号过滤"）
• 回复"确认"完成配置

**请输入：**"""
    
    # interrupt 暂停，等待用户输入
    user_response = interrupt({
        "step": "3/4",
        "step_title": "配置规则参数",
        "question": question_text,
        "current_config_items": config_items,
        "hint": '💡 **操作提示**：\n  • 描述配置要求（支持自然语言）\n  • 可以删除已添加的配置\n  • 配置完成后，回复"确认"继续',
    })

    response_str = str(user_response).strip()
    logger.info(f"rule_config interrupt 返回，用户输入: {response_str}")
    
    # 忽略文件上传的默认消息或空消息
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        logger.info("忽略空消息或文件上传消息，保持 phase=RULE_CONFIG")
        return {
            "messages": [],
            "phase": ReconciliationPhase.RULE_CONFIG.value,
        }
    
    response_lower = response_str.lower()
    
    # 用户确认，进入下一步
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确", "完成"):
        if len(config_items) == 0:
            return {
                "messages": [AIMessage(content="⚠️ 当前还没有添加任何配置，请至少添加一个配置项后再确认。")],
                "phase": ReconciliationPhase.RULE_CONFIG.value,
            }
        logger.info("用户确认配置，进入 VALIDATION_PREVIEW")
        return {
            "messages": [AIMessage(content="✅ 规则配置已确认。正在生成规则并预览效果...")],
            "rule_config_items": config_items,
            "phase": ReconciliationPhase.VALIDATION_PREVIEW.value,
        }
    
    # 用户输入配置或删除指令，使用 LLM 解析
    logger.info(f"用户配置指令: {response_str}")
    
    # 使用新的LLM解析函数
    parsed_result = _parse_rule_config_json_snippet(response_str, config_items)
    action = parsed_result.get("action", "unknown")
    
    new_config_items = config_items.copy()
    feedback_msg = ""
    
    if action == "add":
        # 添加配置项
        new_item = {
            "json_snippet": parsed_result.get("json_snippet", {}),
            "description": parsed_result.get("description", "未知配置"),
            "user_input": response_str,
        }
        new_config_items.append(new_item)
        # 显示更新后的配置列表
        updated_config_display = _format_rule_config_items(new_config_items)
        feedback_msg = f"✅ 已添加配置：{parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
        logger.info(f"添加配置项: {parsed_result.get('description')}, 当前配置项数量: {len(new_config_items)}")
    
    elif action == "delete":
        # 删除配置项
        target = parsed_result.get("target", "").lower()
        deleted_count = 0
        remaining_items = []
        
        for item in new_config_items:
            item_desc = item.get("description", "").lower()
            if target in item_desc or item_desc in target:
                deleted_count += 1
                logger.info(f"删除配置项: {item.get('description')}")
            else:
                remaining_items.append(item)
        
        new_config_items = remaining_items
        
        # 显示更新后的配置列表
        updated_config_display = _format_rule_config_items(new_config_items)
        if deleted_count > 0:
            feedback_msg = f"🗑️ 已删除配置：{parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
        else:
            feedback_msg = f"⚠️ 未找到匹配的配置项，请检查输入\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
    
    elif action == "update":
        # 更新配置项（先删除旧的，再添加新的）
        target = parsed_result.get("target", "").lower()
        updated = False
        
        for i, item in enumerate(new_config_items):
            item_desc = item.get("description", "").lower()
            if target in item_desc or item_desc in target:
                # 更新配置项
                new_config_items[i] = {
                    "json_snippet": parsed_result.get("json_snippet", {}),
                    "description": parsed_result.get("description", "未知配置"),
                    "user_input": response_str,
                }
                updated = True
                logger.info(f"更新配置项: {parsed_result.get('description')}")
                break
        
        # 显示更新后的配置列表
        updated_config_display = _format_rule_config_items(new_config_items)
        if updated:
            feedback_msg = f"✏️ 已更新配置：{parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
        else:
            # 如果没找到，就添加为新配置
            new_item = {
                "json_snippet": parsed_result.get("json_snippet", {}),
                "description": parsed_result.get("description", "未知配置"),
                "user_input": response_str,
            }
            new_config_items.append(new_item)
            updated_config_display = _format_rule_config_items(new_config_items)
            feedback_msg = f"⚠️ 未找到匹配的配置项，已添加为新配置\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
    
    else:
        # 解析失败或未知操作
        feedback_msg = f"⚠️ 未能理解你的配置要求，请重新描述\n\n> {response_str}\n\n提示：可以描述具体的配置项，如\"金额容差0.1元\"、\"订单号104开头\"等"
    
    logger.info(f"配置项数量: {len(config_items)} -> {len(new_config_items)}")
    logger.info(f"保存的配置项: {[item.get('description', '未知') for item in new_config_items]}")
    
    # 确保状态正确保存
    return {
        "messages": [AIMessage(content=feedback_msg)],
        "rule_config_items": new_config_items,  # 明确保存配置项列表
        "phase": ReconciliationPhase.RULE_CONFIG.value,  # 保持在当前阶段
    }


def validation_preview_node(state: AgentState) -> dict:
    """第4步 (HITL)：生成规则 schema，预览对账效果，等待用户确认。"""
    logger.info("validation_preview_node - 开始执行")
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    config_items = state.get("rule_config_items", [])  # 新的配置项列表
    analyses = state.get("file_analyses", [])
    logger.info(f"validation_preview_node - 初始状态: analyses数量={len(analyses)}, config_items数量={len(config_items)}")

    # ⚠️ 提取文件模式：使用带时间戳的文件名生成匹配模式，时间戳部分用*替换
    # 例如：sales_data_115959.csv → sales_data_*.csv
    biz_patterns: list[str] = []
    fin_patterns: list[str] = []
    
    import re
    
    # 调试日志：记录 analyses 的内容
    logger.info(f"validation_preview_node - 收到的 analyses 数量: {len(analyses)}")
    for idx, a in enumerate(analyses):
        logger.info(f"validation_preview_node - analyses[{idx}]: filename={a.get('filename', 'N/A')}, original_filename={a.get('original_filename', 'N/A')}, guessed_source={a.get('guessed_source', 'N/A')}")
    
    for a in analyses:
        src = a.get("guessed_source")
        # 使用带时间戳的文件名（filename），而不是original_filename
        filename_with_timestamp = a.get("filename", "")
        original_filename = a.get("original_filename", "")
        file_path = a.get("file_path", "")
        
        # 如果 filename 不包含时间戳（不包含 _ 后跟数字），尝试从 file_path 中提取
        if filename_with_timestamp and not re.search(r'_\d{6}(\.\w+)$', filename_with_timestamp):
            # 从 file_path 中提取文件名
            if file_path:
                from pathlib import Path
                path_obj = Path(file_path)
                extracted_filename = path_obj.name
                # 如果提取的文件名包含时间戳，使用它
                if re.search(r'_\d{6}(\.\w+)$', extracted_filename) or re.search(r'_\d+(\.\w+)$', extracted_filename):
                    filename_with_timestamp = extracted_filename
                    logger.info(f"validation_preview_node - 从 file_path 提取文件名: {filename_with_timestamp}")
        
        if not filename_with_timestamp:
            continue
        
        # 调试日志
        logger.info(f"validation_preview_node - 文件分析结果: filename={filename_with_timestamp}, original_filename={original_filename}, file_path={file_path}, source={src}")
        
        # 将时间戳部分替换为*通配符
        # 匹配格式：filename_HHMMSS.ext 或 filename_数字.ext
        # 例如：sales_data_115959.csv → sales_data_*.csv
        # 例如：1767597466118_134019.csv → 1767597466118_*.csv
        pattern = filename_with_timestamp
        
        # 首先尝试匹配 _HHMMSS 格式（6位数字，时间戳格式）
        # 例如：1767597466118_134019.csv → 1767597466118_*.csv
        pattern = re.sub(r'_(\d{6})(\.\w+)$', r'_*\2', pattern)
        
        # 如果上面没匹配到，尝试匹配其他数字后缀格式（任意长度的数字）
        # 例如：filename_12345.csv → filename_*.csv
        if pattern == filename_with_timestamp:
            pattern = re.sub(r'_(\d+)(\.\w+)$', r'_*\2', pattern)
        
        # 如果还是没匹配到，说明文件名本身可能不包含时间戳
        # 对于纯数字文件名（如 1767597466118.csv），使用前后通配符模式
        # 例如：1767597466118.csv → *1767597466118_*.csv（确保能匹配带时间戳的版本）
        if pattern == filename_with_timestamp:
            # 检查是否是纯数字文件名
            if re.match(r'^\d+\.\w+$', filename_with_timestamp):
                # 纯数字文件名，生成模式：*数字_*.ext（确保能匹配带时间戳的版本）
                name_parts = filename_with_timestamp.rsplit('.', 1)
                if len(name_parts) == 2:
                    pattern = f"*{name_parts[0]}_*.{name_parts[1]}"
                else:
                    pattern = f"*{filename_with_timestamp}_*"
            else:
                # 其他情况，使用默认模式（前后加通配符）
                pattern = f"*{filename_with_timestamp}*"
        
        # 调试日志：记录生成的 pattern
        logger.info(f"validation_preview_node - 生成的 file_pattern: {pattern} (来源: {src}, 原始文件名: {filename_with_timestamp})")
        
        if src == "business":
            if pattern not in biz_patterns:
                biz_patterns.append(pattern)
        elif src == "finance":
            if pattern not in fin_patterns:
                fin_patterns.append(pattern)

    # 默认模式（如果没有找到文件）
    if not biz_patterns:
        biz_patterns = ["*.csv", "*.xlsx", "*.xls"]
    if not fin_patterns:
        fin_patterns = ["*.csv", "*.xlsx", "*.xls"]

    # 调试日志：记录最终生成的 file_pattern
    logger.info(f"validation_preview_node - 最终生成的 file_pattern: business={biz_patterns}, finance={fin_patterns}")

    biz_field_roles = mappings.get("business", {})
    fin_field_roles = mappings.get("finance", {})

    # 先构建基础 schema（使用默认值）
    base_schema = build_schema(
        description="用户自定义对账规则",
        business_file_patterns=biz_patterns,
        finance_file_patterns=fin_patterns,
        business_field_roles=biz_field_roles,
        finance_field_roles=fin_field_roles,
        order_id_pattern=None,  # 从配置项中获取
        amount_tolerance=0.1,  # 从配置项中获取
        check_order_status=True,  # 从配置项中获取
    )
    
    # 将用户添加的配置项合并到基础schema中
    # ⚠️ 保护 file_pattern，防止被覆盖
    protected_file_patterns = {
        "business": biz_patterns.copy(),
        "finance": fin_patterns.copy(),
    }
    
    if config_items:
        schema = _merge_json_snippets(base_schema, config_items)
        # 恢复被保护的 file_pattern
        if "data_sources" in schema:
            if "business" in schema["data_sources"]:
                schema["data_sources"]["business"]["file_pattern"] = protected_file_patterns["business"]
            if "finance" in schema["data_sources"]:
                schema["data_sources"]["finance"]["file_pattern"] = protected_file_patterns["finance"]
    else:
        schema = base_schema

    # 调试日志：记录合并后的 schema 中的 file_pattern
    biz_patterns_after_merge = schema.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_patterns_after_merge = schema.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    logger.info(f"validation_preview_node - 合并后的 schema file_pattern: business={biz_patterns_after_merge}, finance={fin_patterns_after_merge}")

    # 简单预览（统计匹配信息）
    preview = _preview_schema(schema, analyses)

    preview_text = (
        f"✅ **第4步：确认规则并保存**\n\n"
        f"我已经根据你的配置生成了对账规则！预览结果：\n\n"
        f"📊 **数据统计**\n"
        f"• 业务记录数：{preview.get('biz_count', 'N/A')}\n"
        f"• 财务记录数：{preview.get('fin_count', 'N/A')}\n"
        f"• 预计可匹配：{preview.get('estimated_match', 'N/A')}条\n"
        f"• 验证规则数：{len(schema.get('custom_validations', []))}条\n\n"
        f"规则看起来合理吗？"
    )

    user_response = interrupt({
        "step": "4/4",
        "step_title": "确认并保存规则",
        "question": preview_text,
        "preview": preview,
        "schema_summary": {
            "validations": len(schema.get("custom_validations", [])),
            "biz_patterns": biz_patterns,
            "fin_patterns": fin_patterns,
        },
        "hint": "• 如果确认无误，回复\"保存\"\n• 如果需要调整，回复\"调整\"重新配置",
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


def _translate_rule_name_to_english(rule_name_cn: str) -> str:
    """使用 LLM 将中文规则名称翻译成英文，用作 type_key 和文件名。
    
    返回格式：小写字母和下划线，例如：direct_sales_reconciliation
    """
    from app.utils.llm import get_llm
    import json as _json
    
    prompt = f"""请将以下中文规则名称翻译成英文，并转换为适合作为文件名和标识符的格式。

中文名称：{rule_name_cn}

要求：
1. 翻译成英文（简洁、专业）
2. 只使用小写字母、数字和下划线
3. 单词之间用下划线分隔
4. 如果名称包含"对账"，翻译为 reconciliation
5. 如果名称包含"规则"，可以省略或翻译为 rule

示例：
- "直销对账" → "direct_sales_reconciliation"
- "南京飞翰知晓对账" → "nanjing_feihan_zhixiao_reconciliation"
- "电商订单对账规则" → "ecommerce_order_reconciliation"

只返回翻译后的英文标识符，不要有其他内容。"""
    
    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        type_key = resp.content.strip()
        
        # 清理结果（只保留小写字母、数字和下划线）
        type_key = re.sub(r'[^a-z0-9_]', '_', type_key.lower())
        type_key = re.sub(r'_+', '_', type_key)  # 多个下划线合并为一个
        type_key = type_key.strip('_')  # 去除首尾下划线
        
        # 确保以字母开头
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        
        # 如果翻译失败或结果为空，使用默认方式
        if not type_key or len(type_key) < 3:
            type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
            if not type_key or type_key[0].isdigit():
                type_key = "rule_" + type_key
        
        logger.info(f"规则名称翻译: {rule_name_cn} → {type_key}")
        return type_key
    
    except Exception as e:
        logger.warning(f"LLM 规则名称翻译失败: {e}，使用默认方式")
        # 降级方案：直接转换
        type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        return type_key


async def save_rule_node(state: AgentState) -> dict:
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

    rule_name_cn = str(user_response).strip()
    if not rule_name_cn:
        rule_name_cn = "自定义对账规则"

    # 使用 LLM 将中文名称翻译成英文（用作 type_key 和文件名）
    type_key = _translate_rule_name_to_english(rule_name_cn)
    
    # 更新 schema 的 description 为用户输入的中文名
    schema_with_desc = schema.copy()
    schema_with_desc["description"] = rule_name_cn

    # 调试日志：记录保存的 schema 中的 file_pattern
    biz_patterns = schema_with_desc.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_patterns = schema_with_desc.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    logger.info(f"save_rule_node - 保存的规则 file_pattern: business={biz_patterns}, finance={fin_patterns}")
    logger.info(f"save_rule_node - 完整的 schema data_sources: {schema_with_desc.get('data_sources', {})}")

    # ⚠️ 通过 finance-mcp 工具保存规则（带认证 token）
    auth_token = state.get("auth_token", "")
    try:
        result = await call_mcp_tool("save_reconciliation_rule", {
            "auth_token": auth_token,
            "name": rule_name_cn,
            "description": rule_name_cn,
            "rule_template": schema_with_desc,
            "visibility": "private",  # 默认仅创建者可见
        })
        
        if not result.get("success"):
            logger.error(f"保存规则失败: {result.get('error')}")
            return {
                "messages": [AIMessage(content=f"❌ 规则保存失败: {result.get('error')}")],
                "phase": ReconciliationPhase.SAVE_RULE.value,
            }
    except Exception as e:
        logger.error(f"调用 save_reconciliation_rule 失败: {e}")
        logger.exception(e)
        return {
            "messages": [AIMessage(content=f"❌ 规则保存失败: {str(e)}")],
            "phase": ReconciliationPhase.SAVE_RULE.value,
        }

    msg = (
        f"规则 **{rule_name_cn}** 已保存！\n\n"
        f"现在可以用它开始对账了。要立即开始吗？\n"
        f"（回复\"开始\"立即执行对账，或稍后再说）"
    )

    return {
        "messages": [AIMessage(content=msg)],
        "saved_rule_name": rule_name_cn,
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

def route_after_file_analysis(state: AgentState) -> str:
    """文件分析后路由：如果有分析结果则继续，否则结束等待文件上传。"""
    analyses = state.get("file_analyses", [])
    if analyses:
        return "field_mapping"
    return END


def route_after_field_mapping(state: AgentState) -> str:
    """字段映射后路由：如果用户要调整则重新进入 field_mapping，否则进入 rule_config。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        return "field_mapping"  # 用户输入了调整意见，重新进入
    return "rule_config"  # 用户确认了，进入下一步


def route_after_rule_config(state: AgentState) -> str:
    """规则配置后路由：如果用户要调整则重新进入 rule_config，否则进入 validation_preview。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"  # 用户输入了调整意见，重新进入
    return "validation_preview"  # 用户确认了，进入下一步


def route_after_preview(state: AgentState) -> str:
    """预览后路由：如果用户选择调整则回到 rule_config，否则进入 save_rule。"""
    phase = state.get("phase", "")
    if phase == ReconciliationPhase.RULE_CONFIG.value:
        return "rule_config"
    return "save_rule"


# ── 构建子图 ─────────────────────────────────────────────────────────────────

def entry_router_node(state: AgentState) -> dict:
    """子图入口路由节点：根据 phase 决定进入哪个节点。
    
    这是为了解决 LangGraph 子图 interrupt resume 后重新从入口点开始的问题。
    """
    phase = state.get("phase", "")
    logger.info(f"子图入口路由: phase={phase}")
    
    # 直接返回，让条件边路由到正确的节点
    return {"messages": []}


def route_from_entry(state: AgentState) -> str:
    """从入口路由节点决定下一步。"""
    phase = state.get("phase", "")
    logger.info(f"入口路由决策: phase={phase}")
    
    if phase == ReconciliationPhase.FIELD_MAPPING.value:
        logger.info("路由到: field_mapping")
        return "field_mapping"
    elif phase == ReconciliationPhase.RULE_CONFIG.value:
        logger.info("路由到: rule_config")
        return "rule_config"
    elif phase == ReconciliationPhase.SAVE_RULE.value:
        logger.info("路由到: save_rule")
        return "save_rule"
    else:
        # 默认从 file_analysis 开始
        logger.info(f"路由到: file_analysis (默认，phase={phase})")
        return "file_analysis"


def build_reconciliation_subgraph() -> StateGraph:
    """构建对账规则生成子图（第2层）。"""
    sg = StateGraph(AgentState)

    sg.add_node("entry_router", entry_router_node)
    sg.add_node("file_analysis", file_analysis_node)
    sg.add_node("field_mapping", field_mapping_node)
    sg.add_node("rule_config", rule_config_node)
    sg.add_node("validation_preview", validation_preview_node)
    sg.add_node("save_rule", save_rule_node)

    sg.set_entry_point("entry_router")
    
    # 入口路由：根据 phase 跳转
    sg.add_conditional_edges("entry_router", route_from_entry, {
        "file_analysis": "file_analysis",
        "field_mapping": "field_mapping",
        "rule_config": "rule_config",
        "save_rule": "save_rule",
    })
    
    sg.add_conditional_edges("file_analysis", route_after_file_analysis, {
        "field_mapping": "field_mapping",
        END: END,
    })
    sg.add_conditional_edges("field_mapping", route_after_field_mapping, {
        "field_mapping": "field_mapping",  # 调整意见，重新进入
        "rule_config": "rule_config",      # 确认，进入下一步
    })
    sg.add_conditional_edges("rule_config", route_after_rule_config, {
        "rule_config": "rule_config",           # 调整意见，重新进入
        "validation_preview": "validation_preview",  # 确认，进入下一步
    })
    sg.add_conditional_edges("validation_preview", route_after_preview, {
        "rule_config": "rule_config",
        "save_rule": "save_rule",
    })
    sg.add_edge("save_rule", END)

    return sg

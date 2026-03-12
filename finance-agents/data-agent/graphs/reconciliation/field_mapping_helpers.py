"""字段映射辅助函数模块

包含字段映射操作、格式化、猜测等功能。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _apply_field_mapping_operations(
    current_mappings: dict[str, Any],
    operations: list[dict[str, Any]]
) -> dict[str, Any]:
    """根据操作列表（add/update/delete）调整字段映射。
    
    操作格式：
    [
        {"action": "add", "target": "business|finance", "role": "status", "column": "订单状态"},
        {"action": "update", "target": "business|finance", "role": "order_id", "column": "新列名"},
        {"action": "delete", "target": "business|finance", "role": "status"},
        {"action": "delete_column", "target": "business|finance", "role": "amount", "column": "pay_amt"}  # 仅删除列别名
    ]
    """
    new_mappings: dict[str, dict] = {
        "business": current_mappings.get("business", {}).copy(),
        "finance": current_mappings.get("finance", {}).copy(),
    }
    
    for op in operations:
        action = op.get("action")
        target = op.get("target")  # "business" 或 "finance"
        role = op.get("role")      # "order_id", "amount", "date", "status"
        column = op.get("column")  # 列名或列名列表
        
        if target not in new_mappings:
            logger.warning(f"Invalid target: {target}")
            continue
        
        if action == "add":
            # 添加新字段映射或覆盖现有的
            new_mappings[target][role] = column
            logger.info(f"✅ 添加字段映射: {target}.{role} = {column}")
        
        elif action == "update":
            # 更新现有字段映射
            if role in new_mappings[target]:
                new_mappings[target][role] = column
                logger.info(f"✅ 更新字段映射: {target}.{role} = {column}")
            else:
                logger.warning(f"⚠️ 字段 {role} 不存在于 {target} 中，跳过更新")
        
        elif action == "delete":
            # 删除整个字段映射
            if role in new_mappings[target]:
                del new_mappings[target][role]
                logger.info(f"✅ 删除字段映射: {target}.{role}")
            else:
                logger.warning(f"⚠️ 字段 {role} 不存在于 {target} 中，跳过删除")
        
        elif action == "delete_column":
            # 仅删除某个字段的单个列别名（不删除整个字段）
            if role in new_mappings[target] and column:
                columns_to_remove = column if isinstance(column, list) else [column]
                columns_to_remove = [str(c).strip() for c in columns_to_remove if str(c).strip()]
                if not columns_to_remove:
                    logger.warning(f"⚠️ delete_column 未提供有效列名: {op}")
                    continue
                existing = new_mappings[target][role]
                
                # 如果是列表，移除指定的列
                if isinstance(existing, list):
                    updated_list = [col for col in existing if str(col).strip() not in set(columns_to_remove)]
                    if updated_list:  # 还有其他列
                        new_mappings[target][role] = updated_list
                        logger.info(f"✅ 从{target}.{role}中删除列别名: {columns_to_remove} (剩余: {updated_list})")
                    else:  # 没有其他列了，删除整个字段
                        del new_mappings[target][role]
                        logger.info(f"✅ 删除字段映射: {target}.{role} (最后一个列别名已移除)")
                
                # 如果是字符串，检查是否相同
                elif str(existing).strip() in set(columns_to_remove):
                    del new_mappings[target][role]
                    logger.info(f"✅ 删除字段映射: {target}.{role}")
                else:
                    logger.warning(f"⚠️ 列别名 {columns_to_remove} 不存在于 {target}.{role} 中 (当前: {existing})")
            else:
                logger.warning(f"⚠️ 字段 {role} 不存在于 {target} 中，跳过删除列别名")
    
    return new_mappings


def _format_operations_summary(operations: list[dict[str, Any]], file_names: dict[str, str] | None = None) -> str:
    """将操作列表格式化为用户友好的文本摘要。
    
    Args:
        operations: 操作列表
        file_names: 文件名映射，格式 {"business": "文件1名", "finance": "文件2名"}
    """
    if not operations:
        return "（无操作）"
    
    # 如果没有提供文件名，使用默认值
    if not file_names:
        file_names = {"business": "文件1", "finance": "文件2"}
    else:
        # 补充默认标签
        if "business" not in file_names:
            file_names["business"] = "文件1"
        if "finance" not in file_names:
            file_names["finance"] = "文件2"
    
    def _fmt_col(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return "、".join(str(x) for x in v)
        return str(v)

    lines = []
    for op in operations:
        action = op.get("action")
        target = op.get("target")
        column = op.get("column")
        target_label = file_names.get(target, f"文件（{target}）")
        col_str = _fmt_col(column)

        if action == "add":
            lines.append(f"  ➕ {target_label} 添加 {col_str}")
        elif action == "update":
            lines.append(f"  ✏️ {target_label} 修改 {col_str}")
        elif action == "delete":
            lines.append(f"  ❌ {target_label} 删除字段")
        elif action == "delete_column":
            lines.append(f"  🚫 {target_label} 移除列别名: {col_str}")
    
    return "\n" + "\n".join(lines)


def _format_field_mappings(mappings: dict[str, Any], analyses: list[dict[str, Any]], bullet_style: bool = False) -> str:
    """将字段映射格式化为 业务列名↔财务列名 形式，按 field_roles 配对。

    Args:
        bullet_style: 若为 True，每项前加 • 并与数据统计样式一致
    """
    biz_map = mappings.get("business", {})
    fin_map = mappings.get("finance", {})
    
    def _fmt_col(v: Any) -> str:
        if isinstance(v, list):
            return "、".join(str(x) for x in v)
        return str(v) if v else ""
    
    # 取 business 与 finance 的 field_roles 公共 key 做配对
    common_roles = sorted(biz_map.keys() & fin_map.keys())
    lines: list[str] = []
    for role in common_roles:
        biz_col = biz_map.get(role)
        fin_col = fin_map.get(role)
        if biz_col and fin_col:
            item = f"{_fmt_col(biz_col)}↔{_fmt_col(fin_col)}"
            lines.append(f"• {item}" if bullet_style else item)
    
    if not lines:
        return "（未找到匹配字段）"
    return "\n".join(lines) if bullet_style else "\n\n".join(lines)


def _format_edit_field_mappings(mappings: dict[str, Any]) -> str:
    """编辑模式下格式化字段映射（无需 file_analyses），按 field_roles 配对，格式：业务列名↔财务列名，bullet style。"""
    biz_map = mappings.get("business", {})
    fin_map = mappings.get("finance", {})

    def _fmt_col(v: Any) -> str:
        if isinstance(v, list):
            return "、".join(str(x) for x in v)
        return str(v) if v else ""

    # 取 business 与 finance 的 field_roles 公共 key 做配对
    common_roles = sorted(biz_map.keys() & fin_map.keys())
    lines: list[str] = []
    for role in common_roles:
        biz_col = biz_map.get(role)
        fin_col = fin_map.get(role)
        if biz_col and fin_col:
            item = f"{_fmt_col(biz_col)}↔{_fmt_col(fin_col)}"
            lines.append(f"• {item}")
    return "\n".join(lines) if lines else "（无映射）"


def _build_field_mapping_text(mappings: dict[str, Any]) -> str:
    """将字段映射构建为可保存的自然语言描述，供编辑规则时展示。

    格式示例：
    业务: 订单号->第三方订单号, 金额->应结算平台金额, 日期->支付时间
    财务: 订单号->sup订单号, 金额->发生-, 日期->完成时间
    """
    lines = []
    for source, label in [("business", "业务"), ("finance", "财务")]:
        src_map = mappings.get(source, {})
        if not src_map:
            continue
        parts = []
        for role, col in src_map.items():
            col_str = " / ".join(col) if isinstance(col, list) else str(col)
            parts.append(f"{role}->{col_str}")
        if parts:
            lines.append(f"{label}: {', '.join(parts)}")
    return "\n".join(lines) if lines else ""


def _guess_field_mappings(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """使用 LLM 智能猜测字段映射：原始列名 → 标准角色。"""
    from utils.llm import get_llm

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
        fname = a.get("original_filename") or a.get("filename", "")
        files_info.append(
            f"文件: {fname} (类型: {a['guessed_source']})\n"
            f"  列名: {cols_str}\n"
            f"  示例数据:\n{sample_str}"
        )

    if not files_info:
        return mappings

    prompt = (
        "你是一个财务数据分析专家。以下是用户上传的对账文件信息。\n"
        "请为每个文件的列名匹配到以下标准角色（**只猜测以下 3 个必需角色**）：\n"
        "- order_id: 订单号/交易号（用于两边数据匹配的关键字段，如订单编号、订单号、单号、第三方订单号等）\n"
        "- amount: 金额\n"
        "- date: 日期/时间\n\n"
        "**规则：**\n"
        "- 如果一个角色可能对应多个列名，全部列出。\n"
        "- 如果某个角色没有对应的列，不要包含。\n"
        "- **禁止在初始猜测中包含 status**。即使用户文件有「订单状态」「结算状态」等列，也不要映射。用户若需要状态映射，会在确认时主动添加。\n\n"
        + "\n".join(files_info)
        + "\n\n请严格按以下 JSON 格式回复，不要添加其他内容：\n"
        '{"business": {"order_id": "列名或[列名1,列名2]", "amount": "...", "date": "..."}, '
        '"finance": {"order_id": "...", "amount": "...", "date": "..."}}'
    )

    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()

        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)

        parsed = json.loads(content)
        for source in ("business", "finance"):
            if source in parsed and isinstance(parsed[source], dict):
                mappings[source] = parsed[source]

    except Exception as e:
        logger.warning(f"LLM 字段映射猜测失败: {e}")

    return {k: v for k, v in mappings.items() if v}


__all__ = [
    "_apply_field_mapping_operations",
    "_format_operations_summary",
    "_format_field_mappings",
    "_format_edit_field_mappings",
    "_build_field_mapping_text",
    "_guess_field_mappings",
]

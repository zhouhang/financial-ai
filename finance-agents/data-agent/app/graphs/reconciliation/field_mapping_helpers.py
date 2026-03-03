"""字段映射辅助函数模块

包含字段映射操作、格式化、猜测等功能。
"""

from __future__ import annotations

import logging
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
                existing = new_mappings[target][role]
                
                # 如果是列表，移除指定的列
                if isinstance(existing, list):
                    updated_list = [col for col in existing if col != column]
                    if updated_list:  # 还有其他列
                        new_mappings[target][role] = updated_list
                        logger.info(f"✅ 从{target}.{role}中删除列别名: {column} (剩余: {updated_list})")
                    else:  # 没有其他列了，删除整个字段
                        del new_mappings[target][role]
                        logger.info(f"✅ 删除字段映射: {target}.{role} (最后一个列别名已移除)")
                
                # 如果是字符串，检查是否相同
                elif existing == column:
                    del new_mappings[target][role]
                    logger.info(f"✅ 删除字段映射: {target}.{role}")
                else:
                    logger.warning(f"⚠️ 列别名 {column} 不存在于 {target}.{role} 中 (当前: {existing})")
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
    
    lines = []
    for op in operations:
        action = op.get("action")
        target = op.get("target")
        role = op.get("role")
        column = op.get("column")
        description = op.get("description", "")
        
        target_label = file_names.get(target, f"文件（{target}）")
        
        if action == "add":
            lines.append(f"  ➕ {target_label} 添加 {role}: {column}")
        elif action == "update":
            lines.append(f"  ✏️ {target_label} 修改 {role}: {column}")
        elif action == "delete":
            lines.append(f"  ❌ {target_label} 删除 {role} 字段")
        elif action == "delete_column":
            lines.append(f"  🚫 {target_label} 从 {role} 中移除列别名: {column}")
    
    return "\n" + "\n".join(lines)


def _format_field_mappings(mappings: dict[str, Any], analyses: list[dict[str, Any]], bullet_style: bool = False) -> str:
    """将字段映射格式化为可读文本。
    
    Args:
        mappings: 字段映射字典
        analyses: 文件分析结果列表
        bullet_style: 是否使用 bullet 样式（默认表格样式）
    """
    if not mappings:
        return "（无字段映射）"
    
    # 构建文件名映射
    file_names = {}
    for a in analyses:
        src = a.get("guessed_source")
        if src:
            file_names[src] = a.get("original_filename", src)
    
    lines = []
    for source in ("business", "finance"):
        src_map = mappings.get(source, {})
        if not src_map:
            continue
        
        label = file_names.get(source, "文件1" if source == "business" else "文件2")
        
        if bullet_style:
            lines.append(f"**{label}**:")
            for role, column in src_map.items():
                lines.append(f"  - {role}: {column}")
        else:
            lines.append(f"**{label}**:")
            table_lines = ["  | 字段 | 列名 |", "  | --- | --- |"]
            for role, column in src_map.items():
                col_str = ", ".join(column) if isinstance(column, list) else column
                table_lines.append(f"  | {role} | {col_str} |")
            lines.extend(table_lines)
    
    return "\n".join(lines) if lines else "（无字段映射）"


def _format_edit_field_mappings(mappings: dict[str, Any]) -> str:
    """格式化字段映射供编辑使用"""
    if not mappings:
        return "无映射"
    
    lines = []
    for source in ("business", "finance"):
        src_map = mappings.get(source, {})
        if not src_map:
            continue
        
        lines.append(f"**{source}**:")
        for role, column in src_map.items():
            col_str = ", ".join(column) if isinstance(column, list) else column
            lines.append(f"  - {role}: {col_str}")
    
    return "\n".join(lines) if lines else "无映射"


def _build_field_mapping_text(mappings: dict[str, Any]) -> str:
    """构建字段映射描述文本"""
    return _format_field_mappings(mappings, [], bullet_style=True)


def _guess_field_mappings(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """根据文件分析结果自动猜测字段映射。
    
    目前仅自动猜测 order_id, amount, date 三个核心字段。
    """
    if not analyses:
        return {}
    
    mappings = {"business": {}, "finance": {}}
    
    for analysis in analyses:
        source = analysis.get("guessed_source")
        if not source or source not in mappings:
            continue
        
        headers = analysis.get("headers", [])
        if not headers:
            continue
        
        # 转为小写便于匹配
        headers_lower = [h.lower() for h in headers]
        
        # order_id 匹配
        order_id_patterns = ["order", "订单", "id", "no", "单号", "编号"]
        for pattern in order_id_patterns:
            for i, h in enumerate(headers_lower):
                if pattern in h:
                    mappings[source]["order_id"] = headers[i]
                    break
            if "order_id" in mappings[source]:
                break
        
        # amount 匹配
        amount_patterns = ["amount", "金额", "amt", "sum", "total", "钱"]
        for pattern in amount_patterns:
            for i, h in enumerate(headers_lower):
                if pattern in h:
                    mappings[source]["amount"] = headers[i]
                    break
            if "amount" in mappings[source]:
                break
        
        # date 匹配
        date_patterns = ["date", "日期", "time", "时间", "day"]
        for pattern in date_patterns:
            for i, h in enumerate(headers_lower):
                if pattern in h:
                    mappings[source]["date"] = headers[i]
                    break
            if "date" in mappings[source]:
                break
    
    # 清理空值
    return {k: v for k, v in mappings.items() if v}


__all__ = [
    "_apply_field_mapping_operations",
    "_format_operations_summary",
    "_format_field_mappings",
    "_format_edit_field_mappings",
    "_build_field_mapping_text",
    "_guess_field_mappings",
]

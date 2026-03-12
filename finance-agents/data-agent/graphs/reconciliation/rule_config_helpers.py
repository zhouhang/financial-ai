"""规则配置辅助函数模块

包含规则配置转换、格式化等功能。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _rule_template_to_mappings(rule_template: dict) -> dict[str, Any]:
    """将 rule_template 的 field_roles 转为 confirmed_mappings 格式。"""
    mappings: dict[str, dict] = {"business": {}, "finance": {}}
    ds = rule_template.get("data_sources", {})
    for src in ("business", "finance"):
        roles = ds.get(src, {}).get("field_roles", {})
        for role, col in roles.items():
            if col:
                mappings[src][role] = col
    return mappings


def _get_file_names_from_rule_template(rule_template: dict) -> dict[str, str]:
    """从 rule_template.data_sources 提取 file_pattern 第一个文件名。"""
    ds = rule_template.get("data_sources", {})
    biz_fp = ds.get("business", {}).get("file_pattern") or []
    fin_fp = ds.get("finance", {}).get("file_pattern") or []
    return {
        "business": biz_fp[0] if biz_fp else "文件1",
        "finance": fin_fp[0] if fin_fp else "文件2",
    }


def _rule_template_to_config_items(rule_template: dict) -> list[dict]:
    """将 rule_template 转为 rule_config_items，从 data_cleaning_rules 的 description 获取。
    不自动添加金额容差（仅当用户显式添加时才显示）。
    """
    items: list[dict] = []
    file_labels = _get_file_names_from_rule_template(rule_template)

    # 从 data_cleaning_rules 提取每个有 description 的规则项
    dcr = rule_template.get("data_cleaning_rules", {})
    for src in ("business", "finance"):
        src_label = file_labels.get(src, "文件1" if src == "business" else "文件2")
        src_rules = dcr.get(src, {})
        # field_transforms
        for t in src_rules.get("field_transforms", []):
            desc = t.get("description", "").strip()
            if desc:
                items.append({
                    "json_snippet": {"data_cleaning_rules": {src: {"field_transforms": [t]}}},
                    "description": f"{src_label}：{desc}",
                })
        # aggregations
        for agg in src_rules.get("aggregations", []):
            desc = agg.get("description", "").strip()
            if desc:
                items.append({
                    "json_snippet": {"data_cleaning_rules": {src: {"aggregations": [agg]}}},
                    "description": f"{src_label}：{desc}",
                })
        # row_filters
        for rf in src_rules.get("row_filters", []):
            desc = rf.get("description", "").strip()
            if desc:
                items.append({
                    "json_snippet": {"data_cleaning_rules": {src: {"row_filters": [rf]}}},
                    "description": f"{src_label}：{desc}",
                })
    
    # 若未提取到任何带描述的项，回退为整体展示（避免空列表）
    if not items:
        biz = dcr.get("business", {})
        fin = dcr.get("finance", {})
        if biz or fin:
            items.append({
                "json_snippet": {"data_cleaning_rules": {k: v for k, v in [("business", biz), ("finance", fin)] if v}},
                "description": "数据清理规则（转换、过滤、聚合）",
            })
    return items


def _build_rule_config_text(config_items: list[dict]) -> str:
    """将规则配置项中的用户输入或描述拼接为可保存的自然语言，供编辑规则时展示。"""
    if not config_items:
        return ""
    parts = []
    for item in config_items:
        text = (item.get("user_input") or item.get("description", "")).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _analyze_config_target(json_snippet: dict, file_names: dict[str, str] | None = None) -> str:
    """分析配置片段的目标（文件1、文件2或全局）。
    
    Args:
        json_snippet: JSON配置片段
        file_names: 文件名映射，格式 {"business": "文件1名", "finance": "文件2名"}
    """
    if not file_names:
        file_names = {"business": "文件1", "finance": "文件2"}
    
    if "data_cleaning_rules" in json_snippet:
        cleaning_rules = json_snippet["data_cleaning_rules"]
        has_business = "business" in cleaning_rules
        has_finance = "finance" in cleaning_rules
        
        if has_business and has_finance:
            return f"📁 {file_names.get('business', '文件1')} + {file_names.get('finance', '文件2')}"
        elif has_business:
            return f"📁 {file_names.get('business', '文件1')}"
        elif has_finance:
            return f"📁 {file_names.get('finance', '文件2')}"
    
    if "tolerance" in json_snippet:
        return "🌐 全局配置"
    if "filters" in json_snippet:
        return "🌐 全局配置"
    if "group_by" in json_snippet:
        return "🌐 全局配置"
    
    return "⚙️ 其他配置"


def _format_rule_config_items(config_items: list[dict] = None, file_names: dict[str, str] | None = None) -> str:
    """格式化已添加的配置项列表为用户友好的文本，标注每个规则的适用范围。

    Args:
        config_items: 配置项列表
        file_names: 文件名映射，格式 {"business": "文件1名", "finance": "文件2名"}
    """
    if not config_items or len(config_items) == 0:
        return "（暂无配置，请开始添加配置项）"

    def _strip_two_files_suffix(text: str) -> str:
        """去掉描述中的「（两个文件）」字样，避免重复（目标已标明文件范围）。"""
        for suffix in ("（两个文件）", "(两个文件)"):
            if text.endswith(suffix):
                return text[: -len(suffix)].rstrip().rstrip("，, ")
        return text

    def _strip_leading_filename(text: str, names: dict[str, str]) -> str:
        """若 desc 开头已包含文件名（来自 _rule_template_to_config_items），则去除避免重复显示。"""
        for label in (names or {}).values():
            for sep in ("：", ": ", " "):
                prefix = label + sep
                if text.startswith(prefix):
                    return text[len(prefix) :].strip()
            if text.startswith(label) and len(text) > len(label):
                return text[len(label) :].lstrip("：: ").strip()
        return text

    lines = []
    idx = 1
    for item in config_items:
        desc = item.get("description") or item.get("content") or item.get("name", "")
        if not desc:
            desc = "未知配置"
        json_snippet = item.get("json_snippet", {})
        target = _analyze_config_target(json_snippet, file_names) if json_snippet else ""
        if target:
            desc = _strip_leading_filename(desc, file_names or {})
            desc = _strip_two_files_suffix(desc)
            # 两个文件时，分两行显示（参照第二张图样式）
            if " + " in target:
                parts = [p.strip() for p in target.split(" + ")]
                for part in parts:
                    if part and not part.startswith("📁"):
                        part = "📁 " + part
                    lines.append(f"  {idx}. {part} {desc}")
                    idx += 1
            else:
                lines.append(f"  {idx}. {target} {desc}")
                idx += 1
        else:
            lines.append(f"  {idx}. {desc}")
            idx += 1

    return "\n".join(lines)


__all__ = [
    "_rule_template_to_mappings",
    "_get_file_names_from_rule_template",
    "_rule_template_to_config_items",
    "_build_rule_config_text",
    "_analyze_config_target",
    "_format_rule_config_items",
]

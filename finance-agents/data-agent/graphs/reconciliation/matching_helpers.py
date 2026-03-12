"""规则匹配辅助函数模块

包含规则匹配、字段匹配、模糊匹配等功能。
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


KEY_FIELD_ALIASES = {
    "order_id": ["订单号", "订单", "order", "order_id"],
    "amount": ["金额", "钱", "amount", "发生", "sum", "total"],
    "date": ["日期", "时间", "date", "time", "datetime"],
}

EXACT_MATCH_FIELDS = ["order_id", "amount"]


def _extract_keywords(text: str) -> set[str]:
    """从文本中提取关键词（包括中文词和英文词）。

    对于中文，按长度递减提取子串：
    - "文件1订单号" → {"文件1订单号", "文件1", "订单号", "文件", "1"}
    - "金额求和" → {"金额求和", "金额", "求和"}

    对于英文和数字，保留整体。
    """
    if not text:
        return set()

    keywords = set()
    text = text.strip()

    # 先加入整个文本（精确匹配的候选）
    keywords.add(text)

    # 提取中文子串和关键词
    for i in range(len(text)):
        for j in range(i + 1, len(text) + 1):
            substr = text[i:j]
            # 只加入包含中文或关键英文词的子串
            if any("\u4e00" <= c <= "\u9fff" for c in substr):  # 中文字符
                keywords.add(substr)

    # 按长度从长到短排序（优先精确匹配）
    return keywords


def _compute_keyword_overlap(target_keywords: set[str], desc_keywords: set[str]) -> float:
    """计算两个关键词集合的重叠度（0.0-1.0）。

    优先使用长字符串匹配（更精确），然后计算单字符重叠。
    """
    if not target_keywords or not desc_keywords:
        return 0.0

    # 先检查长字符串的精确匹配
    target_long = [k for k in target_keywords if len(k) >= 3]
    desc_long = [k for k in desc_keywords if len(k) >= 3]

    if target_long and desc_long:
        # 如果有长字符串匹配，使用它们
        long_match = len(target_keywords & desc_keywords)
        if long_match > 0:
            return 0.9  # 长字符串匹配权重很高

    # 计算单字符重叠度
    all_chars_target = set("".join(target_keywords))
    all_chars_desc = set("".join(desc_keywords))

    if not all_chars_target or not all_chars_desc:
        return 0.0

    overlap = len(all_chars_target & all_chars_desc)
    total = len(all_chars_target | all_chars_desc)

    return overlap / total if total > 0 else 0.0


def _calculate_fuzzy_match_score(target: str, description: str) -> float:
    """计算两个文本的相似度得分（0.0-1.0）。

    使用多种方法：
    1. 关键词重叠度
    2. 序列匹配相似度

    返回综合得分。
    """
    if not target or not description:
        return 0.0

    # 方法1：关键词重叠
    target_kw = _extract_keywords(target)
    desc_kw = _extract_keywords(description)
    keyword_score = _compute_keyword_overlap(target_kw, desc_kw)

    # 方法2：序列匹配
    seq_matcher = SequenceMatcher(None, target, description)
    sequence_score = seq_matcher.ratio()

    # 综合得分（关键词权重更高，因为更适合中文）
    combined_score = keyword_score * 0.6 + sequence_score * 0.4

    logger.debug(
        f"匹配分数 - target='{target}' vs description='{description}': "
        f"keyword={keyword_score:.2f}, sequence={sequence_score:.2f}, combined={combined_score:.2f}"
    )

    return combined_score


def _find_matching_items(
    target: str,
    items: list[dict[str, Any]],
    threshold: float = 0.5,
    max_matches: int | None = None,
    strict_substring_only: bool = False,
    key: str = "description",
) -> list[int]:
    """查找与目标重合度最高的配置项索引列表。

    Args:
        target: 用户指定的删除/更新目标
        items: 配置项列表，每项有 "description" 字段（或 key 指定的字段）
        threshold: 最低匹配度阈值（0.0-1.0），默认 0.5
        max_matches: 最多返回的匹配数量，None 表示不限制。删除操作应传 1，避免误删多个
        strict_substring_only: 若为 True（删除场景），仅接受子串匹配，不接受纯模糊匹配，避免误删
        key: 用于匹配的字段名，默认 "description"

    Returns:
        匹配的配置项索引列表（按相似度从高到低排序）
    """
    if not target or not items:
        return []

    target_lower = target.lower().strip()
    # 删除时要求 target 至少 3 字符，避免 "除"、"100" 等误匹配
    if strict_substring_only and len(target_lower) < 3:
        return []

    matches: list[tuple[int, float]] = []

    for idx, item in enumerate(items):
        description = item.get(key, "").lower().strip() if isinstance(item.get(key), str) else str(item.get(key, "")).lower().strip()

        # 先尝试精确匹配（仅 target 包含于 description，避免 description 过短导致误匹配）
        if target_lower in description:
            matches.append((idx, 1.0))  # 精确匹配得分为 1.0
            continue
        # description 包含于 target 时，需确保 description 足够长，避免单字误匹配
        if len(description) >= 4 and description in target_lower:
            matches.append((idx, 0.95))
            continue

        # strict 模式下不接受纯模糊匹配
        if strict_substring_only:
            continue

        # 否则使用模糊匹配
        score = _calculate_fuzzy_match_score(target_lower, description)
        if score >= threshold:
            matches.append((idx, score))

    # 按相似度从高到低排序
    matches.sort(key=lambda x: x[1], reverse=True)

    result = [idx for idx, _ in matches]
    if max_matches is not None and len(result) > max_matches:
        result = result[:max_matches]
    return result


def _is_field_match(rule_field: str, file_columns: list[str], field_role: str) -> tuple[bool, str]:
    """检查规则字段是否与文件列匹配。
    
    Args:
        rule_field: 规则中的字段名
        file_columns: 文件的列名列表
        field_role: 字段角色（如 order_id, amount）
    
    Returns:
        (是否匹配, 匹配类型)
    """
    if not rule_field or not file_columns:
        return False, ""
    
    rule_lower = rule_field.lower()
    columns_lower = [c.lower() for c in file_columns]
    
    # 角色关键词映射
    role_keywords = {
        "order_id": ["order", "订单", "id", "no", "单号", "编号"],
        "amount": ["amount", "金额", "amt", "sum", "total", "钱"],
        "date": ["date", "日期", "time", "时间", "day"],
        "status": ["status", "状态"],
    }
    
    role_words = role_keywords.get(field_role, [])
    
    for col in columns_lower:
        # 直接匹配
        if rule_lower == col:
            return True, "exact"
        
        # 包含匹配
        if rule_lower in col or col in rule_lower:
            return True, "partial"
        
        # 关键词匹配
        for word in role_words:
            if word in rule_lower and word in col:
                return True, "keyword"
    
    return False, ""


def match_rules_by_field_names(
    file_columns: dict[str, list[str]],
    rules: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], float, list[str]]]:
    """根据文件列名匹配规则。

    Args:
        file_columns: 文件列名字典，格式 {"business": [...], "finance": [...]}
        rules: 规则列表（含 rule_template 字段）

    Returns:
        匹配结果列表，每项为 (rule, score, matched_fields)，按 score 降序排列
    """
    if not rules or not file_columns:
        return []

    import json as _json

    results: list[tuple[dict[str, Any], float, list[str]]] = []

    for rule in rules:
        template = rule.get("rule_template", {})
        if isinstance(template, str):
            try:
                template = _json.loads(template)
            except Exception:
                continue

        data_sources = template.get("data_sources", {})
        matched_fields: list[str] = []
        total_fields = 0

        for src in ("business", "finance"):
            src_data = data_sources.get(src, {})
            field_roles = src_data.get("field_roles", {})
            if not field_roles:
                continue

            columns = file_columns.get(src, [])

            for role, rule_field in field_roles.items():
                total_fields += 1
                if isinstance(rule_field, list):
                    for rf in rule_field:
                        is_match, _ = _is_field_match(rf, columns, role)
                        if is_match:
                            matched_fields.append(f"{src}.{role}")
                            break
                elif rule_field:
                    is_match, _ = _is_field_match(rule_field, columns, role)
                    if is_match:
                        matched_fields.append(f"{src}.{role}")

        match_pct = calculate_match_percentage(matched_fields, total_fields) if total_fields > 0 else 0
        score = match_pct / 100.0
        results.append((rule, score, matched_fields))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


def calculate_match_percentage(matched_fields: list[str], total_fields: int = 6) -> int:
    """计算匹配百分比。"""
    if total_fields <= 0:
        return 0
    return min(100, int(len(matched_fields) / total_fields * 100))


def get_match_reason(matched_fields: list[str]) -> str:
    """生成匹配原因描述。"""
    if not matched_fields:
        return "未匹配到任何字段"
    
    parts = []
    for field in matched_fields:
        parts.append(f"✓ {field}")
    
    return f"匹配到 {len(matched_fields)} 个字段: {', '.join(parts)}"


__all__ = [
    "_extract_keywords",
    "_compute_keyword_overlap",
    "_calculate_fuzzy_match_score",
    "_find_matching_items",
    "_is_field_match",
    "match_rules_by_field_names",
    "calculate_match_percentage",
    "get_match_reason",
]

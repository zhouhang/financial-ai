"""对账辅助函数模块

包含字段映射、配置格式化、文本处理等辅助功能。
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)


# 所有支持的文件格式（保存规则时扩展 file_pattern）：Excel + CSV
FILE_PATTERN_EXTENSIONS = (".xlsx", ".xls", ".xlsm", ".xlsb", ".csv")


def _expand_file_patterns(pattern: str) -> list[str]:
    """如果是 Excel 或 CSV 格式的 pattern，扩展为所有支持格式并返回列表"""
    pattern_lower = pattern.lower()
    for ext in FILE_PATTERN_EXTENSIONS:
        if pattern_lower.endswith(ext):
            base = pattern[: -len(ext)]
            return [base + e for e in FILE_PATTERN_EXTENSIONS]
    return [pattern]


def _rewrite_schema_transforms_to_mapped_fields(schema: dict) -> None:
    """将 schema 中 transform/expression 的原始列名替换为映射后的角色名（原地修改）。
    
    LLM 生成的规则使用原始表头（如 sup订单号、roc_oid），
    但 data_cleaner 在字段映射之后执行 transform，此时列名已是角色名（order_id、amount）。
    保存前重写，确保生成的 JSON 文件使用映射字段名。
    """
    if not isinstance(schema, dict):
        return
    data_sources = schema.get("data_sources", {})
    cleaning_rules = schema.get("data_cleaning_rules", {})
    if not cleaning_rules:
        return
    
    def _rewrite_expr(expr: str, field_roles_all_sources: dict) -> str:
        """将 expr 中 row.get('orig_col', x) 替换为 row.get('role', x)"""
        if not expr or not isinstance(expr, str):
            return expr
        result = expr
        for orig_col, role in field_roles_all_sources.items():
            if orig_col == role:
                continue
            for q in ("'", '"'):
                old_pat = f"row.get({q}{orig_col}{q}"
                new_pat = f"row.get({q}{role}{q}"
                result = result.replace(old_pat, new_pat)
        return result
    
    # 合并所有数据源的 field_roles，构建 原始列名 -> 角色名
    orig_to_role = {}
    for _src, src_config in data_sources.items():
        for role, orig_cols in src_config.get("field_roles", {}).items():
            for orig in ([orig_cols] if isinstance(orig_cols, str) else orig_cols):
                orig_to_role[orig] = role
    
    for source_name, rules in cleaning_rules.items():
        for t in rules.get("field_transforms", []):
            for key in ("transform", "expression"):
                if key in t and t[key]:
                    t[key] = _rewrite_expr(t[key], orig_to_role)
        for rf in rules.get("row_filters", []):
            if "condition" in rf and rf["condition"]:
                rf["condition"] = _rewrite_expr(rf["condition"], orig_to_role)


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
            if any('\u4e00' <= c <= '\u9fff' for c in substr):  # 中文字符
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
    all_chars_target = set(''.join(target_keywords))
    all_chars_desc = set(''.join(desc_keywords))
    
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
    
    logger.debug(f"匹配分数 - target='{target}' vs description='{description}': "
                f"keyword={keyword_score:.2f}, sequence={sequence_score:.2f}, combined={combined_score:.2f}")
    
    return combined_score


def _find_matching_items(
    target: str,
    items: list[dict],
    threshold: float = 0.5,
    max_matches: int | None = None,
    strict_substring_only: bool = False,
) -> list[int]:
    """查找与目标重合度最高的配置项索引列表。
    
    Args:
        target: 用户指定的删除/更新目标
        items: 配置项列表，每项有 "description" 字段
        threshold: 最低匹配度阈值（0.0-1.0），默认 0.5
        max_matches: 最多返回的匹配数量，None 表示不限制。删除操作应传 1，避免误删多个
        strict_substring_only: 若为 True（删除场景），仅接受子串匹配，不接受纯模糊匹配，避免误删
    
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
        description = item.get("description", "").lower().strip()
        
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
        file_names = {"business": "文件1（业务数据）", "finance": "文件2（财务数据）"}
    else:
        # 补充默认标签
        if "business" not in file_names:
            file_names["business"] = "文件1（业务数据）"
        if "finance" not in file_names:
            file_names["finance"] = "文件2（财务数据）"
    
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


def _adjust_field_mappings_with_llm(
    current_mappings: dict[str, Any],
    user_instruction: str,
    analyses: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """使用 LLM 根据用户指令调整字段映射。 支持add/update/delete操作和文件级别的控制。
    
    返回：(调整后的映射, 执行的操作列表)
    """
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
    business_filename = ""
    finance_filename = ""
    for a in analyses:
        source = a.get("guessed_source", "")
        filename = a.get("filename", "")
        cols = a.get("columns", [])
        if source == "business":
            business_filename = filename
        elif source == "finance":
            finance_filename = filename
        available_cols.append(f"{filename}: {', '.join(cols[:20])}")
    
    available_cols_str = "\n".join(available_cols)
    
    # 增强的prompt，支持结构化操作
    json_examples = '''操作示例（返回此格式的operations数组）：
- {"action": "add", "target": "finance", "role": "status", "column": "订单状态", "description": "在财务文件添加status字段"}
- {"action": "update", "target": "business", "role": "order_id", "column": "新订单号", "description": "更新文件1的订单号映射"}
- {"action": "delete", "target": "business", "role": "status", "description": "删除文件1的status字段"}
- {"action": "delete_column", "target": "business", "role": "amount", "column": "pay_amt", "description": "仅删除文件1的amount字段中的pay_amt列别名，保留其他列"}
'''
    
    prompt = f"""你是一个字段映射调整助手。用户上传了两个文件，当前的字段映射如下：

{current_mapping_str}

可用的列名：
{available_cols_str}

用户的调整指令：
{user_instruction}

根据用户的指令，生成结构化的操作列表。用户可能会：
1. 只涉及一个文件的调整（如"文件1改为..."或"业务文件添加..."）
2. 同时涉及两个文件的调整（如"两个文件都添加status"）
3. 删除某个字段的列别名（如"去掉pay_amt"、"删除amount中的pay_amt"）⚠️ 重要：如果用户说"删除xxx"且xxx是字段中的某个列名（不是role名），应该使用 delete_column 而不是 delete
4. 删除整个字段（如"删除status字段"）
5. 修改字段映射（如"order_id改为xxx"）

严格按以下 JSON 格式返回，不要添加其他内容：
{{"operations": [操作对象数组]}}

{json_examples}

⚠️ 重要规则：
1. 只生成用户明确指示的操作（不要推断未提到的操作）
2. 如果用户说"文件1"或"业务文件"，target应为"business"
3. 如果用户说"文件2"或"财务文件"，target应为"finance"
4. 如果用户只指定一个文件，只为该文件生成操作
5. 如果用户说"两个文件都..."，为两个文件都生成操作
6. role必须是：order_id、amount、date、status之一（标准定义）
7. column可以是单个列名（如"订单号"）或列名列表（如["订单编号", "订单号"]）
8. 不要生成删除order_id、amount、date整个字段的操作（这些是必需的）
9. ⭐️ 关键区分：
   - 如果用户想删除一个 **role本身**（如"删除status"）→ 使用 action: "delete"，不指定column
   - 如果用户想删除该role下的 **某个列别名**（如"删除pay_amt"）→ 使用 action: "delete_column"，指定column
   - 例：当前amount有["pay_amt", "金额"]两个列，用户说"去掉pay_amt" → delete_column with column="pay_amt"
10. ⭐️ delete_column 严格匹配：每个 delete_column 的 column 必须与用户说的列名**完全一致**。
   - 用户说"去掉喜马订单号、订单号、合单订单号、退款订单号"时，只生成这4个 delete_column，不要多删。
   - "第三方订单号"与"订单号"是不同列，用户没说去掉"第三方订单号"就绝不能删除它。
   - 不要因列名相似或同属某类而推断删除用户未提及的列。
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
        
        parsed = json.loads(content)
        operations = parsed.get("operations", [])
        
        logger.info(f"LLM 生成的操作: {operations}")
        
        # 应用操作
        new_mappings = _apply_field_mapping_operations(current_mappings, operations)
        
        logger.info(f"字段映射调整完成: {new_mappings}")
        return new_mappings, operations
    
    except Exception as e:
        logger.warning(f"LLM 字段映射调整失败: {e}")
        # 失败则返回原映射和空操作列表
        return current_mappings, []


def _format_field_mappings(mappings: dict[str, Any], analyses: list[dict[str, Any]]) -> str:
    """将字段映射格式化为 业务列名↔财务列名 形式，按 field_roles 配对。"""
    business_map = mappings.get("business", {})
    finance_map = mappings.get("finance", {})

    def _fmt_col(v):
        if isinstance(v, list):
            return "、".join(str(x) for x in v)
        return str(v) if v else ""

    # 取 business 与 finance 的 field_roles 公共 key 做配对
    common_roles = sorted(business_map.keys() & finance_map.keys())
    lines: list[str] = []
    for role in common_roles:
        biz_col = business_map.get(role)
        fin_col = finance_map.get(role)
        if biz_col and fin_col:
            lines.append(f"{_fmt_col(biz_col)}↔{_fmt_col(fin_col)}")

    if not lines:
        return "（未找到匹配字段）"
    # 每项前换行，确保 Markdown 渲染时分行显示
    return "\n\n".join(lines)


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
        "business": biz_fp[0] if biz_fp else "业务文件",
        "finance": fin_fp[0] if fin_fp else "财务文件",
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
        src_label = file_labels.get(src, "业务文件" if src == "business" else "财务文件")
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


def _format_edit_field_mappings(mappings: dict[str, Any]) -> str:
    """编辑模式下格式化字段映射（无需 file_analyses），按 field_roles 配对，格式：业务列名↔财务列名。"""
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
            lines.append(f"{_fmt_col(biz_col)}↔{_fmt_col(fin_col)}")
    # 每项前换行，确保 Markdown 渲染时分行显示
    return "\n\n".join(lines) if lines else "（无映射）"


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


def _guess_field_mappings(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """使用 LLM 智能猜测字段映射：原始列名 → 标准角色。"""
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
        "请为每个文件的列名匹配到以下标准角色（**只猜测以下 3 个必需角色**）：\n"
        "- order_id: 订单号/交易号（用于两边数据匹配的关键字段）\n"
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

    return mappings


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


def _build_dummy_analyses_from_mappings(mappings: dict[str, Any]) -> list[dict]:
    """从 mappings 构建虚拟 analyses，供编辑模式下 _adjust_field_mappings_with_llm 使用。"""
    analyses = []
    for src, label in [("business", "业务文件"), ("finance", "财务文件")]:
        cols = []
        for role, col in mappings.get(src, {}).items():
            if isinstance(col, list):
                cols.extend(col)
            elif col:
                cols.append(str(col))
        analyses.append({"guessed_source": src, "filename": label, "columns": cols})
    return analyses


def _analyze_config_target(json_snippet: dict, file_names: dict[str, str] | None = None) -> str:
    """分析配置片段的目标（业务数据、财务数据或全局）。
    
    Args:
        json_snippet: JSON配置片段
        file_names: 文件名映射，格式 {"business": "文件1名", "finance": "文件2名"}
    """
    # 如果没有提供文件名，使用默认值
    if not file_names:
        file_names = {"business": "业务文件(文件1)", "finance": "财务文件(文件2)"}
    
    # 检查是否是数据清理规则
    if "data_cleaning_rules" in json_snippet:
        cleaning_rules = json_snippet["data_cleaning_rules"]
        has_business = "business" in cleaning_rules
        has_finance = "finance" in cleaning_rules
        
        if has_business and has_finance:
            return f"📁 {file_names.get('business', '文件1')} + {file_names.get('finance', '文件2')}"
        elif has_business:
            return f"📁 {file_names.get('business', '业务文件(文件1)')}"
        elif has_finance:
            return f"📁 {file_names.get('finance', '财务文件(文件2)')}"
    
    # 检查是否是全局规则（容差、过滤等）
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
    
    lines = []
    for i, item in enumerate(config_items, 1):
        desc = item.get("description") or item.get("content") or item.get("name", "")
        if not desc:
            desc = "未知配置"
        json_snippet = item.get("json_snippet", {})
        target = _analyze_config_target(json_snippet, file_names) if json_snippet else ""
        if target:
            lines.append(f"  {i}. {target} {desc}")
        else:
            lines.append(f"  {i}. {desc}")
    
    return "\n".join(lines)


def _validate_and_deduplicate_rules(schema: dict) -> dict:
    """验证和去重规则，特别是防止重复的字段转换规则。
    
    问题场景：
    1. 有两个订单号规则：第一个"去单引号截取21位"，第二个"去单引号截取21位、104开头"
    2. 这会导致重复处理同一字段
    3. 两个数据源都有相同的row_filters会导致对账结果显示0个差异
    
    解决方案：
    1. 检测重复的字段transforms（相同字段的多个规则）
    2. 对于同一字段的多个rules，合并为一个（先format后filter）
    3. 将过滤逻辑转移到row_filters
    4. 检测并删除business中的row_filters（row_filters只应该用于finance）
    """
    import copy
    result = copy.deepcopy(schema)
    
    for source in ["business", "finance"]:
        cleaning_rules = result.get("data_cleaning_rules", {}).get(source, {})
        field_transforms = cleaning_rules.get("field_transforms", [])
        
        # 检测同一字段的多个transforms
        field_groups = {}
        for idx, transform in enumerate(field_transforms):
            field = transform.get("field")
            if field not in field_groups:
                field_groups[field] = []
            field_groups[field].append((idx, transform))
        
        # 对于订单号字段，特殊处理去重
        if "order_id" in field_groups and len(field_groups["order_id"]) > 1:
            order_id_rules = field_groups["order_id"]
            logger.warning(f"⚠️ 检测到 {source} 中有 {len(order_id_rules)} 个订单号transform规则，可能存在重复")
            
            # 检查是否有两个非常相似的规则（都是去单引号截取21位）
            descriptions = [r[1].get("description", "") for r in order_id_rules]
            if any("去单引号" in d and "21" in d for d in descriptions) and len(descriptions) > 1:
                # 保留第一个规则，删除其他相似的
                rules_to_keep = []
                found_format_rule = False
                
                for idx, transform in order_id_rules:
                    desc = transform.get("description", "")
                    is_format_rule = "去单引号" in desc and "21" in desc and "104" not in desc
                    
                    if is_format_rule:
                        if not found_format_rule:
                            rules_to_keep.append((idx, transform))
                            found_format_rule = True
                        else:
                            logger.warning(f"  删除重复的规则（保留第一个）: {desc}")
                    else:
                        rules_to_keep.append((idx, transform))
                
                # 重建field_transforms，只保留未重复的规则
                if len(rules_to_keep) < len(order_id_rules):
                    new_field_transforms = []
                    for idx, transform in enumerate(field_transforms):
                        field = transform.get("field")
                        if field == "order_id":
                            # 只保留rules_to_keep中的
                            if any(kk[1] == transform for kk in rules_to_keep):
                                new_field_transforms.append(transform)
                        else:
                            new_field_transforms.append(transform)
                    
                    result["data_cleaning_rules"][source]["field_transforms"] = new_field_transforms
                    logger.info(f"✅ 去重后 {source} 的订单号transform规则数: {len([r for r in new_field_transforms if r.get('field') == 'order_id'])}")
    
    # 🔴 关键检查：防止对账结果显示0个差异的情况
    # 如果两个数据源有相同的row_filters，会导致和数据被过滤成相同，无法对账
    business_row_filters = result.get("data_cleaning_rules", {}).get("business", {}).get("row_filters", [])
    finance_row_filters = result.get("data_cleaning_rules", {}).get("finance", {}).get("row_filters", [])
    
    if business_row_filters and finance_row_filters:
        # 检查是否有相同的条件
        business_conditions = {json.dumps(f.get("condition"), sort_keys=True): f for f in business_row_filters}
        finance_conditions = {json.dumps(f.get("condition"), sort_keys=True): f for f in finance_row_filters}
        
        common_conditions = set(business_conditions.keys()) & set(finance_conditions.keys())
        if common_conditions:
            logger.error(f"🔴 严重问题：业务数据和财务数据有相同的row_filters，会导致对账失败！")
            logger.error(f"   相同的条件: {common_conditions}")
            logger.error(f"   这会导致两个数据源过滤后记录数相同，无法显示实际差异")
            logger.error(f"   正确做法：row_filters只应该用于财务数据，用于排除特殊内部记录（如加款单）")
            
            # 自动删除业务数据的row_filters
            logger.warning(f"⚠️  已自动删除业务数据中的 {len(business_row_filters)} 个row_filters")
            if "data_cleaning_rules" in result and "business" in result["data_cleaning_rules"]:
                result["data_cleaning_rules"]["business"]["row_filters"] = []
    elif business_row_filters and not finance_row_filters:
        logger.warning(f"⚠️ 检测到业务数据有row_filters但财务数据没有，这可能不符合预期")
        logger.warning(f"   row_filters通常只应该用于财务数据，用于排除加款单等特殊记录")
        logger.warning(f"   正在删除业务数据的{len(business_row_filters)}个row_filters")
        if "data_cleaning_rules" in result and "business" in result["data_cleaning_rules"]:
            result["data_cleaning_rules"]["business"]["row_filters"] = []
    
    return result


def _merge_json_snippets(base_schema: dict, snippets: list[dict]) -> dict:
    """将多个JSON片段合并到基础schema中。
    
    Args:
        base_schema: 基础schema（从模板或默认值）
        snippets: JSON片段列表，每个片段包含要合并的配置
    
    Returns:
        合并后的完整schema
    """
    import copy
    result = copy.deepcopy(base_schema)
    
    for snippet_info in snippets:
        snippet = snippet_info.get("json_snippet", {})
        if not snippet:
            continue
        
        # 深度合并（排除 custom_validations，仅使用 base_schema 的，避免 LLM 误输出导致 format 报错）
        _skip_keys = frozenset({"custom_validations"})
        
        def deep_merge(target: dict, source: dict):
            for key, value in source.items():
                if key in _skip_keys:
                    continue
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    deep_merge(target[key], value)
                elif key in target and isinstance(target[key], list) and isinstance(value, list):
                    # 对于列表，追加新项（避免完全重复的项）
                    for item in value:
                        # 简单去重：如果item是dict，检查是否已存在相同的项
                        if isinstance(item, dict):
                            # 通过JSON字符串比较来判断是否重复
                            item_str = json.dumps(item, sort_keys=True)
                            exists = any(json.dumps(existing, sort_keys=True) == item_str 
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


def _translate_rule_name_to_english(rule_name_cn: str) -> str:
    """将中文规则名称翻译成英文，用作 type_key 和文件名。
    
    使用 pypinyin 将中文转为拼音，避免使用 LLM。
    返回格式：小写字母和下划线，例如：direct_sales_reconciliation
    """
    try:
        from pypinyin import pinyin, Style
        
        # 获取拼音（首字母模式更简洁）
        pinyin_list = pinyin(rule_name_cn, style=Style.NORMAL)
        
        # 将拼音转为下划线分隔的英文
        pinyin_words = [py[0] for py in pinyin_list if py[0]]  # 每个汉字的拼音
        type_key = '_'.join(pinyin_words).lower()
        
        # 清理结果（只保留小写字母、数字和下划线）
        type_key = re.sub(r'[^a-z0-9_]', '_', type_key)
        type_key = re.sub(r'_+', '_', type_key)  # 多个下划线合并为一个
        type_key = type_key.strip('_')  # 去除首尾下划线
        
        # 确保以字母开头
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        
        # 如果转换失败或结果为空，使用默认方式
        if not type_key or len(type_key) < 3:
            type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
            if not type_key or type_key[0].isdigit():
                type_key = "rule_" + type_key
        
        logger.info(f"规则名称转换: {rule_name_cn} → {type_key}")
        return type_key
    
    except ImportError:
        logger.warning("pypinyin 库未安装，使用默认方式转换规则名称")
        # 降级方案：直接转换
        type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        return type_key
    
    except Exception as e:
        logger.warning(f"规则名称转换失败: {e}，使用默认方式")
        # 降级方案：直接转换
        type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        return type_key


# ══════════════════════════════════════════════════════════════════════════════
# 规则推荐 - 字段名匹配算法
# ══════════════════════════════════════════════════════════════════════════════

# 字段别名映射（用于模糊匹配）- 只包含通用词，不包含具体字段名
KEY_FIELD_ALIASES = {
    "order_id": ["订单号", "订单", "order", "order_id"],
    "amount": ["金额", "钱", "amount", "发生", "sum", "total"],
    "date": ["日期", "时间", "date", "time", "datetime"],
}

# 严格匹配：这些字段名必须精确匹配，不能模糊匹配
EXACT_MATCH_FIELDS = ["order_id", "amount"]


def _is_field_match(rule_field: str, file_columns: list[str], field_role: str) -> tuple[bool, str]:
    """检查规则字段是否与文件列名匹配。
    
    严格匹配规则：
    1. order_id: 必须精确匹配（包含关系也不行）
    2. amount: 必须完全相同或非常接近（如"发生"匹配"发生-"）
    3. date: 可以模糊匹配
    
    Args:
        rule_field: 规则中的字段名
        file_columns: 文件的列名列表
        field_role: 字段角色 (order_id/amount/date)
    
    Returns:
        (is_match, matched_column)
    """
    if not rule_field:
        return False, ""
    
    # 处理列表类型的字段名
    if isinstance(rule_field, list):
        rule_field = rule_field[0] if rule_field else ""
    
    rule_field = str(rule_field).strip()
    if not rule_field:
        return False, ""
    
    for col in file_columns:
        col = str(col).strip()
        if not col:
            continue
        
        col_lower = col.lower()
        rule_lower = rule_field.lower()
        
        # 1. 精确匹配（最严格）
        if rule_lower == col_lower:
            return True, col
        
        # 2. 对于 order_id，必须更严格匹配
        if field_role == "order_id":
            # 允许：订单号 ↔ 订单号，第三方订单号 ↔ 第三方订单号
            # 不允许：sp订单号 ↔ 第三方订单号
            # 只有完全包含才算匹配
            if rule_lower in col_lower or col_lower in rule_lower:
                # 但要排除部分匹配的情况
                # 例如：sp订单号 不应该匹配 第三方订单号
                continue
        
        # 3. 对于 amount，必须非常接近
        if field_role == "amount":
            # 允许：发生 ↔ 发生-，金额 ↔ 金额
            # 不允许：销售额 ↔ 应结算平台金额
            # 检查是否一个是另一个的子串，且长度差异不大
            if rule_lower in col_lower or col_lower in rule_lower:
                # 长度差异超过3个字符就不算匹配
                if abs(len(rule_lower) - len(col_lower)) <= 2:
                    return True, col
                continue
        
        # 4. 对于 date，可以使用模糊匹配
        if field_role == "date":
            # 检查是否包含时间相关的关键词
            date_keywords = ["日期", "时间", "date", "time", "datetime", "创建", "下单", "支付", "完成", "发生"]
            if any(kw in rule_lower for kw in date_keywords):
                if any(kw in col_lower for kw in date_keywords):
                    if rule_lower in col_lower or col_lower in rule_lower:
                        return True, col
    
    return False, ""


def match_rules_by_field_names(
    file_columns: dict[str, list[str]], 
    rules: list[dict]
) -> list[tuple[dict, int, list[str]]]:
    """根据文件表头字段名匹配规则，返回排序后的匹配结果。
    
    匹配策略：
    1. 必须同时匹配 business 和 finance 的字段
    2. order_id 必须精确匹配
    3. 根据匹配字段数量和精确度计算分数
    
    Args:
        file_columns: {"business": ["sp订单号", "销售额", "订单时间"], "finance": ["sup订单号", "发生-", "完成时间"]}
        rules: 规则列表，每个规则包含 rule_template
    
    Returns:
        [(rule, score, matched_fields), ...] 按 score 降序排列
    """
    matched_rules = []
    
    for rule in rules:
        template = rule.get("rule_template", {})
        if isinstance(template, str):
            try:
                template = json.loads(template)
            except json.JSONDecodeError:
                continue
        
        rule_name = rule.get("name", "")
        
        biz_fields = template.get("data_sources", {}).get("business", {}).get("field_roles", {})
        fin_fields = template.get("data_sources", {}).get("finance", {}).get("field_roles", {})
        
        biz_matched = []
        fin_matched = []
        
        # 匹配 business 字段
        for role, rule_field in biz_fields.items():
            is_match, matched_col = _is_field_match(rule_field, file_columns.get("business", []), role)
            if is_match:
                # order_id 权重更高
                weight = 3 if role == "order_id" else 2
                biz_matched.append((role, matched_col, weight))
        
        # 匹配 finance 字段
        for role, rule_field in fin_fields.items():
            is_match, matched_col = _is_field_match(rule_field, file_columns.get("finance", []), role)
            if is_match:
                weight = 3 if role == "order_id" else 2
                fin_matched.append((role, matched_col, weight))
        
        # 计算总分
        biz_score = sum(w for _, _, w in biz_matched)
        fin_score = sum(w for _, _, w in fin_matched)
        total_score = biz_score + fin_score
        
        # 构建匹配字段描述
        matched_fields = [f"business.{r}:{c}" for r, c, _ in biz_matched]
        matched_fields += [f"finance.{r}:{c}" for r, c, _ in fin_matched]
        
        # 必须同时匹配 business 和 finance 的 order_id
        biz_has_order_id = any(r == "order_id" for r, _, _ in biz_matched)
        fin_has_order_id = any(r == "order_id" for r, _, _ in fin_matched)
        
        # 只有当 business 和 finance 都有匹配时才推荐
        if biz_has_order_id and fin_has_order_id and total_score >= 6:
            matched_rules.append((rule, total_score, matched_fields))
    
    matched_rules.sort(key=lambda x: x[1], reverse=True)
    return matched_rules


def calculate_match_percentage(matched_fields: list[str], total_fields: int = 6) -> int:
    """计算匹配度百分比 - 基于实际匹配的字段计算"""
    if not matched_fields:
        return 0
    
    biz_count = sum(1 for f in matched_fields if f.startswith("business."))
    fin_count = sum(1 for f in matched_fields if f.startswith("finance."))
    
    # 基础分数：每个字段 17%
    base = (biz_count + fin_count) * 17
    
    # 如果 business 和 finance 都有 3 个字段匹配，给满分
    if biz_count >= 3 and fin_count >= 3:
        return 100
    
    return min(100, base)


def get_match_reason(matched_fields: list[str]) -> str:
    """根据匹配字段生成推荐理由"""
    biz_count = sum(1 for f in matched_fields if f.startswith("business."))
    fin_count = sum(1 for f in matched_fields if f.startswith("finance."))
    order_id_matched = any("order_id" in f for f in matched_fields)

    if biz_count >= 3 and fin_count >= 3:
        return "推荐"
    elif biz_count >= 2 and fin_count >= 2:
        return "关键字段匹配" if order_id_matched else "部分匹配"
    elif order_id_matched:
        return "订单号匹配"
    else:
        return "有匹配"


# ══════════════════════════════════════════════════════════════════════════════
# 智能文件分析辅助函数
# ══════════════════════════════════════════════════════════════════════════════

def quick_complexity_check(uploaded_files: list) -> str:
    """快速检查文件复杂度

    Returns:
        "simple": 标准场景（2个文件，标准格式）
        "medium": 中等复杂（多sheet或可能有格式问题）
        "complex": 复杂场景（多文件配对、确定有格式问题）
    """
    if not uploaded_files:
        return "simple"

    file_count = len(uploaded_files)

    # 快速判断
    if file_count > 2:
        return "complex"
    elif file_count == 1:
        return "medium"  # 单文件可能需要拆分或识别
    else:
        # 2个文件，检查是否都是标准格式（简单启发式）
        # 这里只做快速判断，详细检测由MCP工具完成
        return "simple"


async def invoke_intelligent_analyzer(uploaded_files: list, complexity_level: str) -> dict:
    """调用智能文件分析器（基于SKILL.md策略）

    Args:
        uploaded_files: 上传的文件列表
        complexity_level: 复杂度级别

    Returns:
        {
            "success": bool,
            "analyses": list,  # 标准化的文件分析结果
            "recommendations": dict,  # 推荐方案
            "warnings": list  # 警告信息
        }
    """
    from app.tools.mcp_client import call_mcp_tool
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.utils.llm import get_llm
    import json
    from pathlib import Path

    logger.info(f"开始智能文件分析，复杂度: {complexity_level}, 文件数: {len(uploaded_files)}")

    try:
        # 1. 调用MCP工具检测详细复杂度
        complexity_result = await call_mcp_tool("detect_file_complexity", {"files": uploaded_files})

        if not complexity_result.get("success"):
            logger.error(f"复杂度检测失败: {complexity_result.get('error')}")
            # 降级到简单分析
            return await _fallback_to_simple_analysis(uploaded_files)

        complexity_info = complexity_result

        # 2. 处理多文件配对（优先级最高，因为涉及文件选择）
        if complexity_info.get("file_count", 0) > 2:
            return await _smart_file_pairing(uploaded_files, complexity_info)

        # 3. 处理单文件场景
        if complexity_info.get("file_count", 0) == 1:
            # 单文件多sheet
            if complexity_info.get("multi_sheet"):
                return await _analyze_multi_sheet_files(uploaded_files, complexity_info)
            # 单文件单sheet
            return await _analyze_single_file(uploaded_files[0], complexity_info)

        # 4. 处理双文件多sheet场景
        if complexity_info.get("file_count", 0) == 2 and complexity_info.get("multi_sheet"):
            # 双文件中有多sheet文件，需要智能判断
            # 优先尝试直接配对（假设用户上传的是2个标准文件）
            return await _fallback_to_simple_analysis(uploaded_files)

        # 5. 标准场景，但可能有格式问题
        if complexity_info.get("non_standard"):
            return await _analyze_with_format_normalization(uploaded_files, complexity_info)

        # 6. 降级到简单分析
        return await _fallback_to_simple_analysis(uploaded_files)

    except Exception as e:
        logger.error(f"智能分析失败: {e}", exc_info=True)
        return await _fallback_to_simple_analysis(uploaded_files)


async def _analyze_multi_sheet_files(uploaded_files: list, complexity_info: dict) -> dict:
    """分析包含多sheet的Excel文件"""
    from app.tools.mcp_client import call_mcp_tool
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.utils.llm import get_llm
    import json

    logger.info("处理多sheet文件场景")

    all_analyses = []
    warnings = []

    # 对每个多sheet文件进行处理
    for multi_sheet_file in complexity_info.get("multi_sheet_files", []):
        file_path = multi_sheet_file["file_path"]

        # 读取所有sheet
        sheets_result = await call_mcp_tool("read_excel_sheets", {
            "file_path": file_path,
            "sample_rows": 5
        })

        if not sheets_result.get("success"):
            warnings.append(f"无法读取文件 {file_path} 的sheets")
            continue

        sheets = sheets_result.get("sheets", [])

        # 使用LLM识别每个sheet的类型
        sheet_types = await _classify_sheets_with_llm(sheets, file_path)

        # 将识别结果转换为标准分析格式
        for sheet_info in sheets:
            if "error" in sheet_info:
                continue

            sheet_name = sheet_info["sheet_name"]
            guessed_type = sheet_types.get(sheet_name, {}).get("type", "unknown")
            confidence = sheet_types.get(sheet_name, {}).get("confidence", 0.5)

            # 只保留business和finance类型的sheet
            if guessed_type in ["business", "finance"]:
                all_analyses.append({
                    "filename": f"{file_path} - {sheet_name}",
                    "original_filename": f"{multi_sheet_file.get('original_filename', file_path)} - {sheet_name}",
                    "file_path": file_path,
                    "sheet_name": sheet_name,
                    "columns": sheet_info["columns"],
                    "row_count": sheet_info["row_count"],  # 这是样本行数
                    "sample_data": sheet_info["sample_data"],
                    "guessed_source": guessed_type,
                    "confidence": confidence,
                    "processing_notes": f"从多sheet文件中识别（置信度: {int(confidence*100)}%）"
                })
            elif guessed_type == "summary":
                warnings.append(f"{sheet_name}: 识别为汇总表，已跳过")
            else:
                warnings.append(f"{sheet_name}: 类型未知，已跳过")

    # 检查是否成功识别出business和finance
    has_business = any(a["guessed_source"] == "business" for a in all_analyses)
    has_finance = any(a["guessed_source"] == "finance" for a in all_analyses)

    recommendations = {
        "success": has_business and has_finance,
        "message": ""
    }

    if has_business and has_finance:
        recommendations["message"] = "✅ 成功识别出业务数据和财务数据"
    elif has_business:
        recommendations["message"] = "⚠️ 只识别到业务数据，请补充上传财务数据文件"
    elif has_finance:
        recommendations["message"] = "⚠️ 只识别到财务数据，请补充上传业务数据文件"
    else:
        recommendations["message"] = "❌ 未识别到有效的对账数据"

    return {
        "success": True,
        "analyses": all_analyses,
        "recommendations": recommendations,
        "warnings": warnings
    }


async def _classify_sheets_with_llm(sheets: list, file_path: str) -> dict:
    """使用LLM分类sheet类型（参考skill.md策略）

    优化：
    - 限制一次分析的sheet数量（最多15个），避免prompt过长
    - sheet过多时只分析最有可能的候选（按行数排序）
    - 添加30秒超时保护，超时则降级到基于名称判断
    - 失败时使用降级策略_fallback_classify_sheets_by_name
    """
    from app.utils.llm import get_llm
    import json

    # 优化：限制一次分析的sheet数量（最多15个）
    MAX_SHEETS_PER_CALL = 15
    valid_sheets = [s for s in sheets if "error" not in s]

    if len(valid_sheets) > MAX_SHEETS_PER_CALL:
        logger.warning(f"检测到{len(valid_sheets)}个sheet，过多！只分析前{MAX_SHEETS_PER_CALL}个")
        # 优先分析有数据的sheet（行数>0）
        valid_sheets = sorted(valid_sheets, key=lambda s: s.get("row_count", 0), reverse=True)
        valid_sheets = valid_sheets[:MAX_SHEETS_PER_CALL]
        sheets = valid_sheets

    # 构建prompt
    sheets_desc = []
    for sheet in sheets:
        if "error" in sheet:
            continue
        cols_str = ", ".join(sheet.get("columns", [])[:15])
        sheets_desc.append(
            f"Sheet名称: {sheet['sheet_name']}\n"
            f"  列名: {cols_str}\n"
            f"  行数: {sheet.get('row_count', 0)}"
        )

    prompt = f"""你是财务数据分析专家。分析以下Excel文件的sheet，判断每个sheet的数据类型。

文件: {file_path}

Sheet信息（共{len(sheets_desc)}个）：
{chr(10).join(sheets_desc)}

类型定义：
- business: 业务数据（订单、销售、交易等，包含订单号、商品、金额等）
- finance: 财务数据（账单、流水、发票等，包含财务科目、收支等）
- summary: 汇总表（统计、总结类，不包含明细数据）
- other: 其他（说明、模板、空表等）

严格按以下JSON格式回复：
{{"results": [{{"sheet_name": "...", "type": "business|finance|summary|other", "confidence": 0.85, "reason": "..."}}]}}
"""

    try:
        llm = get_llm(temperature=0.1)

        # 添加30秒超时保护
        import asyncio
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, prompt),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error(f"LLM分类sheet超时（30秒），sheet数: {len(sheets_desc)}")
            # 降级：按sheet名称判断
            return _fallback_classify_sheets_by_name(sheets)

        content = resp.content.strip()

        # 提取JSON
        if "```" in content:
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)

        parsed = json.loads(content)
        results = parsed.get("results", [])

        # 转换为字典
        return {
            r["sheet_name"]: {
                "type": r["type"],
                "confidence": r.get("confidence", 0.5),
                "reason": r.get("reason", "")
            }
            for r in results
        }

    except Exception as e:
        logger.error(f"LLM分类sheet失败: {e}", exc_info=True)
        # 降级：按sheet名称判断
        return _fallback_classify_sheets_by_name(sheets)


def _fallback_classify_sheets_by_name(sheets: list) -> dict:
    """降级策略：根据sheet名称简单判断类型"""
    result = {}

    business_keywords = ["订单", "销售", "交易", "业务", "商品", "order", "sales", "transaction"]
    finance_keywords = ["财务", "账单", "流水", "发票", "finance", "bill", "invoice", "account"]
    summary_keywords = ["汇总", "统计", "总结", "summary", "total"]

    for sheet in sheets:
        if "error" in sheet:
            continue

        sheet_name = sheet.get("sheet_name", "").lower()

        # 判断类型
        if any(kw in sheet_name for kw in business_keywords):
            result[sheet["sheet_name"]] = {"type": "business", "confidence": 0.6, "reason": "根据sheet名称判断"}
        elif any(kw in sheet_name for kw in finance_keywords):
            result[sheet["sheet_name"]] = {"type": "finance", "confidence": 0.6, "reason": "根据sheet名称判断"}
        elif any(kw in sheet_name for kw in summary_keywords):
            result[sheet["sheet_name"]] = {"type": "summary", "confidence": 0.6, "reason": "根据sheet名称判断"}
        else:
            result[sheet["sheet_name"]] = {"type": "other", "confidence": 0.3, "reason": "无法识别"}

    logger.info(f"使用降级策略分类了{len(result)}个sheet")
    return result


async def _smart_file_pairing(uploaded_files: list, complexity_info: dict) -> dict:
    """智能文件配对（>2个文件）"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info(f"智能配对场景，共{len(uploaded_files)}个文件")

    # 先分析所有文件
    file_paths = [f.get("file_path") for f in uploaded_files]
    original_filenames_map = {f.get("file_path"): f.get("original_filename") for f in uploaded_files if f.get("original_filename")}

    result = await call_mcp_tool("analyze_files", {
        "file_paths": file_paths,
        "original_filenames": original_filenames_map
    })

    if not result.get("success"):
        return {
            "success": False,
            "error": "文件分析失败",
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    analyses = result.get("analyses", [])

    # 计算文件间的相似度，推荐最佳配对
    business_files = [a for a in analyses if a.get("guessed_source") == "business"]
    finance_files = [a for a in analyses if a.get("guessed_source") == "finance"]

    if not business_files or not finance_files:
        return {
            "success": False,
            "analyses": analyses,
            "recommendations": {
                "message": "❌ 未能识别出有效的业务-财务文件配对"
            },
            "warnings": [f"业务文件: {len(business_files)}个, 财务文件: {len(finance_files)}个"]
        }

    # 简单推荐：选择第一个business和第一个finance
    # TODO: 未来可以实现更智能的配对算法（列名相似度、行数接近度等）
    selected_business = business_files[0]
    selected_finance = finance_files[0]

    recommended_pair = {
        "business": selected_business,
        "finance": selected_finance,
        "confidence": 0.85,
        "reason": "基于文件类型自动配对"
    }

    # 收集被排除的文件
    selected_filenames = {selected_business['original_filename'], selected_finance['original_filename']}
    excluded_files = [
        a['original_filename']
        for a in analyses
        if a.get('original_filename') not in selected_filenames
    ]

    # 构建warnings列表
    warning_msgs = [f"检测到{len(uploaded_files)}个文件，已自动选择最佳配对"]
    if excluded_files:
        warning_msgs.append(f"已排除: {', '.join(excluded_files)}")

    return {
        "success": True,
        "analyses": [selected_business, selected_finance],  # 只返回推荐的配对
        "recommendations": {
            "pairing": recommended_pair,
            "message": f"✅ 推荐配对: {selected_business['original_filename']} ↔ {selected_finance['original_filename']}"
        },
        "warnings": warning_msgs
    }


async def _analyze_single_file(uploaded_file: dict, complexity_info: dict) -> dict:
    """分析单个文件（尝试拆分或提示缺失）"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info("单文件场景，尝试识别类型")

    file_path = uploaded_file.get("file_path")
    result = await call_mcp_tool("analyze_files", {
        "file_paths": [file_path],
        "original_filenames": {file_path: uploaded_file.get("original_filename", "")}
    })

    if not result.get("success"):
        return {
            "success": False,
            "error": "文件分析失败",
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    analyses = result.get("analyses", [])
    if not analyses:
        return {
            "success": False,
            "error": "文件为空",
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    analysis = analyses[0]
    guessed_type = analysis.get("guessed_source")

    opposite_type = "财务数据" if guessed_type == "business" else "业务数据"

    return {
        "success": False,  # 标记为失败，因为缺少配对文件
        "analyses": analyses,
        "recommendations": {
            "message": f"⚠️ 检测到{guessed_type}数据，请上传对应的{opposite_type}文件"
        },
        "warnings": ["只有一个文件，无法完成对账"]
    }


async def _analyze_with_format_normalization(uploaded_files: list, complexity_info: dict) -> dict:
    """处理非标准格式文件"""
    # TODO: 实现格式标准化逻辑
    # 目前降级到简单分析
    return await _fallback_to_simple_analysis(uploaded_files)


async def _fallback_to_simple_analysis(uploaded_files: list) -> dict:
    """降级到简单分析（使用现有的analyze_files工具）"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info("降级到简单文件分析")

    file_paths = [f.get("file_path") for f in uploaded_files]
    original_filenames_map = {f.get("file_path"): f.get("original_filename") for f in uploaded_files if f.get("original_filename")}

    result = await call_mcp_tool("analyze_files", {
        "file_paths": file_paths,
        "original_filenames": original_filenames_map
    })

    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error", "文件分析失败"),
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    return {
        "success": True,
        "analyses": result.get("analyses", []),
        "recommendations": {},
        "warnings": []
    }

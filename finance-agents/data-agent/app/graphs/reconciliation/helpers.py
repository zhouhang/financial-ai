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


def _rule_template_to_config_items(rule_template: dict) -> list[dict]:
    """将 rule_template 转为 rule_config_items，保留用户原有的具体描述（非通用文案）。"""
    items: list[dict] = []
    # 1. 金额容差
    tol = rule_template.get("tolerance", {})
    if tol.get("amount_diff_max") is not None:
        items.append({
            "json_snippet": {"tolerance": dict(tol)},
            "description": f"金额容差 {tol.get('amount_diff_max', 0.1)} 元",
        })
    # 2. 从 data_cleaning_rules 提取每个有 description 的规则项（保留用户原配置）
    dcr = rule_template.get("data_cleaning_rules", {})
    for src in ("business", "finance"):
        src_label = "业务文件" if src == "business" else "财务文件"
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
    """编辑模式下格式化字段映射（无需 file_analyses）。"""
    role_labels = {"order_id": "订单号", "amount": "金额", "date": "日期", "status": "状态"}
    lines: list[str] = []
    for role, label in role_labels.items():
        biz_col = mappings.get("business", {}).get(role)
        fin_col = mappings.get("finance", {}).get(role)
        if biz_col or fin_col:
            biz_str = " / ".join(biz_col) if isinstance(biz_col, list) else str(biz_col or "")
            fin_str = " / ".join(fin_col) if isinstance(fin_col, list) else str(fin_col or "")
            lines.append(f"  • **{label}**：业务 `{biz_str}` ⇄ 财务 `{fin_str}`")
    return "\n".join(lines) if lines else "  （无映射）"


def _build_field_mapping_text(mappings: dict[str, Any]) -> str:
    """将字段映射构建为可保存的自然语言描述，供编辑规则时展示。
    
    格式示例：
    业务: 订单号->第三方订单号, 金额->应结算平台金额, 日期->支付时间
    财务: 订单号->sup订单号, 金额->发生-, 日期->完成时间
    """
    role_labels = {"order_id": "订单号", "amount": "金额", "date": "日期", "status": "状态"}
    lines = []
    for source, label in [("business", "业务"), ("finance", "财务")]:
        src_map = mappings.get(source, {})
        if not src_map:
            continue
        parts = []
        for role, col in src_map.items():
            rl = role_labels.get(role, role)
            col_str = " / ".join(col) if isinstance(col, list) else str(col)
            parts.append(f"{rl}->{col_str}")
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
        desc = item.get("description", "未知配置")
        json_snippet = item.get("json_snippet", {})
        target = _analyze_config_target(json_snippet, file_names)
        lines.append(f"  {i}. {target} {desc}")
    
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

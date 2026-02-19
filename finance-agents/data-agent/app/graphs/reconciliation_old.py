"""对账子图 (Sub-Graph) — 第2层：规则生成工作流

节点流程：
  file_analysis → field_mapping (HITL) → rule_config (HITL) → validation_preview (HITL) → save_rule

每个 HITL 节点通过 interrupt 暂停，等待用户确认后继续。

字段映射逻辑（以用户纠正结果为准）：
  1. 文件解析表头 → LLM 自动猜测（仅 order_id/amount/date，不含 status）
  2. 显示给用户 → 用户可确认或输入自然语言纠正（如「删除status」）
  3. LLM 解析纠正意见 → 更新底层 JSON
  4. 最终以 confirmed_mappings 为准 → 保存到 rule_template.field_roles
  5. field_mapping_text、rule_config_text 一并存入 rule_template，供编辑规则时展示
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
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
        
        parsed = _json.loads(content)
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
        "hint": '''💡 **操作提示**：
  • 如果正确，回复"确认"继续
  • **调整现有字段**（修改/删除）：例如"文件1的订单号改为X", "文件2删除status"
  • **添加新字段**：例如"文件1添加status对应Y", "两个文件都添加status"
  • **混合操作**：例如"文件1: 订单号改为X，添加status为Y; 文件2: 删除status"
  • 详细描述你需要的所有更改，系统会一次性生成所有操作''',
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
    
    # 使用 LLM 调整映射（返回调整后的映射和操作列表）
    adjusted_mappings, operations = _adjust_field_mappings_with_llm(confirmed, response_str, analyses)
    
    # 检查映射是否有变化（且 operations 非空，避免显示无效更新）
    if adjusted_mappings != confirmed and operations:
        operations_summary = _format_operations_summary(operations)
        adjustment_msg = f"✅ 已根据你的调整意见更新字段映射：\n{operations_summary}"
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


def _parse_rule_config_json_snippet(user_input: str, current_config_items: list[dict] = None, field_mappings: dict = None) -> dict[str, Any]:
    """使用 LLM 根据 JSON 模板解析用户输入，返回 JSON 片段。
    
    Args:
        user_input: 用户自然语言输入
        current_config_items: 当前已添加的配置项列表
        field_mappings: 字段映射，包含 business 和 finance 的字段映射关系
    
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
    # 到 finance-mcp/reconciliation/schemas/direct_sales_schema.json（需 parents[4] 到项目根）
    template_path = Path(__file__).resolve().parents[4] / "finance-mcp" / "reconciliation" / "schemas" / "direct_sales_schema.json"
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
    
    # 准备字段映射的详细描述（增强版）
    field_mapping_desc = ""
    business_fields = {}
    finance_fields = {}
    
    if field_mappings:
        biz_fields = field_mappings.get("business", {})
        fin_fields = field_mappings.get("finance", {})
        
        # 构建可用字段的查询表
        for role, field in biz_fields.items():
            if isinstance(field, list):
                for f in field:
                    business_fields[f.lower()] = (role, field)
            else:
                business_fields[field.lower()] = (role, field)
        
        for role, field in fin_fields.items():
            if isinstance(field, list):
                for f in field:
                    finance_fields[f.lower()] = (role, field)
            else:
                finance_fields[field.lower()] = (role, field)
        
        # 构建清晰的字段映射说明
        field_mapping_desc = "\n\n📋 字段映射关系（⚠️ 判断字段所属数据源时，必须以本列表为准，不要依赖示例中的硬编码）：\n"
        field_mapping_desc += "─" * 60 + "\n"
        
        if biz_fields:
            field_mapping_desc += "📁 业务数据(文件1)字段：\n"
            for role, field in biz_fields.items():
                if isinstance(field, list):
                    field_str = " / ".join(field)
                else:
                    field_str = str(field)
                field_mapping_desc += f"   • {role:10} → {field_str}\n"
        
        if fin_fields:
            field_mapping_desc += "📁 财务数据(文件2)字段：\n"
            for role, field in fin_fields.items():
                if isinstance(field, list):
                    field_str = " / ".join(field)
                else:
                    field_str = str(field)
                field_mapping_desc += f"   • {role:10} → {field_str}\n"
    
    # 构建 prompt：使用 replace 替代 f-string 插入 template_json/user_input，
    # 避免 template 中的 JSON（如 {"amount":"sum","date":"first"}）被下游 .format() 误解析为占位符
    template_json = _json.dumps(template, ensure_ascii=False, indent=2)[:2000]
    
    # JSON 示例（使用普通字符串避免转义问题）
    # 增强示例，展示两个文件独立处理的重要性
    json_examples = '''配置项模板示例（使用JSON）：

[示例1] 金额容差（全局）：
{"action": "add", "json_snippet": {"tolerance": {"amount_diff_max": 0.1}}, "description": "金额容差：0.1元"}

[示例2] 金额转换（根据字段映射判断：若 product_price 在业务数据则用此格式配置 business，若在财务数据则配置 finance）：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"finance": {"field_transforms": [{"field": "amount", "transform": "float(row.get('product_price', 0)) / 100", "description": "product_price 除以100转换为元"}]}}}, "description": "财务端转换：product_price除以100"}

[示例3] 财务端金额转换（发生- 在财务数据中）：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"finance": {"field_transforms": [{"field": "amount", "transform": "float(row.get('发生-', 0)) / 100 if row.get('发生-') else None", "description": "发生- 除以100转换为元"}]}}}, "description": "财务端转换：发生-除以100"}

[示例4] 用户未指明文件时，默认对两个文件都配置（订单号处理）- 分离format和filter，注意操作顺序：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"business": {"field_transforms": [{"field": "order_id", "transform": "str(row.get('roc_oid', '')).lstrip(\"'\")[:21]", "description": "订单号先去单引号再截取21位"}], "row_filters": [{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "仅保留104开头的订单号"}]}, "finance": {"field_transforms": [{"field": "order_id", "transform": "str(row.get('sup订单号', '')).lstrip(\"'\")[:21]", "description": "订单号先去单引号再截取21位"}], "row_filters": [{"condition": "str(row.get('order_id', '')).startswith('104')", "description": "仅保留104开头的订单号"}]}}}, "description": "订单号处理：先去单引号再截取21位，仅保留104开头（两个文件）"}

[示例5] 用户明确指定文件1时，只配置 business：
{"action": "add", "json_snippet": {"data_cleaning_rules": {"business": {"field_transforms": [{"field": "order_id", "transform": "str(row.get('roc_oid', '')).lstrip('0')", "description": "删除订单号前导0"}]}}}, "description": "业务文件订单号：删除前导0"}

[示例6] 删除配置（target 必须是用户要删除的具体内容，精确匹配一项）：
{"action": "delete", "target": "金额容差", "description": "删除金额容差配置"}
{"action": "delete", "target": "product_price除以100", "description": "删除product_price除以100的转换"}

[示例7] 聚合类配置（按某字段合并、金额累加等）- 必须放入 aggregations，不能放全局：
- 用户未指定文件 → 放 business.aggregations 和 finance.aggregations
- 用户指定文件1 → 只放 business.aggregations
- 用户指定文件2 → 只放 finance.aggregations
示例（用户未指定，两个都放）：{"action": "add", "json_snippet": {"data_cleaning_rules": {"business": {"aggregations": [{"group_by": "order_id", "agg_fields": {"amount": "sum", "date": "first"}, "description": "按订单号合并，金额累加"}]}, "finance": {"aggregations": [{"group_by": "order_id", "agg_fields": {"amount": "sum", "date": "first"}, "description": "按订单号合并，金额累加"}]}}}, "description": "按订单号合并金额（两个文件）"}'''
    
    # 使用 replace 替代 f-string，避免 template_json 中的 {"amount":"sum","date":"first"} 等
    # 被下游 .format() 误解析为 Invalid format specifier
    prompt = """你是一个对账规则配置助手。请根据JSON模板解析用户的自然语言输入，返回一个JSON片段。

JSON模板结构（参考）：
<<<TEMPLATE_JSON>>>

<<<FIELD_MAPPING_DESC>>><<<CURRENT_ITEMS_DESC>>>

用户的指令：
<<<USER_INPUT>>>

请判断用户的意图：
1. 如果是**添加配置**，返回 action: "add"（每次添加一个逻辑规则，description 对应单一规则）
2. 如果是**删除配置**，返回 action: "delete"，target 必须是**配置项描述中的关键词**（如"product_price除以100"），不要带"删除"等动词前缀
3. 如果是**更新配置**，返回 action: "update"

⚠️ 关键规则 - 数据源识别和隔离（按优先级）：

**🔴 规则1（最高优先级）：用户明确指定文件 - 必须遵守**
- 如果用户说"文件1"或"业务"或"业务数据" → 必须配置到 business，无论字段名如何
- 如果用户说"文件2"或"财务"或"财务数据" → 必须配置到 finance，无论字段名如何
- 用户的明确指定**永远优先于字段名判断**
- 例如：用户说"文件2的product_price除以100" → 即使product_price是业务字段，也要在 finance 配置

**规则2（次优先级）：指明了字段名时，必须根据上方"字段映射关系"判断数据源**
- 当用户**指明了具体字段名**（如 product_price、发生-、roc_oid、sup订单号）时，**必须查看上方"字段映射关系"**：
  * 该字段在"业务数据(文件1)"中 → 只配置到 business
  * 该字段在"财务数据(文件2)"中 → 只配置到 finance
- **不要依赖示例中的字段归属**，用户上传的文件可能与示例不同
- 例如：用户说"product_price除以100" → 若 product_price 在财务数据(文件2)中，则只配置 finance；若在业务数据(文件1)中，则只配置 business

**规则3：未指明文件且未指明具体字段时，默认对两个文件都配置**
- 当用户既没指定文件，也没指明具体字段名（如"订单号处理"、"金额除以100"）时，为 business 和 finance 都配置
- 例如：用户说"订单号去掉开头单引号，截取前21位，保留104开头" → 为两个文件都配置
- 例如：用户说"金额除以100"（未指明具体字段）→ 为两个文件都配置（根据各自字段名写 transform）

**规则3.5：聚合类配置的放置位置（按字段合并、金额累加等）**
- 聚合类配置必须放在 data_cleaning_rules 的 **business.aggregations** 或 **finance.aggregations** 中，绝不能放在全局（tolerance、global 等）
- 放置规则与规则1-4一致：用户未指定文件 → 两个都放；用户指定文件1/业务 → 只放 business；用户指定文件2/财务 → 只放 finance
- 格式：{"group_by": "order_id", "agg_fields": {"amount": "sum", "date": "first"}, "description": "..."}

**规则4：用户明确指定文件时**
- 如果用户说"文件1"或"业务"或"业务数据" → 只配置到 business
- 如果用户说"文件2"或"财务"或"财务数据" → 只配置到 finance
- 如果用户说"两个都"或"两个文件都"或"同时" → 为两个文件都配置

**规则5：分离format和filter - 不要在transform中混合条件逻辑**
- ❌ 错：`"str(row.get('order_id', '')).lstrip(\"'\")[:21] if str(row.get('order_id', '')).startswith('104') else row.get('order_id', '')"`
  问题：False分支返回原始值，导致L开头的订单号无法被过滤掉
- ✅ 对：分成两步
  第一步field_transforms：`"str(row.get('order_id', '')).lstrip(\"'\")[:21]"` → 只做格式处理
  第二步row_filters：`"str(row.get('order_id', '')).startswith('104')"` → 只做过滤（删除不符条件的行）

**规则5.5：操作顺序很重要 - 字符串处理链的顺序决定结果**
⚠️ **用户说的"先...再..."顺序必须精确转化为代码的"先.method()再.method()"顺序**

- 用户说："先去单引号，再截取前21位" 
  → 代码应该是：`str(row.get('order_id', '')).lstrip("'")[:21]` ✅
  → 不能是：`str(row.get('order_id', '')).[:21].lstrip("'")` ❌

- 用户说："先截取前21位，再做其他处理" 
  → 代码应该是：`str(row.get('order_id', '')).[:21].method()` ✅

关键点：
- `.lstrip("'")` 是删除左侧的单引号，应该在所有其他处理之前
- `[:21]` 是取前21个字符，如果在lstrip之后，就是删除单引号后的前21位

例子对比：
- `"'123456789012345678901234"` (34个字符，包括1个开头单引号)
- `.lstrip("'")[:21]` → `"12345678901234567890"` (20个字符，因为删除单引号后再取21位) ✅
- `[:21].lstrip("'")` → `"'1234567890123456789"` (20个字符，先取21位再删单引号，单引号在最左仍被删除) ❌ 结果不同

**规则6：row_filters的使用（列级过滤vs行级过滤）**

⚠️ **row_filters是用来排除特殊/无关的记录，而不是用来"清理"数据格式**

何时使用row_filters：
- ✅ 财务系统有**特殊的内部记录**需要从对账中排除（如加款单、调账记录）
- ✅ 财务系统中有**特定格式的数据**需要单独处理（如只对104开头的订单做对账，加款单等用特殊格式代替）
- ✓ 财务侧有明确的"不应该参与对账的记录"

何时不应该使用row_filters：
- ❌ **不要用row_filters来统一两个系统的数据格式**
- ❌ **不要对业务数据使用row_filters**（业务系统的数据都是有效的业务数据，不应该被排除）
- ❌ **不要对同一个条件在两个数据源上都应用row_filters**（这会导致无法看出差异）

示例：腾讯异业对账
- 财务系统订单格式：104开头（正常订单）、XZFL开头（加款单）
- 业务系统订单格式：104开头、L开头（不同的业务来源）
- 正确配置：
  • finance：row_filters 删除非104开头（如XZFL加款单）
  • business：**不需要row_filters**，保留所有包括L开头的订单
- 错误配置：
  • 两边都加row_filters"104开头"
  • 结果：L开头的业务订单被删除，无法看出与财务的差异

**规则6.5：禁止输出 custom_validations**
- json_snippet 中不要包含 custom_validations，仅配置 data_cleaning_rules、tolerance 等

**规则7：避免重复规则**
- 检查当前已有的配置项（见上方"当前已添加的配置项"）
- 当用户说的需求已经包含在某个配置项中时，建议用户是否要更新或替换，而不是添加新规则
- 例如：如果已经有"订单号去单引号截取21位"的规则，不要再添加"订单号去单引号截取21位、104开头"
  应该改为更新现有规则或添加行过滤规则

**规则7：根据字段名写 transform 表达式**
- 为 business 配置时，使用业务数据字段列表中的列名（如 roc_oid、product_price）
- 为 finance 配置时，使用财务数据字段列表中的列名（如 sup订单号、发生-）

**规则8：transform 表达式必须使用该数据源的列名**
- 业务数据(business)的列名来自"业务数据字段"列表，如 roc_oid、product_price
- 财务数据(finance)的列名来自"财务数据字段"列表，如 sup订单号、发生-
- ❌ 错：在 finance 的 transform 中使用 row.get('product_price', 0)（product_price 是业务列）
- ✅ 对：在 finance 的 transform 中使用 row.get('发生-', 0)

<<<JSON_EXAMPLES>>>

请返回这个JSON格式的结果（只返回JSON，不要其他文字）：
{{"action": "add|delete|update", "json_snippet": {{...}}, "description": "用户友好的描述"}}"""
    
    # 使用 replace 插入变量，避免 template_json 中的 JSON 花括号被 .format() 误解析
    prompt = prompt.replace("<<<TEMPLATE_JSON>>>", template_json, 1)
    prompt = prompt.replace("<<<FIELD_MAPPING_DESC>>>", field_mapping_desc, 1)
    prompt = prompt.replace("<<<CURRENT_ITEMS_DESC>>>", current_items_desc, 1)
    prompt = prompt.replace("<<<USER_INPUT>>>", user_input, 1)
    prompt = prompt.replace("<<<JSON_EXAMPLES>>>", json_examples, 1)
        
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
- "订单号去掉开头单引号，并截取前21位" → {{"order_id_transform": "去掉开头单引号并截取前21位"}}
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
        import json as _json
        business_conditions = {_json.dumps(f.get("condition"), sort_keys=True): f for f in business_row_filters}
        finance_conditions = {_json.dumps(f.get("condition"), sort_keys=True): f for f in finance_row_filters}
        
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
    import json as _json
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
    
    # 构建文件名映射（优先用 original_filename，用户更易识别）
    file_names = {}
    file_analyses = state.get("file_analyses", [])
    for analysis in file_analyses:
        source = analysis.get("guessed_source", "")
        name = analysis.get("original_filename") or analysis.get("filename", "")
        if source == "business" and name:
            file_names["business"] = name
        elif source == "finance" and name:
            file_names["finance"] = name
    
    # 区分初始状态和配置中状态
    if len(config_items) == 0:
        # 初始状态：只显示提示，不显示"当前配置"标题
        question_text = """⚙️ **第3步：配置对账规则参数**

请描述对账规则的配置要求。支持以下类型的配置：

**全局配置**（如金额容差）：
• "金额容差0.1元"

**聚合类配置**（按字段合并、金额累加等，放入 business/finance 的 aggregations，不放全局）：
• 未指定文件："按订单号合并金额" → 两个文件都配置
• 指定文件："文件1按订单号合并" → 只配置业务文件

**针对业务数据(文件1)的配置**：
• "业务文件的product_price除以100"
• "文件1的订单号去掉开头单引号，并截取前21位"

**针对财务数据(文件2)的配置**：
• "财务文件的发生-除以100"
• "文件2的订单号去除空格"

**为两个文件配置不同规则**：
• "文件1的金额除以100，文件2的金额不变"

⚠️ 系统会根据字段名自动识别字段所属的文件（以字段映射为准）。
例如：product_price 在财务数据(文件2)中 → 只在财务文件配置；在业务数据(文件1)中 → 只在业务文件配置

**请输入你的配置要求：**"""
    else:
        # 有配置项时：显示当前配置列表
        config_display = _format_rule_config_items(config_items, file_names)
        question_text = f"""⚙️ **第3步：配置对账规则参数**

当前配置：
{config_display}

你可以：
• 继续添加配置（为业务文件、财务文件或全局配置新规则）
• 删除配置（如"删除金额容差"、"去掉订单号过滤"）
• 回复"确认"完成配置

**请输入：**"""
    
    # interrupt 暂停，等待用户输入
    user_response = interrupt({
        "step": "3/4",
        "step_title": "配置规则参数",
        "question": question_text,
        "current_config_items": config_items,
        "hint": '''💡 **操作提示**：
  • 系统智能识别字段所属的文件（业务或财务）
  • 支持针对单个文件的规则配置
  • 支持为两个文件配置不同的转换规则
  • 完成后回复"确认"继续''',
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
    
    # 获取字段映射以提供更好的上下文
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    
    # 使用新的LLM解析函数，传递字段映射信息
    parsed_result = _parse_rule_config_json_snippet(response_str, config_items, mappings)
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
        updated_config_display = _format_rule_config_items(new_config_items, file_names)
        feedback_msg = f"✅ 已添加配置：{parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
        logger.info(f"添加配置项: {parsed_result.get('description')}, 当前配置项数量: {len(new_config_items)}")
    
    elif action == "delete":
        # 删除配置项 - 只删除匹配度最高的单个配置，避免误删多个
        target = parsed_result.get("target", "").strip()
        # 去掉常见前缀，确保能匹配到配置项描述（如 "删除product_price除以100" → "product_price除以100"）
        for prefix in ("删除", "去掉", "移除", "删掉"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break
        
        if not target:
            feedback_msg = f"⚠️ 未指定删除目标，请检查输入\n\n> {response_str}"
        else:
            # 只匹配并删除最相关的那一项（max_matches=1，strict 仅子串匹配避免误删）
            matching_indices = _find_matching_items(
                target, new_config_items, threshold=0.5, max_matches=1, strict_substring_only=True
            )
            
            if matching_indices:
                # 删除匹配的项（从高索引到低索引，避免索引变化）
                deleted_items_desc = []
                for idx in sorted(matching_indices, reverse=True):
                    item = new_config_items[idx]
                    deleted_items_desc.append(item.get("description", "未知配置"))
                    del new_config_items[idx]
                
                # 显示更新后的配置列表
                updated_config_display = _format_rule_config_items(new_config_items, file_names)
                deleted_desc = "、".join(deleted_items_desc)
                feedback_msg = f"🗑️ 已删除配置：{deleted_desc}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                logger.info(f"删除了 {len(matching_indices)} 个配置项: {deleted_desc}")
            else:
                # 未找到匹配项 - 显示相似度最高的项作为建议
                if new_config_items:
                    # 计算与所有项的相似度并显示最高的几个
                    scores: list[tuple[int, float, str]] = []
                    for idx, item in enumerate(new_config_items):
                        description = item.get("description", "")
                        score = _calculate_fuzzy_match_score(target, description)
                        scores.append((idx, score, description))
                    
                    # 按相似度排序
                    scores.sort(key=lambda x: x[1], reverse=True)
                    
                    # 显示相似度最高的3个作为建议
                    suggestions = "\n\n**相似的配置项：**\n"
                    for idx, (_, score, desc) in enumerate(scores[:3]):
                        suggestions += f"  {idx+1}. {desc} (相似度: {score*100:.0f}%)\n"
                    
                    updated_config_display = _format_rule_config_items(new_config_items, file_names)
                    feedback_msg = f"⚠️ 未找到匹配的配置项\n\n> {response_str}{suggestions}\n\n**当前配置列表：**\n{updated_config_display}\n\n**💡 提示：** 尝试使用配置项中的关键词来删除，或者告诉我要删除的具体内容。"
                else:
                    updated_config_display = _format_rule_config_items(new_config_items, file_names)
                    feedback_msg = f"⚠️ 未找到匹配的配置项，且配置列表为空\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                
                logger.warning(f"删除操作：未找到匹配项，target='{target}'")

    
    elif action == "update":
        # 更新配置项 - 使用智能匹配来找到目标项
        target = parsed_result.get("target", "").strip()
        
        if not target:
            feedback_msg = f"⚠️ 未指定更新目标，请检查输入\n\n> {response_str}"
        else:
            # 使用智能匹配查找最相关的配置项
            matching_indices = _find_matching_items(target, new_config_items, threshold=0.5)
            
            if matching_indices:
                # 更新第一个（最相关的）匹配项
                update_idx = matching_indices[0]
                old_desc = new_config_items[update_idx].get("description", "")
                
                new_config_items[update_idx] = {
                    "json_snippet": parsed_result.get("json_snippet", {}),
                    "description": parsed_result.get("description", "未知配置"),
                    "user_input": response_str,
                }
                
                updated_config_display = _format_rule_config_items(new_config_items, file_names)
                feedback_msg = f"✏️ 已更新配置：{old_desc} → {parsed_result.get('description', '未知配置')}\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                logger.info(f"更新配置项: {old_desc} → {parsed_result.get('description')}")
            else:
                # 未找到匹配项 - 添加为新配置项
                new_item = {
                    "json_snippet": parsed_result.get("json_snippet", {}),
                    "description": parsed_result.get("description", "未知配置"),
                    "user_input": response_str,
                }
                new_config_items.append(new_item)
                
                updated_config_display = _format_rule_config_items(new_config_items, file_names)
                feedback_msg = f"⚠️ 未找到与 '{target}' 相匹配的配置项，已作为新配置添加\n\n> {response_str}\n\n当前配置：\n{updated_config_display}"
                logger.info(f"未找到匹配项，添加为新配置: {parsed_result.get('description')}")
        
        # 显示更新后的配置列表
        updated_config_display = _format_rule_config_items(new_config_items, file_names)
    
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

        # ⚠️ 关键修复：检查 filename 是否真的包含时间戳
        # 如果 filename 看起来是原始文件名（与 original_filename 相同），则从 file_path 提取
        if filename_with_timestamp and original_filename and filename_with_timestamp == original_filename:
            logger.warning(f"validation_preview_node - ⚠️ 发现问题：filename({filename_with_timestamp}) == original_filename({original_filename})，这表示 filename 可能被错误设置")
            # 尝试从 file_path 中提取系统文件名（应该带时间戳）
            if file_path:
                from pathlib import Path
                path_obj = Path(file_path)
                extracted_filename = path_obj.name
                # 验证提取的文件名是否包含时间戳
                has_timestamp = re.search(r'_\d{6}(\.\w+)$', extracted_filename) or re.search(r'_\d+(\.\w+)$', extracted_filename)
                if has_timestamp:
                    filename_with_timestamp = extracted_filename
                    logger.info(f"validation_preview_node - ✅ 修正：从 file_path 提取带时间戳的文件名: {filename_with_timestamp}")
                else:
                    logger.error(f"validation_preview_node - ❌ 从 file_path 提取的文件名也没有时间戳: {extracted_filename}，这表示文件上传阶段可能有问题")
        
        # 如果 filename 不包含时间戳（不包含 _ 后跟数字），尝试从 file_path 中提取
        elif filename_with_timestamp and not re.search(r'_\d{6}(\.\w+)$', filename_with_timestamp) and not re.search(r'_\d+(\.\w+)$', filename_with_timestamp):
            # 从 file_path 中提取文件名
            if file_path:
                from pathlib import Path
                path_obj = Path(file_path)
                extracted_filename = path_obj.name
                # 如果提取的文件名包含时间戳，使用它
                if re.search(r'_\d{6}(\.\w+)$', extracted_filename) or re.search(r'_\d+(\.\w+)$', extracted_filename):
                    logger.warning(f"validation_preview_node - filename({filename_with_timestamp}) 没有时间戳，从 file_path 提取: {extracted_filename}")
                    filename_with_timestamp = extracted_filename

        if not filename_with_timestamp:
            logger.warning(f"validation_preview_node - 跳过文件（没有 filename）: original_filename={original_filename}, file_path={file_path}")
            continue

        # 详细的调试日志
        logger.info(f"validation_preview_node - 处理文件: filename={filename_with_timestamp}, original_filename={original_filename}, file_path={file_path}, source={src}")

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
        # 这是一个诊断点，表示上游可能出现问题
        if pattern == filename_with_timestamp:
            logger.error(f"validation_preview_node - ❌ 警告：无法从 filename={filename_with_timestamp} 生成时间戳通配符，这可能导致对账无法匹配带时间戳的文件")
            # 修复：同时生成原始文件名和带时间戳的文件名模式
            # 例如：1767597466118.csv → ['1767597466118.csv', '1767597466118_*.csv']
            name_parts = filename_with_timestamp.rsplit('.', 1)
            if len(name_parts) == 2:
                # 生成两个模式：原始文件名 + 带时间戳的通配符
                patterns_to_add = [
                    filename_with_timestamp,  # 原始文件名，例如 1767597466118.csv
                    f"{name_parts[0]}_*.{name_parts[1]}"  # 带时间戳的通配符，例如 1767597466118_*.csv
                ]
            else:
                patterns_to_add = [filename_with_timestamp]
        else:
            patterns_to_add = [pattern]

        # 调试日志：记录生成的 pattern（显示是否成功生成通配符）
        has_wildcard = any('*' in p for p in patterns_to_add)
        logger.info(f"validation_preview_node - 生成的 file_pattern: {patterns_to_add} (是否包含通配符: {has_wildcard}, 来源: {src}, 原始 filename: {filename_with_timestamp})")

        # Excel/CSV 格式扩展为所有支持类型（.xlsx/.xls/.xlsm/.xlsb/.csv）
        expanded_patterns = []
        for p in patterns_to_add:
            expanded_patterns.extend(_expand_file_patterns(p))
        
        if src == "business":
            for p in expanded_patterns:
                if p not in biz_patterns:
                    biz_patterns.append(p)
        elif src == "finance":
            for p in expanded_patterns:
                if p not in fin_patterns:
                    fin_patterns.append(p)

    # 默认模式（如果没有找到文件）- 包含所有 Excel + CSV 格式
    if not biz_patterns:
        biz_patterns = [f"*{e}" for e in FILE_PATTERN_EXTENSIONS]
    if not fin_patterns:
        fin_patterns = [f"*{e}" for e in FILE_PATTERN_EXTENSIONS]

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
        # 关键修复：合并后立即验证和去重规则，防止重复处理同一字段
        schema = _validate_and_deduplicate_rules(schema)
    else:
        schema = base_schema

    # 强制恢复被保护的 file_pattern，确保在任何合并后都保留正确的模式
    # 这是关键修复：无论合并过程如何，都要确保 file_pattern 是正确的
    if "data_sources" in schema:
        if "business" in schema["data_sources"]:
            schema["data_sources"]["business"]["file_pattern"] = protected_file_patterns["business"]
        else:
            # 如果 business 不存在，创建它
            schema["data_sources"]["business"] = {"file_pattern": protected_file_patterns["business"]}
        
        if "finance" in schema["data_sources"]:
            schema["data_sources"]["finance"]["file_pattern"] = protected_file_patterns["finance"]
        else:
            # 如果 finance 不存在，创建它
            schema["data_sources"]["finance"] = {"file_pattern": protected_file_patterns["finance"]}
    
    # 再次验证 file_pattern 是否正确设置
    biz_file_pattern = schema.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_file_pattern = schema.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    logger.info(f"validation_preview_node - 修复后的 schema file_pattern: business={biz_file_pattern}, finance={fin_file_pattern}")

    # 调试日志：记录合并后的 schema 中的 file_pattern
    biz_patterns_after_merge = schema.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_patterns_after_merge = schema.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    logger.info(f"validation_preview_node - 合并后的 schema file_pattern: business={biz_patterns_after_merge}, finance={fin_patterns_after_merge}")

    # 简单预览（统计匹配信息）
    preview = _preview_schema(schema, analyses)

    # 字段映射展示
    mapping_display = _format_field_mappings(mappings, analyses)

    # 构建文件名映射（优先用 original_filename，用户更易识别）
    file_names = {}
    for a in analyses:
        src = a.get("guessed_source", "")
        name = a.get("original_filename") or a.get("filename", "")
        if src == "business" and name:
            file_names["business"] = name
        elif src == "finance" and name:
            file_names["finance"] = name
    if not file_names and analyses:
        file_names["business"] = analyses[0].get("original_filename") or analyses[0].get("filename", "文件1") if len(analyses) > 0 else "文件1"
        file_names["finance"] = analyses[1].get("original_filename") or analyses[1].get("filename", "文件2") if len(analyses) > 1 else "文件2"

    # 用户配置的具体规则（第3步添加的配置项，使用真实文件名）
    config_display = (
        _format_rule_config_items(config_items, file_names)
        if config_items
        else "（无额外配置，使用默认规则）"
    )

    preview_text = (
        f"✅ **第4步：确认规则并保存**\n\n"
        f"我已经根据你的配置生成了对账规则！预览结果：\n\n"
        f"📊 **数据统计**\n"
        f"• 业务记录数：{preview.get('biz_count', 'N/A')}\n"
        f"• 财务记录数：{preview.get('fin_count', 'N/A')}\n"
        f"• 预计可匹配：{preview.get('estimated_match', 'N/A')}条\n\n"
        f"🔗 **字段映射**{mapping_display}\n\n"
        f"📋 **你配置的规则**\n{config_display}\n\n"
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

    # ✅ 在保存前扩展 file_pattern 为所有支持的格式
    biz_patterns_orig = schema_with_desc.get("data_sources", {}).get("business", {}).get("file_pattern", [])
    fin_patterns_orig = schema_with_desc.get("data_sources", {}).get("finance", {}).get("file_pattern", [])
    
    logger.info(f"save_rule_node - 保存前规则 file_pattern (原始): business={biz_patterns_orig}, finance={fin_patterns_orig}")
    
    # 扩展 file_pattern 为所有支持的格式（.xlsx/.xls/.xlsm/.xlsb/.csv）
    biz_patterns_expanded = []
    for pattern in biz_patterns_orig:
        biz_patterns_expanded.extend(_expand_file_patterns(pattern))
    
    fin_patterns_expanded = []
    for pattern in fin_patterns_orig:
        fin_patterns_expanded.extend(_expand_file_patterns(pattern))
    
    # 去重
    biz_patterns = list(set(biz_patterns_expanded))
    fin_patterns = list(set(fin_patterns_expanded))
    
    # 更新 schema 中的 file_pattern
    if "data_sources" not in schema_with_desc:
        schema_with_desc["data_sources"] = {}
    if "business" not in schema_with_desc["data_sources"]:
        schema_with_desc["data_sources"]["business"] = {}
    if "finance" not in schema_with_desc["data_sources"]:
        schema_with_desc["data_sources"]["finance"] = {}
    
    schema_with_desc["data_sources"]["business"]["file_pattern"] = biz_patterns
    schema_with_desc["data_sources"]["finance"]["file_pattern"] = fin_patterns
    
    logger.info(f"save_rule_node - 保存前规则 file_pattern (扩展后): business={biz_patterns}, finance={fin_patterns}")
    logger.info(f"save_rule_node - 完整的 schema data_sources: {schema_with_desc.get('data_sources', {})}")
    
    # 检查 file_pattern 是否有效
    def check_pattern_validity(patterns: list[str], source_name: str) -> bool:
        """检查 file_pattern 是否包含通配符，如果不包含则发出警告"""
        if not patterns:
            logger.warning(f"save_rule_node - ⚠️ {source_name} 的 file_pattern 为空")
            return False
        
        has_wildcard = any('*' in p for p in patterns)
        if not has_wildcard:
            logger.error(f"save_rule_node - ❌ 严重问题：{source_name} 的 file_pattern 不包含通配符，这会导致无法匹配带时间戳的文件！patterns={patterns}")
            return False
        
        logger.info(f"save_rule_node - ✅ {source_name} 的 file_pattern 有效：{patterns}")
        return True
    
    biz_valid = check_pattern_validity(biz_patterns, "business")
    fin_valid = check_pattern_validity(fin_patterns, "finance")
    
    if not biz_valid or not fin_valid:
        logger.error(f"save_rule_node - ⚠️ 警告：规则的 file_pattern 可能不完整，请检查规则配置是否正确")
        # 返回警告信息但继续保存
        warning_msg = "⚠️ 警告：规则的 file_pattern 可能有问题，请确保上传的文件包含时间戳后缀（如：filename_134019.csv）"
    else:
        warning_msg = None

    # ⚠️ 保存前将 transform/expression 中的原始列名重写为映射字段名（order_id、amount 等）
    _rewrite_schema_transforms_to_mapped_fields(schema_with_desc)

    # 保存用户自然语言描述，供后续编辑规则功能使用
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    config_items = state.get("rule_config_items", [])
    schema_with_desc["field_mapping_text"] = _build_field_mapping_text(mappings)
    schema_with_desc["rule_config_text"] = _build_rule_config_text(config_items)

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
    
    if warning_msg:
        msg = warning_msg + "\n\n" + msg

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


# ── 编辑规则节点 ─────────────────────────────────────────────────────────────

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


def edit_field_mapping_node(state: AgentState) -> dict:
    """编辑规则 - 第1步：显示当前字段映射，支持修改或确认。"""
    mappings = state.get("confirmed_mappings") or state.get("suggested_mappings", {})
    adjustment_feedback = state.get("mapping_adjustment_feedback")
    rule_name = state.get("editing_rule_name", "规则")

    mapping_display = _format_edit_field_mappings(mappings)
    if adjustment_feedback:
        question_text = f"📋 **编辑「{rule_name}」- 字段映射**\n\n{adjustment_feedback}\n\n当前映射：\n{mapping_display}\n\n请确认或继续修改。"
    else:
        question_text = f"📋 **编辑「{rule_name}」- 字段映射**\n\n当前字段对应关系：\n{mapping_display}\n\n请确认是否正确？回复「确认」继续，或描述需要修改的地方。"

    user_response = interrupt({
        "step": "1/3",
        "step_title": "确认字段映射",
        "question": question_text,
        "suggested_mappings": mappings,
        "hint": "• 回复「确认」继续  • 修改示例：「订单号改为XX」「添加status对应YY」「删除status」",
    })

    response_str = str(user_response).strip()
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {"messages": [], "mapping_adjustment_feedback": None, "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value}

    response_lower = response_str.lower()
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确"):
        return {
            "messages": [AIMessage(content="✅ 字段映射已确认。")],
            "confirmed_mappings": mappings,
            "mapping_adjustment_feedback": None,
            "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
        }

    # 用户需要调整
    dummy_analyses = _build_dummy_analyses_from_mappings(mappings)
    adjusted_mappings, operations = _adjust_field_mappings_with_llm(mappings, response_str, dummy_analyses)
    if adjusted_mappings != mappings and operations:
        ops_summary = _format_operations_summary(operations)
        feedback = f"✅ 已更新：\n{ops_summary}"
    else:
        feedback = f"⚠️ 未能解析修改，请更具体描述。\n\n> {response_str}"

    return {
        "messages": [AIMessage(content=feedback)],
        "suggested_mappings": adjusted_mappings,
        "confirmed_mappings": adjusted_mappings,
        "mapping_adjustment_feedback": feedback,
        "phase": ReconciliationPhase.EDIT_FIELD_MAPPING.value,
    }


def edit_rule_config_node(state: AgentState) -> dict:
    """编辑规则 - 第2步：显示当前规则配置，支持修改或确认。"""
    config_items = state.get("rule_config_items") or []
    rule_name = state.get("editing_rule_name", "规则")
    mappings = state.get("confirmed_mappings") or {}

    config_display = _format_rule_config_items(config_items, {"business": "业务文件", "finance": "财务文件"})
    question_text = f"⚙️ **编辑「{rule_name}」- 规则配置**\n\n当前配置：\n{config_display}\n\n请确认是否正确？回复「确认」继续，或描述需要添加/删除的配置。"

    user_response = interrupt({
        "step": "2/3",
        "step_title": "确认规则配置",
        "question": question_text,
        "current_config_items": config_items,
        "hint": "• 回复「确认」继续  • 添加：「金额容差0.1」  • 删除：「删除金额容差」",
    })

    response_str = str(user_response).strip()
    if not response_str or (response_str.startswith("已上传") and response_str.endswith("请处理。")):
        return {"messages": [], "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value}

    response_lower = response_str.lower()
    if response_lower in ("确认", "ok", "yes", "确定", "对", "没问题", "正确", "完成"):
        return {
            "messages": [AIMessage(content="✅ 规则配置已确认。")],
            "rule_config_items": config_items,
            "phase": ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        }

    # 用户需要调整
    parsed = _parse_rule_config_json_snippet(response_str, config_items, mappings)
    action = parsed.get("action", "unknown")
    new_config_items = config_items.copy()
    feedback_msg = ""

    if action == "add":
        new_item = {
            "json_snippet": parsed.get("json_snippet", {}),
            "description": parsed.get("description", "未知配置"),
            "user_input": response_str,
        }
        new_config_items.append(new_item)
        feedback_msg = f"✅ 已添加：{parsed.get('description', '')}\n\n> {response_str}"
    elif action == "delete":
        target = parsed.get("target", "").strip()
        for prefix in ("删除", "去掉", "移除", "删掉"):
            if target.startswith(prefix):
                target = target[len(prefix):].strip()
                break
        if target:
            matching = _find_matching_items(target, new_config_items, threshold=0.5, max_matches=1, strict_substring_only=True)
            if matching:
                for idx in sorted(matching, reverse=True):
                    del new_config_items[idx]
                feedback_msg = f"🗑️ 已删除匹配的配置\n\n> {response_str}"
            else:
                feedback_msg = f"⚠️ 未找到匹配项\n\n> {response_str}"
        else:
            feedback_msg = f"⚠️ 未指定删除目标\n\n> {response_str}"
    else:
        feedback_msg = f"⚠️ 未能解析，请更具体描述\n\n> {response_str}"

    return {
        "messages": [AIMessage(content=feedback_msg)],
        "rule_config_items": new_config_items,
        "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
    }


def edit_validation_preview_node(state: AgentState) -> dict:
    """编辑规则 - 第3步：预览并确认保存。以 editing_rule_template 为基准，仅更新 field_roles。"""
    import copy

    rule_template = state.get("editing_rule_template") or {}
    mappings = state.get("confirmed_mappings") or {}
    config_items = state.get("rule_config_items") or []
    rule_name = state.get("editing_rule_name", "规则")

    # 以原始 rule_template 为基准（完整保留用户原有配置），仅更新 field_roles
    schema = copy.deepcopy(rule_template)
    schema["description"] = rule_name
    if "data_sources" not in schema:
        schema["data_sources"] = {}
    for src in ("business", "finance"):
        if src not in schema["data_sources"]:
            schema["data_sources"][src] = {}
        schema["data_sources"][src]["field_roles"] = mappings.get(src, {})

    # 若用户编辑过规则配置（增删），从 config_items 重建；否则保留原 schema
    if config_items:
        orig_dcr = rule_template.get("data_cleaning_rules", {})
        base = {
            "version": "1.0",
            "description": rule_name,
            "data_sources": schema["data_sources"],
            "key_field_role": schema.get("key_field_role", "order_id"),
            "tolerance": {"date_format": "%Y-%m-%d", "amount_diff_max": 0.1},
            "data_cleaning_rules": {"global": orig_dcr.get("global", {})},
            "custom_validations": schema.get("custom_validations", []),
        }
        merged = _merge_json_snippets(base, config_items)
        schema["tolerance"] = merged.get("tolerance", schema.get("tolerance"))
        dcr = merged.get("data_cleaning_rules", {})
        if "global" not in dcr and "global" in orig_dcr:
            dcr["global"] = orig_dcr["global"]
        schema["data_cleaning_rules"] = dcr

    schema = _validate_and_deduplicate_rules(schema)

    mapping_display = _format_edit_field_mappings(mappings)
    config_display = _format_rule_config_items(config_items, {"business": "业务文件", "finance": "财务文件"})

    preview_text = (
        f"✅ **编辑「{rule_name}」- 预览**\n\n"
        f"🔗 **字段映射**\n{mapping_display}\n\n"
        f"📋 **规则配置**\n{config_display}\n\n"
        "确认无误后回复「保存」，将删除旧规则并保存新规则。"
    )

    user_response = interrupt({
        "step": "3/3",
        "step_title": "确认并保存",
        "question": preview_text,
        "hint": "• 回复「保存」完成编辑  • 回复「调整」返回上一步修改",
    })

    response_str = str(user_response).strip()
    if response_str in ("调整", "重新配置", "返回", "上一步"):
        return {
            "messages": [AIMessage(content="好的，返回规则配置。")],
            "phase": ReconciliationPhase.EDIT_RULE_CONFIG.value,
        }

    if response_str.lower() not in ("保存", "确认", "ok", "yes"):
        return {
            "messages": [AIMessage(content="请回复「保存」以完成编辑，或「调整」返回修改。")],
            "phase": ReconciliationPhase.EDIT_VALIDATION_PREVIEW.value,
        }

    return {
        "messages": [AIMessage(content="正在保存...")],
        "generated_schema": schema,
        "phase": ReconciliationPhase.EDIT_SAVE.value,
    }


async def edit_save_node(state: AgentState) -> dict:
    """编辑规则 - 保存：仅在此步骤删除旧规则（PostgreSQL+JSON），并新建规则。"""
    schema = state.get("generated_schema")
    rule_id = state.get("editing_rule_id")
    rule_name = state.get("editing_rule_name")
    auth_token = state.get("auth_token", "")

    if not schema or not rule_id or not rule_name:
        return {
            "messages": [AIMessage(content="❌ 缺少规则信息，无法保存。")],
            "phase": ReconciliationPhase.COMPLETED.value,
        }

    _rewrite_schema_transforms_to_mapped_fields(schema)
    mappings = state.get("confirmed_mappings") or {}
    config_items = state.get("rule_config_items", [])
    schema["field_mapping_text"] = _build_field_mapping_text(mappings)
    schema["rule_config_text"] = _build_rule_config_text(config_items)

    # 1. 删除旧规则（PostgreSQL + JSON）
    try:
        del_result = await call_mcp_tool("delete_reconciliation_rule", {
            "auth_token": auth_token,
            "rule_id": rule_id,
        })
        if not del_result.get("success"):
            return {
                "messages": [AIMessage(content=f"❌ 删除旧规则失败: {del_result.get('error', '未知错误')}")],
                "phase": ReconciliationPhase.EDIT_SAVE.value,
            }
    except Exception as e:
        logger.error(f"删除旧规则失败: {e}")
        return {
            "messages": [AIMessage(content=f"❌ 删除旧规则失败: {str(e)}")],
            "phase": ReconciliationPhase.EDIT_SAVE.value,
        }

    # 2. 新建规则（PostgreSQL + JSON）
    try:
        save_result = await call_mcp_tool("save_reconciliation_rule", {
            "auth_token": auth_token,
            "name": rule_name,
            "description": rule_name,
            "rule_template": schema,
            "visibility": "private",
        })
        if not save_result.get("success"):
            return {
                "messages": [AIMessage(content=f"❌ 保存新规则失败: {save_result.get('error', '未知错误')}")],
                "phase": ReconciliationPhase.EDIT_SAVE.value,
            }
    except Exception as e:
        logger.error(f"保存新规则失败: {e}")
        return {
            "messages": [AIMessage(content=f"❌ 保存新规则失败: {str(e)}")],
            "phase": ReconciliationPhase.EDIT_SAVE.value,
        }

    return {
        "messages": [AIMessage(content=f"✅ 规则「{rule_name}」已更新！（已删除旧规则并保存新规则）")],
        "saved_rule_name": rule_name,
        "editing_rule_id": None,
        "editing_rule_name": None,
        "editing_rule_template": None,
        "phase": ReconciliationPhase.COMPLETED.value,
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

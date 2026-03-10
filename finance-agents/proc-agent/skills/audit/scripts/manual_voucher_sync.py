"""手工凭证数据同步规则解析程序

功能：
  - 加载 JSON 格式的字段映射规则（支持多规则）
  - 从手工凭证表中过滤并转换数据
  - 返回解析后的 BI 费用明细表/损益毛利明细表（手工类）数据集

用法：
  python manual_voucher_sync.py --input <手工凭证表.xlsx> --rule <规则文件.json> --target <目标表名> [--output-dir <输出目录>]
  
支持的规则类型：
  - direct_mapping: 直接字段映射
  - constant: 固定常量值
  - extract: 按分隔符截取层级
  - formula: 四则运算公式
  - parse_from_field: 多步拆分解析
  - conditional_extract: 条件正则提取
  - conditional_value: 条件取值
  - conditional_formula: 条件公式
  - lookup: 查找表映射
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ── 规则加载 ──────────────────────────────────────────────────────────────────

def load_rule(rule_path: str | Path) -> dict[str, Any]:
    """加载 JSON 规则文件。"""
    rule_path = Path(rule_path)
    if not rule_path.exists():
        raise FileNotFoundError(f"规则文件不存在: {rule_path}")
    with rule_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ── 全局过滤 ──────────────────────────────────────────────────────────────────

def apply_global_filter(df: pd.DataFrame, global_filter: dict[str, Any]) -> pd.DataFrame:
    """按照全局过滤规则筛选手工凭证表行。

    Args:
        df: 手工凭证原始 DataFrame
        global_filter: 规则文件中的 global_filter 字段

    Returns:
        过滤后的 DataFrame（副本）
    """
    col = global_filter["source_column"]
    if col not in df.columns:
        raise KeyError(f"数据中缺少过滤列: '{col}'")

    include_values: list[str] = global_filter.get("values", [])
    exclude_values: list[str] = global_filter.get("exclude_values", [])
    operator: str = global_filter.get("operator", "in")

    if operator == "starts_with":
        # 前缀匹配模式
        mask_include = df[col].apply(
            lambda x: any(str(x).startswith(v) for v in include_values) if pd.notna(x) else False
        )
    else:
        # 精确匹配模式 (operator == "in")
        mask_include = df[col].isin(include_values)

    if exclude_values:
        mask_exclude = df[col].isin(exclude_values)
        mask_include = mask_include & ~mask_exclude

    filtered = df[mask_include].copy()
    logger.info("全局过滤后剩余记录数: %d（原始: %d）", len(filtered), len(df))
    return filtered


# ── 字段映射处理器 ────────────────────────────────────────────────────────────

def _apply_direct_mapping(row: pd.Series, mapping: dict[str, Any]) -> Any:
    """直接取源表字段值。"""
    src = mapping["source_field"]
    return row.get(src)


def _apply_constant(mapping: dict[str, Any]) -> Any:
    """返回固定常量值（含 null）。"""
    return mapping.get("value")


def _apply_extract(row: pd.Series, mapping: dict[str, Any]) -> Any:
    """从科目名称中按分隔符截取指定层级。

    例：科目名称 = "主营业务成本_直接服务费_项目A"
      level=1 → "主营业务成本"
      level=2 → "直接服务费"
      level=3 → "项目A"
    """
    src = mapping["source_field"]
    delimiter: str = mapping.get("delimiter", "_")
    level: int = mapping["extract_level"]
    value = row.get(src, "")
    if not isinstance(value, str):
        return None
    parts = value.split(delimiter)
    idx = level - 1
    return parts[idx] if idx < len(parts) else None


def _get_value(name: str, row: pd.Series, computed: dict[str, Any]) -> float:
    """从已计算结果或原始行中获取数值。"""
    if name in computed:
        v = computed[name]
    else:
        v = row.get(name, 0)
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (ValueError, TypeError):
        return 0.0


def _apply_formula(row: pd.Series, mapping: dict[str, Any], computed: dict[str, Any]) -> Any:
    """计算公式字段。

    支持公式模式：
      - "A + B" 加法
      - "A - B" 减法
      - "A * (1 + B)" 乘法含税计算
      - "-A" 取负数
    """
    formula: str = mapping["formula"]

    # 解析公式（支持多种模式）
    # 加法: "A + B"
    if " + " in formula and "*" not in formula:
        parts = formula.split(" + ")
        return sum(_get_value(p.strip(), row, computed) for p in parts)

    # 减法: "A - B"
    if " - " in formula and "*" not in formula:
        parts = formula.split(" - ")
        result = _get_value(parts[0].strip(), row, computed)
        for p in parts[1:]:
            result -= _get_value(p.strip(), row, computed)
        return result

    # 乘法含税: "A * (1 + B)"
    mult_match = re.match(r"(.+?)\s*\*\s*\(1\s*\+\s*(.+?)\)", formula)
    if mult_match:
        base_field = mult_match.group(1).strip()
        rate_field = mult_match.group(2).strip()
        base = _get_value(base_field, row, computed)
        rate = _get_value(rate_field, row, computed)
        return base * (1 + rate)

    # 取负数: "-A" 或 "负数A"
    if formula.startswith("-"):
        field_name = formula[1:].strip()
        return -_get_value(field_name, row, computed)

    # 单字段取值
    return _get_value(formula.strip(), row, computed)


def _apply_parse_from_field(row: pd.Series, mapping: dict[str, Any]) -> Any:
    """按多步解析规则从字段中提取值（用于税率字段）。

    解析逻辑（来自规则文件 parse_rules）：
      1. 按 & 分割摘要，取第 2 段作为"调整类型"
      2. 从调整类型中按 + 分割，取第 2 段作为"税率"
         若为空，税率为 0
    """
    src_field = mapping["source_field"]
    raw_value = row.get(src_field, "")
    if not isinstance(raw_value, str):
        raw_value = ""

    current_value: str = raw_value
    parse_rules: list[dict] = mapping.get("parse_rules", [])

    for step_rule in parse_rules:
        split_by: str = step_rule.get("split_by", "")
        extract_index: int = step_rule.get("extract_index", 0)
        fallback = step_rule.get("fallback", None)

        parts = current_value.split(split_by)
        if extract_index < len(parts):
            current_value = parts[extract_index].strip()
        else:
            current_value = ""

        if not current_value and fallback is not None:
            return fallback

    # 最终结果尝试转为数值（百分比格式如 "6%" 转为 0.06）
    current_value = current_value.strip()
    if not current_value:
        return 0

    # 支持 "6%" 格式
    percent_match = re.match(r"^([\d.]+)%$", current_value)
    if percent_match:
        return float(percent_match.group(1)) / 100

    try:
        return float(current_value)
    except ValueError:
        return current_value  # 无法转换时返回原始字符串


def _apply_conditional_extract(row: pd.Series, mapping: dict[str, Any]) -> Any:
    """条件正则提取（用于客户、供应商等字段）。

    根据条件判断是否提取，使用正则表达式从字段中提取值。
    """
    src_field = mapping["source_field"]
    raw_value = row.get(src_field, "")
    if not isinstance(raw_value, str):
        return None

    conditions: list[dict] = mapping.get("conditions", [])
    for cond in conditions:
        pattern = cond.get("extract_pattern")
        if not pattern:
            continue
        match = re.search(pattern, raw_value)
        if match:
            group_idx = cond.get("extract_group", 0)
            try:
                return match.group(group_idx)
            except IndexError:
                continue
    return None


def _apply_conditional_value(row: pd.Series, mapping: dict[str, Any]) -> Any:
    """条件取值（用于税率、核算类型等根据科目名称判断的字段）。

    根据源字段值匹配条件，返回对应的固定值。
    """
    src_field = mapping["source_field"]
    src_value = row.get(src_field, "")
    if not isinstance(src_value, str):
        src_value = str(src_value) if src_value is not None else ""

    conditions: list[dict] = mapping.get("conditions", [])
    for cond in conditions:
        cond_str: str = cond.get("condition", "")
        value = cond.get("value")

        # 处理"其他"条件作为默认值
        if cond_str in ("其他", "其他科目", "default"):
            return value

        # 检查科目名称是否匹配条件（支持多个值用"或"连接）
        if "或" in cond_str:
            # 解析"A或B"格式
            match_patterns = []
            for part in cond_str.split("或"):
                # 提取引号中的值
                quoted = re.findall(r"['"]([^'"]+)['"]", part)
                match_patterns.extend(quoted)
            if any(p in src_value or src_value == p for p in match_patterns):
                return value
        else:
            # 单一条件
            quoted = re.findall(r"['"]([^'"]+)['"]", cond_str)
            if quoted and any(p in src_value or src_value == p for p in quoted):
                return value

    return None


def _apply_conditional_formula(
    row: pd.Series,
    mapping: dict[str, Any],
    computed: dict[str, Any],
) -> Any:
    """条件公式（用于 eas收入不含税、eas成本不含税 等复杂字段）。

    根据条件判断使用不同的公式计算。
    """
    src_field = mapping.get("source_field", "")
    src_value = row.get(src_field, "")
    if not isinstance(src_value, str):
        src_value = str(src_value) if src_value is not None else ""

    # 获取摘要中的调整类型
    summary = row.get("摘要", "")
    if not isinstance(summary, str):
        summary = ""
    adjust_type = ""
    if "&" in summary:
        parts = summary.split("&")
        if len(parts) > 1:
            adjust_type = parts[1].split("+")[0].strip() if "+" in parts[1] else parts[1].strip()

    conditions: list[dict] = mapping.get("conditions", [])
    for cond in conditions:
        cond_str: str = cond.get("condition", "")
        formula: str = cond.get("formula", "")

        # 检查条件是否匹配
        match = False
        if "调整类型" in cond_str and "科目名称" in cond_str:
            # 复合条件：调整类型 + 科目名称
            if "调整收入" in cond_str and adjust_type == "调整收入":
                quoted = re.findall(r"['"]([^'"]+)['"]", cond_str)
                if any(q in src_value for q in quoted):
                    match = True
            elif "调整成本" in cond_str and adjust_type == "调整成本":
                quoted = re.findall(r"['"]([^'"]+)['"]", cond_str)
                if any(q in src_value for q in quoted):
                    match = True
        elif "科目名称" in cond_str:
            # 仅科目名称条件
            quoted = re.findall(r"['"]([^'"]+)['"]", cond_str)
            if "或" in cond_str:
                match = any(q in src_value for q in quoted)
            else:
                match = any(q in src_value for q in quoted)

        if match:
            return _get_value(formula, row, computed)

    return 0


def _apply_lookup(
    row: pd.Series,
    mapping: dict[str, Any],
    lookup_tables: dict[str, pd.DataFrame],
) -> Any:
    """查找表映射（用于关联客户、收入类型等字段）。

    从外部查找表中根据键值查询对应的结果。
    """
    table_name = mapping.get("lookup_table", "")
    lookup_key = mapping.get("lookup_key", mapping.get("lookup_field", ""))
    src_field = mapping.get("source_field", lookup_key)
    return_field = mapping.get("return_field", "")

    # 获取源值
    src_value = row.get(src_field, "")

    # 如果有查找表数据
    if table_name in lookup_tables:
        lookup_df = lookup_tables[table_name]
        if lookup_key in lookup_df.columns:
            matches = lookup_df[lookup_df[lookup_key] == src_value]
            if not matches.empty:
                if return_field and return_field in matches.columns:
                    return matches.iloc[0][return_field]
                else:
                    return mapping.get("match_result", "关联")
            else:
                return mapping.get("no_match_result", "非关联")

    # 无查找表时返回默认值
    return mapping.get("no_match_result", None)


# ── 单行映射 ──────────────────────────────────────────────────────────────────

def map_row(
    row: pd.Series,
    field_mappings: list[dict[str, Any]],
    lookup_tables: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    """将手工凭证表中的单行数据按规则映射为目标行。

    Args:
        row: 手工凭证表中的单条记录
        field_mappings: 规则文件中的 field_mappings 列表
        lookup_tables: 查找表字典（可选）

    Returns:
        映射后的目标字段字典
    """
    if lookup_tables is None:
        lookup_tables = {}

    # 分离规则类型
    formula_types = {"formula", "conditional_formula"}
    normal_mappings = [m for m in field_mappings if m["rule_type"] not in formula_types]
    formula_mappings = [m for m in field_mappings if m["rule_type"] in formula_types]

    result: dict[str, Any] = {}

    # 第一轮：处理非公式字段
    for mapping in normal_mappings:
        target = mapping["target_field"]
        rule_type = mapping["rule_type"]

        if rule_type == "direct_mapping":
            result[target] = _apply_direct_mapping(row, mapping)
        elif rule_type == "constant":
            result[target] = _apply_constant(mapping)
        elif rule_type == "extract":
            result[target] = _apply_extract(row, mapping)
        elif rule_type == "parse_from_field":
            result[target] = _apply_parse_from_field(row, mapping)
        elif rule_type == "conditional_extract":
            result[target] = _apply_conditional_extract(row, mapping)
        elif rule_type == "conditional_value":
            result[target] = _apply_conditional_value(row, mapping)
        elif rule_type == "lookup":
            result[target] = _apply_lookup(row, mapping, lookup_tables)
        else:
            logger.warning("未知 rule_type '%s' 对字段 '%s'，跳过", rule_type, target)

    # 第二轮：处理公式字段（依赖第一轮结果）
    formula_order = [
        # BI费用明细表
        "eas不含税金额", "eas含税金额", "eas税额",
        # BI损益毛利明细表
        "eas收入不含税", "eas成本不含税",
        "含税销售额", "含税采购成本", "含税差额收入",
        "eas税额", "eas差额收入不含税",
    ]
    formula_map_dict = {m["target_field"]: m for m in formula_mappings}

    for field_name in formula_order:
        if field_name in formula_map_dict:
            mapping = formula_map_dict[field_name]
            if mapping["rule_type"] == "conditional_formula":
                result[field_name] = _apply_conditional_formula(row, mapping, result)
            else:
                result[field_name] = _apply_formula(row, mapping, result)

    # 处理未在顺序中的其他公式字段
    for mapping in formula_mappings:
        target = mapping["target_field"]
        if target not in result:
            if mapping["rule_type"] == "conditional_formula":
                result[target] = _apply_conditional_formula(row, mapping, result)
            else:
                result[target] = _apply_formula(row, mapping, result)

    return result


# ── 主解析入口 ────────────────────────────────────────────────────────────────

def get_rule_by_target(
    rule_data: dict[str, Any],
    target_table: str | None = None,
    rule_id: str | None = None,
) -> dict[str, Any] | None:
    """从规则文件中获取指定的规则。

    Args:
        rule_data: 规则文件内容
        target_table: 目标表名称（如 "费用明细表"、"损益毛利明细表"）
        rule_id: 规则 ID

    Returns:
        匹配的规则字典，未找到则返回 None
    """
    # 支持旧格式（单规则）和新格式（多规则）
    if "rules" in rule_data:
        rules = rule_data["rules"]
    else:
        return rule_data

    for rule in rules:
        if rule_id and rule.get("rule_id") == rule_id:
            return rule
        if target_table:
            rule_target = rule.get("target_table", "")
            if target_table in rule_target or rule_target in target_table:
                return rule

    return rules[0] if rules else None


def parse_rule_and_sync(
    source_df: pd.DataFrame,
    rule: dict[str, Any],
    lookup_tables: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """按照规则将手工凭证表转换为目标数据集。

    Args:
        source_df: 手工凭证原始 DataFrame
        rule: 已加载的 JSON 规则字典
        lookup_tables: 查找表字典（可选）

    Returns:
        转换后的目标 DataFrame
    """
    if lookup_tables is None:
        lookup_tables = {}

    logger.info("开始解析规则: %s（版本 %s）", rule.get("rule_id"), rule.get("version"))
    logger.info("目标表: %s", rule.get("target_table", "未指定"))

    # 1. 全局过滤
    global_filter = rule.get("global_filter")
    if global_filter:
        filtered_df = apply_global_filter(source_df, global_filter)
    else:
        filtered_df = source_df.copy()

    if filtered_df.empty:
        logger.warning("全局过滤后数据为空，返回空 DataFrame")
        return pd.DataFrame()

    field_mappings: list[dict[str, Any]] = rule.get("field_mappings", [])

    # 2. 逐行映射
    rows = []
    for _, row in filtered_df.iterrows():
        mapped_row = map_row(row, field_mappings, lookup_tables)
        rows.append(mapped_row)

    result_df = pd.DataFrame(rows)
    logger.info("数据同步完成，生成记录数: %d，列数: %d", len(result_df), len(result_df.columns))
    return result_df


# ── 命令行入口 ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="手工凭证数据同步规则解析程序")
    parser.add_argument("--input", required=True, help="手工凭证表 Excel 文件路径")
    parser.add_argument(
        "--rule",
        default=str(Path(__file__).parent.parent / "references" / "manual_voucher_sync_rule.json"),
        help="JSON 规则文件路径（默认使用 references/manual_voucher_sync_rule.json）",
    )
    parser.add_argument(
        "--target",
        choices=["费用明细表", "损益毛利明细表", "all"],
        default="费用明细表",
        help="目标表类型：费用明细表 / 损益毛利明细表 / all（同时生成两个表）",
    )
    parser.add_argument("--sheet", default=None, help="Excel Sheet 名称，默认读取第一个 Sheet")
    parser.add_argument("--output-dir", default="result", help="输出目录，默认 result/")
    args = parser.parse_args()

    # 加载规则
    rule_data = load_rule(args.rule)
    logger.info("规则加载成功: %s", args.rule)

    # 读取手工凭证表
    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    source_df = pd.read_excel(input_path, sheet_name=args.sheet or 0)
    logger.info("读取手工凭证表成功，行数: %d，列数: %d", len(source_df), len(source_df.columns))

    # 确定要处理的目标表
    targets = []
    if args.target == "all":
        targets = ["费用明细表", "损益毛利明细表"]
    else:
        targets = [args.target]

    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for target in targets:
        rule = get_rule_by_target(rule_data, target)
        if not rule:
            logger.warning("未找到目标表 '%s' 的规则，跳过", target)
            continue

        result_df = parse_rule_and_sync(source_df, rule)

        if result_df.empty:
            logger.warning("目标表 '%s' 结果为空，跳过输出", target)
            continue

        # 输出到 Excel
        target_short = "expense" if "费用" in target else "profit_margin"
        output_path = output_dir / f"bi_{target_short}_manual_{timestamp}.xlsx"
        result_df.to_excel(output_path, index=False)
        logger.info("结果已写入: %s", output_path)

        # 打印前 5 行预览
        print(f"\n=== {rule.get('target_table', target)} 解析结果预览（前5行）===")
        print(result_df.head().to_string(index=False))
        print(f"\n共 {len(result_df)} 条记录，{len(result_df.columns)} 个字段")


if __name__ == "__main__":
    main()

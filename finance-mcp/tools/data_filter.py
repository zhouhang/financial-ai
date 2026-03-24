"""
数据过滤工具模块

提供通用的数据过滤功能，支持对账规则中定义的过滤条件。
支持的操作符：=, !=, >, >=, <, <=, in, not_in, contains, not_contains,
               starts_with, ends_with, is_null, is_not_null, regex_match
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Union

import pandas as pd

logger = logging.getLogger("tools.data_filter")


# ════════════════════════════════════════════════════════════════════════════
# 过滤条件评估函数
# ════════════════════════════════════════════════════════════════════════════

def _evaluate_condition(value: Any, operator: str, compare_value: Any = None) -> bool:
    """
    评估单个过滤条件
    
    Args:
        value: 实际值
        operator: 操作符
        compare_value: 比较值（可选）
    
    Returns:
        是否满足条件
    """
    # 处理空值操作符
    if operator == "is_null":
        return pd.isna(value) or value is None or value == ""
    
    if operator == "is_not_null":
        return not (pd.isna(value) or value is None or value == "")
    
    # 如果实际值为空，其他操作符都返回 False
    if pd.isna(value) or value is None:
        return False
    
    # 转换为字符串进行比较（文本操作符）
    str_value = str(value)
    
    if operator == "=":
        # 支持数值和字符串比较
        try:
            # 尝试数值比较
            return float(value) == float(compare_value)
        except (ValueError, TypeError):
            # 字符串比较
            return str_value == str(compare_value)
    
    elif operator == "!=":
        try:
            return float(value) != float(compare_value)
        except (ValueError, TypeError):
            return str_value != str(compare_value)
    
    elif operator == ">":
        try:
            return float(value) > float(compare_value)
        except (ValueError, TypeError):
            return str_value > str(compare_value)
    
    elif operator == ">=":
        try:
            return float(value) >= float(compare_value)
        except (ValueError, TypeError):
            return str_value >= str(compare_value)
    
    elif operator == "<":
        try:
            return float(value) < float(compare_value)
        except (ValueError, TypeError):
            return str_value < str(compare_value)
    
    elif operator == "<=":
        try:
            return float(value) <= float(compare_value)
        except (ValueError, TypeError):
            return str_value <= str(compare_value)
    
    elif operator == "in":
        # compare_value 应该是列表
        if isinstance(compare_value, list):
            return str_value in [str(v) for v in compare_value]
        return str_value == str(compare_value)
    
    elif operator == "not_in":
        if isinstance(compare_value, list):
            return str_value not in [str(v) for v in compare_value]
        return str_value != str(compare_value)
    
    elif operator == "contains":
        return str(compare_value) in str_value
    
    elif operator == "not_contains":
        return str(compare_value) not in str_value
    
    elif operator == "starts_with":
        return str_value.startswith(str(compare_value))
    
    elif operator == "ends_with":
        return str_value.endswith(str(compare_value))
    
    elif operator == "regex_match":
        try:
            pattern = str(compare_value)
            return re.search(pattern, str_value) is not None
        except re.error as e:
            logger.error(f"正则表达式错误: {e}, pattern={compare_value}")
            return False
    
    else:
        logger.warning(f"未知的操作符: {operator}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# 主过滤函数
# ════════════════════════════════════════════════════════════════════════════

def filter_dataframe(
    df: pd.DataFrame,
    filter_config: Optional[Dict[str, Any]]
) -> pd.DataFrame:
    """
    根据过滤配置筛选 DataFrame
    
    Args:
        df: 输入的 DataFrame
        filter_config: 过滤配置，包含 enabled, conditions, logic 等
    
    Returns:
        过滤后的 DataFrame
    
    示例配置:
        {
            "enabled": true,
            "conditions": [
                {
                    "column": "订单类型",
                    "operator": "in",
                    "values": ["正常订单", "补单"],
                    "description": "只处理正常订单和补单"
                },
                {
                    "column": "金额",
                    "operator": ">",
                    "value": 0,
                    "description": "金额大于0"
                }
            ],
            "logic": "and"
        }
    """
    # 如果过滤未启用或配置为空，返回原数据
    if not filter_config or not filter_config.get("enabled", False):
        logger.info("[数据过滤] 过滤未启用，返回全部数据")
        return df
    
    if df.empty:
        logger.info("[数据过滤] 输入数据为空，直接返回")
        return df
    
    conditions = filter_config.get("conditions", [])
    logic = filter_config.get("logic", "and")
    
    if not conditions:
        logger.info("[数据过滤] 无过滤条件，返回全部数据")
        return df
    
    logger.info(f"[数据过滤] 开始过滤，原始数据 {len(df)} 行，条件数: {len(conditions)}, 逻辑: {logic}")
    
    # 构建条件掩码
    condition_masks: List[pd.Series] = []
    
    for idx, condition in enumerate(conditions):
        column = condition.get("column")
        operator = condition.get("operator")
        description = condition.get("description", f"条件{idx+1}")
        
        if not column or not operator:
            logger.warning(f"[数据过滤] 条件 {idx+1} 配置不完整，跳过")
            continue
        
        # 检查列是否存在
        if column not in df.columns:
            logger.warning(f"[数据过滤] 列 '{column}' 不存在于数据中，跳过此条件")
            continue
        
        # 获取比较值（支持 value 或 values）
        compare_value = condition.get("value") if "value" in condition else condition.get("values")
        
        # 评估条件
        try:
            mask = df[column].apply(lambda x: _evaluate_condition(x, operator, compare_value))
            condition_masks.append(mask)
            matched_count = mask.sum()
            logger.info(f"[数据过滤] 条件 '{description}' ({column} {operator} {compare_value}): 匹配 {matched_count} 行")
        except Exception as e:
            logger.error(f"[数据过滤] 条件 '{description}' 评估失败: {e}")
            continue
    
    if not condition_masks:
        logger.info("[数据过滤] 无有效条件，返回全部数据")
        return df
    
    # 根据逻辑组合条件
    if logic == "and":
        final_mask = condition_masks[0]
        for mask in condition_masks[1:]:
            final_mask = final_mask & mask
    else:  # or
        final_mask = condition_masks[0]
        for mask in condition_masks[1:]:
            final_mask = final_mask | mask
    
    # 应用过滤
    filtered_df = df[final_mask].copy()
    
    logger.info(f"[数据过滤] 过滤完成，原始 {len(df)} 行 -> 过滤后 {len(filtered_df)} 行，过滤掉 {len(df) - len(filtered_df)} 行")
    
    return filtered_df


def filter_dataframe_by_rule_config(
    df: pd.DataFrame,
    file_config: Dict[str, Any]
) -> pd.DataFrame:
    """
    根据文件配置中的 filter 节点过滤 DataFrame
    
    Args:
        df: 输入的 DataFrame
        file_config: 文件配置（source_file 或 target_file），包含 filter 节点
    
    Returns:
        过滤后的 DataFrame
    """
    filter_config = file_config.get("filter")
    table_name = file_config.get("table_name", "未知表")
    
    if not filter_config or not filter_config.get("enabled", False):
        logger.info(f"[数据过滤] {table_name} 过滤未启用")
        return df
    
    logger.info(f"[数据过滤] 处理 {table_name}")
    return filter_dataframe(df, filter_config)


# ════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════════════════════════════

def get_filter_statistics(
    original_df: pd.DataFrame,
    filtered_df: pd.DataFrame,
    file_name: str = ""
) -> Dict[str, Any]:
    """
    获取过滤统计信息
    
    Args:
        original_df: 原始数据
        filtered_df: 过滤后数据
        file_name: 文件名（用于日志）
    
    Returns:
        统计信息字典
    """
    original_count = len(original_df)
    filtered_count = len(filtered_df)
    removed_count = original_count - filtered_count
    
    stats = {
        "file_name": file_name,
        "original_count": original_count,
        "filtered_count": filtered_count,
        "removed_count": removed_count,
        "filter_rate": round(removed_count / original_count * 100, 2) if original_count > 0 else 0
    }
    
    logger.info(f"[数据过滤统计] {file_name}: 原始 {original_count} 行 -> 保留 {filtered_count} 行 (过滤 {removed_count} 行, 过滤率 {stats['filter_rate']}%)")
    
    return stats


def validate_filter_config(filter_config: Dict[str, Any]) -> List[str]:
    """
    验证过滤配置是否有效
    
    Args:
        filter_config: 过滤配置
    
    Returns:
        错误信息列表，为空表示验证通过
    """
    errors = []
    
    if not filter_config:
        return errors
    
    if not isinstance(filter_config, dict):
        errors.append("过滤配置必须是字典类型")
        return errors
    
    conditions = filter_config.get("conditions", [])
    if not isinstance(conditions, list):
        errors.append("conditions 必须是列表类型")
        return errors
    
    valid_operators = {
        "=", "!=", ">", ">=", "<", "<=",
        "in", "not_in", "contains", "not_contains",
        "starts_with", "ends_with", "is_null", "is_not_null", "regex_match"
    }
    
    for idx, condition in enumerate(conditions):
        if not isinstance(condition, dict):
            errors.append(f"条件 {idx+1} 必须是字典类型")
            continue
        
        column = condition.get("column")
        operator = condition.get("operator")
        
        if not column:
            errors.append(f"条件 {idx+1} 缺少 column 字段")
        
        if not operator:
            errors.append(f"条件 {idx+1} 缺少 operator 字段")
        elif operator not in valid_operators:
            errors.append(f"条件 {idx+1} 的操作符 '{operator}' 无效，有效值: {valid_operators}")
        
        # 检查 value/values 是否提供（is_null 和 is_not_null 除外）
        if operator not in ("is_null", "is_not_null"):
            if "value" not in condition and "values" not in condition:
                errors.append(f"条件 {idx+1} 缺少 value 或 values 字段")
    
    logic = filter_config.get("logic", "and")
    if logic not in ("and", "or"):
        errors.append(f"logic 必须是 'and' 或 'or'，当前值: {logic}")
    
    return errors

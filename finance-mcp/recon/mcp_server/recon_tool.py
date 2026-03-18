"""
核对 MCP 工具模块

根据规则定义，执行源文件与目标文件的数据比对与差异分析。
支持两种规则类型：
1. 对账规则：包含 rules 字段
2. 普通对账规则：通过 recon_task_execution 处理

主要功能：
1. 加载规则（从 bus_rules 表，根据传入的 rule_code）
2. 判断规则类型（对账 vs 普通对账）
3. 执行数据核对：关键列匹配、数值比对、聚合比对
4. 输出差异分析结果：差异记录、源文件独有、目标文件独有
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from mcp import Tool

# 导入数据过滤模块
from tools.data_filter import filter_dataframe_by_rule_config, get_filter_statistics

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
# 常量定义
# ════════════════════════════════════════════════════════════════════════════

# 对账报告输出目录（相对于 finance-mcp 目录）
RECON_OUTPUT_DIR = Path(__file__).parent.parent / "output"


# ════════════════════════════════════════════════════════════════════════════
# MCP 工具定义
# ════════════════════════════════════════════════════════════════════════════

def create_recon_tools() -> list[Tool]:
    """创建核对 MCP 工具列表"""
    return [
        Tool(
            name="recon_execute",
            description=(
                "执行对账：根据规则对源文件与目标文件进行数据比对，"
                "支持对账规则（含 rules）和普通对账规则。"
                "输出差异记录、源文件独有记录、目标文件独有记录等。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "validated_files": {
                        "type": "array",
                        "description": "文件校验结果列表，每个元素包含 file_path 和 table_name",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string"},
                                "table_name": {"type": "string"}
                            }
                        }
                    },
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码（rule_code），用于从 bus_rules 表获取规则定义"
                    },
                    "rule_id": {
                        "type": "string",
                        "description": "要执行的核对规则 ID（如 AUDIT_RECONC_001），仅在对账规则中使用，不指定则执行所有匹配的规则"
                    }
                },
                "required": ["validated_files", "rule_code"]
            }
        ),
        Tool(
            name="recon_list_rules",
            description="列出所有可用的核对规则",
            inputSchema={
                "type": "object",
                "properties": {
                    "rule_code": {
                        "type": "string",
                        "description": "规则编码，用于从 bus_rules 表获取规则定义"
                    }
                },
                "required": ["rule_code"]
            }
        )
    ]


async def handle_recon_tool_call(name: str, arguments: dict) -> dict:
    """处理核对工具调用"""
    try:
        if name == "recon_execute":
            return await _handle_recon_execute(arguments)
        elif name == "recon_list_rules":
            return await _handle_recon_list_rules(arguments)
        else:
            return {"success": False, "error": f"未知的工具: {name}"}
    except Exception as e:
        logger.error(f"核对工具调用失败 [{name}]: {e}", exc_info=True)
        return {"success": False, "error": f"工具调用失败: {str(e)}"}


# ════════════════════════════════════════════════════════════════════════════
# 规则加载（复用 tools.rules 中的公共方法）
# ════════════════════════════════════════════════════════════════════════════

def _get_rule_from_bus(rule_code: str) -> Optional[dict]:
    """
    从 bus_rules 表加载指定 rule_code 的规则配置
    
    复用 tools.rules 中的 get_rule_from_bus 函数
    
    Args:
        rule_code: 规则编码
        
    Returns:
        规则字典，包含 id, rule_code, rule, memo 等字段；未找到返回 None
    """
    try:
        from tools.rules import get_rule_from_bus
        return get_rule_from_bus(rule_code)
    except ImportError:
        logger.error(f"[recon] 无法导入 tools.rules.get_rule_from_bus")
        return None


def find_recon_rule_by_id(rules_config: dict, rule_id: str) -> Optional[dict]:
    """根据 rule_id 查找规则"""
    for rule in rules_config.get("rules", []):
        if rule.get("rule_id") == rule_id:
            return rule
    return None


# ════════════════════════════════════════════════════════════════════════════
# 工具处理函数
# ════════════════════════════════════════════════════════════════════════════

async def _handle_recon_list_rules(arguments: dict) -> dict:
    """列出所有核对规则"""
    rule_code = arguments.get("rule_code")
    if not rule_code:
        return {"success": False, "error": "rule_code 不能为空"}
    
    rule_record = _get_rule_from_bus(rule_code)
    if rule_record is None:
        return {"success": False, "error": f"未找到规则配置: rule_code={rule_code}"}
    
    rule_content = rule_record.get("rule", {})
    rules_config = rule_content if isinstance(rule_content, dict) else {}
    
    rules = rules_config.get("rules", [])
    rule_list = []
    for rule in rules:
        rule_list.append({
            "rule_id": rule.get("rule_id"),
            "rule_name": rule.get("rule_name"),
            "description": rule.get("description"),
            "enabled": rule.get("enabled", True),
            "source_table": rule.get("source_file", {}).get("identification", {}).get("match_value"),
            "target_table": rule.get("target_file", {}).get("identification", {}).get("match_value")
        })
    
    return {
        "success": True,
        "rule_code": rule_code,
        "count": len(rule_list),
        "rules": rule_list
    }


async def _handle_recon_execute(arguments: dict) -> dict:
    """执行对账（支持对账和普通对账）"""
    validated_files = arguments.get("validated_files", [])
    rule_code = arguments.get("rule_code", "")
    rule_id = arguments.get("rule_id")
    
    if not validated_files:
        return {"success": False, "error": "validated_files 不能为空"}
    if not rule_code:
        return {"success": False, "error": "rule_code 不能为空"}
    
    # 使用常量定义的输出目录
    output_dir = str(RECON_OUTPUT_DIR)
    
    # 确保输出目录存在
    RECON_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 加载规则（复用 tools.rules 中的公共方法）
    rule_record = _get_rule_from_bus(rule_code)
    if rule_record is None:
        return {"success": False, "error": f"未找到规则: rule_code={rule_code}"}
    
    rule_content = rule_record.get("rule", {})
    
    # 判断规则类型
    is_recon = isinstance(rule_content, dict) and rule_content.get("rules") is not None
    
    logger.info(f"[recon] 规则类型: {'对账' if is_recon else '普通对账'}, rule_code={rule_code}")
    
    # 构建 table_name -> file_path 映射
    table_file_map: dict[str, str] = {}
    for item in validated_files:
        table_name = item.get("table_name", "")
        file_path = item.get("file_path", "")
        if table_name and file_path:
            table_file_map[table_name] = file_path
    
    logger.info(f"[recon] 文件映射: {list(table_file_map.keys())}")
    
    if is_recon:
        # 对账逻辑
        rules_config = rule_content
        
        # 确定要执行的规则
        rules = rules_config.get("rules", [])
        if rule_id:
            target_rule = find_recon_rule_by_id(rules_config, rule_id)
            if target_rule is None:
                return {"success": False, "error": f"未找到 rule_id='{rule_id}' 的规则"}
            rules = [target_rule]
        
        # 执行核对
        results = []
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            
            result = execute_single_recon(rule, table_file_map, output_dir)
            # 只保留成功匹配到文件的规则结果
            if result.get("success") and result.get("source_file") and result.get("target_file"):
                results.append(result)
            elif result.get("success"):
                # 规则启用但未匹配到文件，跳过不加入结果
                logger.info(f"[recon] 规则 {rule.get('rule_id')} 未匹配到文件，跳过")
            else:
                # 执行失败的规则，可以选择保留或跳过
                # 这里选择跳过失败的规则
                logger.warning(f"[recon] 规则 {rule.get('rule_id')} 执行失败: {result.get('error')}")
        
        success_count = len(results)
        
        return {
            "success": True,
            "rule_code": rule_code,
            "rule_type": "recon",
            "total_rules": len(results),
            "success_count": success_count,
            "results": results
        }
    else:
        # 普通对账逻辑
        return await _execute_normal_reconciliation(
            rule_content=rule_content,
            rule_code=rule_code,
            table_file_map=table_file_map,
            output_dir=output_dir,
            validated_files=validated_files
        )


# ════════════════════════════════════════════════════════════════════════════
# 核对执行逻辑
# ════════════════════════════════════════════════════════════════════════════

def execute_single_recon(
    rule: dict,
    table_file_map: dict[str, str],
    output_dir: str
) -> dict:
    """
    执行单个对账规则
    
    Args:
        rule: 规则配置
        table_file_map: table_name -> file_path 映射
        output_dir: 输出目录
    
    Returns:
        核对结果
    """
    rule_id = rule.get("rule_id", "UNKNOWN")
    rule_name = rule.get("rule_name", "未命名规则")
    
    logger.info(f"[recon] [{rule_id}] 开始执行: {rule_name}")
    
    # 1. 识别源文件和目标文件
    source_file_config = rule.get("source_file", {})
    target_file_config = rule.get("target_file", {})
    
    source_path = _find_file_by_identification(
        source_file_config.get("identification", {}),
        table_file_map,
        rule_id,
        "source"
    )
    target_path = _find_file_by_identification(
        target_file_config.get("identification", {}),
        table_file_map,
        rule_id,
        "target"
    )
    
    if source_path is None:
        return {
            "success": False,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "error": "未找到源文件"
        }
    
    if target_path is None:
        return {
            "success": False,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "error": "未找到目标文件"
        }
    
    logger.info(f"[recon] [{rule_id}] 源文件: {source_path}")
    logger.info(f"[recon] [{rule_id}] 目标文件: {target_path}")
    
    # 2. 读取文件
    try:
        df_source = _read_file_as_df(source_path)
        df_target = _read_file_as_df(target_path)
    except Exception as e:
        return {
            "success": False,
            "rule_id": rule_id,
            "rule_name": rule_name,
            "error": f"读取文件失败: {e}"
        }
    
    logger.info(f"[recon] [{rule_id}] 源文件 {len(df_source)} 行，目标文件 {len(df_target)} 行")
    
    # 3. 应用数据过滤
    source_filter_stats = None
    target_filter_stats = None
    
    # 过滤源文件
    df_source_original = df_source.copy()
    logger.info(f"[recon] [{rule_id}] 源文件过滤前: {len(df_source)} 行, filter配置: {source_file_config.get('filter')}")
    df_source = filter_dataframe_by_rule_config(df_source, source_file_config)
    logger.info(f"[recon] [{rule_id}] 源文件过滤后: {len(df_source)} 行")
    if len(df_source) != len(df_source_original):
        source_filter_stats = get_filter_statistics(
            df_source_original, 
            df_source, 
            source_file_config.get("table_name", "源文件")
        )
    else:
        logger.info(f"[recon] [{rule_id}] 源文件无过滤或过滤前后行数相同")
    
    # 过滤目标文件
    df_target_original = df_target.copy()
    logger.info(f"[recon] [{rule_id}] 目标文件过滤前: {len(df_target)} 行, filter配置: {target_file_config.get('filter')}")
    df_target = filter_dataframe_by_rule_config(df_target, target_file_config)
    logger.info(f"[recon] [{rule_id}] 目标文件过滤后: {len(df_target)} 行")
    if len(df_target) != len(df_target_original):
        target_filter_stats = get_filter_statistics(
            df_target_original, 
            df_target, 
            target_file_config.get("table_name", "目标文件")
        )
    else:
        logger.info(f"[recon] [{rule_id}] 目标文件无过滤或过滤前后行数相同")
    
    logger.info(f"[recon] [{rule_id}] 过滤后：源文件 {len(df_source)} 行，目标文件 {len(df_target)} 行")
    
    # 4. 应用列映射
    df_source = _apply_column_mapping(df_source, source_file_config.get("column_mapping", {}))
    df_target = _apply_column_mapping(df_target, target_file_config.get("column_mapping", {}))
    
    # 4. 获取核对配置
    recon_config = rule.get("reconciliation_config", {})
    key_columns_config = recon_config.get("key_columns", {})
    key_columns = key_columns_config.get("columns", [])
    compare_columns_config = recon_config.get("compare_columns", {}).get("columns", [])
    aggregation_config = recon_config.get("aggregation", {})
    
    # 5. 执行聚合（如果启用）
    if aggregation_config.get("enabled", False):
        df_source = _apply_aggregation(df_source, aggregation_config, rule_id, "source")
        df_target = _apply_aggregation(df_target, aggregation_config, rule_id, "target")
    
    # 6. 执行核对比较
    diff_result = _execute_comparison(
        df_source=df_source,
        df_target=df_target,
        key_columns=key_columns,
        compare_columns_config=compare_columns_config,
        diff_analysis_config=rule.get("diff_analysis", {}),
        rule_id=rule_id,
        key_columns_config=key_columns_config
    )
    
    # 7. 输出结果
    output_config = rule.get("output", {})
    output_path = _write_recon_result(
        diff_result=diff_result,
        output_dir=output_dir,
        output_config=output_config,
        rule_id=rule_id,
        rule_name=rule_name,
        key_columns_config=key_columns_config,
        compare_columns_config=compare_columns_config
    )
    
    # 8. 生成下载链接
    download_url = None
    if output_path:
        import os
        from pathlib import Path
        file_name = Path(output_path).name
        # MCP_PUBLIC_BASE_URL 在 unified_mcp_server.py 中定义
        try:
            import unified_mcp_server
            base_url = unified_mcp_server.MCP_PUBLIC_BASE_URL.rstrip("/")
        except (ImportError, AttributeError):
            base_url = os.getenv("MCP_PUBLIC_BASE_URL", "http://localhost:3335").rstrip("/")
        download_url = f"{base_url}/output/recon/{file_name}"
    
    # 9. 构建过滤提示信息
    filter_messages = []
    if source_filter_stats:
        filter_messages.append(
            f"源文件【{source_filter_stats['file_name']}】"
            f"原记录 {source_filter_stats['original_count']} 条，"
            f"过滤后参与对账 {source_filter_stats['filtered_count']} 条"
        )
    if target_filter_stats:
        filter_messages.append(
            f"目标文件【{target_filter_stats['file_name']}】"
            f"原记录 {target_filter_stats['original_count']} 条，"
            f"过滤后参与对账 {target_filter_stats['filtered_count']} 条"
        )
    
    # 构建完整消息
    message_parts = []
    if filter_messages:
        message_parts.append("数据过滤：" + "；".join(filter_messages))
    message_parts.append(
        f"核对完成：差异 {len(diff_result.get('matched_with_diff', []))} 条，"
        f"源独有 {len(diff_result.get('source_only', []))} 条，"
        f"目标独有 {len(diff_result.get('target_only', []))} 条"
    )
    
    result = {
        "success": True,
        "rule_id": rule_id,
        "rule_name": rule_name,
        "source_file": source_path,
        "target_file": target_path,
        "source_rows": len(df_source),
        "target_rows": len(df_target),
        "matched_with_diff": len(diff_result.get("matched_with_diff", [])),
        "source_only": len(diff_result.get("source_only", [])),
        "target_only": len(diff_result.get("target_only", [])),
        "matched_exact": len(diff_result.get("matched_exact", [])),
        "output_file": output_path,
        "download_url": download_url,
        "message": "；".join(message_parts)
    }
    
    # 添加过滤统计详情（可选）
    if source_filter_stats:
        result["source_filter_stats"] = {
            "original_count": source_filter_stats["original_count"],
            "filtered_count": source_filter_stats["filtered_count"],
            "removed_count": source_filter_stats["removed_count"],
            "filter_rate": source_filter_stats["filter_rate"]
        }
    if target_filter_stats:
        result["target_filter_stats"] = {
            "original_count": target_filter_stats["original_count"],
            "filtered_count": target_filter_stats["filtered_count"],
            "removed_count": target_filter_stats["removed_count"],
            "filter_rate": target_filter_stats["filter_rate"]
        }
    
    return result


def _find_file_by_identification(
    identification: dict,
    table_file_map: dict[str, str],
    rule_id: str,
    file_type: str
) -> Optional[str]:
    """根据识别规则查找文件"""
    match_by = identification.get("match_by", "table_name")
    match_value = identification.get("match_value", "")
    match_strategy = identification.get("match_strategy", "exact")
    
    if not match_value:
        logger.warning(f"[recon] [{rule_id}] {file_type} 文件 match_value 未配置")
        return None
    
    if match_by == "table_name":
        if match_strategy == "exact":
            return table_file_map.get(match_value)
        elif match_strategy == "contains":
            for table_name, file_path in table_file_map.items():
                if match_value in table_name:
                    return file_path
        elif match_strategy == "startswith":
            for table_name, file_path in table_file_map.items():
                if table_name.startswith(match_value):
                    return file_path
    
    logger.warning(f"[recon] [{rule_id}] 未找到匹配的 {file_type} 文件: {match_value}")
    return None


def _apply_column_mapping(df: pd.DataFrame, column_mapping: dict) -> pd.DataFrame:
    """应用列名映射"""
    mappings = column_mapping.get("mappings", {})
    if not mappings:
        return df
    
    # 构建重命名字典（source_col -> target_col）
    rename_dict = {}
    for source_col, target_col in mappings.items():
        if source_col in df.columns and source_col != target_col:
            rename_dict[source_col] = target_col
    
    if rename_dict:
        df = df.rename(columns=rename_dict)
    
    return df


def _apply_aggregation(
    df: pd.DataFrame,
    aggregation_config: dict,
    rule_id: str,
    file_type: str
) -> pd.DataFrame:
    """应用分组聚合"""
    group_by = aggregation_config.get("group_by", [])
    aggregations = aggregation_config.get("aggregations", [])
    
    if not group_by or not aggregations:
        return df
    
    # 检查 group_by 列是否存在
    missing_cols = [col for col in group_by if col not in df.columns]
    if missing_cols:
        logger.warning(f"[recon] [{rule_id}] {file_type} 缺少分组列: {missing_cols}")
        return df
    
    # 构建聚合字典
    agg_dict = {}
    for agg in aggregations:
        col = agg.get("column")
        func = agg.get("function", "sum")
        if col in df.columns:
            agg_dict[col] = func
    
    if not agg_dict:
        return df
    
    try:
        grouped = df.groupby(group_by, as_index=False).agg(agg_dict)
        logger.info(f"[recon] [{rule_id}] {file_type} 聚合后 {len(grouped)} 行")
        return grouped
    except Exception as e:
        logger.error(f"[recon] [{rule_id}] {file_type} 聚合失败: {e}")
        return df


def _apply_key_transformations(
    df: pd.DataFrame,
    key_column: str,
    transformations: dict,
    file_type: str,
    rule_id: str
) -> pd.DataFrame:
    """
    应用关键列的数据清洗转换
    
    支持的转换操作（按执行顺序）：
    1. regex_extract: 使用正则表达式提取匹配内容
    2. regex_replace: 使用正则表达式替换匹配内容
    3. strip_prefix: 去除前缀字符串
    4. strip_suffix: 去除后缀字符串
    5. strip_whitespace: 去除首尾空白字符
    6. lowercase: 转换为小写
    
    Args:
        df: DataFrame
        key_column: 关键列名
        transformations: 转换配置
        file_type: "source" 或 "target"
        rule_id: 规则ID
    
    Returns:
        转换后的 DataFrame
    """
    if key_column not in df.columns:
        return df
    
    trans_config = transformations.get(file_type, {})
    if not trans_config:
        return df
    
    original_values = df[key_column].astype(str)
    transformed_values = original_values
    
    # 1. 正则表达式提取 - 提取匹配指定模式的内容
    regex_extract = trans_config.get("regex_extract")
    if regex_extract:
        try:
            extracted = transformed_values.str.extract(regex_extract, expand=False)
            # 如果结果是DataFrame（有多个捕获组），取第一个非空列
            if isinstance(extracted, pd.DataFrame):
                for col in extracted.columns:
                    if extracted[col].notna().any():
                        extracted = extracted[col]
                        break
            # 填充未匹配的值（保持原值）
            transformed_values = extracted.fillna(transformed_values)
            matched_count = extracted.notna().sum()
            logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 正则提取 '{regex_extract}' 匹配 {matched_count} 个值")
        except Exception as e:
            logger.warning(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 正则提取失败: {e}")
    
    # 2. 正则表达式替换 - 替换匹配的内容
    regex_replace = trans_config.get("regex_replace")
    if regex_replace:
        pattern = regex_replace.get("pattern")
        replacement = regex_replace.get("replacement", "")
        if pattern:
            try:
                transformed_values = transformed_values.str.replace(pattern, replacement, regex=True)
                logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 正则替换 '{pattern}' -> '{replacement}'")
            except Exception as e:
                logger.warning(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 正则替换失败: {e}")
    
    # 3. 去除前缀
    strip_prefix = trans_config.get("strip_prefix")
    if strip_prefix:
        transformed_values = transformed_values.str.lstrip(strip_prefix)
        logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 去除前缀 '{strip_prefix}'")
    
    # 4. 去除后缀
    strip_suffix = trans_config.get("strip_suffix")
    if strip_suffix:
        transformed_values = transformed_values.str.removesuffix(strip_suffix)
        logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 去除后缀 '{strip_suffix}'")
    
    # 5. 去除空白字符
    if trans_config.get("strip_whitespace", False):
        transformed_values = transformed_values.str.strip()
        logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 去除首尾空白")
    
    # 6. 转换为小写
    if trans_config.get("lowercase", False):
        transformed_values = transformed_values.str.lower()
        logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 转换为小写")
    
    df[key_column] = transformed_values
    
    # 记录转换统计
    changed_count = (original_values != transformed_values).sum()
    if changed_count > 0:
        logger.info(f"[recon] [{rule_id}] {file_type} 列 '{key_column}' 共转换了 {changed_count} 个值")
    
    return df


def _execute_comparison(
    df_source: pd.DataFrame,
    df_target: pd.DataFrame,
    key_columns: list[str],
    compare_columns_config: list[dict],
    diff_analysis_config: dict,
    rule_id: str,
    key_columns_config: dict = None
) -> dict:
    """
    执行数据比较
    
    Returns:
        {
            "matched_with_diff": DataFrame,  # 匹配但有差异
            "source_only": DataFrame,        # 源文件独有
            "target_only": DataFrame,        # 目标文件独有
            "matched_exact": DataFrame       # 完全匹配
        }
    """
    result = {
        "matched_with_diff": pd.DataFrame(),
        "source_only": pd.DataFrame(),
        "target_only": pd.DataFrame(),
        "matched_exact": pd.DataFrame()
    }
    
    if not key_columns:
        logger.warning(f"[recon] [{rule_id}] 未配置关键列，无法执行比较")
        return result
    
    # 检查关键列是否存在（考虑 cross_file_mapping）
    cross_mapping = key_columns_config.get("cross_file_mapping", {}) if key_columns_config else {}
    if cross_mapping:
        # 使用 cross_file_mapping 中定义的列名进行检查
        source_key_col = cross_mapping.get("source_column")
        target_key_col = cross_mapping.get("target_column")
        source_missing = [source_key_col] if source_key_col and source_key_col not in df_source.columns else []
        target_missing = [target_key_col] if target_key_col and target_key_col not in df_target.columns else []
    else:
        # 使用 key_columns 列表进行检查
        source_missing = [col for col in key_columns if col not in df_source.columns]
        target_missing = [col for col in key_columns if col not in df_target.columns]
    
    if source_missing:
        logger.warning(f"[recon] [{rule_id}] 源文件缺少关键列: {source_missing}")
        return result
    if target_missing:
        logger.warning(f"[recon] [{rule_id}] 目标文件缺少关键列: {target_missing}")
        return result
    
    # 应用数据清洗转换（在添加前缀之前）
    if key_columns_config:
        transformations = key_columns_config.get("transformations", {})
        if transformations:
            # 根据 cross_file_mapping 确定源和目标的关键列
            cross_mapping = key_columns_config.get("cross_file_mapping", {})
            source_key_col = cross_mapping.get("source_column", key_columns[0] if key_columns else None)
            target_key_col = cross_mapping.get("target_column", key_columns[-1] if key_columns else None)
            
            if source_key_col and source_key_col in df_source.columns:
                df_source = _apply_key_transformations(
                    df_source.copy(), source_key_col, transformations, "source", rule_id
                )
            if target_key_col and target_key_col in df_target.columns:
                df_target = _apply_key_transformations(
                    df_target.copy(), target_key_col, transformations, "target", rule_id
                )
    
    # 添加前缀以区分来源
    df_source_prefixed = df_source.add_prefix("source_")
    df_target_prefixed = df_target.add_prefix("target_")
    
    # 确定用于合并的关键列（考虑 cross_file_mapping）
    cross_mapping = key_columns_config.get("cross_file_mapping", {}) if key_columns_config else {}
    if cross_mapping:
        # 使用 cross_file_mapping 中定义的列名
        source_key_col = cross_mapping.get("source_column", key_columns[0] if key_columns else None)
        target_key_col = cross_mapping.get("target_column", key_columns[-1] if key_columns else None)
        source_key_cols = [f"source_{source_key_col}"] if source_key_col else []
        target_key_cols = [f"target_{target_key_col}"] if target_key_col else []
    else:
        # 使用 key_columns 列表
        source_key_cols = [f"source_{col}" for col in key_columns]
        target_key_cols = [f"target_{col}" for col in key_columns]
    
    # 创建合并键（处理 NaN 值）
    def _create_merge_key(df, cols):
        """创建合并键，处理 NaN 值"""
        # 将每列转换为字符串，并用空字符串填充 NaN
        str_cols = df[cols].astype(str).fillna('')
        # 使用 join 连接各列
        return str_cols.agg("||".join, axis=1)
    
    df_source_prefixed["_merge_key"] = _create_merge_key(df_source_prefixed, source_key_cols)
    df_target_prefixed["_merge_key"] = _create_merge_key(df_target_prefixed, target_key_cols)
    
    # 执行外连接
    merged = pd.merge(
        df_source_prefixed,
        df_target_prefixed,
        on="_merge_key",
        how="outer",
        indicator=True
    )
    
    # 分类记录
    source_only = merged[merged["_merge"] == "left_only"].drop(columns=["_merge_key", "_merge"])
    target_only = merged[merged["_merge"] == "right_only"].drop(columns=["_merge_key", "_merge"])
    both = merged[merged["_merge"] == "both"].drop(columns=["_merge_key", "_merge"])
    
    result["source_only"] = source_only
    result["target_only"] = target_only
    
    logger.info(f"[recon] [{rule_id}] 源独有: {len(source_only)}, 目标独有: {len(target_only)}, 匹配: {len(both)}")
    
    if len(both) == 0:
        return result
    
    # 比较匹配记录中的数值差异
    if not compare_columns_config:
        result["matched_exact"] = both
        return result
    
    # 计算差异
    has_diff_mask = pd.Series([False] * len(both), index=both.index)
    
    for cfg in compare_columns_config:
        col = cfg.get("column")
        if not col:
            continue
        
        # 优先使用 source_column/target_column 配置，否则使用 column 字段
        source_col_name = cfg.get("source_column", col)
        target_col_name = cfg.get("target_column", col)
        
        source_col = f"source_{source_col_name}"
        target_col = f"target_{target_col_name}"
        
        if source_col not in both.columns or target_col not in both.columns:
            logger.warning(f"[recon] [{rule_id}] 比较列不存在: {source_col} 或 {target_col}")
            continue
        
        tolerance = cfg.get("tolerance", 0)
        tolerance_type = cfg.get("tolerance_type", "absolute")
        
        # 转换为数值
        source_vals = pd.to_numeric(both[source_col], errors="coerce").fillna(0)
        target_vals = pd.to_numeric(both[target_col], errors="coerce").fillna(0)
        
        diff = (source_vals - target_vals).abs()
        
        if tolerance_type == "absolute":
            col_has_diff = diff > tolerance
        elif tolerance_type == "relative":
            col_has_diff = (diff / target_vals.abs().replace(0, 1)) > tolerance
        else:
            col_has_diff = diff > 0
        
        has_diff_mask = has_diff_mask | col_has_diff
        
        # 添加差异列（使用配置中的 column 作为列名）
        both[f"diff_{col}"] = source_vals - target_vals
        
        logger.info(f"[recon] [{rule_id}] 比较列 {col}: {source_col_name} vs {target_col_name}, 差异 {col_has_diff.sum()} 条")
    
    result["matched_with_diff"] = both[has_diff_mask]
    result["matched_exact"] = both[~has_diff_mask]
    
    logger.info(f"[recon] [{rule_id}] 有差异: {len(result['matched_with_diff'])}, 完全匹配: {len(result['matched_exact'])}")
    
    return result


def _write_recon_result(
    diff_result: dict,
    output_dir: str,
    output_config: dict,
    rule_id: str,
    rule_name: str,
    key_columns_config: dict = None,
    compare_columns_config: list = None
) -> str:
    """写出核对结果，并对关键列添加颜色标记"""
    from openpyxl.styles import PatternFill, Font
    from openpyxl.utils import get_column_letter
    
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_rule_name = re.sub(r'[\\/:*?"<>|]', "_", rule_name)
    filename = f"{safe_rule_name}_核对结果_{timestamp}.xlsx"
    output_path = str(Path(output_dir) / filename)
    
    sheets_config = output_config.get("sheets", {})
    
    # 收集需要标记的列
    marked_columns = _get_marked_columns(key_columns_config, compare_columns_config)
    
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # 汇总表
        if sheets_config.get("summary", {}).get("enabled", True):
            summary_data = {
                "项目": ["规则ID", "规则名称", "差异记录数", "源文件独有数", "目标文件独有数", "完全匹配数", "生成时间"],
                "值": [
                    rule_id,
                    rule_name,
                    len(diff_result.get("matched_with_diff", [])),
                    len(diff_result.get("source_only", [])),
                    len(diff_result.get("target_only", [])),
                    len(diff_result.get("matched_exact", [])),
                    timestamp
                ]
            }
            pd.DataFrame(summary_data).to_excel(
                writer,
                sheet_name=sheets_config.get("summary", {}).get("name", "核对汇总"),
                index=False
            )
        
        # 差异记录
        sheet_name_matched_with_diff = sheets_config.get("matched_with_diff", {}).get("name", "差异记录")
        if sheets_config.get("matched_with_diff", {}).get("enabled", True):
            df = diff_result.get("matched_with_diff", pd.DataFrame())
            if len(df) > 0:
                df.to_excel(
                    writer,
                    sheet_name=sheet_name_matched_with_diff,
                    index=False
                )
        
        # 源文件独有
        sheet_name_source_only = sheets_config.get("source_only", {}).get("name", "源文件独有")
        if sheets_config.get("source_only", {}).get("enabled", True):
            df = diff_result.get("source_only", pd.DataFrame())
            if len(df) > 0:
                df.to_excel(
                    writer,
                    sheet_name=sheet_name_source_only,
                    index=False
                )
        
        # 目标文件独有
        sheet_name_target_only = sheets_config.get("target_only", {}).get("name", "目标文件独有")
        if sheets_config.get("target_only", {}).get("enabled", True):
            df = diff_result.get("target_only", pd.DataFrame())
            if len(df) > 0:
                df.to_excel(
                    writer,
                    sheet_name=sheet_name_target_only,
                    index=False
                )
        
        # 应用颜色标记
        workbook = writer.book
        
        # 定义颜色
        mapping_fill = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")  # 黄色 - mapping列
        compare_fill = PatternFill(start_color="B4C7E7", end_color="B4C7E7", fill_type="solid")  # 蓝色 - 比对列
        diff_fill = PatternFill(start_color="F4B084", end_color="F4B084", fill_type="solid")    # 橙色 - 差异列
        header_font = Font(bold=True)
        
        # 标记差异记录sheet
        if sheet_name_matched_with_diff in workbook.sheetnames:
            _apply_column_highlighting(
                workbook[sheet_name_matched_with_diff],
                marked_columns,
                mapping_fill,
                compare_fill,
                diff_fill,
                header_font
            )
        
        # 标记源文件独有sheet
        if sheet_name_source_only in workbook.sheetnames:
            _apply_column_highlighting(
                workbook[sheet_name_source_only],
                marked_columns,
                mapping_fill,
                compare_fill,
                diff_fill,
                header_font
            )
        
        # 标记目标文件独有sheet
        if sheet_name_target_only in workbook.sheetnames:
            _apply_column_highlighting(
                workbook[sheet_name_target_only],
                marked_columns,
                mapping_fill,
                compare_fill,
                diff_fill,
                header_font
            )
    
    logger.info(f"[recon] [{rule_id}] 结果已输出: {output_path}")
    return output_path


def _get_marked_columns(key_columns_config: dict, compare_columns_config: list) -> dict:
    """
    获取需要标记的列信息
    
    Returns:
        {
            "mapping_source": ["source_sup订单号", ...],  # 黄色 - source mapping列
            "mapping_target": ["target_第三方订单号", ...],  # 黄色 - target mapping列
            "compare_source": ["source_发生-", ...],  # 蓝色 - source 比对列
            "compare_target": ["target_合作方分销收入", ...],  # 蓝色 - target 比对列
            "diff": ["diff_发生减", ...]  # 橙色 - 差异列
        }
    """
    marked = {
        "mapping_source": [],
        "mapping_target": [],
        "compare_source": [],
        "compare_target": [],
        "diff": []
    }
    
    if key_columns_config:
        # 处理 cross_file_mapping
        cross_mapping = key_columns_config.get("cross_file_mapping", {})
        if cross_mapping:
            # 单映射
            source_col = cross_mapping.get("source_column")
            target_col = cross_mapping.get("target_column")
            if source_col:
                marked["mapping_source"].append(f"source_{source_col}")
            if target_col:
                marked["mapping_target"].append(f"target_{target_col}")
        
        # 处理多映射（数组格式）
        cross_mappings = key_columns_config.get("cross_file_mappings", [])
        for mapping in cross_mappings:
            source_col = mapping.get("source_column")
            target_col = mapping.get("target_column")
            if source_col:
                marked["mapping_source"].append(f"source_{source_col}")
            if target_col:
                marked["mapping_target"].append(f"target_{target_col}")
    
    if compare_columns_config:
        for cfg in compare_columns_config:
            col = cfg.get("column")
            source_col = cfg.get("source_column", col)
            target_col = cfg.get("target_column", col)
            
            if source_col:
                marked["compare_source"].append(f"source_{source_col}")
            if target_col:
                marked["compare_target"].append(f"target_{target_col}")
            if col:
                marked["diff"].append(f"diff_{col}")
    
    return marked


def _apply_column_highlighting(
    worksheet,
    marked_columns: dict,
    mapping_fill: PatternFill,
    compare_fill: PatternFill,
    diff_fill: PatternFill,
    header_font: Font
):
    """对 worksheet 的指定列应用颜色标记"""
    if not worksheet or worksheet.max_row == 0:
        return
    
    # 获取表头行
    header_row = 1
    header_map = {}
    for col_idx in range(1, worksheet.max_column + 1):
        cell = worksheet.cell(row=header_row, column=col_idx)
        header_map[cell.value] = col_idx
        # 表头加粗
        cell.font = header_font
    
    # 标记 mapping 列（黄色）
    for col_name in marked_columns.get("mapping_source", []) + marked_columns.get("mapping_target", []):
        if col_name in header_map:
            col_idx = header_map[col_name]
            for row_idx in range(header_row, worksheet.max_row + 1):
                worksheet.cell(row=row_idx, column=col_idx).fill = mapping_fill
    
    # 标记比对列（蓝色）
    for col_name in marked_columns.get("compare_source", []) + marked_columns.get("compare_target", []):
        if col_name in header_map:
            col_idx = header_map[col_name]
            for row_idx in range(header_row, worksheet.max_row + 1):
                worksheet.cell(row=row_idx, column=col_idx).fill = compare_fill
    
    # 标记差异列（橙色）
    for col_name in marked_columns.get("diff", []):
        if col_name in header_map:
            col_idx = header_map[col_name]
            for row_idx in range(header_row, worksheet.max_row + 1):
                worksheet.cell(row=row_idx, column=col_idx).fill = diff_fill


# ════════════════════════════════════════════════════════════════════════════
# 文件读取
# ════════════════════════════════════════════════════════════════════════════

def _read_file_as_df(file_path: str) -> pd.DataFrame:
    """读取 CSV 或 Excel 文件为 DataFrame"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    ext = path.suffix.lower()
    if ext == ".csv":
        try:
            return pd.read_csv(file_path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            import chardet
            with open(file_path, "rb") as f:
                enc = chardet.detect(f.read()).get("encoding", "gbk")
            return pd.read_csv(file_path, encoding=enc)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")

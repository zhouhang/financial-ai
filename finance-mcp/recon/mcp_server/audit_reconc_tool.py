"""
审计核对 MCP 工具模块

根据 audit_reconc.json 规则定义，执行源文件与目标文件的数据比对与差异分析。

主要功能：
1. 加载审计核对规则（从 bus_rules 表，rule_code='audio_reconc'）
2. 根据规则识别源文件和目标文件
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

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
# 常量定义
# ════════════════════════════════════════════════════════════════════════════

AUDIT_RULE_CODE = "audio_reconc"


# ════════════════════════════════════════════════════════════════════════════
# MCP 工具定义
# ════════════════════════════════════════════════════════════════════════════

def create_audit_reconc_tools() -> list[Tool]:
    """创建审计核对 MCP 工具列表"""
    return [
        Tool(
            name="audit_reconc_execute",
            description=(
                "执行审计核对：根据规则对源文件与目标文件进行数据比对，"
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
                    "rule_id": {
                        "type": "string",
                        "description": "要执行的审计核对规则 ID（如 AUDIT_RECONC_001），不指定则执行所有匹配的规则"
                    },
                    "output_dir": {
                        "type": "string",
                        "description": "核对结果输出目录"
                    }
                },
                "required": ["validated_files", "output_dir"]
            }
        ),
        Tool(
            name="audit_reconc_list_rules",
            description="列出所有可用的审计核对规则",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


async def handle_audit_reconc_tool_call(name: str, arguments: dict) -> dict:
    """处理审计核对工具调用"""
    try:
        if name == "audit_reconc_execute":
            return await _handle_audit_reconc_execute(arguments)
        elif name == "audit_reconc_list_rules":
            return await _handle_audit_reconc_list_rules(arguments)
        else:
            return {"success": False, "error": f"未知的工具: {name}"}
    except Exception as e:
        logger.error(f"审计核对工具调用失败 [{name}]: {e}", exc_info=True)
        return {"success": False, "error": f"工具调用失败: {str(e)}"}


# ════════════════════════════════════════════════════════════════════════════
# 规则加载
# ════════════════════════════════════════════════════════════════════════════

def load_audit_rules_from_db() -> Optional[dict]:
    """
    从 bus_rules 表加载审计核对规则配置
    
    Returns:
        audit_reconc.json 的完整内容，未找到返回 None
    """
    try:
        from db_config import get_db_connection
        
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT rule FROM bus_rules WHERE rule_code = %s LIMIT 1",
                    (AUDIT_RULE_CODE,)
                )
                row = cur.fetchone()
                if row is None:
                    logger.warning(f"[audit_reconc] 未找到 rule_code='{AUDIT_RULE_CODE}' 的审计规则")
                    return None
                
                rule_content = row[0]
                if isinstance(rule_content, str):
                    rule_content = json.loads(rule_content)
                
                rules_count = len(rule_content.get("reconciliation_rules", []))
                logger.info(f"[audit_reconc] 成功加载审计核对规则，共 {rules_count} 条")
                return rule_content
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"[audit_reconc] 加载审计规则失败: {e}")
        return None


def find_audit_rule_by_id(rules_config: dict, rule_id: str) -> Optional[dict]:
    """根据 rule_id 查找规则"""
    for rule in rules_config.get("reconciliation_rules", []):
        if rule.get("rule_id") == rule_id:
            return rule
    return None


# ════════════════════════════════════════════════════════════════════════════
# 工具处理函数
# ════════════════════════════════════════════════════════════════════════════

async def _handle_audit_reconc_list_rules(arguments: dict) -> dict:
    """列出所有审计核对规则"""
    rules_config = load_audit_rules_from_db()
    if rules_config is None:
        return {"success": False, "error": "未找到审计核对规则配置"}
    
    rules = rules_config.get("reconciliation_rules", [])
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
        "count": len(rule_list),
        "rules": rule_list
    }


async def _handle_audit_reconc_execute(arguments: dict) -> dict:
    """执行审计核对"""
    validated_files = arguments.get("validated_files", [])
    output_dir = arguments.get("output_dir", "")
    rule_id = arguments.get("rule_id")
    
    if not validated_files:
        return {"success": False, "error": "validated_files 不能为空"}
    if not output_dir:
        return {"success": False, "error": "output_dir 不能为空"}
    
    # 确保输出目录存在
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 加载规则
    rules_config = load_audit_rules_from_db()
    if rules_config is None:
        return {"success": False, "error": "未找到审计核对规则配置"}
    
    # 构建 table_name -> file_path 映射
    table_file_map: dict[str, str] = {}
    for item in validated_files:
        table_name = item.get("table_name", "")
        file_path = item.get("file_path", "")
        if table_name and file_path:
            table_file_map[table_name] = file_path
    
    logger.info(f"[audit_reconc] 文件映射: {list(table_file_map.keys())}")
    
    # 确定要执行的规则
    rules = rules_config.get("reconciliation_rules", [])
    if rule_id:
        target_rule = find_audit_rule_by_id(rules_config, rule_id)
        if target_rule is None:
            return {"success": False, "error": f"未找到 rule_id='{rule_id}' 的规则"}
        rules = [target_rule]
    
    # 执行核对
    results = []
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        
        result = execute_single_audit(rule, table_file_map, output_dir)
        results.append(result)
    
    success_count = sum(1 for r in results if r.get("success"))
    
    return {
        "success": True,
        "total_rules": len(results),
        "success_count": success_count,
        "results": results
    }


# ════════════════════════════════════════════════════════════════════════════
# 核对执行逻辑
# ════════════════════════════════════════════════════════════════════════════

def execute_single_audit(
    rule: dict,
    table_file_map: dict[str, str],
    output_dir: str
) -> dict:
    """
    执行单个审计核对规则
    
    Args:
        rule: 审计规则配置
        table_file_map: table_name -> file_path 映射
        output_dir: 输出目录
    
    Returns:
        核对结果
    """
    rule_id = rule.get("rule_id", "UNKNOWN")
    rule_name = rule.get("rule_name", "未命名规则")
    
    logger.info(f"[audit_reconc] [{rule_id}] 开始执行: {rule_name}")
    
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
    
    logger.info(f"[audit_reconc] [{rule_id}] 源文件: {source_path}")
    logger.info(f"[audit_reconc] [{rule_id}] 目标文件: {target_path}")
    
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
    
    logger.info(f"[audit_reconc] [{rule_id}] 源文件 {len(df_source)} 行，目标文件 {len(df_target)} 行")
    
    # 3. 应用列映射
    df_source = _apply_column_mapping(df_source, source_file_config.get("column_mapping", {}))
    df_target = _apply_column_mapping(df_target, target_file_config.get("column_mapping", {}))
    
    # 4. 获取核对配置
    recon_config = rule.get("reconciliation_config", {})
    key_columns = recon_config.get("key_columns", {}).get("columns", [])
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
        rule_id=rule_id
    )
    
    # 7. 输出结果
    output_config = rule.get("output", {})
    output_path = _write_audit_result(
        diff_result=diff_result,
        output_dir=output_dir,
        output_config=output_config,
        rule_id=rule_id,
        rule_name=rule_name
    )
    
    return {
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
        "message": f"核对完成：差异 {len(diff_result.get('matched_with_diff', []))} 条，"
                   f"源独有 {len(diff_result.get('source_only', []))} 条，"
                   f"目标独有 {len(diff_result.get('target_only', []))} 条"
    }


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
        logger.warning(f"[audit_reconc] [{rule_id}] {file_type} 文件 match_value 未配置")
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
    
    logger.warning(f"[audit_reconc] [{rule_id}] 未找到匹配的 {file_type} 文件: {match_value}")
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
        logger.warning(f"[audit_reconc] [{rule_id}] {file_type} 缺少分组列: {missing_cols}")
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
        logger.info(f"[audit_reconc] [{rule_id}] {file_type} 聚合后 {len(grouped)} 行")
        return grouped
    except Exception as e:
        logger.error(f"[audit_reconc] [{rule_id}] {file_type} 聚合失败: {e}")
        return df


def _execute_comparison(
    df_source: pd.DataFrame,
    df_target: pd.DataFrame,
    key_columns: list[str],
    compare_columns_config: list[dict],
    diff_analysis_config: dict,
    rule_id: str
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
        logger.warning(f"[audit_reconc] [{rule_id}] 未配置关键列，无法执行比较")
        return result
    
    # 检查关键列是否存在
    source_missing = [col for col in key_columns if col not in df_source.columns]
    target_missing = [col for col in key_columns if col not in df_target.columns]
    
    if source_missing:
        logger.warning(f"[audit_reconc] [{rule_id}] 源文件缺少关键列: {source_missing}")
        return result
    if target_missing:
        logger.warning(f"[audit_reconc] [{rule_id}] 目标文件缺少关键列: {target_missing}")
        return result
    
    # 添加前缀以区分来源
    df_source_prefixed = df_source.add_prefix("source_")
    df_target_prefixed = df_target.add_prefix("target_")
    
    # 重命名关键列用于合并
    source_key_cols = [f"source_{col}" for col in key_columns]
    target_key_cols = [f"target_{col}" for col in key_columns]
    
    # 创建合并键
    df_source_prefixed["_merge_key"] = df_source_prefixed[source_key_cols].astype(str).agg("||".join, axis=1)
    df_target_prefixed["_merge_key"] = df_target_prefixed[target_key_cols].astype(str).agg("||".join, axis=1)
    
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
    
    logger.info(f"[audit_reconc] [{rule_id}] 源独有: {len(source_only)}, 目标独有: {len(target_only)}, 匹配: {len(both)}")
    
    if len(both) == 0:
        return result
    
    # 比较匹配记录中的数值差异
    compare_columns = [cfg.get("column") for cfg in compare_columns_config if cfg.get("column")]
    
    if not compare_columns:
        result["matched_exact"] = both
        return result
    
    # 计算差异
    has_diff_mask = pd.Series([False] * len(both), index=both.index)
    
    for cfg in compare_columns_config:
        col = cfg.get("column")
        if not col:
            continue
        
        source_col = f"source_{col}"
        target_col = f"target_{col}"
        
        if source_col not in both.columns or target_col not in both.columns:
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
        
        # 添加差异列
        both[f"diff_{col}"] = source_vals - target_vals
    
    result["matched_with_diff"] = both[has_diff_mask]
    result["matched_exact"] = both[~has_diff_mask]
    
    logger.info(f"[audit_reconc] [{rule_id}] 有差异: {len(result['matched_with_diff'])}, 完全匹配: {len(result['matched_exact'])}")
    
    return result


def _write_audit_result(
    diff_result: dict,
    output_dir: str,
    output_config: dict,
    rule_id: str,
    rule_name: str
) -> str:
    """写出审计核对结果"""
    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_rule_name = re.sub(r'[\\/:*?"<>|]', "_", rule_name)
    filename = f"{safe_rule_name}_核对结果_{timestamp}.xlsx"
    output_path = str(Path(output_dir) / filename)
    
    sheets_config = output_config.get("sheets", {})
    
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
        if sheets_config.get("matched_with_diff", {}).get("enabled", True):
            df = diff_result.get("matched_with_diff", pd.DataFrame())
            if len(df) > 0:
                df.to_excel(
                    writer,
                    sheet_name=sheets_config.get("matched_with_diff", {}).get("name", "差异记录"),
                    index=False
                )
        
        # 源文件独有
        if sheets_config.get("source_only", {}).get("enabled", True):
            df = diff_result.get("source_only", pd.DataFrame())
            if len(df) > 0:
                df.to_excel(
                    writer,
                    sheet_name=sheets_config.get("source_only", {}).get("name", "源文件独有"),
                    index=False
                )
        
        # 目标文件独有
        if sheets_config.get("target_only", {}).get("enabled", True):
            df = diff_result.get("target_only", pd.DataFrame())
            if len(df) > 0:
                df.to_excel(
                    writer,
                    sheet_name=sheets_config.get("target_only", {}).get("name", "目标文件独有"),
                    index=False
                )
    
    logger.info(f"[audit_reconc] [{rule_id}] 结果已输出: {output_path}")
    return output_path


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

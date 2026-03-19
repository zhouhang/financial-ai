"""
数据整理规则 Merge 操作模块

支持两种 merge 模式：

1. 单规则 merge（原有模式）：
   根据 sync_rule.json 中各规则的 merge 节点配置，将新生成文件与已上传的目标文件进行合并

2. 批量文件 merge（新增模式）：
   根据 merge.json 配置（存储在 rule_detail 表，rule_code='verif_recog_merge'），
   将文件校验阶段识别出的同类表（相同 table_name）的多个文件合并为一个文件

配置说明：
  merge.json 格式：
    merge_rules[].table_name     : 表名，用于匹配文件校验阶段关联的 table_name
    merge_rules[].merge_type     : 合并类型，append_rows / aggregate_by_key
    merge_rules[].merge_config   : 合并配置
    merge_rules[].output         : 输出配置
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from security_utils import PROC_OUTPUT_ROOT, UPLOAD_ROOT, resolve_path_under_roots
from tools.rule_schema import load_and_validate_rule

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 批量文件合并（基于 merge.json 配置）
# ════════════════════════════════════════════════════════════════════════════

def load_merge_rules_from_bus(rule_code: str) -> Optional[dict]:
    """
    从 rule_detail 表加载 merge.json 配置

    使用 tools.rules 中的 get_rule 函数，复用缓存机制。

    Args:
        rule_code: 规则编码，用于从 rule_detail 表中查找

    Returns:
        merge.json 的完整内容，如果未找到则返回 None
    """
    try:
        validation_result = load_and_validate_rule(rule_code, expected_kind="merge")
        if not validation_result.get("success"):
            logger.warning(f"[merge_rule] merge 规则校验失败: {validation_result}")
            return None
        rule_content = validation_result.get("rule", {})

        logger.info(f"[merge_rule] 成功加载 rule_code='{rule_code}' 的 merge 规则，共 {len(rule_content.get('merge_rules', []))} 条")
        return rule_content
    except Exception as e:
        logger.error(f"[merge_rule] 加载 rule_code='{rule_code}' 的 merge 规则失败: {e}")
        return None


def find_merge_rule_by_table_name(merge_rules_config: dict, table_name: str) -> Optional[dict]:
    """
    根据 table_name 查找匹配的 merge 规则
    
    Args:
        merge_rules_config: merge.json 的完整内容
        table_name: 要匹配的表名
    
    Returns:
        匹配的 merge 规则配置，未找到返回 None
    """
    merge_rules = merge_rules_config.get("merge_rules", [])
    
    for rule in merge_rules:
        if not rule.get("enabled", True):
            continue
        
        rule_table_name = rule.get("table_name", "")
        if rule_table_name == table_name:
            logger.info(f"[merge_rule] 找到匹配的 merge 规则: rule_id={rule.get('rule_id')}, table_name={table_name}")
            return rule
    
    return None


def execute_batch_merge(
    validated_files: list[dict],
    output_dir: str,
    merge_rules_config: Optional[dict] = None,
    rule_code: Optional[str] = None,
) -> dict:
    """
    批量文件合并：根据文件校验结果，将相同 table_name 的文件合并

    Args:
        validated_files: 文件校验结果列表，每个元素包含:
            - file_path: 文件路径
            - table_name: 文件校验阶段关联的表名
        output_dir: 输出目录
        merge_rules_config: merge.json 配置，如果不传则从数据库加载
        rule_code: 规则编码，当 merge_rules_config 为 None 时用于从数据库加载

    Returns:
        {
            "success": True/False,
            "merged_files": [  # 合并生成的文件列表
                {
                    "table_name": str,
                    "merged_file_path": str,
                    "source_files": [str],  # 参与合并的源文件
                    "total_rows": int,
                    "message": str
                }
            ],
            "skipped": [  # 未合并的表名及原因
                {"table_name": str, "reason": str}
            ],
            "message": str
        }
    """
    # 加载 merge 规则
    if merge_rules_config is None:
        if rule_code is None:
            return {
                "success": False,
                "merged_files": [],
                "skipped": [],
                "message": "未提供 merge_rules_config 且未指定 rule_code，无法加载 merge 规则"
            }
        merge_rules_config = load_merge_rules_from_bus(rule_code)
    
    if merge_rules_config is None:
        return {
            "success": False,
            "merged_files": [],
            "skipped": [],
            "message": "未找到 merge 规则配置"
        }
    
    # 按 table_name 分组文件
    table_files_map: dict[str, list[str]] = {}
    for item in validated_files:
        table_name = item.get("table_name", "")
        file_path = item.get("file_path", "")
        if table_name and file_path:
            if table_name not in table_files_map:
                table_files_map[table_name] = []
            table_files_map[table_name].append(file_path)
    
    logger.info(f"[merge_rule] 文件分组结果: {', '.join([f'{k}: {len(v)}个文件' for k, v in table_files_map.items()])}")
    
    merged_files = []
    skipped = []
    
    for table_name, file_paths in table_files_map.items():
        # 查找匹配的 merge 规则
        merge_rule = find_merge_rule_by_table_name(merge_rules_config, table_name)
        
        if merge_rule is None:
            skipped.append({
                "table_name": table_name,
                "reason": f"未找到 table_name='{table_name}' 的 merge 规则"
            })
            continue
        
        if len(file_paths) < 2:
            skipped.append({
                "table_name": table_name,
                "reason": f"只有 {len(file_paths)} 个文件，无需合并"
            })
            continue
        
        # 执行合并
        result = _execute_multi_file_merge(
            file_paths=file_paths,
            merge_rule=merge_rule,
            output_dir=output_dir,
            table_name=table_name
        )
        
        if result["success"]:
            merged_files.append({
                "table_name": table_name,
                "merged_file_path": result["merged_file_path"],
                "source_files": file_paths,
                "total_rows": result["total_rows"],
                "message": result["message"]
            })
        else:
            skipped.append({
                "table_name": table_name,
                "reason": result["message"]
            })
    
    return {
        "success": True,
        "merged_files": merged_files,
        "skipped": skipped,
        "message": f"合并完成：成功 {len(merged_files)} 个，跳过 {len(skipped)} 个"
    }


def _execute_multi_file_merge(
    file_paths: list[str],
    merge_rule: dict,
    output_dir: str,
    table_name: str,
) -> dict:
    """
    执行多文件合并
    
    Args:
        file_paths: 要合并的文件路径列表
        merge_rule: merge 规则配置
        output_dir: 输出目录
        table_name: 表名
    
    Returns:
        {"success": bool, "merged_file_path": str, "total_rows": int, "message": str}
    """
    rule_id = merge_rule.get("rule_id", "UNKNOWN")
    merge_type = merge_rule.get("merge_type", "append_rows")
    merge_config = merge_rule.get("merge_config", {})
    output_config = merge_rule.get("output", {})
    
    logger.info(f"[merge_rule] [{rule_id}] 开始合并 {len(file_paths)} 个文件，合并类型: {merge_type}")
    
    # 读取所有文件
    dataframes = []
    for fp in file_paths:
        try:
            df = _read_file_as_df(fp)
            dataframes.append(df)
            logger.info(f"[merge_rule] [{rule_id}] 读取文件: {fp}, {len(df)} 行")
        except Exception as e:
            logger.error(f"[merge_rule] [{rule_id}] 读取文件失败: {fp}, {e}")
            return {
                "success": False,
                "merged_file_path": None,
                "total_rows": 0,
                "message": f"读取文件失败: {fp}, {e}"
            }
    
    if not dataframes:
        return {
            "success": False,
            "merged_file_path": None,
            "total_rows": 0,
            "message": "没有成功读取的文件"
        }
    
    # 执行合并
    if merge_type == "append_rows":
        merged_df = _merge_multiple_append_rows(dataframes, merge_config, rule_id)
    elif merge_type == "aggregate_by_key":
        merged_df = _merge_aggregate_by_key(dataframes, merge_config, rule_id)
    else:
        logger.warning(f"[merge_rule] [{rule_id}] 不支持的 merge_type='{merge_type}'，默认使用 append_rows")
        merged_df = _merge_multiple_append_rows(dataframes, merge_config, rule_id)
    
    # 写出合并结果
    file_format = output_config.get("format", "xlsx")
    merged_file_path = _write_batch_merged_file(
        df=merged_df,
        output_dir=output_dir,
        table_name=table_name,
        rule_id=rule_id,
        file_format=file_format
    )
    
    logger.info(f"[merge_rule] [{rule_id}] 合并完成，共 {len(merged_df)} 行，输出: {merged_file_path}")
    
    return {
        "success": True,
        "merged_file_path": merged_file_path,
        "total_rows": len(merged_df),
        "message": f"合并 {len(file_paths)} 个文件成功，共 {len(merged_df)} 行"
    }


def _merge_multiple_append_rows(
    dataframes: list[pd.DataFrame],
    merge_config: dict,
    rule_id: str,
) -> pd.DataFrame:
    """
    多文件追加行合并
    
    Args:
        dataframes: DataFrame 列表
        merge_config: 合并配置
        rule_id: 规则 ID
    
    Returns:
        合并后的 DataFrame
    """
    mismatch_policy = merge_config.get("column_mismatch_policy", {})
    col_policy = mismatch_policy.get("policy", "union_columns")
    fill_val = mismatch_policy.get("fill_missing_value", None)
    
    # 收集所有列
    all_columns = []
    for df in dataframes:
        for col in df.columns:
            if col not in all_columns:
                all_columns.append(col)
    
    logger.info(f"[merge_rule] [{rule_id}] 列并集共 {len(all_columns)} 列")
    
    # 补全各 DataFrame 的缺失列
    aligned_dfs = []
    for df in dataframes:
        df_copy = df.copy()
        for col in all_columns:
            if col not in df_copy.columns:
                df_copy[col] = fill_val
        aligned_dfs.append(df_copy[all_columns])
    
    # 拼接
    merged = pd.concat(aligned_dfs, ignore_index=True)
    
    # 去重
    dedup_config = merge_config.get("deduplication", {})
    if dedup_config.get("enabled", False):
        key_columns = dedup_config.get("key_columns", [])
        if key_columns:
            before_count = len(merged)
            merged = merged.drop_duplicates(subset=key_columns, keep="first")
            logger.info(f"[merge_rule] [{rule_id}] 去重（key={key_columns}）：{before_count} -> {len(merged)} 行")
    
    # 排序
    sort_config = merge_config.get("sort_after_merge", {})
    if sort_config.get("enabled", False):
        sort_columns = sort_config.get("sort_columns", [])
        ascending = sort_config.get("ascending", True)
        if sort_columns:
            merged = merged.sort_values(by=sort_columns, ascending=ascending)
            logger.info(f"[merge_rule] [{rule_id}] 排序：by={sort_columns}, ascending={ascending}")
    
    return merged


def _merge_aggregate_by_key(
    dataframes: list[pd.DataFrame],
    merge_config: dict,
    rule_id: str,
) -> pd.DataFrame:
    """
    按键聚合合并
    
    Args:
        dataframes: DataFrame 列表
        merge_config: 合并配置
        rule_id: 规则 ID
    
    Returns:
        合并后的 DataFrame
    """
    # 先追加合并
    mismatch_policy = merge_config.get("column_mismatch_policy", {})
    fill_val = mismatch_policy.get("fill_missing_value", None)
    
    all_columns = []
    for df in dataframes:
        for col in df.columns:
            if col not in all_columns:
                all_columns.append(col)
    
    aligned_dfs = []
    for df in dataframes:
        df_copy = df.copy()
        for col in all_columns:
            if col not in df_copy.columns:
                df_copy[col] = fill_val
        aligned_dfs.append(df_copy[all_columns])
    
    combined = pd.concat(aligned_dfs, ignore_index=True)
    
    # 获取键列和聚合规则
    key_columns_config = merge_config.get("key_columns", {})
    key_columns = key_columns_config.get("columns", [])
    
    if not key_columns:
        logger.warning(f"[merge_rule] [{rule_id}] aggregate_by_key 未配置 key_columns，退化为 append_rows")
        return combined
    
    aggregation_rules = merge_config.get("aggregation_rules", {})
    default_numeric_rule = aggregation_rules.get("default_numeric_rule", "sum")
    default_text_rule = aggregation_rules.get("default_text_rule", "first")
    column_rules = aggregation_rules.get("column_rules", [])
    
    # 构建聚合字典
    agg_dict = {}
    for col in combined.columns:
        if col in key_columns:
            continue
        
        # 查找自定义规则
        col_rule = None
        for cr in column_rules:
            if cr.get("column") == col:
                col_rule = cr
                break
        
        if col_rule:
            agg_type = col_rule.get("aggregation", "first")
            separator = col_rule.get("separator", "; ")
            distinct = col_rule.get("distinct", False)
            
            if agg_type == "concat":
                if distinct:
                    agg_dict[col] = lambda x, sep=separator: sep.join(str(v) for v in x.dropna().unique())
                else:
                    agg_dict[col] = lambda x, sep=separator: sep.join(str(v) for v in x.dropna())
            else:
                agg_dict[col] = agg_type
        else:
            # 根据数据类型使用默认规则
            if pd.api.types.is_numeric_dtype(combined[col]):
                agg_dict[col] = default_numeric_rule
            else:
                agg_dict[col] = default_text_rule
    
    logger.info(f"[merge_rule] [{rule_id}] 按 {key_columns} 聚合")
    
    try:
        merged = combined.groupby(key_columns, as_index=False).agg(agg_dict)
    except Exception as e:
        logger.error(f"[merge_rule] [{rule_id}] 聚合失败: {e}，退化为 append_rows")
        return combined
    
    return merged


def _write_batch_merged_file(
    df: pd.DataFrame,
    output_dir: str,
    table_name: str,
    rule_id: str,
    file_format: str = "xlsx",
) -> str:
    """
    写出批量合并结果文件
    
    Args:
        df: 合并后的 DataFrame
        output_dir: 输出目录
        table_name: 表名
        rule_id: 规则 ID
        file_format: 文件格式
    
    Returns:
        输出文件路径
    """
    safe_table_name = re.sub(r'[\\/:*?"<>|]', "_", table_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_table_name}_merged_{timestamp}.{file_format}"
    output_path = str(Path(output_dir) / filename)
    
    if file_format == "xlsx":
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
    elif file_format == "csv":
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    else:
        # 默认 xlsx
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
    
    return output_path


# ════════════════════════════════════════════════════════════════════════════
# 单规则合并（原有模式，基于 sync_rule.json 的 merge 节点）
# ════════════════════════════════════════════════════════════════════════════

def execute_merge(
    merge_config: dict,
    generated_file_path: str,
    table_file_map: dict[str, str],
    output_dir: str,
    rule_id: str = "UNKNOWN",
) -> dict:
    """
    根据 merge 配置，将新生成文件与目标文件合并，生成合并结果文件。

    Args:
        merge_config       : 规则中的 merge 节点配置字典
        generated_file_path: 本次规则执行生成的新文件绝对路径
        table_file_map     : table_name → 文件绝对路径 的映射（来自 uploaded_files）
        output_dir         : 合并结果文件的输出目录
        rule_id            : 规则 ID，用于日志

    Returns:
        {
            "merged": True/False,          # 是否执行了 merge
            "generated_file_path": str,    # 本次生成的新文件路径
            "merged_file_path": str|None,  # 合并后结果文件路径（未 merge 时为 None）
            "message": str,                # 执行说明
        }
    """
    # ── 检查 merge 是否启用 ──────────────────────────────────────────────────
    if not merge_config.get("enabled", False):
        logger.info(f"[merge_rule] [{rule_id}] merge 未启用，跳过")
        return {
            "merged": False,
            "generated_file_path": generated_file_path,
            "merged_file_path": None,
            "message": "merge 未启用",
        }

    # ── 查找 merge 目标文件 ──────────────────────────────────────────────────
    target_file_path = _find_target_file(merge_config, table_file_map, rule_id)
    if target_file_path is None:
        msg = "未在上传文件中找到 merge 目标文件，跳过 merge"
        logger.warning(f"[merge_rule] [{rule_id}] {msg}")
        return {
            "merged": False,
            "generated_file_path": generated_file_path,
            "merged_file_path": None,
            "message": msg,
        }

    logger.info(f"[merge_rule] [{rule_id}] 找到 merge 目标文件：{target_file_path}")

    # ── 读取两个文件 ──────────────────────────────────────────────────────────
    try:
        df_generated = _read_file_as_df(generated_file_path)
    except Exception as e:
        msg = f"读取新生成文件失败: {e}"
        logger.error(f"[merge_rule] [{rule_id}] {msg}")
        return {
            "merged": False,
            "generated_file_path": generated_file_path,
            "merged_file_path": None,
            "message": msg,
        }

    try:
        df_target = _read_file_as_df(target_file_path)
    except Exception as e:
        msg = f"读取 merge 目标文件失败: {e}"
        logger.error(f"[merge_rule] [{rule_id}] {msg}")
        return {
            "merged": False,
            "generated_file_path": generated_file_path,
            "merged_file_path": None,
            "message": msg,
        }

    logger.info(
        f"[merge_rule] [{rule_id}] 新文件 {len(df_generated)} 行/{len(df_generated.columns)} 列，"
        f"目标文件 {len(df_target)} 行/{len(df_target.columns)} 列"
    )

    # ── 执行合并 ─────────────────────────────────────────────────────────────
    merge_strategy: dict = merge_config.get("merge_strategy", {})
    merged_df = _do_merge(df_generated, df_target, merge_strategy, rule_id)

    # ── 写出合并结果文件 ──────────────────────────────────────────────────────
    # 从 merge_config 中获取 match_field 作为文件名前缀
    target_file_match = merge_config.get("target_file_match", {})
    match_field = target_file_match.get("match_field", "")
    merged_file_path = _write_merged_file(merged_df, output_dir, rule_id, match_field)

    logger.info(
        f"[merge_rule] [{rule_id}] merge 完成，合并后 {len(merged_df)} 行，"
        f"输出：{merged_file_path}"
    )

    return {
        "merged": True,
        "generated_file_path": generated_file_path,
        "merged_file_path": merged_file_path,
        "message": (
            f"merge 成功：新文件 {len(df_generated)} 行 + 目标文件 {len(df_target)} 行 "
            f"= 合并后 {len(merged_df)} 行，共 {len(merged_df.columns)} 列"
        ),
    }


# ════════════════════════════════════════════════════════════════════════════
# 查找 merge 目标文件
# ════════════════════════════════════════════════════════════════════════════

def _find_target_file(
    merge_config: dict,
    table_file_map: dict[str, str],
    rule_id: str,
) -> Optional[str]:
    """
    根据 target_file_match 配置，从 table_file_map 中查找 merge 目标文件路径。

    支持 match_by:
      - "target_table": 用 match_field 的值在 table_file_map 的 key 中模糊/精确匹配
    """
    target_file_match: dict = merge_config.get("target_file_match", {})
    match_by: str = target_file_match.get("match_by", "target_table")
    match_field: str = (target_file_match.get("match_field") or "").strip()

    if not match_field:
        logger.warning(f"[merge_rule] [{rule_id}] merge.target_file_match.match_field 未配置")
        return None

    if match_by == "target_table":
        # 精确匹配：match_field 必须与 table_file_map 的 key 完全相等才执行 merge
        if match_field in table_file_map:
            return table_file_map[match_field]
        logger.warning(
            f"[merge_rule] [{rule_id}] 未找到精确匹配的目标表 '{match_field}'，"
            f"可用表名：{list(table_file_map.keys())}"
        )
    else:
        logger.warning(f"[merge_rule] [{rule_id}] 不支持的 match_by='{match_by}'")

    return None


# ════════════════════════════════════════════════════════════════════════════
# 合并逻辑
# ════════════════════════════════════════════════════════════════════════════

def _do_merge(
    df_generated: pd.DataFrame,
    df_target: pd.DataFrame,
    merge_strategy: dict,
    rule_id: str,
) -> pd.DataFrame:
    """
    执行合并操作。

    strategy.type:
      - "append_rows": 将新生成文件的行追加到目标文件行之后

    column_mismatch_policy.policy:
      - "union_columns": 取两者列的并集，缺失列用 fill_missing_value 填充
    """
    merge_type: str = merge_strategy.get("type", "append_rows")
    mismatch_policy: dict = merge_strategy.get("column_mismatch_policy", {})
    col_policy: str = mismatch_policy.get("policy", "union_columns")
    fill_val: Any = mismatch_policy.get("fill_missing_value", None)

    if merge_type == "append_rows":
        return _merge_append_rows(df_generated, df_target, col_policy, fill_val, rule_id)
    else:
        logger.warning(f"[merge_rule] [{rule_id}] 不支持的 merge type='{merge_type}'，默认使用 append_rows")
        return _merge_append_rows(df_generated, df_target, col_policy, fill_val, rule_id)


def _merge_append_rows(
    df_new: pd.DataFrame,
    df_old: pd.DataFrame,
    col_policy: str,
    fill_val: Any,
    rule_id: str,
) -> pd.DataFrame:
    """
    追加行合并：df_old 的行在前，df_new 的行追加在后。

    列策略：
      - "union_columns": 两者列取并集（以 df_old 列顺序为基准，df_new 多出的列追加在末尾）
      - 其他（默认）   : 同 union_columns
    """
    cols_old = list(df_old.columns)
    cols_new = list(df_new.columns)

    if cols_old == cols_new:
        # 列完全一致，直接 concat
        merged = pd.concat([df_old, df_new], ignore_index=True)
        logger.info(f"[merge_rule] [{rule_id}] 列完全一致，直接拼接")
    else:
        # 列不一致，取并集
        all_cols = list(dict.fromkeys(cols_old + cols_new))  # 保持 dict 去重保序
        extra_in_old = [c for c in cols_old if c not in cols_new]
        extra_in_new = [c for c in cols_new if c not in cols_old]
        logger.info(
            f"[merge_rule] [{rule_id}] 列不一致：目标文件独有列={extra_in_old}，"
            f"新文件独有列={extra_in_new}，取并集共 {len(all_cols)} 列"
        )

        # 对各 DataFrame 补全缺失列
        for col in all_cols:
            if col not in df_old.columns:
                df_old = df_old.copy()
                df_old[col] = fill_val
            if col not in df_new.columns:
                df_new = df_new.copy()
                df_new[col] = fill_val

        merged = pd.concat(
            [df_old[all_cols], df_new[all_cols]],
            ignore_index=True,
        )

    return merged


# ════════════════════════════════════════════════════════════════════════════
# 文件读写
# ════════════════════════════════════════════════════════════════════════════

def _read_file_as_df(file_path: str) -> pd.DataFrame:
    """读取 CSV 或 Excel 文件为 DataFrame"""
    path = resolve_path_under_roots(file_path, [UPLOAD_ROOT, PROC_OUTPUT_ROOT])
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    ext = path.suffix.lower()
    if ext == ".csv":
        try:
            return pd.read_csv(path, encoding="utf-8-sig")
        except UnicodeDecodeError:
            import chardet
            with open(path, "rb") as f:
                enc = chardet.detect(f.read()).get("encoding", "gbk")
            return pd.read_csv(path, encoding=enc)
    elif ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def _write_merged_file(df: pd.DataFrame, output_dir: str, rule_id: str, match_field: str = "") -> str:
    """将合并后的 DataFrame 写出为 xlsx 文件，返回文件路径
    
    Args:
        df: 合并后的 DataFrame
        output_dir: 输出目录
        rule_id: 规则 ID
        match_field: 用于文件名的前缀（如 "BI费用明细表"）
    """
    # 使用 match_field 作为文件名前缀，如果没有则使用 "merged"
    file_prefix = match_field if match_field else "merged"
    safe_prefix = re.sub(r'[\\/:*?"<>|]', "_", file_prefix)
    safe_rule_id = re.sub(r'[\\/:*?"<>|]', "_", rule_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"{safe_prefix}(合并)_{safe_rule_id}_{timestamp}.xlsx"
    output_path = str(Path(output_dir) / filename)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")

    return output_path

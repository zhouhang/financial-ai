"""
数据整理规则 Merge 操作模块

根据规则中的 merge 节点配置，将新生成文件的内容与已上传的目标文件进行合并，
生成最终合并文件（xlsx）。

merge 节点配置说明（来自 proc_rule.json）：
  enabled          : 是否启用 merge，true 时才执行
  target_file_match:
    match_by       : 匹配方式，目前支持 "target_table"（按表名称匹配上传文件）
    match_field    : 与 match_by 对应的匹配值（即要匹配的目标表名）
  merge_strategy:
    type           : 合并方式，目前支持 "append_rows"（追加行）
    column_mismatch_policy:
      policy       : 列不一致策略，"union_columns" 取两者全量列，缺失列填充空值
      fill_missing_value: 缺失列填充值，默认 null
  output:
    return_fields  : 返回给调用侧的字段列表（generated_file_path + merged_file_path）
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 公共入口
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

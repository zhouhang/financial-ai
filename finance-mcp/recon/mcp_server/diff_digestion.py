"""差异消化引擎:两侧全量数据准备。

给定一条历史对账 run 的未关闭差异 key 集合,产出"当前全量"的两侧
recon-ready DataFrame(全窗口取原始数据 -> 跑该 scheme 的 proc 规则),
供后续用对账比对函数逐条复核重判。
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import pandas as pd

logger = logging.getLogger(__name__)


def load_side_rows_for_keys(
    *,
    full_df: pd.DataFrame,
    key_field: str,
    keys: Iterable[str],
) -> pd.DataFrame:
    """从某侧全量 DataFrame 取 key 命中的行(按单一 join key 字段字符串匹配过滤)。

    空 df / 缺 key 列 / 空 keys 均返回空 DataFrame(尽量保留原列结构)。
    """
    if not isinstance(full_df, pd.DataFrame):
        return pd.DataFrame()
    empty = full_df.iloc[0:0].copy()
    key_set = {str(key).strip() for key in keys if str(key or "").strip()}
    if full_df.empty or not key_set:
        return empty
    if key_field not in full_df.columns:
        return empty
    series = full_df[key_field].map(_normalize_key_token)
    return full_df[series.isin(key_set)].reset_index(drop=True)


def _normalize_key_token(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()

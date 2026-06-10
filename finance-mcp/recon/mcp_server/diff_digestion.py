"""差异消化引擎:两侧全量数据准备。

给定一条历史对账 run 的未关闭差异 key 集合,产出"当前全量"的两侧
recon-ready DataFrame(全窗口取原始数据 -> 跑该 scheme 的 proc 规则),
供后续用对账比对函数逐条复核重判。
"""

from __future__ import annotations

import copy
import logging
import tempfile
from typing import Any, Iterable

import pandas as pd

from .dataset_loader import DatasetLoadError, load_dataset_as_df

logger = logging.getLogger(__name__)

LEFT_RECON_READY = "left_recon_ready"
RIGHT_RECON_READY = "right_recon_ready"

DEFAULT_KEY_BATCH_SIZE = 1000

# 全窗口取数:从 binding query 里剥掉的时间过滤相关键。
# display_date_field 同时也是 loader 不接受的展示字段,必须移除。
_TIME_FILTER_QUERY_KEYS = (
    "biz_date",
    "bill_date",
    "date_field",
    "biz_date_field",
    "display_date_field",
)
# source_type=db 时 loader 仅接受这些 query 键(见 dataset_loader._DB_QUERY_ALLOWED_KEYS)。
_DB_QUERY_ALLOWED_KEYS = {"columns", "filters", "order_by", "limit"}
# key 下推安全的 step action;出现其它 action(如 aggregate)说明该侧
# 输出行不与原始行一一对应,下推会改变口径,必须回退全量。
_PUSHDOWN_SAFE_ACTIONS = {"create_schema", "write_dataset"}


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


def build_full_recon_frames(
    *,
    run: dict,
    proc_rule_code: str,
    proc_rule_json: dict,
    diff_keys: set[str],
    left_key_field: str = "",
    right_key_field: str = "",
    key_batch_size: int = DEFAULT_KEY_BATCH_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全窗口取原始两侧数据 -> 跑 proc -> 返回 (left_recon_ready, right_recon_ready)。

    - run: execution_runs 行(需含 source_snapshot_json,其中 collections[*].binding
      描述每个原始数据集的 dataset_ref)。
    - proc_rule_json: 该 scheme 的 proc steps 规则(rule_detail.rule)。
    - diff_keys: 未关闭差异的 join key 值集合;配合 left/right_key_field
      (proc 输出的 join key 列名,来自 recon 规则 key_columns)做取数下推。
      key 字段缺省或反查不出原始字段时回退全量取数。
    """
    from proc.mcp_server.steps_runtime import execute_steps_rule_to_frames

    bindings = _bindings_by_table(run)
    table_usages = _binding_table_usages(proc_rule_json, set(bindings.keys()))
    if not table_usages:
        raise ValueError("proc 规则没有引用 run 绑定的任何数据集,无法准备两侧全量数据")

    key_field_by_side = {
        LEFT_RECON_READY: str(left_key_field or "").strip(),
        RIGHT_RECON_READY: str(right_key_field or "").strip(),
    }
    normalized_keys = sorted({str(key).strip() for key in diff_keys if str(key or "").strip()})

    preloaded_frames: dict[str, pd.DataFrame] = {}
    for table_name, usages in table_usages.items():
        binding = bindings[table_name]
        dataset_ref = _full_window_dataset_ref(binding)
        raw_key_field = _resolve_pushdown_raw_field(
            table_name=table_name,
            usages=usages,
            proc_rule_json=proc_rule_json,
            key_field_by_side=key_field_by_side,
        )
        if raw_key_field and normalized_keys:
            df = _load_table_by_key_batches(
                dataset_ref=dataset_ref,
                table_name=table_name,
                raw_key_field=raw_key_field,
                keys=normalized_keys,
                batch_size=max(int(key_batch_size), 1),
            )
        else:
            df = load_dataset_as_df(dataset_ref, table_name)
        logger.info(
            "[recon][diff_digestion] 表 %s 全窗口取数完成 rows=%d pushdown=%s",
            table_name,
            len(df),
            raw_key_field or "no",
        )
        preloaded_frames[table_name] = df

    with tempfile.TemporaryDirectory(prefix="diff_digestion_proc_") as output_dir:
        frame_outputs = execute_steps_rule_to_frames(
            proc_rule_code,
            proc_rule_json,
            [],
            output_dir,
            preloaded_frames=preloaded_frames,
        )
    left_df = _frame_for_table(frame_outputs, LEFT_RECON_READY)
    right_df = _frame_for_table(frame_outputs, RIGHT_RECON_READY)
    return left_df, right_df


def _bindings_by_table(run: dict) -> dict[str, dict[str, Any]]:
    snapshot = run.get("source_snapshot_json")
    if isinstance(snapshot, str):
        import json

        snapshot = json.loads(snapshot)
    if not isinstance(snapshot, dict):
        raise ValueError("run.source_snapshot_json 缺失或格式无效")
    bindings: dict[str, dict[str, Any]] = {}
    for item in snapshot.get("collections") or []:
        if not isinstance(item, dict):
            continue
        binding = item.get("binding")
        if not isinstance(binding, dict):
            continue
        table_name = str(binding.get("table_name") or "").strip()
        if not table_name or not isinstance(binding.get("dataset_ref"), dict):
            continue
        bindings[table_name] = binding
    if not bindings:
        raise ValueError("run.source_snapshot_json.collections 没有可用的数据集 binding")
    return bindings


def _binding_table_usages(
    proc_rule_json: dict,
    binding_tables: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """收集 proc 规则中对 run 绑定数据集表的引用(表名 -> 引用它的 steps)。"""
    usages: dict[str, list[dict[str, Any]]] = {}
    for step in proc_rule_json.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for source in step.get("sources") or []:
            if not isinstance(source, dict):
                continue
            table_name = str(source.get("table") or "").strip()
            if table_name in binding_tables:
                usages.setdefault(table_name, []).append(step)
    return usages


def _full_window_dataset_ref(binding: dict[str, Any]) -> dict[str, Any]:
    """复制 binding.dataset_ref 并去掉时间过滤,得到全窗口取数 dataset_ref。"""
    dataset_ref = copy.deepcopy(binding.get("dataset_ref") or {})
    query = dict(dataset_ref.get("query") or {})
    date_field = str(query.get("date_field") or query.get("biz_date_field") or "").strip()
    for key in _TIME_FILTER_QUERY_KEYS:
        query.pop(key, None)
    filters = query.get("filters")
    if date_field and isinstance(filters, dict):
        filters = dict(filters)
        filters.pop(date_field, None)
        query["filters"] = filters
    source_type = str(dataset_ref.get("source_type") or "").strip().lower()
    if source_type == "db":
        query = {key: value for key, value in query.items() if key in _DB_QUERY_ALLOWED_KEYS}
    dataset_ref["query"] = query
    return dataset_ref


def _resolve_pushdown_raw_field(
    *,
    table_name: str,
    usages: list[dict[str, Any]],
    proc_rule_json: dict,
    key_field_by_side: dict[str, str],
) -> str:
    """反查 join key 输出列对应的原始字段;推不出(或下推不安全)返回空串。"""
    sides = {str(step.get("target_table") or "").strip() for step in usages}
    if len(sides) != 1:
        logger.warning(
            "[recon][diff_digestion] 表 %s 被多个目标表引用(%s),key 下推不安全,回退全量",
            table_name,
            sorted(sides),
        )
        return ""
    side = next(iter(sides))
    key_field = key_field_by_side.get(side, "")
    if not key_field:
        logger.warning(
            "[recon][diff_digestion] 表 %s(%s) 未提供 join key 输出列,回退全量取数",
            table_name,
            side,
        )
        return ""
    if not _side_steps_pushdown_safe(proc_rule_json, side):
        logger.warning(
            "[recon][diff_digestion] 表 %s(%s) 的 proc 步含 aggregate/lookup,下推不安全,回退全量",
            table_name,
            side,
        )
        return ""

    raw_fields: set[str] = set()
    for step in usages:
        if str(step.get("action") or "").strip() != "write_dataset":
            return ""
        sources = [item for item in step.get("sources") or [] if isinstance(item, dict)]
        if len(sources) != 1:
            logger.warning(
                "[recon][diff_digestion] 表 %s(%s) write_dataset 含多 source,下推不安全,回退全量",
                table_name,
                side,
            )
            return ""
        raw_field = _key_mapping_source_field(step, key_field)
        if not raw_field:
            logger.warning(
                "[recon][diff_digestion] 表 %s(%s) join key 列 '%s' 非直接 source 映射"
                "(formula/template 推不出原始字段),回退全量取数",
                table_name,
                side,
                key_field,
            )
            return ""
        raw_fields.add(raw_field)
    if len(raw_fields) != 1:
        logger.warning(
            "[recon][diff_digestion] 表 %s(%s) join key 列 '%s' 映射到多个原始字段 %s,回退全量",
            table_name,
            side,
            key_field,
            sorted(raw_fields),
        )
        return ""
    return next(iter(raw_fields))


def _side_steps_pushdown_safe(proc_rule_json: dict, side: str) -> bool:
    for step in proc_rule_json.get("steps") or []:
        if not isinstance(step, dict):
            continue
        if str(step.get("target_table") or "").strip() != side:
            continue
        if str(step.get("action") or "").strip() not in _PUSHDOWN_SAFE_ACTIONS:
            return False
        if _contains_lookup_node(step):
            return False
    return True


def _contains_lookup_node(node: Any) -> bool:
    if isinstance(node, dict):
        if str(node.get("type") or "").strip() == "lookup":
            return True
        return any(_contains_lookup_node(value) for value in node.values())
    if isinstance(node, list):
        return any(_contains_lookup_node(item) for item in node)
    return False


def _key_mapping_source_field(step: dict[str, Any], key_field: str) -> str:
    for mapping in step.get("mappings") or []:
        if not isinstance(mapping, dict):
            continue
        if str(mapping.get("target_field") or "").strip() != key_field:
            continue
        value = mapping.get("value")
        if not isinstance(value, dict) or str(value.get("type") or "").strip() != "source":
            return ""
        source = value.get("source")
        if not isinstance(source, dict):
            return ""
        return str(source.get("field") or "").strip()
    return ""


def _load_table_by_key_batches(
    *,
    dataset_ref: dict[str, Any],
    table_name: str,
    raw_key_field: str,
    keys: list[str],
    batch_size: int,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for start in range(0, len(keys), batch_size):
        batch = keys[start : start + batch_size]
        batch_ref = copy.deepcopy(dataset_ref)
        query = dict(batch_ref.get("query") or {})
        filters = dict(query.get("filters") or {})
        filters[raw_key_field] = batch
        query["filters"] = filters
        batch_ref["query"] = query
        try:
            parts.append(load_dataset_as_df(batch_ref, table_name))
        except DatasetLoadError as exc:
            # 单批 key 在该侧没有命中行(例如对侧独有差异)是正常情况,
            # collection 类 loader 会以"暂无采集记录"报错,按空结果处理。
            logger.info(
                "[recon][diff_digestion] 表 %s key 批次(%d-%d)无命中: %s",
                table_name,
                start,
                start + len(batch),
                exc,
            )
    non_empty = [df for df in parts if isinstance(df, pd.DataFrame) and not df.empty]
    if non_empty:
        return pd.concat(non_empty, ignore_index=True)
    # 所有批次都无命中(例如差异 key 全在对侧):返回带原始列结构的空表,
    # 否则 proc 校验源表列时会报缺列。
    for df in parts:
        if isinstance(df, pd.DataFrame) and len(df.columns):
            return df.iloc[0:0].copy()
    return _empty_frame_with_source_columns(dataset_ref, table_name)


def _empty_frame_with_source_columns(dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
    """取 1 行样本拿到原始列结构,返回同构空表(源表为空时返回无列空表)。"""
    sample_ref = copy.deepcopy(dataset_ref)
    query = dict(sample_ref.get("query") or {})
    query["limit"] = 1
    sample_ref["query"] = query
    try:
        sample_df = load_dataset_as_df(sample_ref, table_name)
    except DatasetLoadError as exc:
        logger.warning(
            "[recon][diff_digestion] 表 %s 无法取样本列结构,返回无列空表: %s",
            table_name,
            exc,
        )
        return pd.DataFrame()
    return sample_df.iloc[0:0].copy()


def _frame_for_table(frame_outputs: list[dict[str, Any]], table_name: str) -> pd.DataFrame:
    for item in frame_outputs or []:
        if str(item.get("target_table") or "").strip() == table_name:
            df = item.get("dataframe")
            if isinstance(df, pd.DataFrame):
                return df
    raise ValueError(f"proc 输出缺少 {table_name},请检查数据整理规则")

"""差异消化引擎:两侧全量数据准备 + 核心重判。

给定一条历史对账 run 的未关闭差异 key 集合,产出"当前全量"的两侧
recon-ready DataFrame(全窗口取原始数据 -> 跑该 scheme 的 proc 规则),
再由 digest_diffs 复用对账比对函数(_execute_comparison)逐条复核重判:
能对上 → resolved;差异类型变了 → reclassified;没变化 → kept。

去重策略(在原始取数后、跑 proc 前):
- 若 df 含 __tally_biz_date 列(或 biz_date 列作为时序凭证)→ 按原始 key 字段分组
  取最新分区行(keep_latest 模式)。
- 否则 → drop_duplicates 全 payload 列(排除 __* 元数据列),消除 99% 的重采重复。
frame 返回值可能仍含同 key 多行(真实一对多或快照变更),消费方需自行处理 key 冲突。
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


# 比对桶名(_execute_comparison 的返回 key)
_COMPARISON_BUCKETS = ("matched_exact", "matched_with_diff", "source_only", "target_only")


def digest_diffs(
    *,
    open_diffs: list[dict[str, Any]],
    source_df: pd.DataFrame,
    target_df: pd.DataFrame,
    key_mappings: list[dict[str, str]],
    compare_columns_config: list[dict[str, Any]],
    rule_id: str,
    key_columns_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """把所有差异 key 的两侧子集各取一次,只调一次 _execute_comparison,按 key 映射回每条归宿。

    open_diffs 每条: {"exception_id":..., "anomaly_type": "source_only"|"target_only"|
    "matched_with_diff", "key": {<source_field>: 值}}
    返回每条: {**原条目, "outcome": "resolved"|"reclassified"|"kept", "new_type":...,
    "resolved_to":...(resolved/reclassified 才有)}

    归宿规则:
    - key 只落 matched_exact → resolved(resolved_to="matched")。
    - 独占规则:同 key 同时落 matched_exact 与 matched_with_diff(上游残留同 key
      多行快照)→ 不许 resolved,按 matched_with_diff 处理。
    - 落 matched_with_diff / source_only / target_only → 与原类型相同 kept,
      不同 reclassified(new_type=resolved_to=桶名)。
    - key 在所有桶都没出现(两侧都查不到,缺数据)→ kept,绝不算解决。
    - key 值为空 → kept,且不参与子集构建。

    纯函数,不碰 DB;同 key 对侧多行时行为以 _execute_comparison 实际落桶为准。
    """
    from . import recon_tool

    if not key_mappings:
        raise ValueError("digest_diffs 需要至少一个 key mapping")
    # 支持范围守卫:宁可整轮报错,不可错判(详见 spec §3.2)。
    # 复合 key:子集过滤/桶回映只看首字段,不同 key 组合会折叠 → 可能假 resolved。
    if len(key_mappings) > 1:
        raise ValueError("差异消化暂不支持复合 join key 规则(key_mappings>1)")
    # key transformations:台账存的是转换后 key,而子集过滤用原始值,
    # "转换后才相等"的行进不了子集 → 独占判定建立在残缺行集上,可能假 resolved。
    transformations = (key_columns_config or {}).get("transformations") or {}
    if isinstance(transformations, dict) and any(
        isinstance(side_cfg, dict) and side_cfg for side_cfg in transformations.values()
    ):
        raise ValueError("差异消化暂不支持 key transformations 规则")
    source_key_field = str(key_mappings[0].get("source_field") or "").strip()
    target_key_field = str(key_mappings[0].get("target_field") or "").strip()

    diff_tokens = [_diff_key_token(diff, source_key_field) for diff in open_diffs]
    key_set = {token for token in diff_tokens if token}

    bucket_keys: dict[str, set[str]] = {name: set() for name in _COMPARISON_BUCKETS}
    # 改判成 matched_with_diff 时,要把重捞后的两侧明细带回回写层,避免详情只剩单边。
    mwd_detail_by_token: dict[str, dict[str, Any]] = {}
    if key_set:
        sub_source = load_side_rows_for_keys(
            full_df=source_df, key_field=source_key_field, keys=key_set
        )
        sub_target = load_side_rows_for_keys(
            full_df=target_df, key_field=target_key_field, keys=key_set
        )
        comparison = recon_tool._execute_comparison(
            sub_source,
            sub_target,
            key_mappings,
            compare_columns_config,
            rule_id,
            key_columns_config,
        )
        # 桶 DataFrame 是 merge 产物:两侧 key 字段同名时只有 source_/target_
        # 角色前缀列,必须用 recon_tool 的行读取 helper 才能取回 key 值。
        source_candidates = recon_tool._candidate_columns_for_field(source_key_field, "source")
        target_candidates = recon_tool._candidate_columns_for_field(target_key_field, "target")
        for bucket_name in _COMPARISON_BUCKETS:
            bucket_df = (comparison or {}).get(bucket_name)
            if not isinstance(bucket_df, pd.DataFrame) or bucket_df.empty:
                continue
            for _, row in bucket_df.iterrows():
                normalized_row = recon_tool._normalize_dataframe_row(row)
                token = _normalize_key_token(
                    recon_tool._resolve_row_value(normalized_row, source_candidates)
                )
                if not token:
                    token = _normalize_key_token(
                        recon_tool._resolve_row_value(normalized_row, target_candidates)
                    )
                if token:
                    bucket_keys[bucket_name].add(token)

        # 用对账引擎同一套明细构造器重建两侧齐全的明细,按 key 索引,
        # 供改判 matched_with_diff 的条目回写时替换残缺的单边快照。
        for detail_row in recon_tool._build_anomaly_rows(
            comparison or {},
            key_mappings=key_mappings,
            compare_columns_config=compare_columns_config,
        ):
            if detail_row.get("anomaly_type") != "matched_with_diff":
                continue
            join_key = detail_row.get("join_key") or []
            detail_token = ""
            if join_key:
                detail_token = _normalize_key_token(join_key[0].get("source_value")) or \
                    _normalize_key_token(join_key[0].get("target_value"))
            if detail_token and detail_token not in mwd_detail_by_token:
                mwd_detail_by_token[detail_token] = detail_row

    results: list[dict[str, Any]] = []
    for diff, token in zip(open_diffs, diff_tokens):
        entry = dict(diff)
        original_type = str(diff.get("anomaly_type") or "").strip()
        outcome, new_type, resolved_to = _judge_diff_outcome(
            token=token, original_type=original_type, bucket_keys=bucket_keys
        )
        entry["outcome"] = outcome
        entry["new_type"] = new_type
        if resolved_to is not None:
            entry["resolved_to"] = resolved_to
        # 改判为 matched_with_diff:带回重捞后的两侧明细(单边桶无需,详情本就单边)。
        if outcome == "reclassified" and new_type == "matched_with_diff":
            refreshed = mwd_detail_by_token.get(token)
            if refreshed is not None:
                entry["refreshed_detail"] = refreshed
        results.append(entry)
    return results


def _diff_key_token(diff: dict[str, Any], source_key_field: str) -> str:
    key_obj = diff.get("key")
    if not isinstance(key_obj, dict):
        return ""
    return _normalize_key_token(key_obj.get(source_key_field))


def _judge_diff_outcome(
    *,
    token: str,
    original_type: str,
    bucket_keys: dict[str, set[str]],
) -> tuple[str, str, str | None]:
    """单条差异归宿判定,返回 (outcome, new_type, resolved_to|None)。"""
    if not token:
        # 空 key:无法定位,保守 kept
        return "kept", original_type, None
    in_exact = token in bucket_keys["matched_exact"]
    in_with_diff = token in bucket_keys["matched_with_diff"]
    in_source_only = token in bucket_keys["source_only"]
    in_target_only = token in bucket_keys["target_only"]
    if in_exact and not (in_with_diff or in_source_only or in_target_only):
        # 只含 matched_exact 才许 resolved(独占规则,防假关闭)
        return "resolved", "matched", "matched"
    if in_with_diff:
        if original_type == "matched_with_diff":
            return "kept", original_type, None
        return "reclassified", "matched_with_diff", "matched_with_diff"
    if in_source_only or in_target_only:
        bucket = "source_only" if in_source_only else "target_only"
        if original_type == bucket:
            return "kept", original_type, None
        return "reclassified", bucket, bucket
    # gone:所有桶都没出现(两侧都查不到),缺数据绝不算解决
    return "kept", original_type, None


def apply_outcomes_to_diff_result(
    diff_result: dict[str, Any],
    results: list[dict[str, Any]],
    *,
    source_key_field: str,
    target_key_field: str,
) -> dict[str, int]:
    """Fold digestion outcomes into a freshly-computed diff_result.

    So a refreshed period rollup reflects post-digestion state (the daily digest reads
    recon_period_rollup, which the digestion writeback does not otherwise update):
      - resolved      → row moves into ``matched_exact`` (leaves in-transit/diff, joins settled).
      - reclassified  → row moves into its new bucket (matched_with_diff/source_only/target_only).
      - kept          → unchanged.

    Mutates ``diff_result`` in place; returns a {dest_bucket: moved_count} tally. Row identity is
    resolved with the same merged-column helpers ``digest_diffs`` uses, so it matches the engine.
    """
    from . import recon_tool

    moves: dict[str, str] = {}  # key token -> destination bucket
    for item in results or []:
        token = _diff_key_token(item, source_key_field)
        if not token:
            continue
        outcome = str(item.get("outcome") or "")
        if outcome == "resolved":
            moves[token] = "matched_exact"
        elif outcome == "reclassified":
            dest = str(item.get("resolved_to") or item.get("new_type") or "")
            if dest in ("matched_with_diff", "source_only", "target_only"):
                moves[token] = dest
    if not moves:
        return {}

    src_cands = recon_tool._candidate_columns_for_field(source_key_field, "source")
    tgt_cands = recon_tool._candidate_columns_for_field(target_key_field, "target")
    moved_rows: dict[str, list] = {name: [] for name in _COMPARISON_BUCKETS}
    tally: dict[str, int] = {}
    for bucket in ("matched_with_diff", "source_only", "target_only"):
        df = diff_result.get(bucket)
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        keep_mask: list[bool] = []
        for _, row in df.iterrows():
            nrow = recon_tool._normalize_dataframe_row(row)
            token = _normalize_key_token(recon_tool._resolve_row_value(nrow, src_cands)) or \
                _normalize_key_token(recon_tool._resolve_row_value(nrow, tgt_cands))
            dest = moves.get(token)
            if dest and dest != bucket:
                moved_rows[dest].append(row)
                tally[dest] = tally.get(dest, 0) + 1
                keep_mask.append(False)
            else:
                keep_mask.append(True)
        if not all(keep_mask):
            diff_result[bucket] = df[keep_mask]
    for dest, rows in moved_rows.items():
        if not rows:
            continue
        add_df = pd.DataFrame(rows)
        existing = diff_result.get(dest)
        if isinstance(existing, pd.DataFrame) and not existing.empty:
            diff_result[dest] = pd.concat([existing, add_df], ignore_index=True)
        else:
            diff_result[dest] = add_df
    return tally


def build_full_recon_frames(
    *,
    run: dict,
    proc_rule_code: str,
    proc_rule_json: dict,
    diff_keys: set[str],
    left_key_field: str = "",
    right_key_field: str = "",
    key_batch_size: int = DEFAULT_KEY_BATCH_SIZE,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """全窗口取原始两侧数据 -> 去重 -> 跑 proc -> 返回 (left_recon_ready, right_recon_ready, meta)。

    - run: execution_runs 行(需含 source_snapshot_json,其中 collections[*].binding
      描述每个原始数据集的 dataset_ref)。
    - proc_rule_json: 该 scheme 的 proc steps 规则(rule_detail.rule)。
    - diff_keys: 未关闭差异的 join key 值集合;配合 left/right_key_field
      (proc 输出的 join key 列名,来自 recon 规则 key_columns)做取数下推。
      key 字段缺省或反查不出原始字段时回退全量取数。

    meta 结构:
    - fetch_degraded (bool): 取数时有 warning 级失败(非"暂无"错误)时为 True。
    - fallback_full_fetch_sides (list): 回退全量取数的侧列表。
    - failed_batches (int): 取数批次失败总数(warning 级)。
    - dedup_mode (str): "keep_latest" | "drop_duplicates" | "none"。

    返回 frame 可能含跨分区重复行(已按 dedup_mode 尽力去重);
    frame 也可能仍含同 key 多行(真实一对多或快照变更),消费方需自行处理 key 冲突。
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

    fetch_degraded = False
    failed_batches = 0
    dedup_mode = "none"

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
            df, table_failed = _load_table_by_key_batches(
                dataset_ref=dataset_ref,
                table_name=table_name,
                raw_key_field=raw_key_field,
                keys=normalized_keys,
                batch_size=max(int(key_batch_size), 1),
            )
            if table_failed > 0:
                fetch_degraded = True
                failed_batches += table_failed
        else:
            try:
                df = load_dataset_as_df(dataset_ref, table_name)
            except DatasetLoadError as exc:
                if _is_empty_collection_error(exc):
                    logger.info(
                        "[recon][diff_digestion] 表 %s 全量取数:暂无采集记录,返回空表: %s",
                        table_name,
                        exc,
                    )
                    df = pd.DataFrame()
                else:
                    logger.warning(
                        "[recon][diff_digestion] 表 %s 全量取数失败(配置/SQL错误),返回空表: %s",
                        table_name,
                        exc,
                    )
                    fetch_degraded = True
                    failed_batches += 1
                    df = pd.DataFrame()

        # 原始取数后、跑 proc 前:去重跨分区重复行
        df, table_dedup_mode = _dedup_raw_frame(df, raw_key_field=raw_key_field)
        # 优先级: keep_latest > drop_duplicates > none
        if table_dedup_mode == "keep_latest" or (table_dedup_mode != "none" and dedup_mode == "none"):
            dedup_mode = table_dedup_mode

        logger.info(
            "[recon][diff_digestion] 表 %s 全窗口取数完成 rows=%d pushdown=%s dedup=%s",
            table_name,
            len(df),
            raw_key_field or "no",
            table_dedup_mode,
        )
        preloaded_frames[table_name] = df

    meta: dict = {
        "fetch_degraded": fetch_degraded,
        "fallback_full_fetch_sides": [],
        "failed_batches": failed_batches,
        "dedup_mode": dedup_mode,
    }

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
    return left_df, right_df, meta


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
            logger.warning(
                "[recon][diff_digestion] 表 %s(%s) step action 非 write_dataset(%s),key 下推不安全,回退全量",
                table_name,
                side,
                str(step.get("action") or ""),
            )
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


def _is_empty_collection_error(exc: DatasetLoadError) -> bool:
    """判断 DatasetLoadError 是否属于"暂无采集记录"类(正常无命中,不是配置/SQL 错误)。"""
    msg = str(exc)
    return any(
        phrase in msg
        for phrase in (
            "暂无采集记录",
            "暂无浏览器采集记录",
            "暂无平台订单明细",
            "暂无支付宝账单明细",
        )
    )


# 用于识别时序列的候选列名(优先级从高到低)
_TALLY_BIZ_DATE_COLS = ("__tally_biz_date", "biz_date", "__tally_captured_at", "captured_at")


def _dedup_raw_frame(df: pd.DataFrame, *, raw_key_field: str) -> tuple[pd.DataFrame, str]:
    """在原始取数后、跑 proc 前去重跨分区重复行。

    返回 (去重后的 df, dedup_mode):
    - "keep_latest": 找到时序列,按 raw_key_field(或全列)分组取最新行。
    - "drop_duplicates": 无时序列,全 payload 列 drop_duplicates。
    - "none": df 为空或无需去重。
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df, "none"

    # 找到可用的时序列
    time_col = ""
    for candidate in _TALLY_BIZ_DATE_COLS:
        if candidate in df.columns:
            time_col = candidate
            break

    if time_col:
        # keep latest: 按 raw_key_field(若存在)分组,取时序最大的那行
        if raw_key_field and raw_key_field in df.columns:
            group_cols = [raw_key_field]
        else:
            # 没有 key 字段信息:按全 payload 列(排除 __* 元数据列)分组
            group_cols = [c for c in df.columns if not c.startswith("__")]
        if group_cols:
            idx = df.groupby(group_cols, sort=False)[time_col].transform("max") == df[time_col]
            deduped = df[idx].drop_duplicates(subset=group_cols).reset_index(drop=True)
        else:
            deduped = df
        return deduped, "keep_latest"

    # 无时序列:全 payload 列 drop_duplicates(排除 __* 元数据列)
    payload_cols = [c for c in df.columns if not c.startswith("__")]
    if not payload_cols:
        return df, "none"
    deduped = df.drop_duplicates(subset=payload_cols).reset_index(drop=True)
    return deduped, "drop_duplicates"


def _load_table_by_key_batches(
    *,
    dataset_ref: dict[str, Any],
    table_name: str,
    raw_key_field: str,
    keys: list[str],
    batch_size: int,
) -> tuple[pd.DataFrame, int]:
    """按 key 分批取数,返回 (合并后的 df, warning 级失败批次数)。"""
    parts: list[pd.DataFrame] = []
    failed_count = 0
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
            if _is_empty_collection_error(exc):
                # 单批 key 在该侧没有命中行(例如对侧独有差异)是正常情况,
                # collection 类 loader 会以"暂无采集记录"报错,按空结果处理。
                logger.info(
                    "[recon][diff_digestion] 表 %s key 批次(%d-%d)无命中: %s",
                    table_name,
                    start,
                    start + len(batch),
                    exc,
                )
            else:
                logger.warning(
                    "[recon][diff_digestion] 表 %s key 批次(%d-%d)取数失败(配置/SQL错误): %s",
                    table_name,
                    start,
                    start + len(batch),
                    exc,
                )
                failed_count += 1
    non_empty = [df for df in parts if isinstance(df, pd.DataFrame) and not df.empty]
    if non_empty:
        return pd.concat(non_empty, ignore_index=True), failed_count
    # 所有批次都无命中(例如差异 key 全在对侧):返回带原始列结构的空表,
    # 否则 proc 校验源表列时会报缺列。
    for df in parts:
        if isinstance(df, pd.DataFrame) and len(df.columns):
            return df.iloc[0:0].copy(), failed_count
    return _empty_frame_with_source_columns(dataset_ref, table_name), failed_count


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

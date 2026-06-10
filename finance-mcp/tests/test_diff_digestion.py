from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

import logging

from recon.mcp_server import diff_digestion
from recon.mcp_server.diff_digestion import (
    build_full_recon_frames,
    digest_diffs,
    load_side_rows_for_keys,
)


class TestLoadSideRowsForKeys:
    def test_filters_rows_matching_keys(self) -> None:
        full_df = pd.DataFrame(
            {
                "订单编号": ["A", "B", "C"],
                "金额": ["1.0", "2.0", "3.0"],
            }
        )
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"A", "C"})
        assert len(result) == 2
        assert sorted(result["订单编号"].tolist()) == ["A", "C"]
        assert list(result.columns) == ["订单编号", "金额"]

    def test_key_matching_is_string_based(self) -> None:
        full_df = pd.DataFrame({"订单编号": [1001, 1002], "金额": [1, 2]})
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"1001"})
        assert len(result) == 1
        assert result.iloc[0]["金额"] == 1

    def test_empty_df_returns_empty(self) -> None:
        full_df = pd.DataFrame(columns=["订单编号", "金额"])
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"A"})
        assert result.empty

    def test_missing_key_column_returns_empty(self) -> None:
        full_df = pd.DataFrame({"其他列": ["A", "B"]})
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys={"A"})
        assert result.empty

    def test_empty_keys_returns_empty(self) -> None:
        full_df = pd.DataFrame({"订单编号": ["A", "B"]})
        result = load_side_rows_for_keys(full_df=full_df, key_field="订单编号", keys=set())
        assert result.empty


def _write_dataset_step(
    *,
    side: str,
    source_table: str,
    key_target: str,
    key_source_value: dict[str, Any],
    amount_target: str,
    amount_source_field: str,
) -> list[dict[str, Any]]:
    target_table = f"{side}_recon_ready"
    return [
        {
            "action": "create_schema",
            "step_id": f"{side}_create",
            "target_table": target_table,
            "schema": {
                "columns": [
                    {"name": key_target, "data_type": "string"},
                    {"name": amount_target, "data_type": "string"},
                ],
                "primary_key": [],
            },
        },
        {
            "action": "write_dataset",
            "step_id": f"{side}_write",
            "target_table": target_table,
            "depends_on": [f"{side}_create"],
            "row_write_mode": "upsert",
            "sources": [{"alias": "source_1", "table": source_table}],
            "mappings": [
                {
                    "target_field": key_target,
                    "field_write_mode": "overwrite",
                    "value": key_source_value,
                },
                {
                    "target_field": amount_target,
                    "field_write_mode": "overwrite",
                    "value": {
                        "type": "source",
                        "source": {"alias": "source_1", "field": amount_source_field},
                    },
                },
            ],
        },
    ]


def _make_proc_rule(
    *,
    left_key_value: dict[str, Any] | None = None,
) -> dict[str, Any]:
    left_key_value = left_key_value or {
        "type": "source",
        "source": {"alias": "source_1", "field": "custom_order_no"},
    }
    steps: list[dict[str, Any]] = []
    steps.extend(
        _write_dataset_step(
            side="left",
            source_table="public.fake_mid_orders",
            key_target="客户订单号",
            key_source_value=left_key_value,
            amount_target="含税销售金额",
            amount_source_field="tax_sale_amount",
        )
    )
    steps.extend(
        _write_dataset_step(
            side="right",
            source_table="browser-collection-fake-shop@1",
            key_target="订单编号",
            key_source_value={
                "type": "source",
                "source": {"alias": "source_1", "field": "订单编号"},
            },
            amount_target="买家实付金额",
            amount_source_field="买家实付金额",
        )
    )
    return {"version": "1.0", "steps": steps}


def _make_run() -> dict[str, Any]:
    return {
        "source_snapshot_json": {
            "biz_date": "2026-06-09",
            "collections": [
                {
                    "binding": {
                        "role_code": "left_1",
                        "table_name": "public.fake_mid_orders",
                        "dataset_ref": {
                            "source_type": "collection_records",
                            "source_key": "ds-left",
                            "query": {
                                "dataset_id": "dataset-left",
                                "resource_key": "public.fake_mid_orders",
                                "biz_date": "2026-06-09",
                                "date_field": "order_finish_time",
                                "display_date_field": "订单完成时间",
                            },
                        },
                    }
                },
                {
                    "binding": {
                        "role_code": "right_1",
                        "table_name": "browser-collection-fake-shop@1",
                        "dataset_ref": {
                            "source_type": "browser_collection_records",
                            "source_key": "ds-right",
                            "query": {
                                "dataset_id": "dataset-right",
                                "resource_key": "browser-collection-fake-shop@1",
                                "biz_date": "2026-06-09",
                                "date_field": "订单付款时间",
                                "display_date_field": "订单付款时间",
                            },
                        },
                    }
                },
            ],
        }
    }


class _FakeLoader:
    """记录每次 load_dataset_as_df 调用并按表名返回固定 DataFrame。"""

    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, dataset_ref: dict[str, Any], table_name: str) -> pd.DataFrame:
        self.calls.append((table_name, json.loads(json.dumps(dataset_ref))))
        df = self.frames[table_name]
        query = dataset_ref.get("query") or {}
        filters = query.get("filters") or {}
        for field, value in filters.items():
            if isinstance(value, list) and field in df.columns:
                allowed = {str(item) for item in value}
                df = df[df[field].map(str).isin(allowed)]
        return df.reset_index(drop=True)

    def calls_for(self, table_name: str) -> list[dict[str, Any]]:
        return [ref for name, ref in self.calls if name == table_name]


@pytest.fixture()
def fake_loader(monkeypatch: pytest.MonkeyPatch) -> _FakeLoader:
    loader = _FakeLoader(
        frames={
            "public.fake_mid_orders": pd.DataFrame(
                {
                    "custom_order_no": ["A1", "A2", "A3"],
                    "tax_sale_amount": ["5.30", "6.60", "7.70"],
                    "order_finish_time": ["2026-06-01", "2026-06-02", "2026-06-03"],
                }
            ),
            "browser-collection-fake-shop@1": pd.DataFrame(
                {
                    "订单编号": ["A1", "A9"],
                    "买家实付金额": ["5.30", "9.90"],
                    "订单付款时间": ["2026-06-01 10:00:00", "2026-06-05 10:00:00"],
                }
            ),
        }
    )
    monkeypatch.setattr(diff_digestion, "load_dataset_as_df", loader)
    return loader


class TestBuildFullReconFrames:
    def test_runs_proc_and_returns_renamed_recon_ready_frames(self, fake_loader: _FakeLoader) -> None:
        left_df, right_df, meta = build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=_make_proc_rule(),
            diff_keys={"A1", "A2"},
            left_key_field="客户订单号",
            right_key_field="订单编号",
        )
        # proc 输出列名(改名后),不是原始字段名;proc 引擎会额外附带
        # __tally_source_record 元数据列
        assert [col for col in left_df.columns if not col.startswith("__")] == ["客户订单号", "含税销售金额"]
        assert [col for col in right_df.columns if not col.startswith("__")] == ["订单编号", "买家实付金额"]
        assert sorted(left_df["客户订单号"].tolist()) == ["A1", "A2"]
        # meta 结构校验
        assert isinstance(meta, dict)
        assert "fetch_degraded" in meta
        assert "dedup_mode" in meta

    def test_pushes_diff_keys_down_to_raw_field_and_strips_time_filters(
        self, fake_loader: _FakeLoader
    ) -> None:
        build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=_make_proc_rule(),
            diff_keys={"A1", "A2"},
            left_key_field="客户订单号",
            right_key_field="订单编号",
        )
        left_calls = fake_loader.calls_for("public.fake_mid_orders")
        assert left_calls, "左侧应该走 loader 取数"
        for ref in left_calls:
            query = ref["query"]
            # 全窗口:去掉时间过滤
            assert "biz_date" not in query
            assert "display_date_field" not in query
            # key 下推到原始字段(改名映射反查 客户订单号 <- custom_order_no)
            assert sorted(query["filters"]["custom_order_no"]) == ["A1", "A2"]

    def test_key_batches_split_large_keysets(self, fake_loader: _FakeLoader) -> None:
        keys = {f"K{i}" for i in range(7)}
        build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=_make_proc_rule(),
            diff_keys=keys,
            left_key_field="客户订单号",
            right_key_field="订单编号",
            key_batch_size=3,
        )
        left_calls = fake_loader.calls_for("public.fake_mid_orders")
        assert len(left_calls) == 3
        seen: list[str] = []
        for ref in left_calls:
            batch = ref["query"]["filters"]["custom_order_no"]
            assert len(batch) <= 3
            seen.extend(batch)
        assert sorted(seen) == sorted(keys)

    def test_formula_key_mapping_falls_back_to_full_load(self, fake_loader: _FakeLoader) -> None:
        proc_rule = _make_proc_rule(
            left_key_value={
                "type": "formula",
                "expr": "{x}",
                "bindings": {
                    "x": {"type": "source", "source": {"alias": "source_1", "field": "custom_order_no"}}
                },
            }
        )
        left_df, _right_df, _meta = build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=proc_rule,
            diff_keys={"A1"},
            left_key_field="客户订单号",
            right_key_field="订单编号",
        )
        left_calls = fake_loader.calls_for("public.fake_mid_orders")
        assert len(left_calls) == 1
        query = left_calls[0]["query"]
        assert "filters" not in query or "custom_order_no" not in (query.get("filters") or {})
        assert "biz_date" not in query

    def test_missing_key_field_falls_back_to_full_load(self, fake_loader: _FakeLoader) -> None:
        build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=_make_proc_rule(),
            diff_keys={"A1"},
        )
        left_calls = fake_loader.calls_for("public.fake_mid_orders")
        assert len(left_calls) == 1
        assert "filters" not in left_calls[0]["query"] or not left_calls[0]["query"].get("filters")

    # ------------------------------------------------------------------
    # Fix #1: 跨分区重复行去重
    # ------------------------------------------------------------------

    def test_dedup_keep_latest_by_biz_date_for_duplicate_key_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同一 key 有新旧两行(带 __tally_biz_date),keep-latest 后只留新值行。"""
        # 构造含 __tally_biz_date 的 frame:订单 A1 有两行,旧值和新值
        stale_row = {
            "custom_order_no": "A1",
            "tax_sale_amount": "5.00",
            "__tally_biz_date": "2026-06-01",
        }
        fresh_row = {
            "custom_order_no": "A1",
            "tax_sale_amount": "5.30",
            "__tally_biz_date": "2026-06-02",
        }
        loader = _FakeLoader(
            frames={
                "public.fake_mid_orders": pd.DataFrame([stale_row, fresh_row]),
                "browser-collection-fake-shop@1": pd.DataFrame(
                    {
                        "订单编号": ["A1"],
                        "买家实付金额": ["5.30"],
                    }
                ),
            }
        )
        monkeypatch.setattr(diff_digestion, "load_dataset_as_df", loader)
        left_df, _right_df, meta = build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=_make_proc_rule(),
            diff_keys={"A1"},
            left_key_field="客户订单号",
            right_key_field="订单编号",
        )
        # proc 输出里,A1 只应对应新值 5.30
        a1_rows = left_df[left_df["客户订单号"] == "A1"]
        assert len(a1_rows) == 1, "keep-latest 后 A1 只应剩一行"
        assert a1_rows.iloc[0]["含税销售金额"] == "5.30"
        assert meta["dedup_mode"] == "keep_latest"

    def test_dedup_full_row_for_identical_duplicate_rows_without_time_column(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """无时间序列时,完全相同的两行去重后只剩一行。"""
        identical_row = {"custom_order_no": "A1", "tax_sale_amount": "5.30"}
        loader = _FakeLoader(
            frames={
                "public.fake_mid_orders": pd.DataFrame([identical_row, identical_row]),
                "browser-collection-fake-shop@1": pd.DataFrame(
                    {
                        "订单编号": ["A1"],
                        "买家实付金额": ["5.30"],
                    }
                ),
            }
        )
        monkeypatch.setattr(diff_digestion, "load_dataset_as_df", loader)
        left_df, _right_df, meta = build_full_recon_frames(
            run=_make_run(),
            proc_rule_code="proc_test_rule",
            proc_rule_json=_make_proc_rule(),
            diff_keys={"A1"},
            left_key_field="客户订单号",
            right_key_field="订单编号",
        )
        a1_rows = left_df[left_df["客户订单号"] == "A1"]
        assert len(a1_rows) == 1, "全列去重后 A1 只应剩一行"
        assert meta["dedup_mode"] == "drop_duplicates"

    # ------------------------------------------------------------------
    # Fix #2: 错误分级 + fetch_degraded meta
    # ------------------------------------------------------------------

    def test_non_empty_dataset_load_error_sets_fetch_degraded_and_logs_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """非'暂无采集记录'的 DatasetLoadError 应设 fetch_degraded=True 并记录 warning。

        左侧 key 批次取数遇配置/SQL 错误时,meta.fetch_degraded=True 且有 warning 日志。
        """
        from recon.mcp_server.dataset_loader import DatasetLoadError

        batch_calls: list[str] = []

        def graded_loader(dataset_ref: dict, table_name: str) -> pd.DataFrame:
            batch_calls.append(table_name)
            if table_name == "public.fake_mid_orders":
                # 判断是否是 key 批次请求(有 filters 里带 custom_order_no)
                query = dataset_ref.get("query") or {}
                filters = query.get("filters") or {}
                if "custom_order_no" in filters:
                    raise DatasetLoadError("SQL 执行失败: column does_not_exist does not exist")
                # 全量请求:返回空但有列的 frame 让 proc 能继续
                return pd.DataFrame(columns=["custom_order_no", "tax_sale_amount"])
            return pd.DataFrame(
                {
                    "订单编号": ["A1"],
                    "买家实付金额": ["5.30"],
                }
            )

        monkeypatch.setattr(diff_digestion, "load_dataset_as_df", graded_loader)
        with caplog.at_level(logging.WARNING):
            left_df, right_df, meta = build_full_recon_frames(
                run=_make_run(),
                proc_rule_code="proc_test_rule",
                proc_rule_json=_make_proc_rule(),
                diff_keys={"A1"},
                left_key_field="客户订单号",
                right_key_field="订单编号",
            )
        assert meta["fetch_degraded"] is True
        assert meta["failed_batches"] >= 1
        # warning 应该被记录
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "非'暂无'错误应记录 warning 日志"


# ---------------------------------------------------------------------------
# digest_diffs:核心重判(纯函数,不碰 DB)
# ---------------------------------------------------------------------------

# 两侧 key 字段故意同名:_execute_comparison 的 merge 产物里只有
# source_订单编号 / target_订单编号 角色前缀列,裸列名取不到,
# 必须用 recon_tool 的行读取 helper 才能映射回 key。
DIGEST_KEY_MAPPINGS = [{"source_field": "订单编号", "target_field": "订单编号"}]
DIGEST_COMPARE_CONFIG = [
    {"name": "金额", "source_column": "金额", "target_column": "金额", "tolerance": 0}
]


def _side_df(rows: list[tuple[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "订单编号": [key for key, _ in rows],
            "金额": [amount for _, amount in rows],
        }
    )


def _open_diff(exception_id: str, anomaly_type: str, key_value: Any) -> dict[str, Any]:
    return {
        "exception_id": exception_id,
        "anomaly_type": anomaly_type,
        "key": {"订单编号": key_value},
    }


def _digest(
    open_diffs: list[dict[str, Any]],
    source_df: pd.DataFrame,
    target_df: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    results = digest_diffs(
        open_diffs=open_diffs,
        source_df=source_df,
        target_df=target_df,
        key_mappings=DIGEST_KEY_MAPPINGS,
        compare_columns_config=DIGEST_COMPARE_CONFIG,
        rule_id="rule-digest-test",
    )
    assert len(results) == len(open_diffs)
    return {item["exception_id"]: item for item in results}


class TestDigestDiffs:
    def test_basic_three_outcomes_with_same_named_key_fields(self) -> None:
        """计划原文用例;key 字段两侧同名,暴露 merge 角色前缀列问题。

        - source_only A:现两侧平 → resolved
        - source_only C:现两侧都有但金额差 → reclassified → matched_with_diff
        - target_only B:source 仍无 → kept
        """
        source_df = _side_df([("A", "10"), ("C", "9")])
        target_df = _side_df([("A", "10"), ("B", "5"), ("C", "10")])
        outcomes = _digest(
            [
                _open_diff("e-a", "source_only", "A"),
                _open_diff("e-c", "source_only", "C"),
                _open_diff("e-b", "target_only", "B"),
            ],
            source_df,
            target_df,
        )
        assert outcomes["e-a"]["outcome"] == "resolved"
        assert outcomes["e-a"]["new_type"] == "matched"
        assert outcomes["e-a"]["resolved_to"] == "matched"
        assert outcomes["e-c"]["outcome"] == "reclassified"
        assert outcomes["e-c"]["new_type"] == "matched_with_diff"
        assert outcomes["e-c"]["resolved_to"] == "matched_with_diff"
        assert outcomes["e-b"]["outcome"] == "kept"
        assert outcomes["e-b"]["new_type"] == "target_only"
        assert "resolved_to" not in outcomes["e-b"]
        # 原条目字段保留
        assert outcomes["e-a"]["anomaly_type"] == "source_only"
        assert outcomes["e-a"]["key"] == {"订单编号": "A"}

    def test_calls_execute_comparison_exactly_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from recon.mcp_server import recon_tool

        calls: list[tuple[int, int]] = []
        real = recon_tool._execute_comparison

        def counting(df_source, df_target, *args, **kwargs):
            calls.append((len(df_source), len(df_target)))
            return real(df_source, df_target, *args, **kwargs)

        monkeypatch.setattr(recon_tool, "_execute_comparison", counting)
        _digest(
            [
                _open_diff("e-a", "source_only", "A"),
                _open_diff("e-c", "source_only", "C"),
                _open_diff("e-b", "target_only", "B"),
            ],
            _side_df([("A", "10"), ("C", "9")]),
            _side_df([("A", "10"), ("B", "5"), ("C", "10")]),
        )
        assert len(calls) == 1, "全部差异 key 必须合并成一次比对"
        # 子集应包含全部差异 key 命中的行
        assert calls[0] == (2, 3)

    def test_matched_with_diff_now_equal_resolves(self) -> None:
        outcomes = _digest(
            [_open_diff("e-a", "matched_with_diff", "A")],
            _side_df([("A", "10")]),
            _side_df([("A", "10")]),
        )
        assert outcomes["e-a"]["outcome"] == "resolved"
        assert outcomes["e-a"]["resolved_to"] == "matched"

    def test_matched_with_diff_target_gone_reclassifies_to_source_only(self) -> None:
        outcomes = _digest(
            [_open_diff("e-a", "matched_with_diff", "A")],
            _side_df([("A", "10")]),
            _side_df([]),
        )
        assert outcomes["e-a"]["outcome"] == "reclassified"
        assert outcomes["e-a"]["new_type"] == "source_only"
        assert outcomes["e-a"]["resolved_to"] == "source_only"

    def test_target_only_now_source_only_reclassifies(self) -> None:
        """source_only ↔ target_only 翻转也算 reclassified。"""
        outcomes = _digest(
            [_open_diff("e-a", "target_only", "A")],
            _side_df([("A", "10")]),
            _side_df([]),
        )
        assert outcomes["e-a"]["outcome"] == "reclassified"
        assert outcomes["e-a"]["new_type"] == "source_only"

    def test_exclusive_rule_blocks_false_resolution(self) -> None:
        """同 key 同时落 matched_exact 和 matched_with_diff(残留多行快照)→ 不许 resolved。"""
        source_df = _side_df([("K", "10"), ("K", "11")])
        target_df = _side_df([("K", "10")])
        outcomes = _digest(
            [
                _open_diff("e-so", "source_only", "K"),
                _open_diff("e-mwd", "matched_with_diff", "K"),
            ],
            source_df,
            target_df,
        )
        assert outcomes["e-so"]["outcome"] != "resolved"
        assert outcomes["e-so"]["outcome"] == "reclassified"
        assert outcomes["e-so"]["new_type"] == "matched_with_diff"
        # 原类型就是 matched_with_diff → kept
        assert outcomes["e-mwd"]["outcome"] == "kept"
        assert outcomes["e-mwd"]["new_type"] == "matched_with_diff"
        assert "resolved_to" not in outcomes["e-mwd"]

    def test_gone_key_is_kept_never_resolved(self) -> None:
        """两侧都查不到该 key(缺数据)→ kept,绝不算解决。"""
        outcomes = _digest(
            [
                _open_diff("e-so", "source_only", "ZZZ"),
                _open_diff("e-mwd", "matched_with_diff", "ZZZ"),
            ],
            _side_df([("A", "10")]),
            _side_df([("A", "10")]),
        )
        for exception_id, original_type in (("e-so", "source_only"), ("e-mwd", "matched_with_diff")):
            assert outcomes[exception_id]["outcome"] == "kept"
            assert outcomes[exception_id]["new_type"] == original_type
            assert "resolved_to" not in outcomes[exception_id]

    def test_empty_key_value_is_kept_and_excluded_from_subsets(self) -> None:
        outcomes = _digest(
            [_open_diff("e-empty", "source_only", "")],
            _side_df([("A", "10")]),
            _side_df([("A", "10")]),
        )
        assert outcomes["e-empty"]["outcome"] == "kept"
        assert outcomes["e-empty"]["new_type"] == "source_only"
        assert "resolved_to" not in outcomes["e-empty"]

    def test_one_to_many_target_rows_follow_comparison_buckets(self) -> None:
        """key 在 target 命中 2 行:不抛错,归宿与 _execute_comparison 落桶一致。

        source K:10 vs target [K:10, K:12] → merge 出两行(一行 exact 一行带差)
        → 独占规则按 matched_with_diff 判。
        """
        outcomes = _digest(
            [_open_diff("e-k", "source_only", "K")],
            _side_df([("K", "10")]),
            _side_df([("K", "10"), ("K", "12")]),
        )
        assert outcomes["e-k"]["outcome"] == "reclassified"
        assert outcomes["e-k"]["new_type"] == "matched_with_diff"

    def test_one_to_many_all_equal_rows_resolve(self) -> None:
        """key 在 target 命中 2 行且都与 source 相等 → 全落 matched_exact → resolved。"""
        outcomes = _digest(
            [_open_diff("e-k", "source_only", "K")],
            _side_df([("K", "10")]),
            _side_df([("K", "10"), ("K", "10")]),
        )
        assert outcomes["e-k"]["outcome"] == "resolved"
        assert outcomes["e-k"]["resolved_to"] == "matched"


# ---------------------------------------------------------------------------
# 集成测试:本地真实数据(DB 不可达时 skip)
# ---------------------------------------------------------------------------

ORDER_SCHEME = "scheme_08f821c91f30"
FUND_SCHEME = "scheme_ce2e971481bf"


def _db_connection_or_skip():
    try:
        from db_config import get_db_connection

        conn = get_db_connection()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"本地数据库不可达,跳过集成测试: {exc}")
    return conn


def _fetch_one(conn, sql: str, params: tuple) -> tuple | None:
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()


def _load_scheme_fixture(scheme_code: str) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    conn = _db_connection_or_skip()
    try:
        scheme_row = _fetch_one(
            conn,
            "SELECT proc_rule_code FROM execution_schemes WHERE scheme_code = %s",
            (scheme_code,),
        )
        if not scheme_row or not scheme_row[0]:
            pytest.skip(f"本地缺少 scheme={scheme_code} 配置,跳过")
        proc_rule_code = str(scheme_row[0])

        run_row = _fetch_one(
            conn,
            """
            SELECT id, source_snapshot_json FROM execution_runs
            WHERE scheme_code = %s AND execution_status = 'success'
            ORDER BY created_at DESC LIMIT 1
            """,
            (scheme_code,),
        )
        if not run_row or not run_row[1]:
            pytest.skip(f"本地缺少 scheme={scheme_code} 的成功 run,跳过")
        run_id = str(run_row[0])
        snapshot = run_row[1]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)

        rule_row = _fetch_one(
            conn,
            "SELECT rule FROM rule_detail WHERE rule_code = %s",
            (proc_rule_code,),
        )
        if not rule_row or not rule_row[0]:
            pytest.skip(f"本地缺少 proc 规则 {proc_rule_code},跳过")
        proc_rule_json = rule_row[0]
        if isinstance(proc_rule_json, str):
            proc_rule_json = json.loads(proc_rule_json)
    finally:
        conn.close()
    return {"source_snapshot_json": snapshot}, proc_rule_code, proc_rule_json, run_id


def _fetch_diff_keys(run_id: str, *, anomaly_type: str, limit: int) -> set[str]:
    conn = _db_connection_or_skip()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT detail_json FROM execution_run_exceptions
                WHERE run_id = %s AND anomaly_type = %s
                LIMIT %s
                """,
                (run_id, anomaly_type, limit),
            )
            rows = cur.fetchall() or []
        finally:
            cur.close()
    finally:
        conn.close()
    keys: set[str] = set()
    for (detail,) in rows:
        if isinstance(detail, str):
            detail = json.loads(detail)
        for item in detail.get("join_key") or []:
            for field in ("source_value", "target_value"):
                value = item.get(field)
                if value is not None and str(value).strip():
                    keys.add(str(value).strip())
    return keys


class TestBuildFullReconFramesIntegration:
    """本地真实数据集成测试;DB 不可达时自动 skip。"""
    def test_fund_scheme_pure_collection_full_frames(self) -> None:
        run, proc_rule_code, proc_rule_json, _run_id = _load_scheme_fixture(FUND_SCHEME)
        left_df, right_df, _meta = build_full_recon_frames(
            run=run,
            proc_rule_code=proc_rule_code,
            proc_rule_json=proc_rule_json,
            diff_keys=set(),
        )
        assert not left_df.empty
        assert not right_df.empty
        assert "订单编号" in left_df.columns
        assert "订单号" in right_df.columns

    def test_order_scheme_db_source_with_rename_and_key_pushdown(self) -> None:
        run, proc_rule_code, proc_rule_json, run_id = _load_scheme_fixture(ORDER_SCHEME)
        diff_keys = _fetch_diff_keys(run_id, anomaly_type="source_only", limit=5)
        if not diff_keys:
            pytest.skip("本地缺少订单对账 source_only 差异样本,跳过")
        left_df, _right_df, _meta = build_full_recon_frames(
            run=run,
            proc_rule_code=proc_rule_code,
            proc_rule_json=proc_rule_json,
            diff_keys=diff_keys,
            left_key_field="客户订单号",
            right_key_field="订单编号",
        )
        assert "客户订单号" in left_df.columns
        assert len(left_df) > 0
        found = set(left_df["客户订单号"].map(str)) & diff_keys
        assert found, "下推取回的左侧数据应包含差异 key"

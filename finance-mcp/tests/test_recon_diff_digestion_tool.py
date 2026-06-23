"""差异消化:db 单事务回写 + recon_diff_digestion MCP 工具编排测试。

连本地库造数据(风格参考 test_handoff_session_db.py):
- 造 run + open exceptions,调用 apply_diff_digestion_results,断言回写与 summary 重算。
- 工具 handler 测试 monkeypatch build_full_recon_frames / digest_diffs,不跑真比对。
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

import psycopg2.extras
import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from auth import db as auth_db

# 本地库已有的公司(武汉福游网络科技有限公司),与 test_handoff_session_db.py 一致
COMPANY_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# _digestion_reclassified_detail:纯函数,改判 matched_with_diff 要并入两侧明细
# ---------------------------------------------------------------------------

class TestReclassifiedDetailMerge:
    def test_merges_refreshed_two_sided_detail_for_matched_with_diff(self) -> None:
        stale = _target_only_detail_json("OID-1")
        refreshed = {
            "anomaly_type": "matched_with_diff",
            "detail_unavailable": False,
            "join_key": [
                {
                    "source_field": "订单编号",
                    "source_value": "OID-1",
                    "target_field": "订单号",
                    "target_value": "OID-1",
                }
            ],
            "raw_record": {"source_订单编号": "OID-1", "target_订单号": "OID-1"},
            "source_record": {"订单编号": "OID-1", "金额": "9"},
            "target_record": {"订单号": "OID-1", "金额": "10"},
            "compare_values": [
                {
                    "name": "金额",
                    "source_field": "金额",
                    "source_value": "9",
                    "target_field": "金额",
                    "target_value": "10",
                }
            ],
        }
        out = auth_db._digestion_reclassified_detail(
            stale, "matched_with_diff", refreshed_detail=refreshed
        )
        assert out["anomaly_type"] == "matched_with_diff"
        assert out["display_reclassified"] is True
        # 两侧都被刷新进来,不再是单边残缺
        assert out["source_record"] == {"订单编号": "OID-1", "金额": "9"}
        assert out["target_record"] == {"订单号": "OID-1", "金额": "10"}
        assert out["compare_values"][0]["source_value"] == "9"
        assert out["compare_values"][0]["target_value"] == "10"
        assert out["raw_record"]["source_订单编号"] == "OID-1"
        assert out["detail_unavailable"] is False

    def test_without_refreshed_detail_keeps_old_behavior(self) -> None:
        stale = _target_only_detail_json("OID-2")
        out = auth_db._digestion_reclassified_detail(stale, "source_only")
        assert out["anomaly_type"] == "source_only"
        assert out["display_reclassified"] is True
        # 未提供刷新明细 → 不杜撰,保持原样
        assert out["source_record"] == {"订单编号": None}

_INITIAL_SUMMARY = {
    "matched_exact": 10,
    "matched_with_diff": 0,
    "source_only": 2,
    "target_only": 1,
    "total_records": 13,
    "has_anomaly": True,
}


# ---------------------------------------------------------------------------
# 造数 / 查数 helpers(真实本地库)
# ---------------------------------------------------------------------------

def _create_run(
    *,
    scheme_code: str = "",
    summary: dict | None = None,
    source_snapshot_json: dict | None = None,
) -> str:
    scheme_code = scheme_code or f"scheme-digestion-{uuid.uuid4().hex[:8]}"
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_runs (
                    company_id, run_code, scheme_code, scheme_type,
                    trigger_type, entry_mode, execution_status,
                    recon_result_summary_json, source_snapshot_json, anomaly_count
                ) VALUES (%s, %s, %s, 'recon', 'manual', 'dataset', 'success', %s::jsonb, %s::jsonb, 3)
                RETURNING id
                """,
                (
                    COMPANY_ID,
                    f"run-digestion-{uuid.uuid4().hex[:12]}",
                    scheme_code,
                    psycopg2.extras.Json(summary if summary is not None else _INITIAL_SUMMARY),
                    psycopg2.extras.Json(source_snapshot_json or {}),
                ),
            )
            run_id = str(cur.fetchone()[0])
        conn.commit()
    return run_id


def _detail_json(key_value: str) -> dict:
    """真实 detail_json 结构(_build_anomaly_rows 写入,本地库 9215 条全部顶层 join_key)。"""
    return {
        "join_key": [
            {
                "source_field": "订单编号",
                "source_value": key_value,
                "target_field": "订单号",
                "target_value": key_value,
            }
        ],
        "anomaly_type": "source_only",
        "raw_record": {},
    }


def _target_only_detail_json(key_value: str) -> dict:
    return {
        "join_key": [
            {
                "source_field": "订单编号",
                "source_value": None,
                "target_field": "订单号",
                "target_value": key_value,
            }
        ],
        "anomaly_type": "target_only",
        "raw_record": {
            "source_订单编号": None,
            "target_订单号": key_value,
        },
        "source_record": {"订单编号": None},
        "target_record": {"订单号": key_value},
        "compare_values": [
            {
                "name": "买家实付金额 ↔ 订单实际金额（元）",
                "source_field": "买家实付金额",
                "source_value": None,
                "target_field": "订单实际金额（元）",
                "target_value": "0",
            }
        ],
    }


def _create_exception(
    run_id: str,
    *,
    anomaly_key: str,
    anomaly_type: str,
    summary: str | None = None,
    detail_json: dict | None = None,
    scheme_code: str = "scheme-digestion",
) -> str:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_run_exceptions (
                    company_id, run_id, scheme_code, anomaly_key, anomaly_type,
                    summary, detail_json, is_closed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, false)
                RETURNING id
                """,
                (
                    COMPANY_ID,
                    run_id,
                    scheme_code,
                    anomaly_key,
                    anomaly_type,
                    summary or f"差异 {anomaly_key}",
                    psycopg2.extras.Json(
                        detail_json if detail_json is not None else _detail_json(anomaly_key)
                    ),
                ),
            )
            exception_id = str(cur.fetchone()[0])
        conn.commit()
    return exception_id


def _fetch_run(run_id: str) -> dict:
    with auth_db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT recon_result_summary_json, resolution_summary_json,
                       review_round, last_resolved_at, anomaly_count
                FROM execution_runs WHERE id = %s
                """,
                (run_id,),
            )
            row = cur.fetchone()
    assert row is not None, f"run {run_id} 不存在"
    return dict(row)


def _fetch_exception(exception_id: str) -> dict:
    with auth_db.get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT anomaly_type, is_closed, processing_status, fix_status,
                       review_round, resolved_at, resolved_to, summary, detail_json
                FROM execution_run_exceptions WHERE id = %s
                """,
                (exception_id,),
            )
            row = cur.fetchone()
    assert row is not None, f"exception {exception_id} 不存在"
    return dict(row)


def _list_exception_ids(run_id: str, *, include_closed: bool = False) -> list[str]:
    rows = auth_db.list_execution_run_exceptions(
        company_id=COMPANY_ID,
        run_id=run_id,
        include_closed=include_closed,
    )
    return [str(row["id"]) for row in rows]


def _delete_run(run_id: str) -> None:
    """删除 run(exceptions 走 ON DELETE CASCADE)。"""
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM execution_runs WHERE id = %s", (run_id,))
        conn.commit()


@pytest.fixture
def digestion_run():
    """造 1 run + 3 open exceptions(2 source_only + 1 target_only),用完清理。"""
    run_id = _create_run()
    exc_resolved = _create_exception(run_id, anomaly_key="key-1", anomaly_type="source_only")
    exc_reclassified = _create_exception(run_id, anomaly_key="key-2", anomaly_type="source_only")
    exc_kept = _create_exception(run_id, anomaly_key="key-3", anomaly_type="target_only")
    try:
        yield {
            "run_id": run_id,
            "resolved": exc_resolved,
            "reclassified": exc_reclassified,
            "kept": exc_kept,
        }
    finally:
        _delete_run(run_id)


# ---------------------------------------------------------------------------
# 提交 1:apply_diff_digestion_results 单事务回写
# ---------------------------------------------------------------------------

class TestApplyDiffDigestionResults:
    def test_mixed_outcomes_writeback_and_summary_recompute(self, digestion_run) -> None:
        run_id = digestion_run["run_id"]
        results = [
            {
                "exception_id": digestion_run["resolved"],
                "outcome": "resolved",
                "new_type": "matched",
                "resolved_to": "matched",
            },
            {
                "exception_id": digestion_run["reclassified"],
                "outcome": "reclassified",
                "new_type": "matched_with_diff",
                "resolved_to": "matched_with_diff",
            },
            {
                "exception_id": digestion_run["kept"],
                "outcome": "kept",
                "new_type": "target_only",
            },
        ]
        meta = {"fetch_degraded": False, "failed_batches": 0, "dedup_mode": "keep_latest"}

        outcome = auth_db.apply_diff_digestion_results(
            run_id=run_id, results=results, review_round=1, digestion_meta=meta
        )

        assert outcome["resolved"] == 1
        assert outcome["reclassified"] == 1
        assert outcome["kept"] == 1
        assert outcome["open_counts"] == {
            "source_only": 0,
            "target_only": 1,
            "matched_with_diff": 1,
        }

        # resolved → 关闭 + 审计字段
        resolved_row = _fetch_exception(digestion_run["resolved"])
        assert resolved_row["is_closed"] is True
        assert resolved_row["fix_status"] == "resolved_by_digestion"
        assert resolved_row["processing_status"] == "verified_closed"
        assert resolved_row["resolved_to"] == "matched"
        assert resolved_row["resolved_at"] is not None
        assert resolved_row["review_round"] == 1

        # reclassified → 改类型保持 open
        reclassified_row = _fetch_exception(digestion_run["reclassified"])
        assert reclassified_row["is_closed"] is False
        assert reclassified_row["anomaly_type"] == "matched_with_diff"
        assert reclassified_row["resolved_to"] == "matched_with_diff"
        assert reclassified_row["review_round"] == 1

        # kept → 只 +轮次
        kept_row = _fetch_exception(digestion_run["kept"])
        assert kept_row["is_closed"] is False
        assert kept_row["anomaly_type"] == "target_only"
        assert kept_row["review_round"] == 1
        assert kept_row["resolved_at"] is None

        # run summary 重算:只动三个差异键 + has_anomaly;matched_exact/total_records 不动
        run_row = _fetch_run(run_id)
        summary = run_row["recon_result_summary_json"]
        assert summary["source_only"] == 0
        assert summary["target_only"] == 1
        assert summary["matched_with_diff"] == 1
        assert summary["has_anomaly"] is True
        assert summary["matched_exact"] == _INITIAL_SUMMARY["matched_exact"]
        assert summary["total_records"] == _INITIAL_SUMMARY["total_records"]

        assert run_row["review_round"] == 1
        assert run_row["last_resolved_at"] is not None
        # anomaly_count 必须同步更新为剩余 open 差异数(前端看板读此列)

        assert _list_exception_ids(run_id) == [
            digestion_run["kept"],
            digestion_run["reclassified"],
        ]
        assert set(_list_exception_ids(run_id, include_closed=True)) == {
            digestion_run["resolved"],
            digestion_run["reclassified"],
            digestion_run["kept"],
        }
        assert run_row["anomaly_count"] == 2  # target_only(1) + matched_with_diff(1)
        resolution = run_row["resolution_summary_json"]
        assert resolution["resolved"] == 1
        assert resolution["reclassified"] == 1
        assert resolution["kept"] == 1
        assert resolution["by_type"] == {
            "source_only": 0,
            "target_only": 1,
            "matched_with_diff": 1,
        }
        assert resolution["digestion_meta"] == meta
        assert resolution.get("at")

    def test_reclassified_exception_updates_display_snapshot(self) -> None:
        run_id = _create_run(
            source_snapshot_json={
                "collections": [
                    {
                        "binding": {
                            "role_code": "left_1",
                            "input_plan_target_table": "left_recon_ready",
                            "display_name": "博宽服务专营店-店铺订单",
                        }
                    },
                    {
                        "binding": {
                            "role_code": "right_1",
                            "input_plan_target_table": "right_recon_ready",
                            "display_name": "博宽服务专营店-收支明细",
                        }
                    },
                ]
            }
        )
        exception_id = _create_exception(
            run_id,
            anomaly_key="stale-target-only-key",
            anomaly_type="target_only",
            summary="仅 收支明细 存在（店铺订单 缺失）：订单号=3306514334587002794",
            detail_json=_target_only_detail_json("3306514334587002794"),
        )
        try:
            auth_db.apply_diff_digestion_results(
                run_id=run_id,
                results=[
                    {
                        "exception_id": exception_id,
                        "outcome": "reclassified",
                        "new_type": "matched_with_diff",
                        "resolved_to": "matched_with_diff",
                    }
                ],
                review_round=1,
            )

            row = _fetch_exception(exception_id)
            assert row["anomaly_type"] == "matched_with_diff"
            assert row["detail_json"]["anomaly_type"] == "matched_with_diff"
            assert "仅 收支明细 存在" not in row["summary"]
            assert "博宽服务专营店-店铺订单 与 博宽服务专营店-收支明细" in row["summary"]
            assert "金额差异" in row["summary"]
            assert "3306514334587002794" in row["summary"]
        finally:
            _delete_run(run_id)

    def test_reclassify_merges_refreshed_two_sided_detail(self) -> None:
        """改判 matched_with_diff 带 refreshed_detail 时,详情两侧齐全(修复单边残缺)。"""
        run_id = _create_run()
        exception_id = _create_exception(
            run_id,
            anomaly_key="td-key",
            anomaly_type="target_only",
            detail_json=_target_only_detail_json("OID-9"),
        )
        try:
            auth_db.apply_diff_digestion_results(
                run_id=run_id,
                results=[
                    {
                        "exception_id": exception_id,
                        "outcome": "reclassified",
                        "new_type": "matched_with_diff",
                        "resolved_to": "matched_with_diff",
                        "refreshed_detail": {
                            "anomaly_type": "matched_with_diff",
                            "detail_unavailable": False,
                            "join_key": [
                                {
                                    "source_field": "订单编号",
                                    "source_value": "OID-9",
                                    "target_field": "订单号",
                                    "target_value": "OID-9",
                                }
                            ],
                            "raw_record": {"source_金额": "9", "target_金额": "10"},
                            "source_record": {"订单编号": "OID-9", "金额": "9"},
                            "target_record": {"订单号": "OID-9", "金额": "10"},
                            "compare_values": [
                                {
                                    "name": "金额",
                                    "source_field": "金额",
                                    "source_value": "9",
                                    "target_field": "金额",
                                    "target_value": "10",
                                }
                            ],
                        },
                    }
                ],
                review_round=1,
            )
            row = _fetch_exception(exception_id)
            detail = row["detail_json"]
            assert detail["anomaly_type"] == "matched_with_diff"
            assert detail["display_reclassified"] is True
            # 两侧都有数据,不再是"金额不一致却只有一边"
            assert detail["source_record"] == {"订单编号": "OID-9", "金额": "9"}
            assert detail["target_record"] == {"订单号": "OID-9", "金额": "10"}
            assert detail["compare_values"][0]["source_value"] == "9"
            assert detail["compare_values"][0]["target_value"] == "10"
        finally:
            _delete_run(run_id)

    def test_second_round_all_resolved_clears_has_anomaly(self, digestion_run) -> None:
        run_id = digestion_run["run_id"]
        # 第一轮:resolved/reclassified/kept 各一
        auth_db.apply_diff_digestion_results(
            run_id=run_id,
            results=[
                {
                    "exception_id": digestion_run["resolved"],
                    "outcome": "resolved",
                    "new_type": "matched",
                    "resolved_to": "matched",
                },
                {
                    "exception_id": digestion_run["reclassified"],
                    "outcome": "reclassified",
                    "new_type": "matched_with_diff",
                    "resolved_to": "matched_with_diff",
                },
                {
                    "exception_id": digestion_run["kept"],
                    "outcome": "kept",
                    "new_type": "target_only",
                },
            ],
            review_round=1,
        )
        # 第二轮:剩余 2 条全 resolved
        outcome = auth_db.apply_diff_digestion_results(
            run_id=run_id,
            results=[
                {
                    "exception_id": digestion_run["reclassified"],
                    "outcome": "resolved",
                    "new_type": "matched",
                    "resolved_to": "matched",
                },
                {
                    "exception_id": digestion_run["kept"],
                    "outcome": "resolved",
                    "new_type": "matched",
                    "resolved_to": "matched",
                },
            ],
            review_round=2,
            digestion_meta={"fetch_degraded": True},
        )

        assert outcome["resolved"] == 2
        assert outcome["open_counts"] == {
            "source_only": 0,
            "target_only": 0,
            "matched_with_diff": 0,
        }
        run_row = _fetch_run(run_id)
        summary = run_row["recon_result_summary_json"]
        assert summary["has_anomaly"] is False
        assert summary["source_only"] == 0
        assert summary["target_only"] == 0
        assert summary["matched_with_diff"] == 0
        assert summary["matched_exact"] == _INITIAL_SUMMARY["matched_exact"]
        assert summary["total_records"] == _INITIAL_SUMMARY["total_records"]
        assert run_row["review_round"] == 2
        # 全 resolved 后 anomaly_count 必须归零
        assert run_row["anomaly_count"] == 0
        resolution = run_row["resolution_summary_json"]
        assert resolution["digestion_meta"] == {"fetch_degraded": True}

        for key in ("reclassified", "kept"):
            row = _fetch_exception(digestion_run[key])
            assert row["is_closed"] is True
            assert row["fix_status"] == "resolved_by_digestion"
            assert row["review_round"] == 2

    def test_run_get_exposes_digestion_fields(self, digestion_run) -> None:
        """前端轮询靠 review_round 变化判断完成,run 查询白名单必须透出新字段。"""
        run = auth_db.get_execution_run(company_id=COMPANY_ID, run_id=digestion_run["run_id"])
        assert run is not None
        for field in ("review_round", "last_resolved_at", "resolution_summary_json"):
            assert field in run, f"get_execution_run 缺少字段 {field}"
        runs = auth_db.list_execution_runs(company_id=COMPANY_ID, scheme_code=run["scheme_code"])
        assert runs, "list_execution_runs 未返回测试 run"
        for field in ("review_round", "last_resolved_at", "resolution_summary_json"):
            assert field in runs[0], f"list_execution_runs 缺少字段 {field}"

    def test_unknown_exception_id_rolls_back_whole_batch(self, digestion_run) -> None:
        """单事务:任一条回写未命中 → 整批回滚,不留半套状态。"""
        run_id = digestion_run["run_id"]
        with pytest.raises(Exception):
            auth_db.apply_diff_digestion_results(
                run_id=run_id,
                results=[
                    {
                        "exception_id": digestion_run["resolved"],
                        "outcome": "resolved",
                        "new_type": "matched",
                        "resolved_to": "matched",
                    },
                    {
                        "exception_id": str(uuid.uuid4()),
                        "outcome": "kept",
                        "new_type": "source_only",
                    },
                ],
                review_round=1,
            )
        # 第一条不应被提交
        row = _fetch_exception(digestion_run["resolved"])
        assert row["is_closed"] is False
        assert row["review_round"] == 0
        run_row = _fetch_run(run_id)
        assert run_row["review_round"] == 0
        assert run_row["recon_result_summary_json"]["source_only"] == 2


# ---------------------------------------------------------------------------
# 提交 2:recon_diff_digestion MCP 工具编排
# ---------------------------------------------------------------------------

RECON_RULE_JSON = {
    "rule_id": "rule-digestion",
    "rules": [
        {
            "rule_id": "rule-digestion",
            "recon": {
                "key_columns": {
                    "mappings": [{"source_field": "订单编号", "target_field": "订单号"}],
                    "source_field": "订单编号",
                    "target_field": "订单号",
                    "transformations": {},
                },
                "compare_columns": {
                    "columns": [
                        {"source_field": "买家实付金额", "target_field": "订单实际金额（元）"}
                    ]
                },
            },
        }
    ],
}

PROC_RULE_JSON = {"steps": []}


def _create_rule(rule_code: str, rule_json: dict, rule_type: str) -> None:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rule_detail (id, rule_code, rule, rule_type, name)
                VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM rule_detail), %s, %s::jsonb, %s, %s)
                """,
                (rule_code, psycopg2.extras.Json(rule_json), rule_type, f"消化测试规则 {rule_code}"),
            )
        conn.commit()


def _delete_rule(rule_code: str) -> None:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rule_detail WHERE rule_code = %s", (rule_code,))
        conn.commit()


def _create_scheme(scheme_code: str, proc_rule_code: str, recon_rule_code: str) -> None:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_schemes (
                    company_id, scheme_code, scheme_name, scheme_type,
                    proc_rule_code, recon_rule_code
                ) VALUES (%s, %s, %s, 'recon', %s, %s)
                """,
                (COMPANY_ID, scheme_code, f"消化测试方案 {scheme_code}", proc_rule_code, recon_rule_code),
            )
        conn.commit()


def _delete_scheme(scheme_code: str) -> None:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM execution_schemes WHERE company_id = %s AND scheme_code = %s",
                (COMPANY_ID, scheme_code),
            )
        conn.commit()


@pytest.fixture
def digestion_tool_setup():
    """run + scheme + proc/recon rule + 3 条 open exceptions(覆盖 key 回退链)。"""
    suffix = uuid.uuid4().hex[:8]
    scheme_code = f"scheme-dd-{suffix}"
    proc_rule_code = f"dataset_proc_dd_{suffix}"
    recon_rule_code = f"dataset_recon_dd_{suffix}"
    _create_rule(proc_rule_code, PROC_RULE_JSON, "data_process")
    _create_rule(recon_rule_code, RECON_RULE_JSON, "recon")
    _create_scheme(scheme_code, proc_rule_code, recon_rule_code)
    run_id = _create_run(scheme_code=scheme_code)
    # e1: join_key[0].source_value 直取
    exc_source = _create_exception(
        run_id,
        anomaly_key="A1",
        anomaly_type="source_only",
        scheme_code=scheme_code,
        detail_json={
            "join_key": [
                {
                    "source_field": "订单编号",
                    "source_value": "A1",
                    "target_field": "订单号",
                    "target_value": None,
                }
            ]
        },
    )
    # e2: source_value 为空 → 回退 target_value(target_only 真实形态)
    exc_target = _create_exception(
        run_id,
        anomaly_key="B2-anomaly-key",
        anomaly_type="target_only",
        scheme_code=scheme_code,
        detail_json={
            "join_key": [
                {
                    "source_field": "订单编号",
                    "source_value": None,
                    "target_field": "订单号",
                    "target_value": "B2",
                }
            ]
        },
    )
    # e3: join_key 缺失 → 回退顶层 anomaly_key
    exc_fallback = _create_exception(
        run_id,
        anomaly_key="C3",
        anomaly_type="matched_with_diff",
        scheme_code=scheme_code,
        detail_json={"join_key": []},
    )
    try:
        yield {
            "run_id": run_id,
            "scheme_code": scheme_code,
            "proc_rule_code": proc_rule_code,
            "recon_rule_code": recon_rule_code,
            "exc_source": exc_source,
            "exc_target": exc_target,
            "exc_fallback": exc_fallback,
        }
    finally:
        _delete_run(run_id)
        _delete_scheme(scheme_code)
        _delete_rule(proc_rule_code)
        _delete_rule(recon_rule_code)


def _import_tool_modules():
    from recon.mcp_server import diff_digestion
    from tools import execution_runs

    return execution_runs, diff_digestion


def _bypass_worker_auth(monkeypatch, execution_runs_module) -> None:
    monkeypatch.setattr(
        execution_runs_module,
        "_require_scheduler_user",
        lambda token: {"id": "worker-1", "role": "scheduler"},
    )


class TestReconDiffDigestionTool:
    def test_tool_registered_and_routable(self) -> None:
        execution_runs, _ = _import_tool_modules()
        tools = {tool.name: tool for tool in execution_runs.create_tools()}
        assert "recon_diff_digestion" in tools, "recon_diff_digestion 工具未注册"
        schema = tools["recon_diff_digestion"].inputSchema
        assert set(schema.get("required") or []) == {"worker_token", "run_id"}

        import unified_mcp_server

        assert "recon_diff_digestion" in unified_mcp_server._EXECUTION_TOOL_NAMES, (
            "recon_diff_digestion 未加入 _EXECUTION_TOOL_NAMES,unified 路由不到"
        )

    @pytest.mark.asyncio
    async def test_orchestration_happy_path(self, monkeypatch, digestion_tool_setup) -> None:
        execution_runs, diff_digestion = _import_tool_modules()
        _bypass_worker_auth(monkeypatch, execution_runs)
        setup = digestion_tool_setup
        captured: dict[str, Any] = {}

        import pandas as pd

        meta = {
            "fetch_degraded": False,
            "fallback_full_fetch_sides": [],
            "failed_batches": 0,
            "dedup_mode": "keep_latest",
        }

        def fake_build_full_recon_frames(**kwargs):
            captured["build_kwargs"] = kwargs
            return pd.DataFrame(), pd.DataFrame(), dict(meta)

        def fake_digest_diffs(**kwargs):
            captured["digest_kwargs"] = kwargs
            by_id = {
                setup["exc_source"]: ("resolved", "matched", "matched"),
                setup["exc_target"]: ("reclassified", "source_only", "source_only"),
                setup["exc_fallback"]: ("kept", "matched_with_diff", None),
            }
            results = []
            for diff in kwargs["open_diffs"]:
                outcome, new_type, resolved_to = by_id[diff["exception_id"]]
                entry = {**diff, "outcome": outcome, "new_type": new_type}
                if resolved_to is not None:
                    entry["resolved_to"] = resolved_to
                results.append(entry)
            return results

        monkeypatch.setattr(diff_digestion, "build_full_recon_frames", fake_build_full_recon_frames)
        monkeypatch.setattr(diff_digestion, "digest_diffs", fake_digest_diffs)

        result = await execution_runs.handle_tool_call(
            "recon_diff_digestion",
            {"worker_token": "worker-token", "run_id": setup["run_id"]},
        )

        assert result.get("success") is True, f"工具应成功,实际: {result}"
        assert result["resolved"] == 1
        assert result["reclassified"] == 1
        assert result["kept"] == 1
        assert result["fetch_degraded"] is False
        assert result["open_counts"]["source_only"] == 1  # exc_target 被改判 source_only
        assert result["open_counts"]["matched_with_diff"] == 1

        # exceptions → open_diffs 转换(含 key 回退链)
        open_diffs = captured["digest_kwargs"]["open_diffs"]
        by_id = {diff["exception_id"]: diff for diff in open_diffs}
        assert by_id[setup["exc_source"]]["anomaly_type"] == "source_only"
        assert by_id[setup["exc_source"]]["key"] == {"订单编号": "A1"}
        assert by_id[setup["exc_target"]]["key"] == {"订单编号": "B2"}
        assert by_id[setup["exc_fallback"]]["key"] == {"订单编号": "C3"}

        # build_full_recon_frames 入参
        build_kwargs = captured["build_kwargs"]
        assert build_kwargs["proc_rule_code"] == setup["proc_rule_code"]
        assert build_kwargs["proc_rule_json"] == PROC_RULE_JSON
        assert build_kwargs["diff_keys"] == {"A1", "B2", "C3"}
        assert build_kwargs["left_key_field"] == "订单编号"
        assert build_kwargs["right_key_field"] == "订单号"
        assert str(build_kwargs["run"]["id"]) == setup["run_id"]

        # digest_diffs 入参取自 recon 规则
        digest_kwargs = captured["digest_kwargs"]
        assert digest_kwargs["key_mappings"] == [
            {"source_field": "订单编号", "target_field": "订单号"}
        ]
        assert digest_kwargs["compare_columns_config"] == (
            RECON_RULE_JSON["rules"][0]["recon"]["compare_columns"]["columns"]
        )
        assert digest_kwargs["key_columns_config"] == (
            RECON_RULE_JSON["rules"][0]["recon"]["key_columns"]
        )
        assert digest_kwargs["rule_id"] == setup["recon_rule_code"]

        # 回写落库(review_round=run.review_round+1=1)
        resolved_row = _fetch_exception(setup["exc_source"])
        assert resolved_row["is_closed"] is True
        assert resolved_row["fix_status"] == "resolved_by_digestion"
        assert resolved_row["review_round"] == 1
        run_row = _fetch_run(setup["run_id"])
        assert run_row["review_round"] == 1
        assert result.get("review_round") == 1

    @pytest.mark.asyncio
    async def test_digest_value_error_becomes_failure(
        self, monkeypatch, digestion_tool_setup
    ) -> None:
        """digest_diffs 的守卫 ValueError 必须转 success:False,不得吞掉、不得回写。"""
        execution_runs, diff_digestion = _import_tool_modules()
        _bypass_worker_auth(monkeypatch, execution_runs)
        setup = digestion_tool_setup

        import pandas as pd

        monkeypatch.setattr(
            diff_digestion,
            "build_full_recon_frames",
            lambda **kwargs: (pd.DataFrame(), pd.DataFrame(), {"fetch_degraded": False}),
        )

        def raising_digest(**kwargs):
            raise ValueError("差异消化暂不支持复合 join key 规则(key_mappings>1)")

        monkeypatch.setattr(diff_digestion, "digest_diffs", raising_digest)

        result = await execution_runs.handle_tool_call(
            "recon_diff_digestion",
            {"worker_token": "worker-token", "run_id": setup["run_id"]},
        )

        assert result.get("success") is False
        assert "复合 join key" in str(result.get("error") or "")
        # 不应有任何回写
        row = _fetch_exception(setup["exc_source"])
        assert row["is_closed"] is False
        assert row["review_round"] == 0
        assert _fetch_run(setup["run_id"])["review_round"] == 0

    @pytest.mark.asyncio
    async def test_no_open_exceptions_short_circuit(self, monkeypatch) -> None:
        execution_runs, diff_digestion = _import_tool_modules()
        _bypass_worker_auth(monkeypatch, execution_runs)
        suffix = uuid.uuid4().hex[:8]
        scheme_code = f"scheme-dd-{suffix}"
        proc_rule_code = f"dataset_proc_dd_{suffix}"
        recon_rule_code = f"dataset_recon_dd_{suffix}"
        _create_rule(proc_rule_code, PROC_RULE_JSON, "data_process")
        _create_rule(recon_rule_code, RECON_RULE_JSON, "recon")
        _create_scheme(scheme_code, proc_rule_code, recon_rule_code)
        run_id = _create_run(scheme_code=scheme_code)

        def must_not_call(**kwargs):
            raise AssertionError("open=0 时不应取数/重判")

        monkeypatch.setattr(diff_digestion, "build_full_recon_frames", must_not_call)
        monkeypatch.setattr(diff_digestion, "digest_diffs", must_not_call)
        try:
            result = await execution_runs.handle_tool_call(
                "recon_diff_digestion",
                {"worker_token": "worker-token", "run_id": run_id},
            )
        finally:
            _delete_run(run_id)
            _delete_scheme(scheme_code)
            _delete_rule(proc_rule_code)
            _delete_rule(recon_rule_code)

        assert result.get("success") is True
        assert result["resolved"] == 0
        assert result["reclassified"] == 0
        assert result["kept"] == 0
        assert "无未关闭差异" in str(result.get("message") or "")

    @pytest.mark.asyncio
    async def test_missing_run_id_fails(self, monkeypatch) -> None:
        execution_runs, _ = _import_tool_modules()
        _bypass_worker_auth(monkeypatch, execution_runs)
        result = await execution_runs.handle_tool_call(
            "recon_diff_digestion", {"worker_token": "worker-token"}
        )
        assert result.get("success") is False
        assert "run_id" in str(result.get("error") or "")

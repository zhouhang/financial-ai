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

def _create_run(*, scheme_code: str = "", summary: dict | None = None) -> str:
    scheme_code = scheme_code or f"scheme-digestion-{uuid.uuid4().hex[:8]}"
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_runs (
                    company_id, run_code, scheme_code, scheme_type,
                    trigger_type, entry_mode, execution_status,
                    recon_result_summary_json, anomaly_count
                ) VALUES (%s, %s, %s, 'recon', 'manual', 'dataset', 'success', %s::jsonb, 3)
                RETURNING id
                """,
                (
                    COMPANY_ID,
                    f"run-digestion-{uuid.uuid4().hex[:12]}",
                    scheme_code,
                    psycopg2.extras.Json(summary if summary is not None else _INITIAL_SUMMARY),
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


def _create_exception(
    run_id: str,
    *,
    anomaly_key: str,
    anomaly_type: str,
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
                    f"差异 {anomaly_key}",
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
                SELECT anomaly_type, is_closed, fix_status,
                       review_round, resolved_at, resolved_to
                FROM execution_run_exceptions WHERE id = %s
                """,
                (exception_id,),
            )
            row = cur.fetchone()
    assert row is not None, f"exception {exception_id} 不存在"
    return dict(row)


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
        resolution = run_row["resolution_summary_json"]
        assert resolution["digestion_meta"] == {"fetch_degraded": True}

        for key in ("reclassified", "kept"):
            row = _fetch_exception(digestion_run[key])
            assert row["is_closed"] is True
            assert row["fix_status"] == "resolved_by_digestion"
            assert row["review_round"] == 2

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

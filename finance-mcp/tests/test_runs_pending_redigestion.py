"""list_runs_pending_redigestion:回填消化 sweep 选 run(真实本地库)。

窗口内、execution_status='success'、仍有 open 异常、且有 plan_code 的 run 才返回;
不按 scheme/平台过滤(回填消化对所有对账任务统一生效)。
"""
import uuid

import psycopg2.extras

import auth.db as auth_db

COMPANY_ID = "00000000-0000-0000-0000-000000000001"


def _mk_run(*, biz_date: str, plan_code: str | None, status: str = "success") -> str:
    scheme_code = f"scheme-redigest-{uuid.uuid4().hex[:8]}"
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_runs (
                    company_id, run_code, scheme_code, plan_code, scheme_type,
                    trigger_type, entry_mode, execution_status,
                    run_context_json, anomaly_count
                ) VALUES (%s, %s, %s, %s, 'recon', 'schedule', 'dataset', %s, %s::jsonb, 0)
                RETURNING id
                """,
                (
                    COMPANY_ID,
                    f"run-{uuid.uuid4().hex[:8]}",
                    scheme_code,
                    plan_code,
                    status,
                    psycopg2.extras.Json({"biz_date": biz_date}),
                ),
            )
            run_id = str(cur.fetchone()[0])
        conn.commit()
    return run_id


def _add_exc(run_id: str, *, is_closed: bool) -> None:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_run_exceptions (
                    company_id, run_id, scheme_code, anomaly_key, anomaly_type, is_closed
                ) VALUES (%s, %s, 'scheme-redigest', %s, 'source_only', %s)
                """,
                (COMPANY_ID, run_id, f"k-{uuid.uuid4().hex[:6]}", is_closed),
            )
        conn.commit()


def _del(run_id: str) -> None:
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM execution_runs WHERE id = %s", (run_id,))
        conn.commit()


def _ids(rows: list[dict]) -> set[str]:
    return {str(r["run_id"]) for r in rows}


def test_returns_success_run_with_open_exception_in_window() -> None:
    run_id = _mk_run(biz_date="2026-06-20", plan_code="plan-redigest-1")
    _add_exc(run_id, is_closed=False)
    try:
        rows = auth_db.list_runs_pending_redigestion(
            company_id=COMPANY_ID, since_date="2026-06-10"
        )
        match = [r for r in rows if str(r["run_id"]) == run_id]
        assert match, "窗口内 success+open 异常的 run 应返回"
        assert match[0]["plan_code"] == "plan-redigest-1"
        assert match[0]["biz_date"] == "2026-06-20"
    finally:
        _del(run_id)


def test_excludes_run_with_only_closed_exceptions() -> None:
    run_id = _mk_run(biz_date="2026-06-20", plan_code="plan-redigest-2")
    _add_exc(run_id, is_closed=True)
    try:
        rows = auth_db.list_runs_pending_redigestion(
            company_id=COMPANY_ID, since_date="2026-06-10"
        )
        assert run_id not in _ids(rows), "无 open 异常的 run 不应返回"
    finally:
        _del(run_id)


def test_excludes_out_of_window_run() -> None:
    run_id = _mk_run(biz_date="2026-06-01", plan_code="plan-redigest-3")
    _add_exc(run_id, is_closed=False)
    try:
        rows = auth_db.list_runs_pending_redigestion(
            company_id=COMPANY_ID, since_date="2026-06-10"
        )
        assert run_id not in _ids(rows), "biz_date < since_date 的 run 不应返回"
    finally:
        _del(run_id)


def test_excludes_failed_run() -> None:
    run_id = _mk_run(biz_date="2026-06-20", plan_code="plan-redigest-4", status="failed")
    _add_exc(run_id, is_closed=False)
    try:
        rows = auth_db.list_runs_pending_redigestion(
            company_id=COMPANY_ID, since_date="2026-06-10"
        )
        assert run_id not in _ids(rows), "未成功的 run 不应返回"
    finally:
        _del(run_id)


def test_excludes_run_without_plan_code() -> None:
    run_id = _mk_run(biz_date="2026-06-20", plan_code=None)
    _add_exc(run_id, is_closed=False)
    try:
        rows = auth_db.list_runs_pending_redigestion(
            company_id=COMPANY_ID, since_date="2026-06-10"
        )
        assert run_id not in _ids(rows), "缺 plan_code 无法入队 resolve,不应返回"
    finally:
        _del(run_id)

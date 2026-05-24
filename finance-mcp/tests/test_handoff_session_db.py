from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import auth.db as auth_db


def test_ensure_schema_creates_handoff_table():
    auth_db.ensure_browser_handoff_schema()
    with auth_db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('public.browser_handoff_sessions')")
            assert cur.fetchone()[0] is not None


import uuid


def _new_id():
    return str(uuid.uuid4())


def test_insert_get_and_mark_handoff_session():
    auth_db.ensure_browser_handoff_schema()
    sj = _new_id()
    row = auth_db.insert_handoff_session(
        company_id="00000000-0000-0000-0000-000000000001",
        sync_job_id=sj, data_source_id=None, agent_id="browser-agent-local",
        profile_key="shop-x", reason="RISK_VERIFICATION", channel_config_id=None,
        expires_in_seconds=900,
    )
    hid = row["id"]
    got = auth_db.get_handoff_session(handoff_session_id=hid)
    assert got and got["status"] == "pending" and str(got["sync_job_id"]) == sj
    updated = auth_db.mark_handoff_session_status(handoff_session_id=hid, status="completed")
    assert updated["status"] == "completed" and updated["completed_at"] is not None


def test_set_browser_sync_job_status_no_throw():
    res = auth_db.set_browser_sync_job_status(sync_job_id=_new_id(), status="waiting_human_verification")
    assert res in (0, 1)  # nonexistent id -> 0 rows; existing -> 1; must not raise

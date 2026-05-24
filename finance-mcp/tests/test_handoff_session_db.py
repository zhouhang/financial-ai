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

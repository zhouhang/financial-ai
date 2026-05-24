from __future__ import annotations
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth.handoff_token import build_handoff_token, verify_handoff_token


def test_roundtrip_ok():
    tok = build_handoff_token(handoff_session_id="hs-1", company_id="c1", ttl_seconds=600)
    payload = verify_handoff_token(tok)
    assert payload is not None
    assert payload["handoff_session_id"] == "hs-1"
    assert payload["company_id"] == "c1"


def test_wrong_purpose_or_garbage_rejected():
    import jwt, os
    secret = os.getenv("JWT_SECRET", "tally-secret-change-in-production")
    bad = jwt.encode({"purpose": "other", "handoff_session_id": "x"}, secret, algorithm="HS256")
    assert verify_handoff_token(bad) is None
    assert verify_handoff_token("not-a-jwt") is None
    assert verify_handoff_token("") is None


def test_expired_rejected():
    tok = build_handoff_token(handoff_session_id="hs-2", company_id="c1", ttl_seconds=1)
    time.sleep(2)
    assert verify_handoff_token(tok) is None

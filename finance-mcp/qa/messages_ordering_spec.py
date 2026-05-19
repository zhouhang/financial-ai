from __future__ import annotations

from datetime import datetime, timedelta

import psycopg2
import pytest

from auth.db import create_conversation, delete_conversation, get_conn, get_messages


def _first_user_id() -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users LIMIT 1")
            row = cur.fetchone()
            return str(row[0]) if row else None


def test_get_messages_orders_by_seq_not_created_at() -> None:
    """get_messages 必须按插入顺序(seq)返回消息,与 created_at 无关。

    构造场景:按 msg-0..msg-4 顺序插入,但把 created_at 故意设为递减。
    旧实现 ORDER BY created_at ASC 会把顺序反转;
    修复后 ORDER BY seq ASC 应保持插入顺序。
    这同时覆盖了真实根因——多条消息 created_at 并列时排序不确定。
    """
    try:
        user_id = _first_user_id()
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        pytest.skip("数据库不可用，跳过会话顺序集成测试")

    if not user_id:
        pytest.skip("users 表为空，无法创建测试会话")

    conv = create_conversation(user_id, "ordering-spec")
    assert conv is not None
    conv_id = str(conv["id"])

    try:
        base = datetime(2026, 1, 1, 12, 0, 0)
        with get_conn() as conn:
            with conn.cursor() as cur:
                for i in range(5):
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, created_at)
                           VALUES (%s, %s, %s, %s)""",
                        (conv_id, "assistant", f"msg-{i}", base - timedelta(minutes=i)),
                    )
            conn.commit()

        messages = get_messages(conv_id)
        contents = [m["content"] for m in messages]
        assert contents == [f"msg-{i}" for i in range(5)]
    finally:
        delete_conversation(conv_id, user_id)

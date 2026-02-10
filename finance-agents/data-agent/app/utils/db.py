"""用于存储/加载对账规则的数据库工具。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def ensure_tables():
    """如果不存在，则创建 reconciliation_rules 表。"""
    ddl = """
    CREATE TABLE IF NOT EXISTS reconciliation_rules (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
        type_key VARCHAR(128) NOT NULL,
        schema_json JSONB NOT NULL,
        description TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()
        logger.info("reconciliation_rules 表已确保存在")
    except Exception as e:
        logger.error(f"确保表失败: {e}")


def save_rule(name: str, type_key: str, schema: dict, description: str = "") -> int:
    """插入或更新对账规则。返回行 ID。"""
    sql = """
    INSERT INTO reconciliation_rules (name, type_key, schema_json, description, updated_at)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (name) DO UPDATE SET
        type_key = EXCLUDED.type_key,
        schema_json = EXCLUDED.schema_json,
        description = EXCLUDED.description,
        updated_at = EXCLUDED.updated_at
    RETURNING id;
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (name, type_key, json.dumps(schema, ensure_ascii=False), description, datetime.now()))
            row_id = cur.fetchone()[0]
        conn.commit()
    return row_id


def load_rule(name: str) -> Optional[dict[str, Any]]:
    """按名称加载规则。如果未找到则返回 None。"""
    sql = "SELECT name, type_key, schema_json, description FROM reconciliation_rules WHERE name = %s"
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (name,))
            row = cur.fetchone()
    if row:
        return {
            "name": row["name"],
            "type_key": row["type_key"],
            "schema": row["schema_json"] if isinstance(row["schema_json"], dict) else json.loads(row["schema_json"]),
            "description": row["description"],
        }
    return None


def list_rules() -> list[dict[str, Any]]:
    """列出所有已保存的规则（仅名称 + 描述）。"""
    sql = "SELECT name, type_key, description, created_at FROM reconciliation_rules ORDER BY created_at DESC"
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        {
            "name": r["name"],
            "type_key": r["type_key"],
            "description": r["description"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

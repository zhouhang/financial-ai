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


def save_rule(name: str, type_key: str, schema: dict, description: str = "") -> str:
    """插入或更新对账规则。返回 UUID。
    
    注意：实际的表结构使用 rule_template (jsonb) 而不是 schema_json
    created_by 是必填字段，这里使用一个默认的系统用户 UUID
    """
    import uuid
    
    # 使用默认系统用户 UUID（如果数据库中没有，需要先创建）
    # 这里暂时使用一个固定的 UUID，实际应该从配置或环境变量获取
    default_user_id = "00000000-0000-0000-0000-000000000001"
    
    sql = """
    INSERT INTO reconciliation_rules (
        id, name, description, created_by, rule_template, version, status
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (name) DO UPDATE SET
        description = EXCLUDED.description,
        rule_template = EXCLUDED.rule_template,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id;
    """
    
    rule_id = str(uuid.uuid4())
    version = schema.get("version", "1.0")
    
    with _get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    sql,
                    (
                        rule_id,
                        name,
                        description,
                        default_user_id,
                        json.dumps(schema, ensure_ascii=False),
                        version,
                        'active'
                    )
                )
                returned_id = cur.fetchone()[0]
        conn.commit()
                logger.info(f"规则已保存到数据库: {name} (id={returned_id})")
                return str(returned_id)
            except Exception as e:
                conn.rollback()
                logger.error(f"保存规则到数据库失败: {e}")
                raise


def load_rule(name: str) -> Optional[dict[str, Any]]:
    """按名称加载规则。如果未找到则返回 None。"""
    sql = "SELECT name, description, rule_template FROM reconciliation_rules WHERE name = %s AND status = 'active'"
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (name,))
            row = cur.fetchone()
    if row:
        return {
            "name": row["name"],
            "schema": row["rule_template"] if isinstance(row["rule_template"], dict) else json.loads(row["rule_template"]),
            "description": row["description"],
        }
    return None


def list_rules() -> list[dict[str, Any]]:
    """列出所有已保存的规则（仅名称 + 描述）。"""
    sql = "SELECT name, description, created_at FROM reconciliation_rules WHERE status = 'active' ORDER BY created_at DESC"
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        {
            "name": r["name"],
            "description": r["description"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]

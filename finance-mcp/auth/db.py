"""认证模块的数据库操作"""

import os
import logging
from typing import Optional, Any
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


def _get_db_config() -> dict:
    """获取数据库连接配置"""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "finflux"),
        "user": os.getenv("DB_USER", "finflux_user"),
        "password": os.getenv("DB_PASSWORD", "123456"),
    }


@contextmanager
def get_conn():
    """获取数据库连接的上下文管理器"""
    conn = psycopg2.connect(**_get_db_config())
    try:
        yield conn
    finally:
        conn.close()


# ── 用户操作 ──────────────────────────────────────────────────────────

def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名查询用户"""
    sql = """
    SELECT u.id, u.username, u.password_hash, u.email, u.phone, u.role, u.status,
           u.company_id, u.department_id,
           c.name AS company_name,
           d.name AS department_name
    FROM users u
    LEFT JOIN company c ON u.company_id = c.id
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.username = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (username,))
            return cur.fetchone()


def get_user_by_id(user_id: str) -> Optional[dict]:
    """根据 ID 查询用户"""
    sql = """
    SELECT u.id, u.username, u.email, u.phone, u.role, u.status,
           u.company_id, u.department_id,
           c.name AS company_name,
           d.name AS department_name
    FROM users u
    LEFT JOIN company c ON u.company_id = c.id
    LEFT JOIN departments d ON u.department_id = d.id
    WHERE u.id = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (user_id,))
            return cur.fetchone()


def create_user(username: str, password_hash: str, email: str = None,
                phone: str = None, company_id: str = None,
                department_id: str = None, role: str = "member") -> dict:
    """创建新用户，返回用户信息"""
    sql = """
    INSERT INTO users (username, password_hash, email, phone, company_id, department_id, role)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id, username, email, phone, company_id, department_id, role, status
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (username, password_hash, email, phone,
                              company_id, department_id, role))
            user = cur.fetchone()
            conn.commit()
            return dict(user)


def update_last_login(user_id: str):
    """更新最后登录时间"""
    sql = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_id,))
            conn.commit()


# ── 公司/部门查询 ────────────────────────────────────────────────────

def list_companies() -> list[dict]:
    """列出所有公司"""
    sql = "SELECT id, name, code FROM company WHERE status = 'active' ORDER BY name"
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def list_departments(company_id: str) -> list[dict]:
    """列出公司下的所有部门"""
    sql = """
    SELECT id, name, code, parent_id
    FROM departments
    WHERE company_id = %s
    ORDER BY name
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (company_id,))
            return [dict(r) for r in cur.fetchall()]


# ── 规则 CRUD ─────────────────────────────────────────────────────────

def list_rules_for_user(user_id: str, company_id: str = None,
                        department_id: str = None,
                        status: str = "active") -> list[dict]:
    """查询用户可见的规则列表。

    可见性规则：
    - private: 仅创建者可见
    - department: 同部门可见
    - company: 同公司可见
    - admin: 可以看到所有规则
    """
    sql = """
    SELECT r.id, r.name, r.description, r.visibility, r.version,
           r.use_count, r.last_used_at, r.tags, r.status,
           r.created_at, r.updated_at,
           u.username AS created_by_name,
           r.created_by
    FROM reconciliation_rules r
    JOIN users u ON r.created_by = u.id
    WHERE r.status = %s
      AND (
        r.created_by = %s                              -- 自己创建的
        OR r.visibility = 'company' AND r.company_id = %s  -- 公司可见
        OR r.visibility = 'department' AND r.department_id = %s  -- 部门可见
        OR %s = ANY(r.shared_with_users)               -- 被分享的
      )
    ORDER BY r.updated_at DESC
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (status, user_id, company_id, department_id, user_id))
            rows = cur.fetchall()
            return [_serialize_rule_row(r) for r in rows]


def get_rule_by_id(rule_id: str) -> Optional[dict]:
    """根据 ID 获取规则详情（含 rule_template）"""
    sql = """
    SELECT r.*, u.username AS created_by_name
    FROM reconciliation_rules r
    JOIN users u ON r.created_by = u.id
    WHERE r.id = %s
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (rule_id,))
            row = cur.fetchone()
            if row:
                return _serialize_rule_row(row, include_template=True)
            return None


def get_rule_by_name(name: str, created_by: str = None) -> Optional[dict]:
    """根据名称获取规则详情"""
    sql = """
    SELECT r.*, u.username AS created_by_name
    FROM reconciliation_rules r
    JOIN users u ON r.created_by = u.id
    WHERE r.name = %s
    """
    params = [name]
    if created_by:
        sql += " AND r.created_by = %s"
        params.append(created_by)
    sql += " ORDER BY r.updated_at DESC LIMIT 1"

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if row:
                return _serialize_rule_row(row, include_template=True)
            return None


def create_rule(name: str, description: str, created_by: str,
                company_id: str, department_id: str,
                rule_template: dict, visibility: str = "private",
                tags: list[str] = None) -> dict:
    """创建新规则"""
    import json
    sql = """
    INSERT INTO reconciliation_rules
        (name, description, created_by, company_id, department_id,
         rule_template, visibility, tags, version, status)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '1.0', 'active')
    RETURNING id, name, description, visibility, version, status, created_at
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (
                name, description, created_by, company_id, department_id,
                json.dumps(rule_template, ensure_ascii=False),
                visibility, tags or [],
            ))
            row = cur.fetchone()
            conn.commit()
            return _serialize_rule_row(row)


def update_rule(rule_id: str, **kwargs) -> Optional[dict]:
    """更新规则。支持更新的字段：name, description, rule_template, visibility, tags, status"""
    import json

    allowed_fields = {"name", "description", "rule_template", "visibility", "tags", "status"}
    update_parts = []
    params = []

    for field, value in kwargs.items():
        if field in allowed_fields and value is not None:
            if field == "rule_template":
                update_parts.append(f"{field} = %s")
                params.append(json.dumps(value, ensure_ascii=False))
            elif field == "tags":
                update_parts.append(f"{field} = %s")
                params.append(value)
            else:
                update_parts.append(f"{field} = %s")
                params.append(value)

    if not update_parts:
        return None

    params.append(rule_id)
    sql = f"""
    UPDATE reconciliation_rules
    SET {', '.join(update_parts)}, updated_at = CURRENT_TIMESTAMP
    WHERE id = %s
    RETURNING id, name, description, visibility, version, status, updated_at
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            if row:
                return _serialize_rule_row(row)
            return None


def delete_rule(rule_id: str) -> bool:
    """软删除规则（设置 status = 'archived'）"""
    sql = """
    UPDATE reconciliation_rules
    SET status = 'archived', updated_at = CURRENT_TIMESTAMP
    WHERE id = %s AND status = 'active'
    RETURNING id
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (rule_id,))
            result = cur.fetchone()
            conn.commit()
            return result is not None


def can_user_modify_rule(user_id: str, role: str, rule: dict) -> bool:
    """检查用户是否有权限修改规则"""
    # admin 可以修改任何规则
    if role == "admin":
        return True
    # 创建者可以修改自己的规则
    if str(rule.get("created_by")) == user_id:
        return True
    # manager 可以修改同部门/同公司的规则
    if role == "manager":
        return True
    return False


# ── 辅助函数 ──────────────────────────────────────────────────────────

def _serialize_rule_row(row: dict, include_template: bool = False) -> dict:
    """将数据库行序列化为可 JSON 化的字典"""
    result = {}
    for key, val in row.items():
        if key == "rule_template" and not include_template:
            continue
        if hasattr(val, "isoformat"):
            result[key] = val.isoformat()
        elif isinstance(val, (list, dict)):
            result[key] = val
        elif hasattr(val, "__str__"):
            result[key] = str(val)
        else:
            result[key] = val
    return result

"""认证模块的数据库操作"""

import os
import logging
from typing import Optional, Any
from contextlib import contextmanager
import time

import psycopg2
import psycopg2.extras
from psycopg2 import OperationalError, InterfaceError

logger = logging.getLogger(__name__)


def _get_db_config() -> dict:
    """获取数据库连接配置 - 引用统一的 db_config"""
    from db_config import db_config
    return db_config.get_connection_params()


def get_conn(max_retries=3, retry_delay=1):
    """获取数据库连接的上下文管理器，带重试机制"""
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**_get_db_config())
            return _ConnectionContextManager(conn)
        except (OperationalError, InterfaceError) as e:
            logger.warning(f"数据库连接失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                logger.error(f"数据库连接失败，已达到最大重试次数: {e}")
                raise


class _ConnectionContextManager:
    """数据库连接的上下文管理器类"""
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()

    def cursor(self, cursor_factory=None):
        """获取游标，自动处理连接失效"""
        try:
            # 检查连接是否仍然有效
            with self.conn.cursor() as test_cursor:
                test_cursor.execute('SELECT 1')
        except (OperationalError, InterfaceError):
            logger.warning("数据库连接已失效，尝试重新连接")
            self.conn.close()
            # 重新建立连接
            self.conn = psycopg2.connect(**_get_db_config())
        
        return self.conn.cursor(cursor_factory=cursor_factory)

    def commit(self):
        """提交事务"""
        self.conn.commit()

    def rollback(self):
        """回滚事务"""
        self.conn.rollback()


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
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (username,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"查询用户失败 (username={username}): {e}")
        return None


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
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (user_id,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"查询用户失败 (user_id={user_id}): {e}")
        return None


def create_user(username: str, password_hash: str, email: str = None,
                phone: str = None, company_id: str = None,
                department_id: str = None, role: str = "member") -> dict:
    """创建新用户，返回用户信息"""
    sql = """
    INSERT INTO users (username, password_hash, email, phone, company_id, department_id, role)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id, username, email, phone, company_id, department_id, role, status
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (username, password_hash, email, phone,
                                  company_id, department_id, role))
                user = cur.fetchone()
                conn.commit()
                return dict(user)
    except Exception as e:
        logger.error(f"创建用户失败 (username={username}): {e}")
        raise


def update_last_login(user_id: str):
    """更新最后登录时间"""
    sql = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id,))
                conn.commit()
    except Exception as e:
        logger.error(f"更新登录时间失败 (user_id={user_id}): {e}")
        # Don't raise here as this is not critical for login


# ── 公司/部门查询 ────────────────────────────────────────────────────

def list_companies() -> list[dict]:
    """列出所有公司"""
    sql = "SELECT id, name, code FROM company WHERE status = 'active' ORDER BY name"
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询公司列表失败: {e}")
        return []


def list_departments(company_id: str) -> list[dict]:
    """列出公司下的所有部门"""
    sql = """
    SELECT id, name, code, parent_id
    FROM departments
    WHERE company_id = %s
    ORDER BY name
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (company_id,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"查询部门列表失败 (company_id={company_id}): {e}")
        return []


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
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (status, user_id, company_id, department_id, user_id))
                rows = cur.fetchall()
                return [_serialize_rule_row(r) for r in rows]
    except Exception as e:
        logger.error(f"查询规则列表失败 (user_id={user_id}): {e}")
        return []


def get_rule_by_id(rule_id: str) -> Optional[dict]:
    """根据 ID 获取规则详情（含 rule_template）"""
    sql = """
    SELECT r.*, u.username AS created_by_name
    FROM reconciliation_rules r
    JOIN users u ON r.created_by = u.id
    WHERE r.id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (rule_id,))
                row = cur.fetchone()
                if row:
                    return _serialize_rule_row(row, include_template=True)
                return None
    except Exception as e:
        logger.error(f"查询规则详情失败 (rule_id={rule_id}): {e}")
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

    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                if row:
                    return _serialize_rule_row(row, include_template=True)
                return None
    except Exception as e:
        logger.error(f"查询规则详情失败 (name={name}): {e}")
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
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (
                    name, description, created_by, company_id, department_id,
                    json.dumps(rule_template, ensure_ascii=False),
                    visibility, tags or [],
                ))
                row = cur.fetchone()
                conn.commit()
                return _serialize_rule_row(row)
    except Exception as e:
        logger.error(f"创建规则失败 (name={name}): {e}")
        raise


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
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                conn.commit()
                if row:
                    return _serialize_rule_row(row)
                return None
    except Exception as e:
        logger.error(f"更新规则失败 (rule_id={rule_id}): {e}")
        return None


def delete_rule(rule_id: str) -> bool:
    """物理删除规则（从数据库中完全删除）"""
    sql = """
    DELETE FROM reconciliation_rules
    WHERE id = %s
    RETURNING id
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (rule_id,))
                result = cur.fetchone()
                conn.commit()
                return result is not None
    except Exception as e:
        logger.error(f"删除规则失败 (rule_id={rule_id}): {e}")
        return False


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


# ══════════════════════════════════════════════════════════════════════════════
# 公司部门管理
# ══════════════════════════════════════════════════════════════════════════════

def create_company(name: str) -> dict | None:
    """创建公司，返回公司dict或None（如果已存在）"""
    import uuid
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 检查是否已存在
                cur.execute("SELECT id FROM company WHERE name = %s", (name,))
                if cur.fetchone():
                    return None
                
                # 生成唯一的 code
                code = f"COMP_{uuid.uuid4().hex[:8].upper()}"
                
                cur.execute(
                    "INSERT INTO company (name, code) VALUES (%s, %s) RETURNING id, name, code, created_at",
                    (name, code)
                )
                row = cur.fetchone()
                c.commit()
                return dict(row)
    except Exception as e:
        logger.error(f"创建公司失败: {e}")
        return None


def create_department(company_id: str, name: str) -> dict | None:
    """创建部门，返回部门dict或None（如果已存在）"""
    import uuid
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 检查是否已存在
                cur.execute(
                    "SELECT id FROM departments WHERE company_id = %s AND name = %s",
                    (company_id, name)
                )
                if cur.fetchone():
                    return None
                
                # 生成唯一的 code
                code = f"DEPT_{uuid.uuid4().hex[:8].upper()}"
                
                cur.execute(
                    "INSERT INTO departments (company_id, name, code) VALUES (%s, %s, %s) RETURNING id, company_id, name, code, created_at",
                    (company_id, name, code)
                )
                row = cur.fetchone()
                c.commit()
                return dict(row)
    except Exception as e:
        logger.error(f"创建部门失败: {e}")
        return None


def list_companies() -> list[dict]:
    """获取公司列表"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id, name, created_at FROM company ORDER BY created_at DESC")
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"获取公司列表失败: {e}")
        return []


def list_departments(company_id: str | None = None) -> list[dict]:
    """获取部门列表，可按公司筛选"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if company_id:
                    cur.execute(
                        "SELECT id, company_id, name, created_at FROM departments WHERE company_id = %s ORDER BY created_at DESC",
                        (company_id,)
                    )
                else:
                    cur.execute("SELECT id, company_id, name, created_at FROM departments ORDER BY created_at DESC")
                rows = cur.fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"获取部门列表失败: {e}")
        return []


def get_admin_view() -> dict:
    """获取管理员视图 - 公司部门员工规则层级"""
    conn = get_conn()
    result = {"companies": []}
    
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 获取所有公司
                cur.execute("SELECT id, name, created_at FROM company ORDER BY name")
                companies = cur.fetchall()
                
                for company in companies:
                    company_id = company["id"]
                    company_data = {
                        "id": str(company["id"]),
                        "name": company["name"],
                        "departments": []
                    }
                    
                    # 获取该公司的部门
                    cur.execute(
                        "SELECT id, name FROM departments WHERE company_id = %s ORDER BY name",
                        (company_id,)
                    )
                    departments = cur.fetchall()
                    
                    for dept in departments:
                        dept_id = dept["id"]
                        dept_data = {
                            "id": str(dept["id"]),
                            "name": dept["name"],
                            "employees": [],
                            "rules": []
                        }
                        
                        # 获取该部门的员工
                        cur.execute(
                            "SELECT id, username, email FROM users WHERE department_id = %s",
                            (dept_id,)
                        )
                        employees = cur.fetchall()
                        for emp in employees:
                            dept_data["employees"].append({
                                "id": str(emp["id"]),
                                "username": emp["username"],
                                "email": emp.get("email")
                            })
                        
                        # 获取该部门的规则
                        cur.execute(
                            "SELECT id, name, visibility FROM reconciliation_rules WHERE department_id = %s",
                            (dept_id,)
                        )
                        rules = cur.fetchall()
                        for rule in rules:
                            dept_data["rules"].append({
                                "id": str(rule["id"]),
                                "name": rule["name"],
                                "visibility": rule["visibility"]
                            })
                        
                        company_data["departments"].append(dept_data)
                    
                    result["companies"].append(company_data)
        
        return result
    except Exception as e:
        logger.error(f"获取管理员视图失败: {e}")
        return {"companies": [], "error": str(e)}

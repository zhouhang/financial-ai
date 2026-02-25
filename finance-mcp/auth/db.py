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


def list_all_active_rules(status: str = "active") -> list[dict]:
    """查询所有活跃规则（游客模式使用）
    
    Args:
        status: 规则状态
        
    Returns:
        list: 规则列表
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
    ORDER BY r.use_count DESC
    LIMIT 50
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (status,))
                rows = cur.fetchall()
                return [_serialize_rule_row(r) for r in rows]
    except Exception as e:
        logger.error(f"查询所有活跃规则失败: {e}")
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
    """创建新规则，自动计算并存储 field_mapping_hash"""
    import json
    
    hash_value = compute_field_mapping_hash(rule_template)
    
    sql = """
    INSERT INTO reconciliation_rules
        (name, description, created_by, company_id, department_id,
         rule_template, visibility, tags, version, status, field_mapping_hash)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '1.0', 'active', %s)
    RETURNING id, name, description, visibility, version, status, created_at
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (
                    name, description, created_by, company_id, department_id,
                    json.dumps(rule_template, ensure_ascii=False),
                    visibility, tags or [], hash_value,
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


# ══════════════════════════════════════════════════════════════════════════════
# 规则推荐功能 - 字段映射哈希
# ══════════════════════════════════════════════════════════════════════════════

def compute_field_mapping_hash(rule_template: dict) -> str:
    """计算字段映射的哈希值，用于规则匹配推荐。
    
    提取6个关键字段（业务和财务的 order_id, amount, date），
    排序后计算 MD5 哈希。
    """
    import hashlib
    
    fields = []
    for source in ["business", "finance"]:
        for role in ["order_id", "amount", "date"]:
            value = (
                rule_template.get("data_sources", {})
                .get(source, {})
                .get("field_roles", {})
                .get(role)
            )
            if isinstance(value, list):
                value = ",".join(sorted(value))
            elif value:
                value = str(value)
            else:
                value = ""
            fields.append(f"{source}.{role}={value}")
    
    fields.sort()
    hash_input = "|".join(fields)
    return hashlib.md5(hash_input.encode()).hexdigest()


def add_field_mapping_hash_column():
    """迁移：为 reconciliation_rules 表添加 field_mapping_hash 字段"""
    sql = """
    ALTER TABLE reconciliation_rules 
    ADD COLUMN IF NOT EXISTS field_mapping_hash VARCHAR(32);
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        logger.info("field_mapping_hash 字段已添加")
    except Exception as e:
        logger.error(f"添加 field_mapping_hash 字段失败: {e}")
        raise


def create_field_mapping_hash_index():
    """迁移：创建 field_mapping_hash 字段的 B-tree 索引"""
    sql = """
    CREATE INDEX IF NOT EXISTS idx_rules_field_mapping_hash 
    ON reconciliation_rules(field_mapping_hash);
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        logger.info("field_mapping_hash 索引已创建")
    except Exception as e:
        logger.error(f"创建索引失败: {e}")
        raise


def migrate_existing_rules_hash():
    """迁移：为现有规则计算并填充 field_mapping_hash"""
    import json
    
    sql = """
    SELECT id, rule_template 
    FROM reconciliation_rules 
    WHERE field_mapping_hash IS NULL OR field_mapping_hash = ''
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                
                if not rows:
                    logger.info("没有需要迁移的规则")
                    return 0
                
                count = 0
                for row in rows:
                    rule_id = row["id"]
                    template = row["rule_template"]
                    if isinstance(template, str):
                        template = json.loads(template)
                    
                    hash_value = compute_field_mapping_hash(template)
                    
                    update_sql = """
                    UPDATE reconciliation_rules 
                    SET field_mapping_hash = %s 
                    WHERE id = %s
                    """
                    cur.execute(update_sql, (hash_value, rule_id))
                    count += 1
                
                conn.commit()
                logger.info(f"已迁移 {count} 条规则的 field_mapping_hash")
                return count
    except Exception as e:
        logger.error(f"迁移规则哈希失败: {e}")
        raise


def search_rules_by_field_mapping(field_mapping_hash: str, limit: int = 3) -> list[dict]:
    """根据字段映射哈希搜索匹配规则"""
    sql = """
    SELECT r.id, r.name, r.description, r.rule_template, r.field_mapping_hash,
           r.created_at, r.created_by
    FROM reconciliation_rules r
    WHERE r.field_mapping_hash = %s 
      AND r.status = 'active'
    LIMIT %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (field_mapping_hash, limit))
                rows = cur.fetchall()
                return [_serialize_rule_row(r, include_template=True) for r in rows]
    except Exception as e:
        logger.error(f"搜索规则失败: {e}")
        return []


def batch_get_rules_by_ids(rule_ids: list[str]) -> list[dict]:
    """批量获取规则详情（含 rule_template）
    
    Args:
        rule_ids: 规则 ID 列表
        
    Returns:
        规则详情列表，包含 rule_template
    """
    if not rule_ids:
        return []
    
    # 使用 ANY 数组查询，将 UUID 转换为 text 后比较
    sql = """
    SELECT r.*, u.username AS created_by_name
    FROM reconciliation_rules r
    JOIN users u ON r.created_by = u.id
    WHERE r.id::text = ANY(%s)
      AND r.status = 'active'
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (rule_ids,))
                rows = cur.fetchall()
                return [_serialize_rule_row(r, include_template=True) for r in rows]
    except Exception as e:
        logger.error(f"批量获取规则失败: {e}")
        return []


def copy_rule(source_rule_id: str, new_name: str, user_id: str) -> dict:
    """复制规则为新规则"""
    import json
    
    sql = """
    SELECT * FROM reconciliation_rules WHERE id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (source_rule_id,))
                row = cur.fetchone()
                
                if not row:
                    raise ValueError(f"源规则不存在: {source_rule_id}")
                
                template = row["rule_template"]
                if isinstance(template, str):
                    template = json.loads(template)
                
                new_hash = compute_field_mapping_hash(template)
                
                insert_sql = """
                INSERT INTO reconciliation_rules
                    (name, description, created_by, company_id, department_id,
                     rule_template, visibility, tags, version, status, field_mapping_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, description, created_at
                """
                cur.execute(insert_sql, (
                    new_name,
                    row["description"],
                    user_id,
                    row["company_id"],
                    row["department_id"],
                    json.dumps(template, ensure_ascii=False),
                    row["visibility"],
                    row["tags"] or [],
                    row["version"],
                    "active",
                    new_hash,
                ))
                new_row = cur.fetchone()
                conn.commit()
                return _serialize_rule_row(new_row)
    except Exception as e:
        logger.error(f"复制规则失败: {e}")
        raise


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


# ══════════════════════════════════════════════════════════════════════════════
# 会话管理
# ══════════════════════════════════════════════════════════════════════════════

def create_conversation(user_id: str, title: str = None) -> dict | None:
    """创建新会话"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """INSERT INTO conversations (user_id, title) 
                       VALUES (%s, %s) 
                       RETURNING id, user_id, title, created_at, updated_at, status""",
                    (user_id, title)
                )
                row = cur.fetchone()
                c.commit()
                result = dict(row)
                result["id"] = str(result["id"])
                result["user_id"] = str(result["user_id"])
                return result
    except Exception as e:
        logger.error(f"创建会话失败: {e}")
        return None


def get_conversation(conversation_id: str, user_id: str) -> dict | None:
    """获取单个会话（验证所有权）"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at, status 
                       FROM conversations 
                       WHERE id = %s AND user_id = %s""",
                    (conversation_id, user_id)
                )
                row = cur.fetchone()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["user_id"] = str(result["user_id"])
                    return result
                return None
    except Exception as e:
        logger.error(f"获取会话失败: {e}")
        return None


def list_conversations(user_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """获取用户的会话列表"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, user_id, title, created_at, updated_at, status 
                       FROM conversations 
                       WHERE user_id = %s AND status = 'active'
                       ORDER BY updated_at DESC
                       LIMIT %s OFFSET %s""",
                    (user_id, limit, offset)
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item["id"] = str(item["id"])
                    item["user_id"] = str(item["user_id"])
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        return []


def update_conversation(conversation_id: str, user_id: str, title: str = None, status: str = None) -> dict | None:
    """更新会话"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 构建更新语句
                updates = []
                params = []
                if title is not None:
                    updates.append("title = %s")
                    params.append(title)
                if status is not None:
                    updates.append("status = %s")
                    params.append(status)
                
                if not updates:
                    return get_conversation(conversation_id, user_id)
                
                params.extend([conversation_id, user_id])
                cur.execute(
                    f"""UPDATE conversations 
                        SET {', '.join(updates)}
                        WHERE id = %s AND user_id = %s
                        RETURNING id, user_id, title, created_at, updated_at, status""",
                    params
                )
                row = cur.fetchone()
                c.commit()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["user_id"] = str(result["user_id"])
                    return result
                return None
    except Exception as e:
        logger.error(f"更新会话失败: {e}")
        return None


def delete_conversation(conversation_id: str, user_id: str) -> bool:
    """删除会话（物理删除）及关联的历史消息"""
    conn_manager = get_conn()
    try:
        with conn_manager as c:
            with c.cursor() as cur:
                # 1. 删除该会话下的所有消息
                cur.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))
                # 2. 物理删除会话
                cur.execute(
                    "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                    (conversation_id, user_id)
                )
                c.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        try:
            conn_manager.rollback()
        except Exception:
            pass
        return False


def save_message(conversation_id: str, role: str, content: str, metadata: dict = None, attachments: list = None) -> dict | None:
    """保存消息（支持附件，向后兼容）"""
    import json
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 尝试使用新的 attachments 列（如果存在）
                try:
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, metadata, attachments)
                           VALUES (%s, %s, %s, %s, %s)
                           RETURNING id, conversation_id, role, content, metadata, attachments, created_at""",
                        (conversation_id, role, content, json.dumps(metadata or {}), json.dumps(attachments or []))
                    )
                    row = cur.fetchone()
                except Exception as column_error:
                    # 如果 attachments 列不存在，回退到旧版本（不包含 attachments）
                    logger.warning(f"attachments 列不存在，使用旧版本保存: {column_error}")
                    cur.execute(
                        """INSERT INTO messages (conversation_id, role, content, metadata)
                           VALUES (%s, %s, %s, %s)
                           RETURNING id, conversation_id, role, content, metadata, created_at""",
                        (conversation_id, role, content, json.dumps(metadata or {}))
                    )
                    row = cur.fetchone()

                # 同时更新会话的 updated_at
                cur.execute(
                    "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (conversation_id,)
                )

                c.commit()
                if row:
                    result = dict(row)
                    result["id"] = str(result["id"])
                    result["conversation_id"] = str(result["conversation_id"])
                    # 确保总是返回 attachments 字段（即使是空数组）
                    if "attachments" not in result:
                        result["attachments"] = []
                    return result
                return None
    except Exception as e:
        logger.error(f"保存消息失败: {e}")
        return None


def should_display_message(role: str, content: str, metadata: dict = None) -> bool:
    """判断消息是否应该显示给用户。

    过滤掉以下类型的消息：
    - JSON响应（意图识别等）
    - HTML表单
    - 代码块
    - 系统消息
    - 进度提示消息（包含SPINNER等临时标记）

    Args:
        role: 消息角色 (user/assistant/system)
        content: 消息内容
        metadata: 可选的元数据

    Returns:
        True 表示应该显示，False 表示应该过滤掉
    """
    if not content:
        return False

    content_stripped = content.strip()

    # 过滤JSON响应
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        return False

    # 过滤代码块
    if content_stripped.startswith("```"):
        return False

    # 过滤HTML表单
    if content_stripped.startswith("<"):
        return False

    # 过滤系统消息
    if role == "system":
        return False

    # 过滤进度消息（临时指示器）
    progress_patterns = [
        "{{SPINNER}}",
        "正在保存",
        "📊 进度：",
    ]
    for pattern in progress_patterns:
        if pattern in content:
            return False

    return True


def get_messages(conversation_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """获取会话的消息列表（已过滤不应显示的消息，向后兼容）"""
    conn = get_conn()
    try:
        with conn as c:
            with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 尝试查询包含 attachments 列
                try:
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, attachments, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY created_at ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )
                except Exception as column_error:
                    # 如果 attachments 列不存在，查询不包含它
                    logger.warning(f"attachments 列不存在，使用旧版本查询: {column_error}")
                    cur.execute(
                        """SELECT id, conversation_id, role, content, metadata, created_at
                           FROM messages
                           WHERE conversation_id = %s
                           ORDER BY created_at ASC
                           LIMIT %s OFFSET %s""",
                        (conversation_id, limit, offset)
                    )

                rows = cur.fetchall()
                result = []
                for row in rows:
                    # 应用过滤器：只返回应该显示的消息
                    if should_display_message(row["role"], row["content"], row.get("metadata")):
                        item = dict(row)
                        item["id"] = str(item["id"])
                        item["conversation_id"] = str(item["conversation_id"])
                        # 确保 attachments 总是一个列表
                        if "attachments" not in item or item.get("attachments") is None:
                            item["attachments"] = []
                        result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取消息列表失败: {e}")
        return []


# ── 游客认证操作 ──────────────────────────────────────────────────────────

import secrets
from datetime import datetime, timedelta


def create_guest_token(session_id: str, ip_address: str = None, user_agent: str = None) -> dict:
    """创建游客临时token
    
    Args:
        session_id: 会话ID
        ip_address: 用户IP地址
        user_agent: 用户浏览器信息
        
    Returns:
        dict: 包含 token 和过期时间
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=7)
    
    sql = """
    INSERT INTO guest_auth_tokens (token, session_id, ip_address, user_agent, expires_at)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id, token, usage_count, max_usage, expires_at
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (token, session_id, ip_address, user_agent, expires_at))
                result = cur.fetchone()
                conn.commit()
                
                return {
                    "id": str(result["id"]),
                    "token": result["token"],
                    "usage_count": result["usage_count"],
                    "max_usage": result["max_usage"],
                    "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None
                }
    except Exception as e:
        logger.error(f"创建游客token失败: {e}")
        return None


def verify_guest_token(token: str) -> Optional[dict]:
    """验证游客token
    
    Args:
        token: 游客token
        
    Returns:
        dict: token信息，如果无效则返回None
    """
    sql = """
    SELECT id, token, session_id, usage_count, max_usage, expires_at, created_at
    FROM guest_auth_tokens
    WHERE token = %s
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (token,))
                result = cur.fetchone()
                
                if not result:
                    return None
                
                # 检查是否过期 - 统一转换为 naive datetime 进行比较
                if result["expires_at"]:
                    expires_at = result["expires_at"]
                    # 确保两个datetime都是naive（不带时区信息）
                    if hasattr(expires_at, 'tzinfo') and expires_at.tzinfo is not None:
                        # 如果有时区信息，去掉时区信息转为naive
                        expires_at = expires_at.replace(tzinfo=None)
                    now = datetime.utcnow()
                    if expires_at < now:
                        return {"valid": False, "error": "token已过期"}
                
                return {
                    "id": str(result["id"]),
                    "token": result["token"],
                    "session_id": result["session_id"],
                    "usage_count": result["usage_count"],
                    "max_usage": result["max_usage"],
                    "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None,
                    "valid": True
                }
    except Exception as e:
        logger.error(f"验证游客token失败: {e}")
        return None


def increment_guest_usage(token: str) -> Optional[dict]:
    """增加游客token使用次数
    
    Args:
        token: 游客token
        
    Returns:
        dict: 更新后的token信息
    """
    sql = """
    UPDATE guest_auth_tokens
    SET usage_count = usage_count + 1
    WHERE token = %s
    RETURNING id, token, session_id, usage_count, max_usage, expires_at
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (token,))
                result = cur.fetchone()
                conn.commit()
                
                if not result:
                    return None
                
                return {
                    "id": str(result["id"]),
                    "token": result["token"],
                    "session_id": result["session_id"],
                    "usage_count": result["usage_count"],
                    "max_usage": result["max_usage"],
                    "expires_at": result["expires_at"].isoformat() if result["expires_at"] else None
                }
    except Exception as e:
        logger.error(f"增加游客使用次数失败: {e}")
        return None


def list_recommended_rules(limit: int = 20) -> list:
    """获取系统推荐规则列表（返回所有活跃规则）
    
    Args:
        limit: 返回数量限制
        
    Returns:
        list: 推荐规则列表
    """
    sql = """
    SELECT id, name, description, visibility, version, use_count, status,
           created_at, key_field_role, field_mapping_hash
    FROM reconciliation_rules
    WHERE status = 'active'
    ORDER BY use_count DESC
    LIMIT %s
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (limit,))
                rows = cur.fetchall()
                
                result = []
                for row in rows:
                    item = dict(row)
                    item["id"] = str(item["id"])
                    item["created_at"] = item["created_at"].isoformat() if item["created_at"] else None
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"获取推荐规则列表失败: {e}")
        return []

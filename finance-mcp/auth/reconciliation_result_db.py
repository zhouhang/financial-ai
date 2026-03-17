"""对账结果存储 - 数据库操作模块

提供对账会话、文件组、差异记录的 CRUD 操作。
"""

import json
import logging
from datetime import datetime
from typing import Optional, Any, List, Dict
from enum import Enum

import psycopg2
import psycopg2.extras

from auth.db import get_conn, _serialize_datetimes

logger = logging.getLogger(__name__)


# ── 枚举定义 ─────────────────────────────────────────────────────────────

class SessionStatus(str, Enum):
    """会话状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SessionType(str, Enum):
    """会话类型"""
    STANDARD = "standard"      # 标准对账
    AUDIT = "audit"           # 审计对账
    CUSTOM = "custom"         # 自定义


class ProcessStatus(str, Enum):
    """差异处理状态"""
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中
    RESOLVED = "resolved"     # 已解决
    IGNORED = "ignored"       # 已忽略
    ESCALATED = "escalated"   # 已升级


class ProcessResult(str, Enum):
    """处理结果"""
    FIXED = "fixed"           # 已修正
    EXPLAINED = "explained"   # 已说明
    ACCEPTED = "accepted"     # 已接受
    DISPUTED = "disputed"     # 有争议
    OTHER = "other"           # 其他


# ── 会话操作 ─────────────────────────────────────────────────────────────

def create_session(
    operator_id: str,
    rule_id: str = None,
    task_id: str = None,
    session_name: str = None,
    session_type: str = "standard",
    department_id: str = None,
    notes: str = None,
    tags: List[str] = None,
) -> Optional[dict]:
    """
    创建对账会话
    
    Args:
        operator_id: 操作人ID（必填）
        rule_id: 对账规则ID
        task_id: 关联的任务ID（兼容现有流程）
        session_name: 会话名称
        session_type: 会话类型 standard/audit/custom
        department_id: 部门ID
        notes: 备注
        tags: 标签列表
    
    Returns:
        创建的会话信息，失败返回 None
    """
    sql = """
    INSERT INTO reconciliation_sessions 
    (operator_id, rule_id, task_id, session_name, session_type, 
     department_id, notes, tags, status, started_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running', CURRENT_TIMESTAMP)
    RETURNING id, session_name, session_type, status, started_at, created_at
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (
                    operator_id, rule_id, task_id, session_name, session_type,
                    department_id, notes, tags or []
                ))
                row = cur.fetchone()
                conn.commit()
                logger.info(f"创建对账会话: id={row['id']}, operator={operator_id}")
                return _serialize_datetimes(dict(row))
    except Exception as e:
        logger.error(f"创建对账会话失败: {e}")
        return None


def get_session(session_id: str) -> Optional[dict]:
    """获取会话详情"""
    sql = """
    SELECT s.*, 
           r.name as rule_name,
           u.username as operator_name,
           d.name as department_name
    FROM reconciliation_sessions s
    LEFT JOIN reconciliation_rules r ON s.rule_id = r.id
    LEFT JOIN users u ON s.operator_id = u.id
    LEFT JOIN departments d ON s.department_id = d.id
    WHERE s.id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (session_id,))
                row = cur.fetchone()
                return _serialize_datetimes(dict(row)) if row else None
    except Exception as e:
        logger.error(f"获取会话失败 (session_id={session_id}): {e}")
        return None


def update_session_status(
    session_id: str,
    status: str,
    total_file_groups: int = None,
    total_records: int = None,
    total_issues: int = None,
    processed_issues: int = None,
) -> bool:
    """更新会话状态和统计信息"""
    update_parts = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
    params = [status]
    
    if status == "completed":
        update_parts.append("completed_at = CURRENT_TIMESTAMP")
    if total_file_groups is not None:
        update_parts.append("total_file_groups = %s")
        params.append(total_file_groups)
    if total_records is not None:
        update_parts.append("total_records = %s")
        params.append(total_records)
    if total_issues is not None:
        update_parts.append("total_issues = %s")
        params.append(total_issues)
    if processed_issues is not None:
        update_parts.append("processed_issues = %s")
        params.append(processed_issues)
    
    params.append(session_id)
    sql = f"""
    UPDATE reconciliation_sessions 
    SET {', '.join(update_parts)}
    WHERE id = %s
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"更新会话状态失败 (session_id={session_id}): {e}")
        return False


def list_sessions(
    operator_id: str = None,
    rule_id: str = None,
    status: str = None,
    limit: int = 50,
    offset: int = 0,
) -> List[dict]:
    """列出对账会话"""
    conditions = []
    params = []
    
    if operator_id:
        conditions.append("s.operator_id = %s")
        params.append(operator_id)
    if rule_id:
        conditions.append("s.rule_id = %s")
        params.append(rule_id)
    if status:
        conditions.append("s.status = %s")
        params.append(status)
    
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    
    sql = f"""
    SELECT s.id, s.session_name, s.session_type, s.status,
           s.total_file_groups, s.total_records, s.total_issues, s.processed_issues,
           s.started_at, s.completed_at, s.created_at,
           r.name as rule_name,
           u.username as operator_name
    FROM reconciliation_sessions s
    LEFT JOIN reconciliation_rules r ON s.rule_id = r.id
    LEFT JOIN users u ON s.operator_id = u.id
    {where_clause}
    ORDER BY s.created_at DESC
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [_serialize_datetimes(dict(r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"列出会话失败: {e}")
        return []


# ── 文件组操作 ───────────────────────────────────────────────────────────

def create_file_group(
    session_id: str,
    group_name: str = None,
    group_order: int = 0,
    business_files: List[dict] = None,
    finance_files: List[dict] = None,
) -> Optional[dict]:
    """
    创建文件组
    
    Args:
        session_id: 会话ID
        group_name: 文件组名称
        group_order: 显示顺序
        business_files: 业务文件列表 [{name, path, size}, ...]
        finance_files: 财务文件列表 [{name, path, size}, ...]
    
    Returns:
        创建的文件组信息
    """
    sql = """
    INSERT INTO reconciliation_file_groups 
    (session_id, group_name, group_order, business_files, finance_files, status)
    VALUES (%s, %s, %s, %s, %s, 'pending')
    RETURNING id, session_id, group_name, group_order, status, created_at
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (
                    session_id, group_name, group_order,
                    json.dumps(business_files or []),
                    json.dumps(finance_files or [])
                ))
                row = cur.fetchone()
                conn.commit()
                return _serialize_datetimes(dict(row))
    except Exception as e:
        logger.error(f"创建文件组失败: {e}")
        return None


def update_file_group_summary(
    file_group_id: str,
    total_business_records: int = 0,
    total_finance_records: int = 0,
    matched_records: int = 0,
    unmatched_records: int = 0,
    issues_by_type: dict = None,
    status: str = "completed",
    error_message: str = None,
) -> bool:
    """更新文件组对账摘要"""
    sql = """
    UPDATE reconciliation_file_groups 
    SET total_business_records = %s,
        total_finance_records = %s,
        matched_records = %s,
        unmatched_records = %s,
        issues_by_type = %s,
        status = %s,
        error_message = %s,
        completed_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    total_business_records, total_finance_records,
                    matched_records, unmatched_records,
                    json.dumps(issues_by_type or {}),
                    status, error_message, status,
                    file_group_id
                ))
                conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"更新文件组摘要失败 (file_group_id={file_group_id}): {e}")
        return False


def get_file_groups(session_id: str) -> List[dict]:
    """获取会话下的所有文件组"""
    sql = """
    SELECT * FROM reconciliation_file_groups
    WHERE session_id = %s
    ORDER BY group_order
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (session_id,))
                return [_serialize_datetimes(dict(r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"获取文件组失败 (session_id={session_id}): {e}")
        return []


# ── 差异记录操作 ─────────────────────────────────────────────────────────

def save_result_records(
    file_group_id: str,
    issues: List[dict],
    comparison_fields: List[dict] = None,
    key_fields_mapping: List[dict] = None,
    primary_amount_field: str = None,
) -> int:
    """
    批量保存差异记录
    
    Args:
        file_group_id: 文件组ID
        issues: 差异列表，每个差异可包含:
            - order_id: 订单号（主键，联合键时为第一个键的值或组合值）
            - issue_type: 问题类型
            - detail: 详情
            - business_amount: 业务侧主要金额
            - finance_amount: 财务侧主要金额
            - comparison_values: 多字段比较值
            - key_fields: 合并键字段值
            - 其他动态字段将存入 extra_data
        comparison_fields: 比较字段定义列表，如:
            [
                {"name": "amount", "target_col": "target_应结算平台金额", "source_col": "source_发生+", "type": "amount"},
                {"name": "date", "target_col": "target_支付时间", "source_col": "source_完成时间", "type": "date"}
            ]
        key_fields_mapping: 合并键映射定义列表（支持联合键），如:
            [
                {"source_col": "sup订单号", "target_col": "第三方订单号"},
                {"source_col": "渠道ID", "target_col": "channel_id"}
            ]
        primary_amount_field: 主要金额字段名（用于 business_amount/finance_amount）
    
    Returns:
        成功保存的记录数
    """
    if not issues:
        return 0
    
    # 固定字段
    fixed_fields = {
        'order_id', 'issue_type', 'detail', 
        'business_amount', 'finance_amount', 'amount_diff',
        'comparison_values', 'key_fields',
        'business_raw', 'finance_raw'
    }
    
    sql = """
    INSERT INTO reconciliation_result_records 
    (file_group_id, order_id, issue_type, detail, 
     business_amount, finance_amount, amount_diff,
     comparison_values, key_fields, extra_data, 
     business_raw, finance_raw, row_index, process_status)
    VALUES %s
    """
    
    # 准备数据
    values = []
    for idx, issue in enumerate(issues):
        # 提取固定字段
        order_id = str(issue.get('order_id', ''))
        issue_type = issue.get('issue_type', '')
        detail = issue.get('detail', '')
        
        # 主要金额字段
        business_amount = issue.get('business_amount')
        finance_amount = issue.get('finance_amount')
        amount_diff = None
        if business_amount is not None and finance_amount is not None:
            try:
                amount_diff = float(business_amount) - float(finance_amount)
            except (ValueError, TypeError):
                pass
        
        # 多字段比较值
        comparison_values = issue.get('comparison_values', {})
        if not comparison_values and comparison_fields:
            # 从 issue 中自动构建 comparison_values
            comparison_values = _build_comparison_values(issue, comparison_fields)
        
        # 合并键字段（支持联合键）
        key_fields_data = issue.get('key_fields', {})
        if not key_fields_data and key_fields_mapping:
            # 从 issue 中根据映射定义自动构建 key_fields
            key_fields_data = _build_key_fields(issue, key_fields_mapping)
        
        # 如果没有 order_id，尝试从 key_fields 中生成
        if not order_id and key_fields_data:
            # 使用联合键值组合生成 order_id
            order_id = _generate_composite_key(key_fields_data)
        
        # 原始数据
        business_raw = issue.get('business_raw')
        finance_raw = issue.get('finance_raw')
        
        # 提取动态字段
        extra_data = {}
        for k, v in issue.items():
            if k not in fixed_fields and v is not None:
                extra_data[k] = v
        
        values.append((
            file_group_id, order_id, issue_type, detail,
            business_amount, finance_amount, amount_diff,
            json.dumps(comparison_values), json.dumps(key_fields_data),
            json.dumps(extra_data),
            json.dumps(business_raw) if business_raw else None,
            json.dumps(finance_raw) if finance_raw else None,
            idx, 'pending'
        ))
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur, sql, values,
                    template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                )
                conn.commit()
                logger.info(f"保存差异记录: file_group_id={file_group_id}, count={len(values)}")
                return len(values)
    except Exception as e:
        logger.error(f"保存差异记录失败: {e}")
        return 0


def _build_key_fields(issue: dict, key_fields_mapping: List[dict]) -> dict:
    """
    根据映射定义自动构建合并键字段
    
    Args:
        issue: 差异记录
        key_fields_mapping: 合并键映射定义列表
    
    Returns:
        键值对字典 {source_col: value, target_col: value, ...}
    """
    key_fields = {}
    
    for mapping in key_fields_mapping:
        source_col = mapping.get('source_col')
        target_col = mapping.get('target_col')
        
        # 存储 source 和 target 两边的键值
        if source_col and source_col in issue:
            key_fields[source_col] = issue[source_col]
        if target_col and target_col in issue:
            key_fields[target_col] = issue[target_col]
    
    return key_fields


def _generate_composite_key(key_fields: dict) -> str:
    """
    根据联合键字段生成组合键值字符串
    
    Args:
        key_fields: 键值对字典
    
    Returns:
        组合键字符串，如 "订单A001|渠道123"
    """
    # 按 key 排序保证一致性
    sorted_keys = sorted(key_fields.keys())
    values = [str(key_fields.get(k, '')) for k in sorted_keys]
    return '|'.join(values)


def _build_comparison_values(issue: dict, comparison_fields: List[dict]) -> dict:
    """
    根据 comparison_fields 定义自动构建比较值
    
    Args:
        issue: 差异记录
        comparison_fields: 比较字段定义
    
    Returns:
        比较值字典 {"字段名": {"target": 目标值, "source": 源值, "diff": 差异, "match": bool}}
    """
    comparison_values = {}
    
    for field_def in comparison_fields:
        name = field_def.get('name')
        target_col = field_def.get('target_col')
        source_col = field_def.get('source_col')
        field_type = field_def.get('type', 'text')
        
        target_val = issue.get(target_col)
        source_val = issue.get(source_col)
        
        # 计算差异
        diff = None
        match = None
        
        if field_type == 'amount' and target_val is not None and source_val is not None:
            try:
                diff = float(target_val) - float(source_val)
                match = abs(diff) < 0.01  # 金额容差
            except (ValueError, TypeError):
                pass
        elif field_type == 'date':
            match = str(target_val) == str(source_val) if target_val and source_val else False
        else:
            match = str(target_val) == str(source_val) if target_val is not None and source_val is not None else False
        
        comparison_values[name] = {
            'target': target_val,
            'source': source_val,
            'diff': diff,
            'match': match,
            'target_col': target_col,
            'source_col': source_col,
            'type': field_type
        }
    
    return comparison_values


def get_result_records(
    file_group_id: str,
    process_status: str = None,
    issue_type: str = None,
    limit: int = 1000,
    offset: int = 0,
) -> List[dict]:
    """
    获取差异记录
    
    Args:
        file_group_id: 文件组ID
        process_status: 处理状态过滤
        issue_type: 问题类型过滤
        limit: 返回数量限制
        offset: 偏移量
    
    Returns:
        差异记录列表，comparison_values、key_fields、extra_data 字段已合并到主记录中
    """
    conditions = ["file_group_id = %s"]
    params = [file_group_id]
    
    if process_status:
        conditions.append("process_status = %s")
        params.append(process_status)
    if issue_type:
        conditions.append("issue_type = %s")
        params.append(issue_type)
    
    sql = f"""
    SELECT id, order_id, issue_type, detail,
           business_amount, finance_amount, amount_diff,
           comparison_values, key_fields, extra_data,
           business_raw, finance_raw,
           process_status, processed_by, processed_at, 
           process_result, process_notes,
           review_status, reviewed_by, reviewed_at, review_notes,
           row_index, created_at, updated_at
    FROM reconciliation_result_records
    WHERE {' AND '.join(conditions)}
    ORDER BY row_index
    LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                records = []
                for r in cur.fetchall():
                    rec = _serialize_datetimes(dict(r))
                    # 合并 comparison_values 到主记录（展开为字段名）
                    comparison = rec.pop('comparison_values', {}) or {}
                    for field_name, vals in comparison.items():
                        rec[f'{field_name}_target'] = vals.get('target')
                        rec[f'{field_name}_source'] = vals.get('source')
                        rec[f'{field_name}_diff'] = vals.get('diff')
                        rec[f'{field_name}_match'] = vals.get('match')
                    # 保留原始 comparison_values 用于完整数据
                    rec['comparison_values'] = comparison
                    
                    # 合并 key_fields 到主记录
                    keys = rec.pop('key_fields', {}) or {}
                    for k, v in keys.items():
                        rec[k] = v
                    rec['key_fields'] = keys
                    
                    # 合并 extra_data 到主记录
                    extra = rec.pop('extra_data', {}) or {}
                    rec.update(extra)
                    rec['extra_data'] = extra
                    
                    records.append(rec)
                return records
    except Exception as e:
        logger.error(f"获取差异记录失败: {e}")
        return []


def update_record_process_status(
    record_id: str,
    process_status: str,
    processed_by: str = None,
    process_result: str = None,
    process_notes: str = None,
) -> bool:
    """
    更新差异记录的处理状态
    
    Args:
        record_id: 记录ID
        process_status: 新的处理状态
        processed_by: 处理人ID
        process_result: 处理结果
        process_notes: 处理备注
    
    Returns:
        是否更新成功
    """
    update_parts = [
        "process_status = %s",
        "updated_at = CURRENT_TIMESTAMP"
    ]
    params = [process_status]
    
    if processed_by:
        update_parts.append("processed_by = %s")
        params.append(processed_by)
        update_parts.append("processed_at = CURRENT_TIMESTAMP")
    
    if process_result:
        update_parts.append("process_result = %s")
        params.append(process_result)
    
    if process_notes is not None:
        update_parts.append("process_notes = %s")
        params.append(process_notes)
    
    params.append(record_id)
    sql = f"""
    UPDATE reconciliation_result_records 
    SET {', '.join(update_parts)}
    WHERE id = %s
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                conn.commit()
                
                # 记录处理历史
                if cur.rowcount > 0:
                    _add_process_history(
                        record_id=record_id,
                        action="status_change",
                        new_status=process_status,
                        operator_id=processed_by,
                        content=process_notes
                    )
                
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"更新差异处理状态失败 (record_id={record_id}): {e}")
        return False


def batch_update_process_status(
    record_ids: List[str],
    process_status: str,
    processed_by: str = None,
    process_result: str = None,
    process_notes: str = None,
) -> int:
    """批量更新差异处理状态"""
    if not record_ids:
        return 0
    
    update_parts = ["process_status = %s", "updated_at = CURRENT_TIMESTAMP"]
    params = [process_status]
    
    if processed_by:
        update_parts.append("processed_by = %s")
        params.append(processed_by)
        update_parts.append("processed_at = CURRENT_TIMESTAMP")
    if process_result:
        update_parts.append("process_result = %s")
        params.append(process_result)
    if process_notes is not None:
        update_parts.append("process_notes = %s")
        params.append(process_notes)
    
    params.append(tuple(record_ids))
    sql = f"""
    UPDATE reconciliation_result_records 
    SET {', '.join(update_parts)}
    WHERE id IN %s
    """
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                affected = cur.rowcount
                conn.commit()
                
                # 批量记录历史
                for rid in record_ids:
                    _add_process_history(
                        record_id=rid,
                        action="status_change",
                        new_status=process_status,
                        operator_id=processed_by,
                        content=process_notes
                    )
                
                return affected
    except Exception as e:
        logger.error(f"批量更新差异处理状态失败: {e}")
        return 0


# ── 列定义操作 ───────────────────────────────────────────────────────────

def save_column_definitions(
    session_id: str,
    columns: List[dict],
) -> int:
    """
    保存列定义
    
    Args:
        session_id: 会话ID
        columns: 列定义列表 [{name, display_name, type, order, ...}, ...]
    
    Returns:
        成功保存的列数
    """
    if not columns:
        return 0
    
    sql = """
    INSERT INTO reconciliation_result_columns 
    (session_id, column_name, display_name, column_type, column_order, 
     is_visible, width, format_config, validation_rules)
    VALUES %s
    ON CONFLICT (session_id, column_name) DO UPDATE SET
        display_name = EXCLUDED.display_name,
        column_type = EXCLUDED.column_type,
        column_order = EXCLUDED.column_order,
        is_visible = EXCLUDED.is_visible,
        width = EXCLUDED.width,
        format_config = EXCLUDED.format_config
    """
    
    values = []
    for col in columns:
        values.append((
            session_id,
            col.get('name'),
            col.get('display_name'),
            col.get('type', 'text'),
            col.get('order', 0),
            col.get('is_visible', True),
            col.get('width'),
            json.dumps(col.get('format_config', {})),
            json.dumps(col.get('validation_rules', {}))
        ))
    
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(cur, sql, values)
                conn.commit()
                return len(values)
    except Exception as e:
        logger.error(f"保存列定义失败: {e}")
        return 0


def get_column_definitions(session_id: str) -> List[dict]:
    """获取列定义"""
    sql = """
    SELECT column_name, display_name, column_type, column_order, 
           is_visible, width, format_config, validation_rules
    FROM reconciliation_result_columns
    WHERE session_id = %s
    ORDER BY column_order
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (session_id,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"获取列定义失败 (session_id={session_id}): {e}")
        return []


# ── 处理历史操作 ─────────────────────────────────────────────────────────

def _add_process_history(
    record_id: str,
    action: str,
    operator_id: str = None,
    old_status: str = None,
    new_status: str = None,
    content: str = None,
) -> bool:
    """添加处理历史记录（内部函数）"""
    sql = """
    INSERT INTO reconciliation_process_history 
    (record_id, action, old_status, new_status, content, operator_id)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    record_id, action, old_status, new_status, content, operator_id
                ))
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"添加处理历史失败: {e}")
        return False


def get_process_history(record_id: str) -> List[dict]:
    """获取差异记录的处理历史"""
    sql = """
    SELECT h.*, u.username as operator_name
    FROM reconciliation_process_history h
    LEFT JOIN users u ON h.operator_id = u.id
    WHERE h.record_id = %s
    ORDER BY h.created_at DESC
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (record_id,))
                return [_serialize_datetimes(dict(r)) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"获取处理历史失败 (record_id={record_id}): {e}")
        return []


# ── 统计查询 ─────────────────────────────────────────────────────────────

def get_session_statistics(session_id: str) -> dict:
    """获取会话统计信息"""
    sql = """
    SELECT 
        COUNT(rec.id) as total_issues,
        COUNT(*) FILTER (WHERE rec.process_status = 'pending') as pending_issues,
        COUNT(*) FILTER (WHERE rec.process_status = 'processing') as processing_issues,
        COUNT(*) FILTER (WHERE rec.process_status = 'resolved') as resolved_issues,
        COUNT(*) FILTER (WHERE rec.process_status = 'ignored') as ignored_issues,
        COUNT(*) FILTER (WHERE rec.process_status = 'escalated') as escalated_issues
    FROM reconciliation_result_records rec
    JOIN reconciliation_file_groups fg ON rec.file_group_id = fg.id
    WHERE fg.session_id = %s
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (session_id,))
                row = cur.fetchone()
                return dict(row) if row else {}
    except Exception as e:
        logger.error(f"获取会话统计失败 (session_id={session_id}): {e}")
        return {}


def get_issues_by_type(session_id: str) -> dict:
    """获取按问题类型分类的统计"""
    sql = """
    SELECT 
        rec.issue_type,
        COUNT(*) as count,
        COUNT(*) FILTER (WHERE rec.process_status = 'pending') as pending,
        COUNT(*) FILTER (WHERE rec.process_status = 'resolved') as resolved
    FROM reconciliation_result_records rec
    JOIN reconciliation_file_groups fg ON rec.file_group_id = fg.id
    WHERE fg.session_id = %s
    GROUP BY rec.issue_type
    ORDER BY count DESC
    """
    conn_manager = get_conn()
    try:
        with conn_manager as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (session_id,))
                return {r['issue_type']: dict(r) for r in cur.fetchall()}
    except Exception as e:
        logger.error(f"获取问题类型统计失败 (session_id={session_id}): {e}")
        return {}

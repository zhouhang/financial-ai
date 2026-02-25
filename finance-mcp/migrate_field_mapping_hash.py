#!/usr/bin/env python3
"""迁移脚本：为现有规则计算并填充 field_mapping_hash

运行方式：
    cd finance-mcp
    python3 migrate_field_mapping_hash.py

功能：
    1. 添加 field_mapping_hash 字段（如不存在）
    2. 创建 B-tree 索引（如不存在）
    3. 为所有 field_mapping_hash 为空的规则计算并填充哈希值
"""

import sys
import os
import json
import hashlib
import logging
from typing import Optional

import psycopg2
import psycopg2.extras

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ── 数据库配置 ─────────────────────────────────────────────────────────────────

def get_db_config():
    """从环境变量或 .env 读取数据库配置"""
    # 尝试加载 .env
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        env_path = Path(__file__).parent.parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass
    
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', '5432')),
        'database': os.getenv('DB_NAME', 'tally'),
        'user': os.getenv('DB_USER', 'tally_user'),
        'password': os.getenv('DB_PASSWORD', '123456'),
    }


def get_conn():
    """获取数据库连接"""
    return psycopg2.connect(**get_db_config())


# ── 哈希计算 ─────────────────────────────────────────────────────────────────

def compute_field_mapping_hash(rule_template: dict) -> str:
    """计算字段映射的哈希值，用于规则匹配推荐。
    
    提取6个关键字段（业务和财务的 order_id, amount, date），
    排序后计算 MD5 哈希。
    """
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
                value = ",".join(sorted(str(v) for v in value))
            elif value:
                value = str(value)
            else:
                value = ""
            fields.append(f"{source}.{role}={value}")
    
    fields.sort()
    hash_input = "|".join(fields)
    return hashlib.md5(hash_input.encode()).hexdigest()


# ── 迁移函数 ─────────────────────────────────────────────────────────────────

def add_field_mapping_hash_column():
    """迁移：为 reconciliation_rules 表添加 field_mapping_hash 字段"""
    sql = """
    ALTER TABLE reconciliation_rules 
    ADD COLUMN IF NOT EXISTS field_mapping_hash VARCHAR(32);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info("field_mapping_hash 字段已添加")


def create_field_mapping_hash_index():
    """迁移：创建 field_mapping_hash 字段的 B-tree 索引"""
    sql = """
    CREATE INDEX IF NOT EXISTS idx_rules_field_mapping_hash 
    ON reconciliation_rules(field_mapping_hash);
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info("field_mapping_hash 索引已创建")


def migrate_existing_rules_hash() -> int:
    """迁移：为现有规则计算并填充 field_mapping_hash"""
    sql = """
    SELECT id, name, rule_template 
    FROM reconciliation_rules 
    WHERE field_mapping_hash IS NULL OR field_mapping_hash = ''
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            
            if not rows:
                logger.info("没有需要迁移的规则")
                return 0
            
            count = 0
            for row in rows:
                rule_id = row["id"]
                rule_name = row["name"]
                template = row["rule_template"]
                
                if isinstance(template, str):
                    template = json.loads(template)
                
                if not template:
                    logger.warning(f"规则 '{rule_name}' 没有 rule_template，跳过")
                    continue
                
                hash_value = compute_field_mapping_hash(template)
                
                update_sql = """
                UPDATE reconciliation_rules 
                SET field_mapping_hash = %s 
                WHERE id = %s
                """
                cur.execute(update_sql, (hash_value, rule_id))
                logger.info(f"  - {rule_name}: {hash_value[:8]}...")
                count += 1
            
            conn.commit()
            return count


def main():
    logger.info("=" * 60)
    logger.info("开始迁移 field_mapping_hash")
    logger.info("=" * 60)
    
    # 显示数据库配置
    config = get_db_config()
    logger.info(f"数据库: {config['database']}@{config['host']}:{config['port']}")
    
    # Step 1: 添加字段
    logger.info("\n[Step 1/3] 添加 field_mapping_hash 字段...")
    try:
        add_field_mapping_hash_column()
        logger.info("✓ 字段添加完成")
    except Exception as e:
        logger.error(f"✗ 添加字段失败: {e}")
        sys.exit(1)
    
    # Step 2: 创建索引
    logger.info("\n[Step 2/3] 创建 B-tree 索引...")
    try:
        create_field_mapping_hash_index()
        logger.info("✓ 索引创建完成")
    except Exception as e:
        logger.error(f"✗ 创建索引失败: {e}")
        sys.exit(1)
    
    # Step 3: 填充哈希值
    logger.info("\n[Step 3/3] 为现有规则计算 field_mapping_hash...")
    try:
        count = migrate_existing_rules_hash()
        logger.info(f"✓ 已更新 {count} 条规则")
    except Exception as e:
        logger.error(f"✗ 填充哈希值失败: {e}")
        sys.exit(1)
    
    logger.info("\n" + "=" * 60)
    logger.info("迁移完成!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

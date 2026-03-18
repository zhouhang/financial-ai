#!/usr/bin/env python3
"""
查询并展示 bus_rules 表数据
JSON 字段会以格式化后的 JSON 展示
"""
import json
import psycopg2
from psycopg2.extras import RealDictCursor

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'tally',
    'user': 'tally_user',
    'password': '123456'
}


def get_connection():
    """获取数据库连接"""
    return psycopg2.connect(**DB_CONFIG)


def format_json(obj, indent=2):
    """格式化 JSON 对象"""
    if obj is None:
        return None
    if isinstance(obj, str):
        try:
            return json.loads(obj)
        except (json.JSONDecodeError, TypeError):
            return obj
    return obj


def print_bus_rules():
    """查询并展示 bus_rules 表数据"""
    conn = get_connection()
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, rule_code, rule, memo, rule_type
            FROM bus_rules
            ORDER BY id;
        """)
        rows = cur.fetchall()
    
    print("=" * 100)
    print(f"bus_rules 表数据 (共 {len(rows)} 条记录)")
    print("=" * 100)
    
    for row in rows:
        print(f"\n{'='*100}")
        print(f"ID: {row['id']}")
        print(f"rule_code: {row['rule_code']}")
        print(f"memo: {row['memo']}")
        print(f"rule_type: {row['rule_type']}")
        print(f"{'-'*100}")
        print("rule (JSON):")
        
        # 格式化 JSON 字段
        rule_json = format_json(row['rule'])
        if isinstance(rule_json, dict):
            # 如果是字典，格式化输出
            print(json.dumps(rule_json, indent=2, ensure_ascii=False))
        else:
            # 如果解析失败，直接输出原始值
            print(rule_json)
    
    conn.close()
    print(f"\n{'='*100}")
    print("查询完成")
    print("=" * 100)


def print_bus_rules_summary():
    """以表格形式展示 bus_rules 表摘要"""
    conn = get_connection()
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, rule_code, memo, rule_type
            FROM bus_rules
            ORDER BY id;
        """)
        rows = cur.fetchall()
    
    print("\n" + "=" * 100)
    print("bus_rules 表摘要")
    print("=" * 100)
    print(f"{'ID':<6} {'rule_code':<25} {'rule_type':<10} {'memo':<50}")
    print("-" * 100)
    
    for row in rows:
        memo = (row['memo'] or '')[:47] + '...' if len(row['memo'] or '') > 50 else row['memo'] or ''
        print(f"{row['id']:<6} {row['rule_code']:<25} {row['rule_type']:<10} {memo:<50}")
    
    conn.close()
    print("=" * 100)


def print_bus_agent_rules():
    """查询并展示 bus_agent_rules 表数据"""
    conn = get_connection()
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, code, name, desc_text, parent_code, type, memo, file_rule_code, "order"
            FROM bus_agent_rules
            ORDER BY id;
        """)
        rows = cur.fetchall()
    
    print("\n" + "=" * 100)
    print(f"bus_agent_rules 表数据 (共 {len(rows)} 条记录)")
    print("=" * 100)
    
    for row in rows:
        type_desc = "数字员工" if row['type'] == '1' else "具体规则"
        print(f"\n{'='*100}")
        print(f"ID: {row['id']}")
        print(f"code: {row['code']}")
        print(f"name: {row['name']}")
        print(f"type: {row['type']} ({type_desc})")
        print(f"parent_code: {row['parent_code'] or '(无)'}")
        print(f"memo: {row['memo'] or '(无)'}")
        print(f"file_rule_code: {row['file_rule_code'] or '(无)'}")
        print(f"order: {row['order']}")
        if row['desc_text']:
            print(f"desc_text: {row['desc_text']}")
    
    conn.close()
    print(f"\n{'='*100}")
    print("查询完成")
    print("=" * 100)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        # 只显示 bus_agent_rules
        print_bus_agent_rules()
    elif len(sys.argv) > 1 and sys.argv[1] == "summary":
        # 只显示摘要
        print_bus_rules_summary()
    else:
        # 显示所有内容
        print_bus_rules_summary()
        print_bus_rules()
        print_bus_agent_rules()

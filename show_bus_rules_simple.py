#!/usr/bin/env python3
"""
以清晰格式展示 bus_rules 表数据
"""
import json
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'tally',
    'user': 'tally_user',
    'password': '123456'
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def show_rule_summary():
    """展示规则摘要"""
    conn = get_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, rule_code, rule_type, memo
            FROM bus_rules
            ORDER BY id;
        """)
        rows = cur.fetchall()
    
    print("\n" + "="*100)
    print("📋 bus_rules 表摘要")
    print("="*100)
    print(f"{'ID':<4} {'rule_code':<25} {'rule_type':<8} {'memo'}")
    print("-"*100)
    for row in rows:
        print(f"{row['id']:<4} {row['rule_code']:<25} {row['rule_type']:<8} {row['memo']}")
    print("="*100)
    conn.close()


def show_rule_detail(rule_code):
    """展示指定规则的详细 JSON"""
    conn = get_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, rule_code, rule_type, memo, rule
            FROM bus_rules
            WHERE rule_code = %s
            ORDER BY id;
        """, (rule_code,))
        row = cur.fetchone()
    
    if not row:
        print(f"❌ 未找到规则：{rule_code}")
        conn.close()
        return
    
    print("\n" + "="*100)
    print(f"📄 规则详情：{row['rule_code']}")
    print("="*100)
    print(f"ID: {row['id']}")
    print(f"类型：{row['rule_type']}")
    print(f"说明：{row['memo']}")
    print("-"*100)
    print("JSON 内容:")
    
    # 格式化 JSON
    rule_json = row['rule']
    if isinstance(rule_json, str):
        rule_json = json.loads(rule_json)
    
    print(json.dumps(rule_json, indent=2, ensure_ascii=False))
    print("="*100)
    conn.close()


def show_all_rules_json():
    """展示所有规则的 JSON（精简版）"""
    conn = get_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, rule_code, rule_type, memo, rule
            FROM bus_rules
            ORDER BY id;
        """)
        rows = cur.fetchall()
    
    for row in rows:
        print("\n" + "="*100)
        print(f"📄 [{row['id']}] {row['rule_code']} ({row['rule_type']})")
        print(f"   {row['memo']}")
        print("="*100)
        
        rule_json = row['rule']
        if isinstance(rule_json, str):
            rule_json = json.loads(rule_json)
        
        # 精简显示：只显示顶层键
        print("顶层结构:", list(rule_json.keys()))
        
        # 根据类型显示不同内容
        if row['rule_type'] == 'file':
            # 文件校验规则
            file_val = rule_json.get('file_validation_rules', {})
            print(f"  - version: {file_val.get('version', 'N/A')}")
            print(f"  - table_schemas 数量：{len(file_val.get('table_schemas', []))}")
            for ts in file_val.get('table_schemas', []):
                print(f"    • {ts.get('table_name')} ({ts.get('table_id')}) - {ts.get('description', '')[:50]}")
        
        elif row['rule_type'] == 'bus':
            # 业务规则
            if 'rules' in rule_json:
                rules = rule_json['rules']
                print(f"  - rules 数量：{len(rules)}")
                for r in rules:
                    target = r.get('target_table', 'N/A')
                    desc = r.get('description', '')[:50]
                    print(f"    • {r.get('rule_id')} → {target} - {desc}")
            
            if 'merge_rules' in rule_json:
                merge_rules = rule_json['merge_rules']
                print(f"  - merge_rules 数量：{len(merge_rules)}")
                for mr in merge_rules:
                    print(f"    • {mr.get('rule_id')} - {mr.get('table_name')} ({mr.get('merge_type', '')})")
            
            if 'reconciliation_config' in rule_json:
                print(f"  - 对账规则：包含核对配置")
                recon = rule_json['reconciliation_config']
                key_cols = recon.get('key_columns', {})
                print(f"    关键列：{key_cols.get('columns', [])}")
        
        print("="*100)
    
    conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "summary":
            show_rule_summary()
        elif sys.argv[1] == "all":
            show_all_rules_json()
        else:
            # 显示指定规则
            rule_code = sys.argv[1]
            show_rule_detail(rule_code)
    else:
        # 默认显示摘要 + 所有规则精简版
        show_rule_summary()
        print("\n\n按任意键继续查看 JSON 详情...")
        input()
        show_all_rules_json()

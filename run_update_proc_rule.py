"""
将 manual_voucher_sync_rule.json 内容更新至 bus_proc_rules 表 rule_code='recognition'
"""
import sys
import json
import os

sys.path.insert(0, '/Users/fanyuli/Desktop/workspace/financial-ai/finance-mcp')

from db_config import get_db_connection

JSON_FILE = '/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/skills/audit/references/manual_voucher_sync_rule.json'

# 1. 读取 JSON 文件
with open(JSON_FILE, 'r', encoding='utf-8') as f:
    rule_content = json.load(f)

print(f"JSON 文件读取成功，共 {len(rule_content.get('rules', []))} 条规则")

conn = get_db_connection()
try:
    with conn.cursor() as cur:
        # 先查一下表结构和目标行
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'bus_proc_rules'
            ORDER BY ordinal_position
        """)
        cols = cur.fetchall()
        print("\nbus_proc_rules 表字段：")
        for c in cols:
            print(f"  {c[0]}  ({c[1]})")

        cur.execute("SELECT * FROM bus_proc_rules WHERE rule_code = 'recognition'")
        row = cur.fetchone()
        if row is None:
            print("\n[ERROR] 未找到 rule_code='recognition' 的记录，请确认 rule_code 是否正确")
            sys.exit(1)

        col_names = [desc[0] for desc in cur.description]
        print(f"\n找到目标行，字段：{col_names}")
        print(f"当前行数据预览：")
        for k, v in zip(col_names, row):
            display = str(v)[:120] if v is not None else 'NULL'
            print(f"  {k}: {display}")

        # 找 rule / rule_json / content 等存储规则内容的字段
        # 优先用 rule，其次 rule_json，再次 content
        rule_field = None
        for candidate in ('rule', 'rule_json', 'content', 'rule_content', 'config', 'config_json'):
            if candidate in col_names:
                rule_field = candidate
                break

        if rule_field is None:
            print(f"\n[ERROR] 未找到合适的规则内容字段（尝试了 rule/rule_json/content/rule_content/config/config_json），请手动指定")
            sys.exit(1)

        print(f"\n将更新字段：{rule_field}")
        rule_json_str = json.dumps(rule_content, ensure_ascii=False)

        cur.execute(
            f"UPDATE bus_proc_rules SET {rule_field} = %s WHERE rule_code = 'recognition'",
            (rule_json_str,)
        )
        conn.commit()
        print(f"\n✅ 更新成功！rule_code='recognition' 的 {rule_field} 字段已更新")

except Exception as e:
    conn.rollback()
    print(f"\n❌ 更新失败: {e}")
    raise
finally:
    conn.close()

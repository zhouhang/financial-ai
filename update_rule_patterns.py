#!/usr/bin/env python3
"""直接更新规则中的 file_pattern，以验证修复"""
import os
import sys
import json
import psycopg2
import psycopg2.extras

# 数据库连接配置
db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "tally"),
    "user": os.getenv("DB_USER", "tally_user"),
    "password": os.getenv("DB_PASSWORD", "123456"),
}

# 连接数据库
conn = psycopg2.connect(**db_config)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# 查询现有规则
cur.execute("""
    SELECT id, name, rule_template
    FROM reconciliation_rules
    WHERE name = '南京飞翰'
""")

rule = cur.fetchone()
if not rule:
    print("❌ 规则不存在")
    cur.close()
    conn.close()
    sys.exit(1)

rule_id = rule['id']
rule_template = json.loads(rule['rule_template']) if isinstance(rule['rule_template'], str) else rule['rule_template']

print("=" * 80)
print("修复前的 file_pattern:")
print("=" * 80)

biz_patterns = rule_template.get('data_sources', {}).get('business', {}).get('file_pattern', [])
fin_patterns = rule_template.get('data_sources', {}).get('finance', {}).get('file_pattern', [])

print(f"business: {biz_patterns}")
print(f"finance:  {fin_patterns}")

# 现在手动应用 _expand_file_patterns 逻辑
FILE_PATTERN_EXTENSIONS = (".xlsx", ".xls", ".xlsm", ".xlsb", ".csv")

def expand_file_patterns(pattern: str) -> list:
    """扩展 file_pattern"""
    pattern_lower = pattern.lower()
    for ext in FILE_PATTERN_EXTENSIONS:
        if pattern_lower.endswith(ext):
            base = pattern[: -len(ext)]
            return [base + e for e in FILE_PATTERN_EXTENSIONS]
    return [pattern]

# 扩展patterns
expanded_biz_patterns = []
for p in biz_patterns:
    expanded_biz_patterns.extend(expand_file_patterns(p))
expanded_biz_patterns = list(set(expanded_biz_patterns))

expanded_fin_patterns = []
for p in fin_patterns:
    expanded_fin_patterns.extend(expand_file_patterns(p))
expanded_fin_patterns = list(set(expanded_fin_patterns))

print("\n" + "=" * 80)
print("修复后的 file_pattern:")
print("=" * 80)
print(f"business: {expanded_biz_patterns}")
print(f"finance:  {expanded_fin_patterns}")

# 更新 rule_template
rule_template['data_sources']['business']['file_pattern'] = expanded_biz_patterns
rule_template['data_sources']['finance']['file_pattern'] = expanded_fin_patterns

# 更新到数据库
rule_template_json = json.dumps(rule_template)
cur.execute("""
    UPDATE reconciliation_rules
    SET rule_template = %s
    WHERE id = %s
""", (rule_template_json, rule_id))

conn.commit()

print(f"\n✅ 规则已更新")

cur.close()
conn.close()

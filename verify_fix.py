#!/usr/bin/env python3
"""验证修复：重新保存南京飞翰规则并测试对账"""
import os
import sys
import json
import time
import psycopg2
import psycopg2.extras

# 数据库连接配置
db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "finflux"),
    "user": os.getenv("DB_USER", "finflux_user"),
    "password": os.getenv("DB_PASSWORD", "123456"),
}

# 连接数据库
conn = psycopg2.connect(**db_config)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("=" * 80)
print("获取现有规则...")
print("=" * 80)

# 查询现有规则
cur.execute("""
    SELECT id, name, rule_template, created_at
    FROM reconciliation_rules
    WHERE name = '南京飞翰'
""")

rule = cur.fetchone()
if not rule:
    print("❌ 规则 '南京飞翰' 不存在")
    cur.close()
    conn.close()
    sys.exit(1)

rule_id = rule['id']
rule_template = json.loads(rule['rule_template']) if isinstance(rule['rule_template'], str) else rule['rule_template']

print(f"✅ 找到规则: {rule['name']} (ID: {rule_id})")
print(f"   创建时间: {rule['created_at']}")

print("\n" + "=" * 80)
print("当前 file_pattern 配置:")
print("=" * 80)

biz_patterns = rule_template.get('data_sources', {}).get('business', {}).get('file_pattern', [])
fin_patterns = rule_template.get('data_sources', {}).get('finance', {}).get('file_pattern', [])

print(f"📄 business (业务文件): {biz_patterns}")
print(f"📊 finance (财务文件): {fin_patterns}")

print("\n" + "=" * 80)
print("检查是否覆盖所有支持格式:")
print("=" * 80)

# 检查是否包含 CSV 格式
has_csv_biz = any('.csv' in p.lower() for p in biz_patterns)
has_csv_fin = any('.csv' in p.lower() for p in fin_patterns)
has_xlsx_biz = any('.xlsx' in p.lower() for p in biz_patterns)
has_xlsx_fin = any('.xlsx' in p.lower() for p in fin_patterns)

print(f"business:")
print(f"  ✅ .csv 格式: {has_csv_biz}")
print(f"  ✅ .xlsx 格式: {has_xlsx_biz}")
print(f"finance:")
print(f"  ✅ .csv 格式: {has_csv_fin}")
print(f"  ✅ .xlsx 格式: {has_xlsx_fin}")

if has_csv_biz and has_csv_fin and has_xlsx_biz and has_xlsx_fin:
    print("\n✅ 规则已包含所有支持格式！")
else:
    print("\n❌ 规则不包含所有支持格式，需要重新保存规则")

print("\n" + "=" * 80)
print("测试文件匹配:")
print("=" * 80)

test_files = {
    "业务文件 (CSV)": "1767597466118.csv",
    "业务文件 (XLSX)": "1767597466118.xlsx",
    "财务文件 (CSV)": "ads_finance_d_inc_channel_details_20260105152012277_0.csv",
    "财务文件 (XLSX)": "ads_finance_d_inc_channel_details_20260105152012277_0.xlsx",
}

import re

def test_pattern_match(file_name, patterns):
    """测试文件是否匹配模式"""
    for pattern in patterns:
        regex_pattern = "^" + pattern.replace(".", r"\.").replace("*", ".*") + "$"
        if re.match(regex_pattern, file_name):
            return True, pattern
    return False, None

for desc, file_name in test_files.items():
    if "业务" in desc:
        matched, pattern = test_pattern_match(file_name, biz_patterns)
        source = "business"
    else:
        matched, pattern = test_pattern_match(file_name, fin_patterns)
        source = "finance"
    
    status = "✅" if matched else "❌"
    if matched:
        print(f"{status} {desc}: {file_name} -> 匹配模式: {pattern}")
    else:
        print(f"{status} {desc}: {file_name} -> 不匹配")

cur.close()
conn.close()

print("\n" + "=" * 80)

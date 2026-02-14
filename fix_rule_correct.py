#!/usr/bin/env python3
"""正确处理带有数字后缀的文件名"""
import os
import json
import psycopg2
import psycopg2.extras
import re

FILE_PATTERN_EXTENSIONS = (".xlsx", ".xls", ".xlsm", ".xlsb", ".csv")

def _expand_file_patterns(pattern: str) -> list[str]:
    """如果是 Excel 或 CSV 格式的 pattern，扩展为所有支持格式并返回列表"""
    pattern_lower = pattern.lower()
    for ext in FILE_PATTERN_EXTENSIONS:
        if pattern_lower.endswith(ext):
            base = pattern[: -len(ext)]
            return [base + e for e in FILE_PATTERN_EXTENSIONS]
    return [pattern]

# 实际的文件名
actual_files = {
    "business": "1767597466118.csv",
    "finance": "ads_finance_d_inc_channel_details_20260105152012277_0.csv"
}

print("=" * 100)
print("生成正确的 file_pattern")
print("=" * 100)

patterns_by_source = {}

for source, filename in actual_files.items():
    print(f"\n📄 {source}: {filename}")
    
    # 生成两个模式：
    # 1. 原始文件名（不包含时间戳）
    # 2. 带时间戳的通配符版本
    #    - 对于纯数字开头的文件名（如 1767597466118.csv），生成 1767597466118_*.csv
    #    - 对于带有时间戳部分的文件名（如 ads_...277_0.csv），需要找到真正的时间戳
    
    # 先检查是否已经包含了数字后缀（表示时间戳）
    # 例如：ads_finance_d_inc_channel_details_20260105152012277_0.csv
    # 这里 20260105152012277 本身已经是时间戳了
    
    # 为了简单起见，对所有文件生成两个模式：
    # 1. 原始文件名
    # 2. 文件名前缀 + _*  （用于匹配带时间戳的版本）
    
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        # 分析：是否最后一个 _ 后跟纯数字
        last_underscore = name_parts[0].rfind('_')
        if last_underscore != -1:
            last_part = name_parts[0][last_underscore + 1:]
            if last_part.isdigit() and len(last_part) <= 3:
                # 这可能是版本号（如_0），不是时间戳
                # 生成 filename_*.ext 来匹配带时间戳的版本
                # 例如：ads_finance_d_inc_channel_details_20260105152012277_0.csv
                #    -> ads_finance_d_inc_channel_details_20260105152012277_0_*.csv
                base = name_parts[0]
                patterns = [
                    filename,  # 原始文件名
                    f"{base}_*.{name_parts[1]}"  # 带时间戳的通配符
                ]
            else:
                # 最后一段看起来像时间戳，只生成通配符版本
                # 例如 file_123456.csv  
                patterns = [
                    filename,
                    re.sub(r'_(\d+)(\.\w+)$', r'_*\2', filename)
                ]
        else:
            # 没有下划线，生成 filename_*.ext
            patterns = [
                filename,
                f"{name_parts[0]}_*.{name_parts[1]}"
            ]
    else:
        patterns = [filename]
    
    print(f"   生成的基础模式: {patterns}")
    
    # 扩展为所有支持的格式
    expanded = []
    for p in patterns:
        expanded.extend(_expand_file_patterns(p))
    expanded = list(set(expanded))
    
    print(f"   扩展后: {len(expanded)} 个模式")
    print(f"   样例: {sorted(list(expanded))[:3]}...")
    
    patterns_by_source[source] = expanded

# 更新数据库
db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "finflux"),
    "user": os.getenv("DB_USER", "finflux_user"),
    "password": os.getenv("DB_PASSWORD", "123456"),
}

conn = psycopg2.connect(**db_config)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
    SELECT id, name, rule_template
    FROM reconciliation_rules
    WHERE name = '南京飞翰'
""")

rule = cur.fetchone()
if rule:
    rule_id = rule['id']
    rule_template = json.loads(rule['rule_template']) if isinstance(rule['rule_template'], str) else rule['rule_template']
    
    rule_template['data_sources']['business']['file_pattern'] = patterns_by_source['business']
    rule_template['data_sources']['finance']['file_pattern'] = patterns_by_source['finance']
    
    rule_template_json = json.dumps(rule_template)
    cur.execute("""
        UPDATE reconciliation_rules
        SET rule_template = %s
        WHERE id = %s
    """, (rule_template_json, rule_id))
    
    conn.commit()
    print(f"\n✅ 规则已更新！")

cur.close()
conn.close()

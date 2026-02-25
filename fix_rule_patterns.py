#!/usr/bin/env python3
"""使用新逻辑更新现有规则"""
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

def generate_patterns_from_filename(filename: str) -> list[str]:
    """根据文件名生成 file_pattern"""
    pattern = filename
    
    # 首先尝试匹配 _HHMMSS 格式（6位数字，时间戳格式）
    pattern = re.sub(r'_(\d{6})(\.\w+)$', r'_*\2', pattern)
    
    # 如果上面没匹配到，尝试匹配其他数字后缀格式（任意长度的数字）
    if pattern == filename:
        pattern = re.sub(r'_(\d+)(\.\w+)$', r'_*\2', pattern)
    
    # 如果还是没匹配到，说明文件名本身可能不包含时间戳
    if pattern == filename:
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) == 2:
            patterns_to_add = [
                filename,  # 原始文件名
                f"{name_parts[0]}_*.{name_parts[1]}"  # 带时间戳的通配符
            ]
        else:
            patterns_to_add = [filename]
    else:
        patterns_to_add = [pattern]
    
    # 扩展为所有支持的格式
    expanded = []
    for p in patterns_to_add:
        expanded.extend(_expand_file_patterns(p))
    
    return list(set(expanded))

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

# 查询规则
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
    exit(1)

rule_id = rule['id']
rule_template = json.loads(rule['rule_template']) if isinstance(rule['rule_template'], str) else rule['rule_template']

# 从规则中提取原始文件名（这是一个近似值，因为规则模式中可能已经没有了）
# 我们需要从当前的模式中反向推断

print("=" * 100)
print(f"规则: {rule['name']} (ID: {rule_id})")
print("=" * 100)

# 现有的 patterns
biz_patterns_old = rule_template.get('data_sources', {}).get('business', {}).get('file_pattern', [])
fin_patterns_old = rule_template.get('data_sources', {}).get('finance', {}).get('file_pattern', [])

print(f"\n修复前:")
print(f"  business: {biz_patterns_old}")
print(f"  finance:  {fin_patterns_old}")

# 反向推断原始文件名
def extract_base_filename(pattern: str) -> str:
    """从模式中提取基础文件名"""
    # 移除文件格式后缀
    for ext in FILE_PATTERN_EXTENSIONS:
        if pattern.endswith(ext):
            base = pattern[:-len(ext)]
            # 移除 _* 后缀
            if base.endswith('_*'):
                base = base[:-2]
            return base + ext
    return pattern

# 生成新的patterns
biz_patterns_new = []
for old_pattern in biz_patterns_old:
    base_file = extract_base_filename(old_pattern)
    new_patterns = generate_patterns_from_filename(base_file)
    biz_patterns_new.extend(new_patterns)

fin_patterns_new = []
for old_pattern in fin_patterns_old:
    base_file = extract_base_filename(old_pattern)
    new_patterns = generate_patterns_from_filename(base_file)
    fin_patterns_new.extend(new_patterns)

biz_patterns_new = list(set(biz_patterns_new))
fin_patterns_new = list(set(fin_patterns_new))

print(f"\n修复后:")
print(f"  business: {biz_patterns_new}")
print(f"  finance:  {fin_patterns_new}")

# 更新规则
rule_template['data_sources']['business']['file_pattern'] = biz_patterns_new
rule_template['data_sources']['finance']['file_pattern'] = fin_patterns_new

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

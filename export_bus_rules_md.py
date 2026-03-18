#!/usr/bin/env python3
"""
将 bus_rules 表的每条数据导出为单独的 Markdown 文件
保存到桌面，文件名以 rule_code 命名
"""
import json
import os
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

# 桌面目录
DESKTOP_DIR = os.path.expanduser("~/Desktop/工作/福禄财务数据/bus_rules_export")


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


def generate_markdown(row):
    """生成 Markdown 内容"""
    rule_json = format_json(row['rule'])
    
    # 规则类型描述
    type_desc_map = {
        'file': '📁 文件校验规则',
        'bus': '💼 业务规则'
    }
    type_desc = type_desc_map.get(row['rule_type'], row['rule_type'])
    
    # 构建 Markdown 内容
    md_content = f"""# {row['rule_code']}

## 📋 基本信息

| 字段 | 值 |
|------|-----|
| **ID** | {row['id']} |
| **规则编码** | `{row['rule_code']}` |
| **规则类型** | {type_desc} |
| **说明** | {row['memo']} |

---

## 📄 JSON 内容

```json
{json.dumps(rule_json, indent=2, ensure_ascii=False)}
```

---

## 📊 规则结构分析

"""
    
    # 根据规则类型添加不同的分析
    if isinstance(rule_json, dict):
        if row['rule_type'] == 'file':
            # 文件校验规则
            file_val = rule_json.get('file_validation_rules', {})
            md_content += f"""### 文件校验规则配置

- **版本**: {file_val.get('version', 'N/A')}
- **描述**: {file_val.get('description', 'N/A')}
- **表数量**: {len(file_val.get('table_schemas', []))}

#### 表结构定义

"""
            for i, ts in enumerate(file_val.get('table_schemas', []), 1):
                is_ness = "✅ 必传" if ts.get('is_ness') else "⚪ 可选"
                md_content += f"""
##### {i}. {ts.get('table_name')} (`{ts.get('table_id')}`)

- **必要性**: {is_ness}
- **文件类型**: {', '.join(ts.get('file_type', []))}
- **描述**: {ts.get('description', 'N/A')}
- **必需列**: {', '.join(ts.get('required_columns', []))}
- **可选列**: {len(ts.get('optional_columns', []))} 个
- **列别名字段**: {len(ts.get('column_aliases', {}))} 个

"""
        
        elif row['rule_type'] == 'bus':
            # 业务规则
            if 'rules' in rule_json:
                rules = rule_json['rules']
                md_content += f"""### 数据整理规则

- **规则数量**: {len(rules)}

#### 规则详情

"""
                for i, r in enumerate(rules, 1):
                    md_content += f"""
##### {i}. {r.get('rule_id', 'N/A')}

- **目标表**: {r.get('target_table', 'N/A')}
- **描述**: {r.get('description', 'N/A')}
- **源表**: {r.get('source_tables', 'N/A')}
- **字段映射数量**: {len(r.get('field_mappings', []))}
- **是否启用合并**: {'✅ 是' if r.get('merge', {}).get('enabled') else '❌ 否'}

"""
            
            if 'merge_rules' in rule_json:
                merge_rules = rule_json['merge_rules']
                md_content += f"""
### 数据合并规则

- **规则数量**: {len(merge_rules)}

#### 合并规则详情

"""
                for i, mr in enumerate(merge_rules, 1):
                    md_content += f"""
##### {i}. {mr.get('rule_id', 'N/A')}

- **表名**: {mr.get('table_name', 'N/A')}
- **合并类型**: {mr.get('merge_type', 'N/A')}
- **描述**: {mr.get('description', 'N/A')}
- **是否启用**: {'✅ 是' if mr.get('enabled') else '❌ 否'}

"""
            
            if 'reconciliation_config' in rule_json:
                recon = rule_json['reconciliation_config']
                md_content += f"""
### 对账规则配置

- **关键列**: {recon.get('key_columns', {}).get('columns', [])}
- **差异列数量**: {len(recon.get('diff_columns', {}).get('columns', []))}

"""
    
    md_content += """
---

*此文档由脚本自动生成*
"""
    
    return md_content


def export_all_rules():
    """导出所有规则为 Markdown 文件"""
    conn = get_connection()
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT id, rule_code, rule_type, memo, rule
            FROM bus_rules
            ORDER BY id;
        """)
        rows = cur.fetchall()
    
    # 创建输出目录
    os.makedirs(DESKTOP_DIR, exist_ok=True)
    print(f"📁 输出目录：{DESKTOP_DIR}")
    print("="*80)
    
    exported_files = []
    
    for row in rows:
        rule_code = row['rule_code']
        md_content = generate_markdown(row)
        
        # 生成文件名
        filename = f"{rule_code}.md"
        filepath = os.path.join(DESKTOP_DIR, filename)
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        exported_files.append({
            'rule_code': rule_code,
            'filepath': filepath,
            'rule_type': row['rule_type'],
            'memo': row['memo']
        })
        
        print(f"✅ 已导出：{filename}")
        print(f"   路径：{filepath}")
        print(f"   类型：{row['rule_type']}")
        print(f"   说明：{row['memo']}")
        print()
    
    conn.close()
    
    # 打印汇总
    print("="*80)
    print(f"📊 导出完成，共导出 {len(exported_files)} 个文件")
    print("="*80)
    
    # 生成索引文件
    index_md = generate_index(exported_files)
    index_path = os.path.join(DESKTOP_DIR, "README.md")
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(index_md)
    print(f"📑 已生成索引文件：README.md")
    
    return exported_files


def generate_index(exported_files):
    """生成索引 Markdown 文件"""
    file_rules = [f for f in exported_files if f['rule_type'] == 'file']
    bus_rules = [f for f in exported_files if f['rule_type'] == 'bus']
    
    md_content = f"""# bus_rules 规则文档索引

> 本目录包含 {len(exported_files)} 个规则文档，每个规则一个独立的 Markdown 文件。

---

## 📁 文件校验规则 (file) - 共 {len(file_rules)} 个

| 规则编码 | 说明 | 文档 |
|----------|------|------|
"""
    
    for f in file_rules:
        md_content += f"| `{f['rule_code']}` | {f['memo']} | [查看]({f['rule_code']}.md) |\n"
    
    md_content += f"""
## 💼 业务规则 (bus) - 共 {len(bus_rules)} 个

| 规则编码 | 说明 | 文档 |
|----------|------|------|
"""
    
    for f in bus_rules:
        md_content += f"| `{f['rule_code']}` | {f['memo']} | [查看]({f['rule_code']}.md) |\n"
    
    md_content += f"""
---

## 📊 统计信息

- **总规则数**: {len(exported_files)}
- **文件校验规则**: {len(file_rules)}
- **业务规则**: {len(bus_rules)}

---

*此索引由脚本自动生成*
"""
    
    return md_content


if __name__ == "__main__":
    print("="*80)
    print("📝 开始导出 bus_rules 规则文档")
    print("="*80)
    print()
    
    exported = export_all_rules()
    
    print()
    print("="*80)
    print("🎉 所有文档已保存到桌面:")
    print(f"   {DESKTOP_DIR}")
    print("="*80)

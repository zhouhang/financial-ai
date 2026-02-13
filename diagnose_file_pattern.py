#!/usr/bin/env python3
"""
诊断脚本：检查已保存规则的 file_pattern 是否正确生成

用法：
python diagnose_file_pattern.py <规则名称>

示例：
python diagnose_file_pattern.py "直销对账"
python diagnose_file_pattern.py "nanjing_feihan"
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 导入配置
sys.path.insert(0, str(Path(__file__).parent / "finance-mcp"))
from reconciliation.mcp_server.config import SCHEMA_DIR, RECONCILIATION_SCHEMAS_FILE

def load_json_with_comments(file_path: Path) -> dict:
    """加载 JSON 文件（支持注释）"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 移除注释
    import re
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    lines = []
    for line in content.split('\n'):
        if '//' in line:
            line = line[:line.index('//')]
        lines.append(line)
    content = '\n'.join(lines)
    
    return json.loads(content)

def diagnose_rule(rule_name: str):
    """诊断指定规则的 file_pattern"""
    print(f"\n{'='*60}")
    print(f"诊断规则: {rule_name}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 1. 读取配置文件
    if not RECONCILIATION_SCHEMAS_FILE.exists():
        print(f"❌ 配置文件不存在: {RECONCILIATION_SCHEMAS_FILE}")
        return
    
    try:
        config = load_json_with_comments(RECONCILIATION_SCHEMAS_FILE)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return
    
    # 2. 查找对应的规则
    types = config.get("types", [])
    matched_type = None
    schema_file = None
    
    for type_config in types:
        type_cn = type_config.get("name_cn", "")
        type_key = type_config.get("type_key", "")
        schema_path = type_config.get("schema_path", "")
        
        # 匹配规则名称（中文或英文）
        if type_cn == rule_name or type_key == rule_name or schema_path == rule_name:
            matched_type = type_config
            schema_file = schema_path
            break
    
    if not matched_type:
        # 尝试从 schema 目录中查找
        schema_files = list(SCHEMA_DIR.glob("*.json"))
        for sf in schema_files:
            if rule_name in sf.name:
                schema_file = sf.name
                break
        
        if not schema_file:
            print(f"❌ 找不到规则：{rule_name}")
            print(f"   可用规则：")
            for type_config in types:
                print(f"   - {type_config.get('name_cn', 'N/A')} ({type_config.get('type_key', 'N/A')})")
            return
    
    # 3. 读取规则的 schema 文件
    schema_path = SCHEMA_DIR / schema_file if isinstance(schema_file, str) else SCHEMA_DIR / matched_type.get("schema_path", "")
    
    if not schema_path.exists():
        print(f"❌ Schema 文件不存在: {schema_path}")
        return
    
    try:
        schema = load_json_with_comments(schema_path)
    except Exception as e:
        print(f"❌ 读取 Schema 文件失败: {e}")
        return
    
    # 4. 检查 file_pattern
    print(f"📄 Schema 文件: {schema_path.name}\n")
    
    data_sources = schema.get("data_sources", {})
    
    # 检查业务数据源
    business_source = data_sources.get("business", {})
    biz_patterns = business_source.get("file_pattern", [])
    
    print("🔹 业务数据源 (business):")
    print(f"   file_pattern: {biz_patterns}")
    
    if not biz_patterns:
        print(f"   ⚠️  警告：file_pattern 为空")
    else:
        has_wildcard = any('*' in p for p in biz_patterns)
        if not has_wildcard:
            print(f"   ❌ 严重问题：file_pattern 不包含通配符 (*)")
            print(f"   这意味着无法匹配带时间戳的文件！")
            print(f"   应该是：['业务_*.csv', '业务_*.xlsx'] 等格式")
        else:
            print(f"   ✅ 正常：包含通配符")
    
    biz_fields = business_source.get("field_roles", {})
    print(f"   field_roles: {list(biz_fields.keys())}")
    
    # 检查财务数据源
    finance_source = data_sources.get("finance", {})
    fin_patterns = finance_source.get("file_pattern", [])
    
    print(f"\n🔹 财务数据源 (finance):")
    print(f"   file_pattern: {fin_patterns}")
    
    if not fin_patterns:
        print(f"   ⚠️  警告：file_pattern 为空")
    else:
        has_wildcard = any('*' in p for p in fin_patterns)
        if not has_wildcard:
            print(f"   ❌ 严重问题：file_pattern 不包含通配符 (*)")
            print(f"   这意味着无法匹配带时间戳的文件！")
            print(f"   应该是：['财务_*.csv', '账单_*.xlsx'] 等格式")
        else:
            print(f"   ✅ 正常：包含通配符")
    
    fin_fields = finance_source.get("field_roles", {})
    print(f"   field_roles: {list(fin_fields.keys())}")
    
    # 5. 测试文件匹配
    print(f"\n📊 文件匹配测试:")
    test_files = [
        "业务数据.csv",
        "业务数据_134019.csv",
        "业务数据_20260213154030.csv",
        "财务账单.xlsx",
        "财务账单_134019.xlsx",
    ]
    
    from reconciliation.mcp_server.file_matcher import FileMatcher
    matcher = FileMatcher(schema)
    
    print("\n   业务数据测试：")
    for test_file in test_files[:3]:
        result = matcher._match_pattern(test_file, biz_patterns)
        status = "✅ 匹配" if result else "❌ 不匹配"
        print(f"   {status}: {test_file}")
    
    print("\n   财务数据测试：")
    for test_file in test_files[3:]:
        result = matcher._match_pattern(test_file, fin_patterns)
        status = "✅ 匹配" if result else "❌ 不匹配"
        print(f"   {status}: {test_file}")
    
    # 6. 检查其他配置
    print(f"\n⚙️ 其他配置:")
    tolerance = schema.get("tolerance", {})
    if tolerance:
        print(f"   tolerance: {tolerance}")
    
    custom_validations = schema.get("custom_validations", [])
    print(f"   custom_validations: {len(custom_validations)} 条规则")
    
    # 总结
    print(f"\n{'='*60}")
    print("📋 诊断总结:")
    
    biz_ok = biz_patterns and any('*' in p for p in biz_patterns)
    fin_ok = fin_patterns and any('*' in p for p in fin_patterns)
    
    if biz_ok and fin_ok:
        print("✅ 规则配置正常，可以用于对账")
    else:
        print("❌ 规则配置有问题：")
        if not biz_ok:
            print("   - 业务数据源的 file_pattern 有问题")
        if not fin_ok:
            print("   - 财务数据源的 file_pattern 有问题")
        print("\n💡 解决方案：")
        print("   1. 重新创建规则，确保上传的文件包含时间戳（如：filename_HHMMSS.csv）")
        print("   2. 在规则配置时，系统会自动生成通配符模式")
        print("   3. 如果问题仍未解决，检查文件上传是否成功")
    
    print(f"{'='*60}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python diagnose_file_pattern.py <规则名称>")
        print("\n示例:")
        print("  python diagnose_file_pattern.py '直销对账'")
        print("  python diagnose_file_pattern.py 'nanjing_feihan'")
        sys.exit(1)
    
    rule_name = sys.argv[1]
    diagnose_rule(rule_name)

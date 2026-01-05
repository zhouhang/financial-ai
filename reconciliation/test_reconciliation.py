"""
测试对账功能
"""
import asyncio
import json
from pathlib import Path
from mcp_server.reconciliation_engine import ReconciliationEngine
from mcp_server.schema_loader import SchemaLoader

async def test_reconciliation():
    """测试对账功能"""
    
    print("=" * 70)
    print("开始对账测试")
    print("=" * 70)
    
    # 1. 加载 schema
    schema_file = "schemas/example_schema.json"
    print(f"\n1. 加载 Schema: {schema_file}")
    schema = SchemaLoader.load_from_file(schema_file)
    SchemaLoader.validate_schema(schema)
    print("   ✅ Schema 验证通过")
    
    # 2. 准备文件
    business_file = str(Path("test_data/business_flow.csv").absolute())
    finance_file = str(Path("test_data/ads_finance_d_inc_channel_details_20250101.csv").absolute())
    
    print(f"\n2. 准备测试文件:")
    print(f"   业务文件: {business_file}")
    print(f"   财务文件: {finance_file}")
    
    # 检查文件是否存在
    if not Path(business_file).exists():
        print(f"   ❌ 业务文件不存在")
        return
    if not Path(finance_file).exists():
        print(f"   ❌ 财务文件不存在")
        return
    print("   ✅ 文件检查通过")
    
    # 3. 创建对账引擎
    print(f"\n3. 创建对账引擎...")
    engine = ReconciliationEngine(schema)
    print("   ✅ 对账引擎创建成功")
    
    # 4. 执行对账
    print(f"\n4. 执行对账（这可能需要一些时间）...")
    print("-" * 70)
    
    file_paths = [business_file, finance_file]
    result = engine.reconcile(file_paths)
    
    print("-" * 70)
    print("\n5. 对账结果:")
    
    # 摘要
    summary = result['summary']
    print(f"\n   📊 对账摘要:")
    print(f"      业务记录总数: {summary.total_business_records}")
    print(f"      财务记录总数: {summary.total_finance_records}")
    print(f"      匹配记录数:   {summary.matched_records}")
    print(f"      未匹配记录数: {summary.unmatched_records}")
    
    # 问题统计
    issues = result['issues']
    print(f"\n   ⚠️  问题详情（共 {len(issues)} 个问题）:")
    
    # 按问题类型统计
    issue_types = {}
    for issue in issues:
        issue_type = issue.issue_type
        issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
    
    for issue_type, count in issue_types.items():
        print(f"      {issue_type}: {count} 个")
    
    # 显示前10个问题示例
    print(f"\n   📋 问题示例（前10个）:")
    for i, issue in enumerate(issues[:10], 1):
        print(f"\n      问题 {i}:")
        print(f"        订单号: {issue.order_id}")
        print(f"        类型:   {issue.issue_type}")
        print(f"        业务值: {issue.business_value}")
        print(f"        财务值: {issue.finance_value}")
        print(f"        详情:   {issue.detail}")
    
    # 元数据
    metadata = result['metadata']
    print(f"\n   📝 元数据:")
    print(f"      业务文件数: {metadata.business_file_count}")
    print(f"      财务文件数: {metadata.finance_file_count}")
    print(f"      规则版本:   {metadata.rule_version}")
    print(f"      处理时间:   {metadata.processed_at}")
    
    # 保存结果到文件
    result_file = "results/test_result.json"
    Path("results").mkdir(exist_ok=True)
    
    result_dict = {
        "summary": summary.to_dict(),
        "issues": [issue.to_dict() for issue in issues],
        "metadata": metadata.to_dict()
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=2)
    
    print(f"\n6. 结果已保存到: {result_file}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成！")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_reconciliation())


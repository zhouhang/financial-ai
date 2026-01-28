#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接运行reconciliation引擎来验证结果
"""
import sys
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.reconciliation_engine import ReconciliationEngine
from reconciliation.mcp_server.schema_loader import SchemaLoader
import json

print("="*80)
print("【运行Reconciliation - 完整版本】")
print("="*80)

schema_path = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/schemas/direct_sales_schema.json'
business_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/官网.xlsx'
finance_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/合单.xlsx'

# 加载schema
schema = SchemaLoader.load_from_file(schema_path)

# 创建引擎
engine = ReconciliationEngine(schema)

# 运行reconciliation
print("\n运行reconciliation...")
result_full = engine.reconcile([business_file, finance_file])

# 提取result中的关键信息
result = {
    'total_issues': len(result_full['issues']),
    'issue_summary': result_full['summary'].get('issues_by_type', {}),
    'reconciliation_results': result_full['issues']
}

print(f"\n【Reconciliation结果】")
print(f"总问题数: {result['total_issues']}")
print(f"\n问题分类统计:")
for issue_type, count in result['issue_summary'].items():
    print(f"  {issue_type}: {count}")

print(f"\n【详细问题信息】")
print(f"总记录数: {len(result['reconciliation_results'])}")

# 查看第一条记录的结构
if result['reconciliation_results']:
    print(f"\n第一条记录的字段:")
    rec = result['reconciliation_results'][0]
    for key in rec.keys():
        print(f"  - {key}: {rec[key]}")

# 统计各类问题
issues_by_type = {}
for rec in result['reconciliation_results']:
    if 'issue_type' in rec:
        issue = rec['issue_type']
    elif 'reconciliation_result' in rec:
        issue = rec['reconciliation_result']
    else:
        issue = 'unknown'
    
    if issue not in issues_by_type:
        issues_by_type[issue] = []
    issues_by_type[issue].append(rec)

for issue_type, records in sorted(issues_by_type.items()):
    print(f"\n【{issue_type}】({len(records)}条)")
    # 显示前3条样本
    for i, rec in enumerate(records[:3]):
        print(f"  [{i+1}] 业务订单: {rec.get('business_order_id', 'N/A')}, 金额: {rec.get('business_amount', 'N/A')}")
        if 'finance_order_id' in rec and rec['finance_order_id']:
            print(f"      财务订单: {rec.get('finance_order_id', 'N/A')}, 金额: {rec.get('finance_amount', 'N/A')}")
        if rec.get('message'):
            print(f"      原因: {rec['message']}")
    if len(records) > 3:
        print(f"  ... 还有 {len(records) - 3} 条")

# 特别关注L订单
print("\n【L订单分析】")
l_orders = [rec for rec in result['reconciliation_results'] if str(rec.get('business_order_id', '')).startswith('L')]
print(f"L订单总数: {len(l_orders)}")
for rec in l_orders:
    print(f"  {rec['business_order_id']} - {rec['reconciliation_result']}: {rec.get('message', '')}")

# 特别关注104订单
print("\n【104订单分析】")
b104_orders = [rec for rec in result['reconciliation_results'] if str(rec.get('business_order_id', '')).startswith('104')]
print(f"业务104订单总数: {len(b104_orders)}")
matched_104 = len([r for r in b104_orders if r['reconciliation_result'] == 'matched'])
unmatched_104 = len([r for r in b104_orders if r['reconciliation_result'] != 'matched'])
print(f"  匹配: {matched_104}")
print(f"  不匹配: {unmatched_104}")

if unmatched_104 > 0:
    print(f"\n不匹配的104订单 (样本):")
    for rec in [r for r in b104_orders if r['reconciliation_result'] != 'matched'][:5]:
        print(f"  {rec['business_order_id']} - {rec['reconciliation_result']}: {rec.get('message', '')}")

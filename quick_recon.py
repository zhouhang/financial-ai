#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速对账结果统计
"""
import sys
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.reconciliation_engine import ReconciliationEngine
from reconciliation.mcp_server.schema_loader import SchemaLoader
import json

print("="*80)
print("【快速对账结果】")
print("="*80)

# 加载schema
schema_path = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/schemas/direct_sales_schema.json'
with open(schema_path, 'r', encoding='utf-8') as f:
    schema = json.load(f)

engine = ReconciliationEngine(schema)

# 执行对账
file_paths = [
    '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/官网.xlsx',
    '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/合单.xlsx'
]

print("\n执行对账...")
result = engine.reconcile(file_paths)

# 统计
issues = result.get('issues', [])
print(f"\n【对账结果】")
print(f"  总问题数: {len(issues)}")

issue_types = {}
for issue in issues:
    issue_type = issue.get('issue_type')
    if issue_type not in issue_types:
        issue_types[issue_type] = []
    issue_types[issue_type].append(issue)

print(f"\n【问题分类】")
for issue_type in sorted(issue_types.keys()):
    count = len(issue_types[issue_type])
    print(f"  {issue_type}: {count}")

# L订单统计
l_issues = [i for i in issues if i.get('order_id', '').startswith('L')]
print(f"\n【L订单统计】")
print(f"  L开头的订单总数: {len(l_issues)}")
if l_issues:
    l_by_type = {}
    for issue in l_issues:
        t = issue.get('issue_type')
        l_by_type[t] = l_by_type.get(t, 0) + 1
    for t in sorted(l_by_type.keys()):
        print(f"    {t}: {l_by_type[t]}")

print(f"\n✓ 完成")

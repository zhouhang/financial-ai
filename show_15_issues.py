#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
详细查看reconciliation的15条问题
"""
import sys
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.reconciliation_engine import ReconciliationEngine
from reconciliation.mcp_server.schema_loader import SchemaLoader
import json

schema_path = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/schemas/direct_sales_schema.json'
business_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/官网.xlsx'
finance_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/合单.xlsx'

# 加载schema
schema = SchemaLoader.load_from_file(schema_path)

# 创建引擎
engine = ReconciliationEngine(schema)

# 运行reconciliation
print("运行reconciliation...")
result_full = engine.reconcile([business_file, finance_file])

result = {
    'total_issues': len(result_full['issues']),
    'issue_summary': result_full['summary'].get('issues_by_type', {}),
    'reconciliation_results': result_full['issues']
}

print(f"\n【Reconciliation结果】")
print(f"总问题数: {result['total_issues']}")

# 详细显示每一条问题
print(f"\n【15条问题详情】")
for i, rec in enumerate(result['reconciliation_results']):
    print(f"\n[{i+1}] {rec.get('issue_type')}")
    print(f"    订单ID: {rec.get('order_id')}")
    print(f"    业务值: {rec.get('business_value')}")
    print(f"    财务值: {rec.get('finance_value')}")
    print(f"    详情: {rec.get('detail')}")

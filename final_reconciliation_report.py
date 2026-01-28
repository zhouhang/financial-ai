#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
最终reconciliation报告
"""
import sys
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.reconciliation_engine import ReconciliationEngine
from reconciliation.mcp_server.schema_loader import SchemaLoader

schema_path = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/schemas/direct_sales_schema.json'
business_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/官网.xlsx'
finance_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/合单.xlsx'

# 加载schema
schema = SchemaLoader.load_from_file(schema_path)

# 创建引擎
engine = ReconciliationEngine(schema)

# 运行reconciliation
result_full = engine.reconcile([business_file, finance_file])

print("\n" + "="*80)
print("【最终Reconciliation报告】")
print("="*80)

print(f"\n【对账概览】")
print(f"业务文件: 官网.xlsx")
print(f"财务文件: 合单.xlsx")
print(f"对账规则版本: {result_full['summary'].get('rule_version', 'N/A')}")

print(f"\n【对账结果统计】")
print(f"业务记录总数: {result_full['summary'].get('business_count', 0)}")
print(f"财务记录总数: {result_full['summary'].get('finance_count', 0)}")
print(f"匹配记录数: {result_full['summary'].get('matched_count', 0)}")
print(f"问题记录数: {len(result_full['issues'])}")
print(f"对账完成率: {result_full['summary'].get('reconciliation_rate', '0')}")

print(f"\n【问题分类统计】")
for issue_type, count in sorted(result_full['summary'].get('issues_by_type', {}).items(), key=lambda x: -x[1]):
    print(f"  • {issue_type}: {count}条")

# 统计详细信息
print(f"\n【详细问题分析】")

# L订单分析
l_orders = [rec for rec in result_full['issues'] if str(rec.get('order_id', '')).startswith('L')]
print(f"\nL订单(missing_in_finance): {len(l_orders)}条")
for rec in l_orders:
    print(f"  • {rec['order_id']}: 金额 {rec['business_value']}")

# 104订单amount_mismatch
mismatch_orders = [rec for rec in result_full['issues'] if rec.get('issue_type') == 'amount_mismatch']
print(f"\n金额不匹配(104订单): {len(mismatch_orders)}条")
for rec in mismatch_orders:
    try:
        biz_val = float(rec['business_value']) if rec['business_value'] else 0
        fin_val = float(rec['finance_value']) if rec['finance_value'] else 0
        diff = abs(biz_val - fin_val)
        print(f"  • {rec['order_id']}: 业务 {biz_val} vs 财务 {fin_val} (差额 {diff})")
    except:
        print(f"  • {rec['order_id']}: 业务 {rec['business_value']} vs 财务 {rec['finance_value']}")

print(f"\n" + "="*80)
print(f"✅ Reconciliation完成!")
print(f"="*80 + "\n")

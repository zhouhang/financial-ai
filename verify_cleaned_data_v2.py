#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重新验证清洗后的数据
"""
import sys
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.data_cleaner import DataCleaner
import json

print("="*80)
print("【验证清洗后的数据 - V2】")
print("="*80)

schema_path = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/schemas/direct_sales_schema.json'
with open(schema_path, 'r', encoding='utf-8') as f:
    schema = json.load(f)

cleaner = DataCleaner(schema)

# 清洗业务数据
print("\n【业务数据清洗】")
business_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/官网.xlsx'
df_business = cleaner.load_and_clean("business", [business_file])

print(f"清洗后总数: {len(df_business)}")

# 统计104订单
df_104 = df_business[df_business['order_id'].astype(str).str.startswith('104')]
print(f"104开头的订单: {len(df_104)}")
print(f"104订单号长度分布:")
len_dist = df_104['order_id'].astype(str).apply(len).value_counts().sort_index()
for length, count in len_dist.items():
    status = "✓" if length == 21 else "❌"
    print(f"  length {length}: {count} {status}")

print(f"样本 (前5个):")
for idx, row in df_104.head(5).iterrows():
    print(f"  {row['order_id']} ({len(str(row['order_id']))}位)")

# 统计L订单
print("\n【L订单统计】")
df_L = df_business[df_business['order_id'].astype(str).str.startswith('L')]
print(f"L开头的订单: {len(df_L)}")
print(f"L订单号长度分布:")
len_dist_L = df_L['order_id'].astype(str).apply(len).value_counts().sort_index()
for length, count in len_dist_L.items():
    print(f"  length {length}: {count}")

print(f"样本:")
for idx, row in df_L.iterrows():
    print(f"  {row['order_id']} ({len(str(row['order_id']))}位)")

# 清洗财务数据
print("\n【财务数据清洗】")
finance_file = '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/合单.xlsx'
df_finance = cleaner.load_and_clean("finance", [finance_file])

print(f"清洗后总数: {len(df_finance)}")

# 统计104订单
df_104_finance = df_finance[df_finance['order_id'].astype(str).str.startswith('104')]
print(f"104开头的订单: {len(df_104_finance)}")
print(f"104订单号长度分布:")
len_dist_finance = df_104_finance['order_id'].astype(str).apply(len).value_counts().sort_index()
for length, count in len_dist_finance.items():
    print(f"  length {length}: {count}")

print(f"样本 (前5个):")
for idx, row in df_104_finance.head(5).iterrows():
    print(f"  {row['order_id']} ({len(str(row['order_id']))}位)")

# 对比匹配
print("\n【对比匹配】")
business_orders = set(df_104['order_id'].unique())
finance_orders = set(df_104_finance['order_id'].unique())

matched = business_orders & finance_orders
only_business = business_orders - finance_orders
only_finance = finance_orders - business_orders

print(f"业务104订单数: {len(business_orders)}")
print(f"财务104订单数: {len(finance_orders)}")
print(f"两边都有的: {len(matched)}")
print(f"只在业务有 (missing_in_finance): {len(only_business)}")
print(f"只在财务有 (missing_in_business): {len(only_finance)}")

if len(only_business) > 0:
    print(f"\n业务独有 (样本):")
    for order_id in list(only_business)[:5]:
        print(f"  {order_id}")

if len(only_finance) > 0:
    print(f"\n财务独有 (样本):")
    for order_id in list(only_finance)[:5]:
        print(f"  {order_id}")

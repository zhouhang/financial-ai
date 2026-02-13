#!/usr/bin/env python3
"""
详细诊断脚本：追踪财务数据清洗的每一步
"""
import sys
import pandas as pd
from pathlib import Path

# 添加 finance-mcp 到路径
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.data_cleaner import DataCleaner
from reconciliation.mcp_server.config import SCHEMA_DIR
import json

def test_data_cleaner_steps():
    """详细测试数据清洗的每一步"""
    
    print("=" * 80)
    print("详细诊断：财务数据清洗过程")
    print("=" * 80)
    
    # 1. 加载 schema
    schema_file = SCHEMA_DIR / "nanjingfeihan_schema.json"
    with open(schema_file, 'r', encoding='utf-8') as f:
        schema = json.load(f)
    
    # 2. 加载财务文件
    base_path = Path('/Users/kevin/workspace/financial-ai/finance-mcp')
    finance_file = str(base_path / 'uploads/2026/2/13/ads_finance_d_inc_channel_details_20260105152012277_0_161222.csv')
    
    print(f"\n📄 财务文件: {Path(finance_file).name}")
    
    # 直接加载财务文件
    df = pd.read_csv(finance_file, encoding='utf-8')
    print(f"   原始行数: {len(df)}")
    print(f"   列数: {len(df.columns)}")
    
    # 查看订单号列
    print(f"\n📋 原始数据中的订单号列样本（sup订单号）：")
    for i, val in enumerate(df['sup订单号'].head(5)):
        print(f"   {i+1}. {repr(val)} (类型: {type(val).__name__})")
    
    # 初始化数据清洗器
    cleaner = DataCleaner(schema)
    
    # 手动执行清洗步骤，逐步跟踪
    print(f"\n🔄 执行清洗步骤...")
    
    # 1. 加载文件（已经做了）
    dfs = [df]
    combined_df = pd.concat(dfs, ignore_index=True)
    print(f"   1. 加载文件完成: {len(combined_df)} 行")
    
    # 2. 字段映射
    source_config = schema.get("data_sources", {}).get("finance", {})
    field_roles = source_config.get("field_roles", {})
    print(f"\n   2. 字段映射规则：")
    for role, fields in field_roles.items():
        print(f"      {role}: {fields}")
    
    # 执行字段映射
    mapped_df = cleaner._map_fields(combined_df, field_roles)
    print(f"      映射后列名: {[col for col in mapped_df.columns if col in ['order_id', 'amount', 'date']]}")
    
    # 3. 字段转换
    cleaning_rules = schema.get("data_cleaning_rules", {})
    source_rules = cleaning_rules.get("finance", {})
    field_transforms = source_rules.get("field_transforms", [])
    
    print(f"\n   3. 字段转换规则（{len(field_transforms)} 个）：")
    for i, transform in enumerate(field_transforms, 1):
        field = transform.get("field")
        op = transform.get("operation") or transform.get("transform", "expr")
        desc = transform.get("description", "无描述")
        print(f"      {i}. {field} - {op}: {desc}")
    
    # 执行字段转换
    transformed_df = cleaner._apply_field_transforms(mapped_df, field_transforms, [finance_file])
    print(f"      转换后行数: {len(transformed_df)}")
    
    # 检查转换后的订单号
    if 'order_id' in transformed_df.columns:
        print(f"\n      转换后的订单号样本：")
        for i, val in enumerate(transformed_df['order_id'].head(5)):
            print(f"      {i+1}. {repr(val)} (类型: {type(val).__name__})")
    
    # 4. 行过滤
    row_filters = source_rules.get("row_filters", [])
    print(f"\n   4. 行过滤规则（{len(row_filters)} 个）：")
    for i, filter_rule in enumerate(row_filters, 1):
        condition = filter_rule.get("condition")
        desc = filter_rule.get("description", "无描述")
        print(f"      {i}. {desc}")
        print(f"         条件: {condition}")
    
    # 执行行过滤前的测试
    if row_filters:
        filter_rule = row_filters[0]
        condition = filter_rule.get("condition")
        
        # 在几个样本上测试条件
        print(f"\n      在样本上测试条件...")
        for i in range(min(5, len(transformed_df))):
            row = transformed_df.iloc[i]
            try:
                result = eval(condition, {"row": row, "pd": pd, "np": __import__('numpy')})
                order_id = row.get('order_id', 'N/A')
                print(f"      {i+1}. 订单号 {repr(order_id)}: {result}")
            except Exception as e:
                print(f"      {i+1}. 错误: {e}")
    
    # 执行行过滤
    filtered_df = cleaner._apply_row_filters(transformed_df, row_filters)
    print(f"      过滤后行数: {len(filtered_df)}")
    
    if len(filtered_df) == 0:
        print(f"\n   ❌ 所有行都被过滤掉了！")
        # 分析为什么
        print(f"\n   诊断：检查订单号值...")
        if 'order_id' in transformed_df.columns:
            sample_order_ids = transformed_df['order_id'].head(10).tolist()
            for oid in sample_order_ids:
                starts_with_104 = str(oid).startswith('104')
                print(f"      {repr(oid)}: startswith('104') = {starts_with_104}")

if __name__ == "__main__":
    test_data_cleaner_steps()

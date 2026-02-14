#!/usr/bin/env python3
"""
诊断腾讯异业对账匹配问题
"""
import pandas as pd
import sys
from pathlib import Path

# 文件路径
biz_file = Path("/Users/kevin/Desktop/工作/测试数据/资产对账测试数据/腾讯异业/2025-12-01~2025-12-01对账流水.csv")
fin_file = Path("/Users/kevin/Desktop/工作/测试数据/资产对账测试数据/腾讯异业/ads_finance_d_inc_channel_details_20260105133821735_0.csv")

print("=" * 80)
print("🔍 腾讯异业对账匹配问题诊断")
print("=" * 80)

# 读取业务文件
print("\n📊 业务文件分析")
print("-" * 80)
try:
    biz_df = pd.read_csv(biz_file)
    print(f"✓ 业务文件行数: {len(biz_df)}")
    print(f"✓ 业务文件列数: {len(biz_df.columns)}")
    print(f"✓ 业务文件列名: {list(biz_df.columns)}")
    print(f"\n业务文件前3行数据:")
    print(biz_df.head(3).to_string())
except Exception as e:
    print(f"❌ 业务文件读取失败: {e}")
    sys.exit(1)

# 读取财务文件
print("\n\n📊 财务文件分析")
print("-" * 80)
try:
    fin_df = pd.read_csv(fin_file)
    print(f"✓ 财务文件行数: {len(fin_df)}")
    print(f"✓ 财务文件列数: {len(fin_df.columns)}")
    print(f"✓ 财务文件列名: {list(fin_df.columns)}")
    print(f"\n财务文件前3行数据:")
    print(fin_df.head(3).to_string())
except Exception as e:
    print(f"❌ 财务文件读取失败: {e}")
    sys.exit(1)

# 分析关键字段
print("\n\n🔑 关键字段分析")
print("-" * 80)

# 业务文件关键字段
print("业务文件:")
print(f"  - roc_oid 唯一值数: {biz_df['roc_oid'].nunique()}")
print(f"  - roc_oid 示例值: {biz_df['roc_oid'].dropna().head(5).tolist()}")
print(f"  - pay_amt 总计: {biz_df['pay_amt'].sum()}")
print(f"  - pay_amt 行数: {len(biz_df[biz_df['pay_amt'] > 0])}")
print(f"  - statis_date 日期: {biz_df['statis_date'].unique()[:5]}")

print("\n财务文件:")
print(f"  - 订单号 唯一值数: {fin_df['订单号'].nunique()}")
print(f"  - 订单号 示例值: {fin_df['订单号'].dropna().head(5).tolist()}")
print(f"  - 发生+ 总计: {fin_df['发生+'].sum()}")
print(f"  - 发生+ 行数: {len(fin_df[fin_df['发生+'].notna()])}")
print(f"  - 完成时间 日期: {fin_df['完成时间'].unique()[:5]}")

# 尝试匹配
print("\n\n🔗 匹配尝试分析")
print("-" * 80)

# 方法1: 直接按订单号匹配
biz_orders = set(biz_df['roc_oid'].dropna().astype(str))
fin_orders = set(fin_df['订单号'].dropna().astype(str))

print(f"业务文件订单号集合大小: {len(biz_orders)}")
print(f"财务文件订单号集合大小: {len(fin_orders)}")
print(f"交集(匹配的订单): {len(biz_orders & fin_orders)}")
print(f"业务独有订单: {len(biz_orders - fin_orders)}")
print(f"财务独有订单: {len(fin_orders - biz_orders)}")

if biz_orders & fin_orders:
    matched_order = list(biz_orders & fin_orders)[0]
    print(f"\n✓ 成功匹配的订单示例: {matched_order}")
    biz_matched = biz_df[biz_df['roc_oid'].astype(str) == matched_order]
    fin_matched = fin_df[fin_df['订单号'].astype(str) == matched_order]
    print(f"  业务端数据: {biz_matched[['roc_oid', 'pay_amt']].to_dict('records')}")
    print(f"  财务端数据: {fin_matched[['订单号', '发生+']].to_dict('records')}")
else:
    print(f"\n❌ 没有成功匹配的订单号！")
    print(f"\n业务文件订单号示例: {list(biz_orders)[:5]}")
    print(f"财务文件订单号示例: {list(fin_orders)[:5]}")

# 检查金额字段
print("\n\n💰 金额字段分析")
print("-" * 80)
print(f"业务文件pay_amt字段类型: {biz_df['pay_amt'].dtype}")
print(f"业务文件pay_amt统计:")
print(biz_df['pay_amt'].describe())

print(f"\n财务文件发生+字段类型: {fin_df['发生+'].dtype}")
print(f"财务文件发生+统计:")
print(fin_df['发生+'].describe())

# 尝试金额汇总匹配
biz_total = biz_df['pay_amt'].sum()
fin_total = fin_df['发生+'].sum()
print(f"\n业务文件金额总和: {biz_total}")
print(f"财务文件金额总和: {fin_total}")
print(f"金额差异: {abs(biz_total - fin_total)}")

print("\n" + "=" * 80)

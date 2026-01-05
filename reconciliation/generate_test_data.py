"""
生成测试数据 - 3000+ 条记录
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

# 设置随机种子以便复现
np.random.seed(42)
random.seed(42)

# 生成业务流水数据 (3200 条)
def generate_business_data(num_records=3200):
    """生成业务流水数据"""
    data = []
    start_date = datetime(2025, 1, 1)
    
    for i in range(num_records):
        order_id = f"ROC{100000 + i}"
        amount = round(random.uniform(10, 5000), 2)
        date = start_date + timedelta(days=random.randint(0, 60))
        
        # 80% 的订单是正常客户，20% 是测试客户
        customer = "正常客户" if random.random() > 0.2 else "测试客户"
        
        # 95% 的订单是已完成，5% 是已取消
        status = "已完成" if random.random() > 0.05 else "已取消"
        
        data.append({
            "roc_oid": order_id,
            "product_price": amount,
            "statis_date": date.strftime("%Y-%m-%d %H:%M:%S"),
            "客户": customer,
            "status": status
        })
    
    df = pd.DataFrame(data)
    return df

# 生成财务流水数据 (3100 条)
def generate_finance_data(num_records=3100):
    """生成财务流水数据"""
    data = []
    start_date = datetime(2025, 1, 1)
    
    for i in range(num_records):
        order_id = f"ROC{100000 + i}"
        
        # 财务金额以"分"为单位
        amount = random.uniform(1000, 500000)  # 10元-5000元（分）
        
        # 添加一些金额差异（模拟对账问题）
        if random.random() < 0.05:  # 5% 的记录有金额差异
            amount += random.uniform(-500, 500)
        
        date = start_date + timedelta(days=random.randint(0, 60))
        
        # 添加一些日期差异
        if random.random() < 0.03:  # 3% 的记录有日期差异
            date += timedelta(days=random.randint(1, 3))
        
        data.append({
            "sup订单号": order_id,
            "发生-": round(amount, 2),
            "完成时间": date.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    # 添加一些只在财务系统的订单
    for i in range(50):
        order_id = f"ROC{400000 + i}"
        amount = random.uniform(1000, 500000)
        date = start_date + timedelta(days=random.randint(0, 60))
        
        data.append({
            "sup订单号": order_id,
            "发生-": round(amount, 2),
            "完成时间": date.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    df = pd.DataFrame(data)
    return df

# 生成带有重复订单号的业务数据（用于测试聚合）
def generate_business_with_duplicates(base_df, duplicate_ratio=0.1):
    """
    生成包含重复订单号的数据
    
    Args:
        base_df: 基础数据
        duplicate_ratio: 重复比例
    """
    df = base_df.copy()
    num_duplicates = int(len(df) * duplicate_ratio)
    
    # 随机选择一些订单号进行重复
    duplicate_indices = random.sample(range(len(df)), num_duplicates)
    
    duplicate_rows = []
    for idx in duplicate_indices:
        row = df.iloc[idx].copy()
        # 修改金额（模拟分批支付）
        row['product_price'] = round(row['product_price'] * random.uniform(0.3, 0.7), 2)
        duplicate_rows.append(row)
    
    duplicate_df = pd.DataFrame(duplicate_rows)
    result_df = pd.concat([df, duplicate_df], ignore_index=True)
    
    # 随机打乱顺序
    result_df = result_df.sample(frac=1).reset_index(drop=True)
    
    return result_df

def main():
    """生成所有测试数据"""
    print("开始生成测试数据...")
    
    # 生成业务数据
    print("生成业务流水数据...")
    business_df = generate_business_data(3200)
    business_with_dup_df = generate_business_with_duplicates(business_df, duplicate_ratio=0.1)
    
    # 保存业务数据
    business_file = "test_data/business_flow.csv"
    business_with_dup_df.to_csv(business_file, index=False, encoding='utf-8-sig')
    print(f"业务流水数据已保存: {business_file}, 共 {len(business_with_dup_df)} 条记录")
    
    # 生成财务数据
    print("生成财务流水数据...")
    finance_df = generate_finance_data(3100)
    
    # 财务数据也添加一些重复订单（模拟分批到账）
    finance_dup_indices = random.sample(range(len(finance_df)), 150)
    finance_duplicate_rows = []
    for idx in finance_dup_indices:
        row = finance_df.iloc[idx].copy()
        row['发生-'] = round(row['发生-'] * random.uniform(0.2, 0.5), 2)
        finance_duplicate_rows.append(row)
    
    finance_dup_df = pd.DataFrame(finance_duplicate_rows)
    finance_with_dup_df = pd.concat([finance_df, finance_dup_df], ignore_index=True)
    finance_with_dup_df = finance_with_dup_df.sample(frac=1).reset_index(drop=True)
    
    # 保存财务数据
    finance_file = "test_data/ads_finance_d_inc_channel_details_20250101.csv"
    finance_with_dup_df.to_csv(finance_file, index=False, encoding='utf-8-sig')
    print(f"财务流水数据已保存: {finance_file}, 共 {len(finance_with_dup_df)} 条记录")
    
    # 统计信息
    print("\n数据生成完成！统计信息：")
    print(f"  业务流水: {len(business_with_dup_df)} 条")
    print(f"    - 正常客户: {len(business_with_dup_df[business_with_dup_df['客户'] == '正常客户'])} 条")
    print(f"    - 测试客户: {len(business_with_dup_df[business_with_dup_df['客户'] == '测试客户'])} 条")
    print(f"    - 已完成: {len(business_with_dup_df[business_with_dup_df['status'] == '已完成'])} 条")
    print(f"    - 已取消: {len(business_with_dup_df[business_with_dup_df['status'] == '已取消'])} 条")
    print(f"  财务流水: {len(finance_with_dup_df)} 条")
    print(f"\n预期对账问题：")
    print(f"  - 金额差异: 约 {int(3100 * 0.05)} 笔")
    print(f"  - 日期差异: 约 {int(3100 * 0.03)} 笔")
    print(f"  - 业务有财务无: 约 {3200 - 3100} 笔")
    print(f"  - 财务有业务无: 约 50 笔")

if __name__ == "__main__":
    main()


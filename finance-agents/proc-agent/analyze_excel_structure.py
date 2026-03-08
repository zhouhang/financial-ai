#!/usr/bin/env python3
"""
分析Excel文件结构的脚本
用于检查手工凭证、BI费用明细表和BI损益毛利明细表的结构
"""

import pandas as pd
import openpyxl
import os
import sys

def analyze_excel_file(file_path, max_rows=20):
    """分析Excel文件结构"""
    print(f"\n{'='*80}")
    print(f"分析文件: {file_path}")
    print(f"{'='*80}")
    
    if not os.path.exists(file_path):
        print(f"错误: 文件不存在 - {file_path}")
        return
    
    try:
        # 使用openpyxl获取工作表名称
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet_names = wb.sheetnames
        print(f"工作表列表: {sheet_names}")
        
        # 分析每个工作表
        for sheet_name in sheet_names:
            print(f"\n工作表: {sheet_name}")
            print("-" * 40)
            
            try:
                # 使用pandas读取工作表
                df = pd.read_excel(file_path, sheet_name=sheet_name, nrows=max_rows)
                
                # 显示基本信息
                print(f"行数: {len(df)}, 列数: {len(df.columns)}")
                print(f"列名: {list(df.columns)}")
                
                # 显示前几行数据
                print(f"\n前{min(5, len(df))}行数据:")
                print(df.head(min(5, len(df))))
                
                # 显示数据类型
                print(f"\n数据类型:")
                print(df.dtypes)
                
                # 检查是否有空值
                print(f"\n空值统计:")
                print(df.isnull().sum())
                
            except Exception as e:
                print(f"读取工作表 {sheet_name} 时出错: {e}")
        
        wb.close()
        
    except Exception as e:
        print(f"分析文件时出错: {e}")

def main():
    """主函数"""
    # 使用最新的文件（按时间排序）
    base_dir = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-mcp/uploads"
    
    # 查找最新的手工凭证文件
    manual_vouchers = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if "手工凭证原表202507月" in file and file.endswith(".xlsx"):
                full_path = os.path.join(root, file)
                manual_vouchers.append((full_path, os.path.getmtime(full_path)))
    
    # 查找最新的BI费用明细表
    bi_expense_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if "BI费用明细表202507月" in file and file.endswith(".xlsx"):
                full_path = os.path.join(root, file)
                bi_expense_files.append((full_path, os.path.getmtime(full_path)))
    
    # 查找最新的BI损益毛利明细表
    bi_profit_files = []
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if "BI损益毛利明细表原表202507月" in file and file.endswith(".xlsx"):
                full_path = os.path.join(root, file)
                bi_profit_files.append((full_path, os.path.getmtime(full_path)))
    
    # 按修改时间排序，获取最新的文件
    manual_vouchers.sort(key=lambda x: x[1], reverse=True)
    bi_expense_files.sort(key=lambda x: x[1], reverse=True)
    bi_profit_files.sort(key=lambda x: x[1], reverse=True)
    
    print("找到的Excel文件:")
    print(f"手工凭证文件: {len(manual_vouchers)} 个")
    print(f"BI费用明细表: {len(bi_expense_files)} 个")
    print(f"BI损益毛利明细表: {len(bi_profit_files)} 个")
    
    # 分析最新的文件
    if manual_vouchers:
        analyze_excel_file(manual_vouchers[0][0])
    
    if bi_expense_files:
        analyze_excel_file(bi_expense_files[0][0])
    
    if bi_profit_files:
        analyze_excel_file(bi_profit_files[0][0])

if __name__ == "__main__":
    main()
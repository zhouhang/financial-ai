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
    # 直接分析指定的Excel文件路径
    target_file = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-mcp/uploads/2026/3/8/手工凭证原表202507月_155026.xlsx"
    
    print("开始分析指定的Excel文件:")
    print(f"目标文件: {target_file}")
    
    # 检查文件是否存在
    if not os.path.exists(target_file):
        print(f"错误: 文件不存在 - {target_file}")
        print("请检查文件路径是否正确。")
        return
    
    # 分析指定的文件
    analyze_excel_file(target_file)

if __name__ == "__main__":
    main()
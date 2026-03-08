#!/usr/bin/env python3
"""
简单的Excel文件分析器
用于快速查看Excel文件结构
"""

import pandas as pd
import os

def quick_analyze(file_path):
    """快速分析Excel文件"""
    print(f"\n{'='*80}")
    print(f"分析文件: {os.path.basename(file_path)}")
    print(f"完整路径: {file_path}")
    print(f"{'='*80}")
    
    if not os.path.exists(file_path):
        print(f"文件不存在!")
        return
    
    try:
        # 获取所有工作表名称
        xls = pd.ExcelFile(file_path)
        sheet_names = xls.sheet_names
        print(f"工作表: {sheet_names}")
        
        # 分析每个工作表
        for sheet in sheet_names:
            print(f"\n--- 工作表: {sheet} ---")
            try:
                df = pd.read_excel(file_path, sheet_name=sheet, nrows=10)
                print(f"形状: {df.shape}")
                print(f"列名: {list(df.columns)}")
                print("\n前5行数据:")
                print(df.head())
                print("-" * 40)
            except Exception as e:
                print(f"读取工作表 {sheet} 时出错: {e}")
                
    except Exception as e:
        print(f"分析文件时出错: {e}")

def main():
    """主函数"""
    # 使用最新的文件
    base_dir = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-mcp/uploads"
    
    # 查找文件
    files_to_analyze = []
    
    # 手工凭证文件
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if "手工凭证原表202507月" in file and file.endswith(".xlsx"):
                files_to_analyze.append(os.path.join(root, file))
                break
        if files_to_analyze:
            break
    
    # BI费用明细表
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if "BI费用明细表202507月" in file and file.endswith(".xlsx"):
                files_to_analyze.append(os.path.join(root, file))
                break
        if len(files_to_analyze) >= 2:
            break
    
    # BI损益毛利明细表
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if "BI损益毛利明细表原表202507月" in file and file.endswith(".xlsx"):
                files_to_analyze.append(os.path.join(root, file))
                break
        if len(files_to_analyze) >= 3:
            break
    
    # 分析文件
    for file_path in files_to_analyze:
        quick_analyze(file_path)

if __name__ == "__main__":
    main()
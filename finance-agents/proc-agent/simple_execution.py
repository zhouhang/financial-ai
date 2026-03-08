#!/usr/bin/env python3
"""
简化版执行脚本
"""

import sys
import os

# 设置工作目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# 添加技能脚本目录到路径
sys.path.insert(0, "skills/recognition/scripts")

try:
    # 导入处理函数
    from recognition_rule import process
    
    # 输入文件路径
    input_files = [
        "doc/AI分析底稿原表/手工凭证原表202507月.xlsx",
        "doc/AI分析底稿原表/BI费用明细表202507月.xlsx",
        "doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx"
    ]
    
    # 转换为绝对路径
    input_files = [os.path.abspath(f) for f in input_files]
    
    # 输出目录
    output_dir = os.path.abspath("result/default")
    
    print(f"开始处理BI费用报表填充...")
    print(f"输入文件:")
    for f in input_files:
        print(f"  - {os.path.basename(f)}")
        if not os.path.exists(f):
            print(f"    ⚠️  文件不存在！")
    print(f"输出目录: {output_dir}")
    
    # 检查文件是否存在
    missing_files = [f for f in input_files if not os.path.exists(f)]
    if missing_files:
        print(f"\n错误：以下文件不存在:")
        for f in missing_files:
            print(f"  - {f}")
        sys.exit(1)
    
    # 执行处理
    result = process(
        input_files=input_files,
        output_dir=output_dir,
        chat_id="default"
    )
    
    print("\n处理结果:")
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
except Exception as e:
    print(f"执行过程中发生错误: {e}")
    import traceback
    traceback.print_exc()
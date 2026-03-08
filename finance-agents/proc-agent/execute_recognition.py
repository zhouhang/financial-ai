#!/usr/bin/env python3
"""直接执行recognition_rule.py脚本处理手工凭证并生成BI报表"""

import subprocess
import sys
import os
import json

# 设置Python路径
python_path = sys.executable

# 脚本路径
script_path = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/skills/recognition/scripts/recognition_rule.py"

# 输入文件
voucher_file = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/手工凭证原表202507月.xlsx"
expense_file = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI费用明细表202507月.xlsx"
profit_file = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx"

# 输出目录
output_dir = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/result/default"

# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

# 构建命令
cmd = [
    python_path,
    script_path,
    "--input", voucher_file,
    "--input", expense_file,
    "--input", profit_file,
    "--output-dir", output_dir,
    "--chat-id", "default"
]

print("开始执行recognition_rule.py脚本...")
print(f"Python路径: {python_path}")
print(f"脚本路径: {script_path}")
print(f"手工凭证文件: {voucher_file}")
print(f"BI费用明细表: {expense_file}")
print(f"BI损益毛利明细表: {profit_file}")
print(f"输出目录: {output_dir}")
print("-" * 80)

try:
    # 执行脚本
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    print("标准输出:")
    print("-" * 80)
    print(result.stdout)
    
    if result.stderr:
        print("\n标准错误:")
        print("-" * 80)
        print(result.stderr)
    
    print("\n" + "="*80)
    print(f"返回码: {result.returncode}")
    
    # 尝试解析JSON输出
    try:
        if result.stdout.strip():
            output_data = json.loads(result.stdout)
            print("\n解析后的执行结果:")
            print(json.dumps(output_data, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print("\n输出不是有效的JSON格式")
    
    print("="*80)
    
except Exception as e:
    print(f"执行过程中发生错误: {e}")
    import traceback
    traceback.print_exc()
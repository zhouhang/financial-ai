#!/usr/bin/env python3
"""
执行recognition技能脚本的包装脚本
"""

import subprocess
import sys
import os

# 设置Python路径
python_path = sys.executable
script_path = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/run_recognition.py"

print(f"开始执行recognition技能脚本...")
print(f"Python路径: {python_path}")
print(f"脚本路径: {script_path}")

try:
    # 执行脚本
    result = subprocess.run(
        [python_path, script_path],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    print("\n" + "="*80)
    print("标准输出:")
    print("="*80)
    print(result.stdout)
    
    if result.stderr:
        print("\n" + "="*80)
        print("标准错误:")
        print("="*80)
        print(result.stderr)
    
    print("\n" + "="*80)
    print(f"返回码: {result.returncode}")
    print("="*80)
    
except Exception as e:
    print(f"执行过程中发生错误: {e}")
    import traceback
    traceback.print_exc()
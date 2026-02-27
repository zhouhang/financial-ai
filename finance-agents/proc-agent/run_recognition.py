#!/usr/bin/env python3
"""运行recognition_rule.py脚本的辅助脚本"""

import subprocess
import sys
import os

# 设置Python路径
python_path = sys.executable

# 脚本路径
script_path = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/skills/recognition/scripts/recognition_rule.py"

# 输入文件
input_files = [
    "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/手工凭证原表202507月.xlsx",
    "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI费用明细表202507月.xlsx",
    "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx"
]

# 输出目录
output_dir = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/result/default"

# 构建命令
cmd = [python_path, script_path]
for input_file in input_files:
    cmd.extend(["--input", input_file])
cmd.extend(["--output-dir", output_dir])
cmd.extend(["--chat-id", "default"])

print("运行命令:", " ".join(cmd))
print("-" * 80)

# 运行脚本
try:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    
    print("标准输出:")
    print(result.stdout)
    print("-" * 80)
    
    if result.stderr:
        print("标准错误:")
        print(result.stderr)
        print("-" * 80)
    
    print("返回码:", result.returncode)
    
except Exception as e:
    print(f"运行脚本时出错: {e}")
    sys.exit(1)
#!/usr/bin/env python3
import subprocess
import sys

# 运行direct_process.py
result = subprocess.run([sys.executable, "direct_process.py"], 
                       capture_output=True, text=True, encoding='utf-8')

print("标准输出:")
print(result.stdout)

if result.stderr:
    print("\n标准错误:")
    print(result.stderr)

print(f"\n返回码: {result.returncode}")
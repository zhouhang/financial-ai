import subprocess
import sys
import os

# 设置工作目录
os.chdir("/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent")

# 构建命令
cmd = [
    sys.executable,
    "skills/recognition/scripts/recognition_rule.py",
    "--input", "doc/AI分析底稿原表/手工凭证原表202507月.xlsx",
    "--input", "doc/AI分析底稿原表/BI费用明细表202507月.xlsx", 
    "--input", "doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx",
    "--output-dir", "result/default",
    "--chat-id", "default"
]

print("执行命令:", " ".join(cmd))
print("=" * 80)

# 执行命令
try:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    
    print("脚本输出:")
    print(result.stdout)
    
    if result.stderr:
        print("\n错误输出:")
        print(result.stderr)
    
    print(f"\n返回码: {result.returncode}")
    
except Exception as e:
    print(f"执行失败: {e}")
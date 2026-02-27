import subprocess
import sys
import os

# 切换到工作目录
os.chdir("/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent")

# 构建命令
cmd = [
    sys.executable,
    "-m", "skills.recognition.scripts.recognition_rule",
    "--input", "doc/AI分析底稿原表/手工凭证原表202507月.xlsx",
    "--input", "doc/AI分析底稿原表/BI费用明细表202507月.xlsx",
    "--input", "doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx",
    "--output-dir", "result/default"
]

print("执行命令:", " ".join(cmd))
print("=" * 80)

try:
    # 运行命令
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # 实时输出
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip())
    
    # 获取剩余输出和错误
    stdout, stderr = process.communicate()
    if stdout:
        print(stdout)
    if stderr:
        print("\n错误输出:")
        print(stderr)
    
    print(f"\n进程返回码: {process.returncode}")
    
except Exception as e:
    print(f"执行失败: {e}")
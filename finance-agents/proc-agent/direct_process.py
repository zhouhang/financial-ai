import sys
import os
import json

# 添加路径
sys.path.insert(0, "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent")

try:
    from skills.recognition.scripts.recognition_rule import process
    
    # 输入文件
    input_files = [
        "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/手工凭证原表202507月.xlsx",
        "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI费用明细表202507月.xlsx",
        "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx"
    ]
    
    # 输出目录
    output_dir = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/result/default"
    
    print("开始处理...")
    print(f"输入文件: {input_files}")
    print(f"输出目录: {output_dir}")
    print("=" * 80)
    
    result = process(input_files, output_dir, "default")
    
    print("处理结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
except Exception as e:
    print(f"处理失败: {e}")
    import traceback
    traceback.print_exc()
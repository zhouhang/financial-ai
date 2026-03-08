#!/usr/bin/env python3
"""
执行recognition技能脚本，填充BI费用报表
"""

import sys
import os
import json
from pathlib import Path

# 添加技能脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent / "skills" / "recognition" / "scripts"))

from recognition_rule import process

def main():
    """执行recognition技能处理"""
    # 输入文件路径
    input_files = [
        "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/手工凭证原表202507月.xlsx",
        "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI费用明细表202507月.xlsx",
        "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/doc/AI分析底稿原表/BI损益毛利明细表原表202507月.xlsx"
    ]
    
    # 输出目录
    output_dir = "/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents/proc-agent/result/default"
    
    print(f"开始处理BI费用报表填充...")
    print(f"输入文件:")
    for f in input_files:
        print(f"  - {Path(f).name}")
    print(f"输出目录: {output_dir}")
    
    # 执行处理
    result = process(
        input_files=input_files,
        output_dir=output_dir,
        chat_id="default"
    )
    
    # 输出结果
    print("\n处理结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result

if __name__ == "__main__":
    main()
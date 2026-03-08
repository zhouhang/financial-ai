#!/usr/bin/env python3
"""
直接执行recognition技能
"""

import sys
import os
import json
from pathlib import Path

# 设置工作目录
current_dir = Path(__file__).parent
os.chdir(current_dir)

# 添加技能脚本目录到路径
sys.path.insert(0, str(current_dir / "skills" / "recognition" / "scripts"))

try:
    # 导入处理函数
    from recognition_rule import process
    
    # 输入文件路径
    input_files = [
        str(current_dir / "doc" / "AI分析底稿原表" / "手工凭证原表202507月.xlsx"),
        str(current_dir / "doc" / "AI分析底稿原表" / "BI费用明细表202507月.xlsx"),
        str(current_dir / "doc" / "AI分析底稿原表" / "BI损益毛利明细表原表202507月.xlsx")
    ]
    
    # 输出目录
    output_dir = str(current_dir / "result" / "default")
    
    print("=" * 80)
    print("开始执行recognition技能 - BI费用报表填充")
    print("=" * 80)
    
    # 检查输入文件
    print("\n检查输入文件:")
    for i, f in enumerate(input_files, 1):
        exists = Path(f).exists()
        status = "✅ 存在" if exists else "❌ 不存在"
        print(f"{i}. {Path(f).name}: {status}")
        if not exists:
            print(f"   路径: {f}")
    
    # 检查输出目录
    print(f"\n输出目录: {output_dir}")
    if not Path(output_dir).exists():
        print("创建输出目录...")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 执行处理
    print("\n" + "=" * 80)
    print("开始处理...")
    print("=" * 80)
    
    result = process(
        input_files=input_files,
        output_dir=output_dir,
        chat_id="default"
    )
    
    print("\n" + "=" * 80)
    print("处理完成！")
    print("=" * 80)
    
    print("\n处理结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 显示生成的文件
    if result.get("result_files"):
        print("\n生成的文件:")
        for file_info in result["result_files"]:
            file_path = file_info.get("file_path", "")
            if file_path and Path(file_path).exists():
                file_size = Path(file_path).stat().st_size
                print(f"  - {Path(file_path).name} ({file_size} bytes)")
    
except ImportError as e:
    print(f"导入错误: {e}")
    print("\n尝试检查技能脚本目录...")
    scripts_dir = current_dir / "skills" / "recognition" / "scripts"
    print(f"技能脚本目录: {scripts_dir}")
    if scripts_dir.exists():
        print("目录存在，内容:")
        for item in scripts_dir.iterdir():
            print(f"  - {item.name}")
    else:
        print("目录不存在！")
        
except Exception as e:
    print(f"执行过程中发生错误: {e}")
    import traceback
    traceback.print_exc()
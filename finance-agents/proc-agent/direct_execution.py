#!/usr/bin/env python3
"""
直接执行recognition技能处理
"""

import sys
import os
import json
from pathlib import Path

# 设置工作目录
current_dir = Path(__file__).parent
os.chdir(current_dir)
print(f"工作目录: {current_dir}")

# 添加技能脚本目录到路径
scripts_dir = current_dir / "skills" / "recognition" / "scripts"
sys.path.insert(0, str(scripts_dir))

print(f"技能脚本目录: {scripts_dir}")

# 检查技能脚本
if not scripts_dir.exists():
    print(f"错误：技能脚本目录不存在！")
    sys.exit(1)

print(f"技能脚本目录内容:")
for item in scripts_dir.iterdir():
    print(f"  - {item.name}")

# 尝试导入
print(f"\n尝试导入recognition_rule...")
try:
    from recognition_rule import process
    print("✅ 导入成功！")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 输入文件路径
input_files = [
    str(current_dir / "doc" / "AI分析底稿原表" / "手工凭证原表202507月.xlsx"),
    str(current_dir / "doc" / "AI分析底稿原表" / "BI费用明细表202507月.xlsx"),
    str(current_dir / "doc" / "AI分析底稿原表" / "BI损益毛利明细表原表202507月.xlsx")
]

# 检查文件
print(f"\n检查输入文件:")
missing_files = []
for i, f in enumerate(input_files, 1):
    path = Path(f)
    if path.exists():
        print(f"{i}. ✅ {path.name} ({path.stat().st_size:,} bytes)")
    else:
        print(f"{i}. ❌ {path.name} - 文件不存在")
        missing_files.append(f)

if missing_files:
    print(f"\n错误：以下文件不存在:")
    for f in missing_files:
        print(f"  - {f}")
    sys.exit(1)

# 输出目录
output_dir = str(current_dir / "result" / "default")
print(f"\n输出目录: {output_dir}")

# 确保输出目录存在
Path(output_dir).mkdir(parents=True, exist_ok=True)

# 执行处理
print(f"\n开始执行process函数...")
try:
    result = process(
        input_files=input_files,
        output_dir=output_dir,
        chat_id="default"
    )
    
    print(f"\n✅ 处理完成！")
    print(f"结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
except Exception as e:
    print(f"❌ 处理失败: {e}")
    import traceback
    traceback.print_exc()
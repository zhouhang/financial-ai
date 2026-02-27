import os
import sys

def find_file(root_dir, filename):
    """在目录树中查找文件"""
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if filename in filenames:
            return os.path.join(dirpath, filename)
    return None

# 查找recognition_rule.py
script_path = find_file("/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents", "recognition_rule.py")
if script_path:
    print(f"找到脚本文件: {script_path}")
else:
    print("未找到recognition_rule.py文件")
    
    # 查找所有Python文件
    print("\n查找所有Python文件:")
    py_files = []
    for dirpath, dirnames, filenames in os.walk("/Users/fanyuli/Desktop/workspace/financial-ai/finance-agents"):
        for filename in filenames:
            if filename.endswith('.py'):
                full_path = os.path.join(dirpath, filename)
                py_files.append(full_path)
    
    # 显示前20个Python文件
    print(f"找到 {len(py_files)} 个Python文件")
    for i, file in enumerate(py_files[:20]):
        print(f"{i+1}. {file}")
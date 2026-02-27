"""脚本生成器模块

根据规则文件生成 Python 处理脚本。
"""

import re
from pathlib import Path
from typing import Dict, Optional, Any


class ScriptGenerator:
    """脚本生成器"""

    def __init__(self, base_dir: Optional[Path] = None):
        """初始化脚本生成器

        参数:
            base_dir: proc-agent 根目录
        """
        if base_dir is None:
            from . import AUDIT_AGENT_DIR
            base_dir = AUDIT_AGENT_DIR

        self.base_dir = base_dir

    def generate_script(
        self,
        rule_name: str,
        rule_info: Dict[str, Any],
        output_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """生成处理脚本

        参数:
            rule_name: 规则名称
            rule_info: 规则信息
            output_path: 输出路径（None 则使用默认路径）

        返回:
            生成结果
        """
        if output_path is None:
            output_path = self.base_dir / "scripts" / f"{rule_name}_rule.py"

        # 确保目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 生成脚本内容
        script_content = self._generate_script_content(rule_name, rule_info)

        # 保存脚本
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(script_content)

            return {
                "success": True,
                "script_path": str(output_path),
                "message": f"脚本生成成功：{output_path.name}"
            }
        except Exception as e:
            return {
                "success": False,
                "script_path": str(output_path),
                "message": f"脚本生成失败：{str(e)}"
            }

    def _generate_script_content(
        self,
        rule_name: str,
        rule_info: Dict[str, Any]
    ) -> str:
        """生成脚本内容

        参数:
            rule_name: 规则名称
            rule_info: 规则信息

        返回:
            脚本内容
        """
        description = rule_info.get('description', rule_name)
        data_sources = rule_info.get('data_sources', [])
        processing_rules = rule_info.get('processing_rules', '')
        output_format = rule_info.get('output_format', {})

        # 提取输出字段
        output_fields = []
        if 'fields' in output_format:
            output_fields = output_format['fields']
        elif 'columns' in output_format:
            output_fields = output_format['columns']

        # 生成脚本模板
        script = f'''#!/usr/bin/env python3
"""
{description}

本脚本由数据整理数字员工自动生成。
规则名称：{rule_name}
"""

import pandas as pd
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent  # 指向 proc-agent 目录
DATA_DIR = BASE_DIR / 'data'
RESULT_DIR = BASE_DIR / 'result'

# 确保结果目录存在
RESULT_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────────────────────

def find_file_by_pattern(files: List[str], patterns: List[str]) -> Optional[str]:
    """根据模式匹配查找文件"""
    for f in files:
        for pattern in patterns:
            if pattern in f:
                return f
    return None


def round_decimal(value: float, decimals: int = 2) -> float:
    """四舍五入保留指定小数位"""
    return round(value, decimals)


# ──────────────────────────────────────────────────────────────────────────────
# 数据加载函数
# ──────────────────────────────────────────────────────────────────────────────

'''

        # 生成数据源加载函数
        for i, source in enumerate(data_sources):
            script += f'''
def load_{source.lower().replace(" ", "_").replace("-", "_")}(data_dir: Path) -> Optional[pd.DataFrame]:
    """加载{source}数据

    参数:
        data_dir: 数据目录

    返回:
        DataFrame 或 None
    """
    files = [f for f in data_dir.glob('*.xlsx') if f.is_file()]

    # TODO: 根据文件名或内容识别{source}文件
    # 示例：查找文件名包含"{source}"的文件
    target_file = find_file_by_pattern(
        [str(f) for f in files],
        ['{source}']
    )

    if not target_file:
        print("未找到{source}文件")
        return None

    print(f"找到{source}文件：{{Path(target_file).name}}")

    try:
        df = pd.read_excel(target_file)
        print(f"加载完成，共 {{len(df)}} 条记录")
        return df
    except Exception as e:
        print(f"加载失败：{{e}}")
        return None

'''

        # 生成数据处理函数
        script += f'''
# ──────────────────────────────────────────────────────────────────────────────
# 数据处理函数
# ──────────────────────────────────────────────────────────────────────────────

def process_data(
    data_dir: Path,
    output_dir: Path
) -> Dict[str, Any]:
    """处理数据

    参数:
        data_dir: 数据目录
        output_dir: 输出目录

    返回:
        处理结果
    """
    print("="*60)
    print("{description}")
    print("="*60)

    # 1. 加载数据
    print("\\n[步骤 1] 加载数据...")

'''

        # 生成数据加载调用
        for i, source in enumerate(data_sources):
            var_name = f"df_{i}"
            func_name = f"load_{source.lower().replace(' ', '_').replace('-', '_')}"
            script += f'''    {var_name} = {func_name}(data_dir)
    if {var_name} is None:
        print("错误：未找到{source}数据")
        return {{"status": "error", "error": "未找到{source}数据"}}

'''

        # 生成处理规则说明
        script += f'''    # 2. 数据处理
    print("\\n[步骤 2] 数据处理...")
    # TODO: 根据以下规则实现数据处理逻辑
    #
    # 处理规则:
    # {processing_rules[:500]}...  # 限制长度

    # 示例处理逻辑（需要根据实际规则完善）
    result_data = []

    # 3. 生成输出
    print("\\n[步骤 3] 生成输出...")

    output_file = output_dir / f"{rule_name}_{{datetime.now().strftime('%Y%m%d_%H%M%S')}}.xlsx"

    if result_data:
        result_df = pd.DataFrame(result_data)
        result_df.to_excel(output_file, index=False)
        print(f"已导出结果到：{{output_file}}")
    else:
        print("警告：没有生成数据")

    return {{
        "status": "success",
        "output_file": str(output_file),
        "record_count": len(result_data)
    }}


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """主函数"""
    result = process_data(DATA_DIR, RESULT_DIR)
    return result


if __name__ == '__main__':
    main()
'''

        return script

    def validate_script(self, script_path: Path) -> Dict[str, Any]:
        """验证脚本语法

        参数:
            script_path: 脚本路径

        返回:
            验证结果
        """
        import ast

        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 语法检查
            ast.parse(content)

            return {
                "valid": True,
                "message": "脚本语法正确"
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "message": f"语法错误：{str(e)}",
                "line": e.lineno
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"验证失败：{str(e)}"
            }


# 全局脚本生成器实例
_script_generator: Optional[ScriptGenerator] = None


def get_script_generator(base_dir: Optional[Path] = None) -> ScriptGenerator:
    """获取脚本生成器实例

    参数:
        base_dir: proc-agent 根目录

    返回:
        脚本生成器实例
    """
    global _script_generator
    if _script_generator is None:
        _script_generator = ScriptGenerator(base_dir)
    return _script_generator

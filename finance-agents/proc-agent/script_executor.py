"""脚本执行器模块

安全执行生成的 Python 脚本，处理数据整理业务。
"""

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
import traceback


class ScriptExecutionResult:
    """脚本执行结果"""

    def __init__(
        self,
        success: bool,
        output: str = "",
        error: str = "",
        result_file: Optional[str] = None
    ):
        self.success = success
        self.output = output
        self.error = error
        self.result_file = result_file

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "result_file": self.result_file,
        }


def execute_script(
    script_path: str,
    input_files: Optional[list] = None,
    output_dir: Optional[str] = None,
    timeout: int = 300
) -> ScriptExecutionResult:
    """执行 Python 脚本

    参数:
        script_path: 脚本文件路径
        input_files: 输入文件路径列表
        output_dir: 输出目录
        timeout: 超时时间（秒），默认 5 分钟

    返回:
        脚本执行结果
    """
    script_path = Path(script_path)

    # 检查脚本是否存在
    if not script_path.exists():
        return ScriptExecutionResult(
            success=False,
            error=f"脚本文件不存在：{script_path}"
        )

    # 构建命令
    cmd = [sys.executable, str(script_path)]

    # 添加输入文件参数
    if input_files:
        for f in input_files:
            cmd.extend(["--input", str(f)])

    # 添加输出目录参数
    if output_dir:
        cmd.extend(["--output-dir", str(output_dir)])

    try:
        # 执行脚本
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=script_path.parent
        )

        # 检查执行结果
        if result.returncode == 0:
            return ScriptExecutionResult(
                success=True,
                output=result.stdout,
                result_file=output_dir
            )
        else:
            return ScriptExecutionResult(
                success=False,
                output=result.stdout,
                error=f"脚本执行失败：{result.stderr}"
            )

    except subprocess.TimeoutExpired:
        return ScriptExecutionResult(
            success=False,
            error=f"脚本执行超时（{timeout}秒）"
        )
    except Exception as e:
        return ScriptExecutionResult(
            success=False,
            error=f"脚本执行异常：{str(e)}\n{traceback.format_exc()}"
        )


def execute_script_in_process(
    script_path: str,
    input_files: Optional[list] = None,
    output_dir: Optional[str] = None
) -> ScriptExecutionResult:
    """在进程中执行脚本（用于需要访问当前环境变量的场景）

    参数:
        script_path: 脚本文件路径
        input_files: 输入文件路径列表
        output_dir: 输出目录

    返回:
        脚本执行结果
    """
    script_path = Path(script_path)

    # 检查脚本是否存在
    if not script_path.exists():
        return ScriptExecutionResult(
            success=False,
            error=f"脚本文件不存在：{script_path}"
        )

    try:
        # 导入并执行脚本
        import importlib.util
        spec = importlib.util.spec_from_file_location("script_module", script_path)
        if spec is None or spec.loader is None:
            return ScriptExecutionResult(
                success=False,
                error=f"无法加载脚本：{script_path}"
            )

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 调用主函数
        if hasattr(module, 'main'):
            # 设置模块参数
            if hasattr(module, 'DATA_DIR') and input_files:
                # 使用第一个输入文件作为数据目录
                module.DATA_DIR = Path(input_files[0]).parent
            if hasattr(module, 'RESULT_DIR') and output_dir:
                module.RESULT_DIR = Path(output_dir)

            # 执行主函数
            module.main()

            return ScriptExecutionResult(
                success=True,
                output=f"脚本执行成功，结果保存在：{output_dir}",
                result_file=output_dir
            )
        else:
            return ScriptExecutionResult(
                success=False,
                error="脚本中没有找到 main 函数"
            )

    except Exception as e:
        return ScriptExecutionResult(
            success=False,
            error=f"脚本执行异常：{str(e)}\n{traceback.format_exc()}"
        )

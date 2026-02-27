"""规则创建与验证处理器

整合规则管理、脚本生成和结果验证功能。
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from .rule_manager import RuleManager, get_rule_manager
from .script_generator import ScriptGenerator, get_script_generator
from .result_validator import ResultValidator, get_result_validator


class RuleCreationProcessor:
    """规则创建处理器"""

    def __init__(self, base_dir: Optional[Path] = None):
        """初始化规则创建处理器

        参数:
            base_dir: proc-agent 根目录
        """
        self.rule_manager = get_rule_manager(base_dir)
        self.script_generator = get_script_generator(base_dir)
        self.result_validator = get_result_validator(base_dir)

    def create_rule_from_intent(
        self,
        rule_name: str,
        user_intent: str,
        user_description: str,
        data_sources: List[str],
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """根据用户意图创建规则

        参数:
            rule_name: 规则名称
            user_intent: 用户意图描述
            user_description: 用户规则描述
            data_sources: 数据源列表
            user_id: 用户 ID

        返回:
            创建结果
        """
        # 1. 提取意图关键词
        intent_keywords = self._extract_intent_keywords(user_intent)

        # 2. 生成处理规则（这里使用模板，后续可以用 LLM 生成）
        processing_rules = self._generate_processing_rules(user_description)

        # 3. 生成输出格式
        output_format = self._generate_output_format(rule_name)

        # 4. 创建规则
        try:
            rule_info = self.rule_manager.create_rule(
                rule_name=rule_name,
                description=user_description,
                intent_keywords=intent_keywords,
                data_sources=data_sources,
                processing_rules=processing_rules,
                output_format=output_format,
                user_id=user_id
            )

            # 5. 生成脚本
            script_result = self.script_generator.generate_script(
                rule_name=rule_name,
                rule_info=rule_info.__dict__ if hasattr(rule_info, '__dict__') else rule_info
            )

            return {
                "success": True,
                "rule_info": rule_info.__dict__ if hasattr(rule_info, '__dict__') else rule_info,
                "script_result": script_result,
                "message": f"规则 '{rule_name}' 创建成功"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"规则创建失败：{str(e)}"
            }

    def _extract_intent_keywords(self, user_intent: str) -> List[str]:
        """提取意图关键词

        参数:
            user_intent: 用户意图描述

        返回:
            关键词列表
        """
        # 简单的关键词提取（后续可以用 LLM）
        # 按逗号、句号分割
        keywords = []
        for sep in ['，', ',', '。', '.', ' ', '\n']:
            user_intent = user_intent.replace(sep, ' ')

        words = user_intent.split()
        # 过滤掉常见虚词
        stop_words = {'的', '了', '是', '在', '我', '有', '和', '就', '不', '人', '都', '一', '一个'}
        keywords = [w for w in words if w not in stop_words and len(w) > 1]

        return keywords[:10]  # 限制关键词数量

    def _generate_processing_rules(self, user_description: str) -> str:
        """生成处理规则

        参数:
            user_description: 用户规则描述

        返回:
            处理规则（Markdown 格式）
        """
        # 这里使用模板，后续可以用 LLM 生成
        return f"""## 数据处理流程

1. 读取用户上传的数据文件
2. 根据以下规则进行处理：

{user_description}

3. 验证数据完整性
4. 生成输出结果

## 数据验证规则

- 检查必填字段是否存在
- 检查数据格式是否正确
- 检查数据范围是否合理

## 异常处理

- 数据缺失时跳过该记录
- 格式错误时记录日志
- 处理失败时返回错误信息
"""

    def _generate_output_format(self, rule_name: str) -> Dict[str, Any]:
        """生成输出格式

        参数:
            rule_name: 规则名称

        返回:
            输出格式定义
        """
        return {
            "format": "excel",
            "sheet_name": rule_name,
            "fields": [
                {"name": "序号", "type": "int", "description": "记录序号"},
                {"name": "处理结果", "type": "str", "description": "处理结果描述"}
            ]
        }

    def validate_rule(
        self,
        rule_name: str,
        test_data_files: List[str],
        reference_result_file: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """验证规则

        参数:
            rule_name: 规则名称
            test_data_files: 测试数据文件列表
            reference_result_file: 参考结果文件（可选）
            user_id: 用户 ID

        返回:
            验证结果
        """
        # 1. 获取规则
        rule_info = self.rule_manager.get_rule(rule_name, user_id)
        if not rule_info:
            return {
                "success": False,
                "error": f"规则 '{rule_name}' 不存在"
            }

        # 2. 检查脚本是否存在
        script_path = self.rule_manager.get_rule_script(rule_name, user_id)
        if not script_path:
            # 生成脚本
            script_result = self.script_generator.generate_script(
                rule_name=rule_name,
                rule_info=rule_info
            )
            if not script_result.get("success"):
                return {
                    "success": False,
                    "error": "脚本生成失败",
                    "details": script_result
                }
            script_path = Path(script_result["script_path"])

        # 3. 执行脚本
        from .script_executor import execute_script
        exec_result = execute_script(
            script_path=str(script_path),
            input_files=test_data_files
        )

        if not exec_result.success:
            return {
                "success": False,
                "error": "脚本执行失败",
                "details": exec_result.error
            }

        # 4. 比较结果（如果有参考结果）
        validation_result = {
            "success": True,
            "rule_name": rule_name,
            "execution_result": exec_result.to_dict() if hasattr(exec_result, 'to_dict') else exec_result.__dict__
        }

        if reference_result_file:
            # 查找生成的结果文件
            generated_file = self._find_generated_result(rule_name)
            if generated_file:
                comparison = self.result_validator.compare_results(
                    generated_file=generated_file,
                    reference_file=reference_result_file
                )
                validation_result["comparison"] = comparison

                # 生成验证报告
                report_path = self.result_validator.validation_dir / f"{rule_name}_validation.md"
                report = self.result_validator.generate_validation_report(
                    comparison=comparison,
                    rule_name=rule_name,
                    output_path=report_path
                )
                validation_result["validation_report"] = report
            else:
                validation_result["warning"] = "未找到生成的结果文件，无法比较"

        return validation_result

    def _find_generated_result(self, rule_name: str) -> Optional[str]:
        """查找生成的结果文件

        参数:
            rule_name: 规则名称

        返回:
            结果文件路径
        """
        result_dir = Path(__file__).parent / "result"
        pattern = f"{rule_name}_*.xlsx"

        result_files = list(result_dir.glob(pattern))
        if result_files:
            # 返回最新的文件
            return str(max(result_files, key=lambda p: p.stat().st_mtime))

        return None


# 全局规则创建处理器实例
_rule_creation_processor: Optional[RuleCreationProcessor] = None


def get_rule_creation_processor(base_dir: Optional[Path] = None) -> RuleCreationProcessor:
    """获取规则创建处理器实例

    参数:
        base_dir: proc-agent 根目录

    返回:
        规则创建处理器实例
    """
    global _rule_creation_processor
    if _rule_creation_processor is None:
        _rule_creation_processor = RuleCreationProcessor(base_dir)
    return _rule_creation_processor

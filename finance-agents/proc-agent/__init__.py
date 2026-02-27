"""数据整理数字员工核心模块

该模块提供了数据整理的核心功能，包括：
1. 意图识别：根据用户请求识别业务类型
2. 规则管理：创建、编辑、删除业务规则
3. 脚本生成：根据规则生成处理脚本
4. 结果验证：比较处理结果与参考结果
5. 对话式规则创建：通过自然语言对话创建规则
6. 脚本执行：调用或生成 Python 脚本执行数据处理

注意：
- proc-agent 是数据整理数字员工（Data-Process Agent）
- 审计数据整理是 proc-agent 支持的一个业务领域
- 审计不是独立的 agent
"""

from pathlib import Path

# proc-agent 根目录
PROC_AGENT_DIR = Path(__file__).parent

from .skill_handler import process_audit_data
from .script_executor import execute_script
from .intent_recognizer import identify_intent
from .rule_manager import RuleManager, get_rule_manager
from .script_generator import ScriptGenerator, get_script_generator
from .result_validator import ResultValidator, get_result_validator
from .rule_creation_processor import RuleCreationProcessor, get_rule_creation_processor
from .llm_rule_understanding import LLMRuleUnderstanding, get_llm_rule_understanding
from .conversational_rule_creator import (
    ConversationalRuleCreator,
    get_rule_creator,
    build_rule_creation_graph
)

__all__ = [
    "process_audit_data",
    "execute_script",
    "identify_intent",
    "RuleManager",
    "get_rule_manager",
    "ScriptGenerator",
    "get_script_generator",
    "ResultValidator",
    "get_result_validator",
    "RuleCreationProcessor",
    "get_rule_creation_processor",
    "LLMRuleUnderstanding",
    "get_llm_rule_understanding",
    "ConversationalRuleCreator",
    "get_rule_creator",
    "build_rule_creation_graph",
    "PROC_AGENT_DIR"
]

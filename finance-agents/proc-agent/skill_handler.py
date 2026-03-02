"""技能处理器模块

审计数据整理技能的主处理器，协调意图识别、规则加载、脚本执行等流程。
支持审计类 skill（audit）和核算类 skill（recognition）两大类别。
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import traceback

from .intent_recognizer import (
    identify_intent,
    get_rule_file,
    get_script_file,
    IntentType,
    CHAT_ID_REQUIRED_INTENTS,
)
from .script_executor import execute_script, execute_script_in_process, ScriptExecutionResult


# 获取 proc-agent 根目录
AUDIT_AGENT_DIR = Path(__file__).parent


class AuditDataSkillResult:
    """审计/核算数据技能执行结果"""

    def __init__(
        self,
        skill_id: str = "AUDIT-DATA-ORGANIZER-001",
        intent_type: str = "",
        rule_file: str = "",
        status: str = "pending",
        data: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.skill_id = skill_id
        self.intent_type = intent_type
        self.rule_file = rule_file
        self.status = status
        self.data = data or {}
        self.error = error
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "skill_id": self.skill_id,
            "intent_type": self.intent_type,
            "rule_file": self.rule_file,
            "status": self.status,
            "data": self.data,
            "metadata": self.metadata
        }
        if self.error:
            result["error"] = self.error
        return result


def handle_error(
    error_code: str,
    error_message: str,
    suggestion: Optional[str] = None
) -> Dict[str, Any]:
    """标准化错误处理

    参数:
        error_code: 错误代码
        error_message: 错误描述
        suggestion: 处理建议

    返回:
        错误响应字典
    """
    return {
        "code": error_code,
        "message": error_message,
        "suggestion": suggestion
    }


def process_audit_data(
    user_request: str,
    files: List[str],
    output_dir: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """处理审计/核算数据整理请求

    参数:
        user_request: 用户的自然语言请求
        files: 上传的文件路径列表
        output_dir: 输出目录，默认为 result/（审计类）或 result/{chat_id}/（核算类）
        chat_id: 用户会话 ID，核算类 skill 用于隔离输出目录

    返回:
        处理结果字典
    """
    # 初始化结果
    result = AuditDataSkillResult()

    try:
        # 步骤 1: 意图识别
        intent_type, score = identify_intent(user_request)
        result.intent_type = intent_type
        result.metadata["intent_score"] = score

        # 根据意图类型设置 skill_id
        if intent_type == IntentType.RECOGNITION_REPORT:
            result.skill_id = "RECOGNITION-REPORT-GEN-001"

        # 步骤 2: 获取规则文件和脚本文件路径
        rule_file = get_rule_file(intent_type)
        script_file = get_script_file(intent_type)

        if rule_file:
            result.rule_file = str(AUDIT_AGENT_DIR / rule_file)
        result.metadata["script_path"] = str(AUDIT_AGENT_DIR / script_file) if script_file else None

        # 步骤 3: 检查脚本是否存在
        if not script_file:
            result.status = "error"
            result.error = handle_error(
                "SCRIPT_NOT_FOUND",
                f"未找到意图 '{intent_type}' 对应的脚本文件",
                "请联系管理员配置对应的处理脚本"
            )
            return result.to_dict()

        script_path = AUDIT_AGENT_DIR / script_file
        if not script_path.exists():
            result.status = "error"
            result.error = handle_error(
                "SCRIPT_NOT_FOUND",
                f"脚本文件不存在：{script_path}",
                "请检查脚本文件是否正确部署"
            )
            return result.to_dict()

        # 步骤 4: 判断是否为需要 chat_id 的 recognition 类 skill
        is_recognition = intent_type in CHAT_ID_REQUIRED_INTENTS
        effective_chat_id = chat_id or "default"

        # 步骤 5: 设置输出目录
        if is_recognition:
            # recognition skill 使用 result/{chat_id}/ 隔离目录
            if not output_dir:
                output_dir = str(AUDIT_AGENT_DIR / "result" / effective_chat_id)
        else:
            if not output_dir:
                output_dir = str(AUDIT_AGENT_DIR / "result")
        os.makedirs(output_dir, exist_ok=True)

        # 步骤 6: 执行脚本
        result.status = "running"

        if is_recognition:
            # recognition skill 通过子进程执行，传递 --chat-id 参数
            exec_result = execute_script(
                script_path=str(script_path),
                input_files=files,
                output_dir=output_dir,
                extra_args={"--chat-id": effective_chat_id},
                timeout=300,
            )
        else:
            # 审计类 skill 使用进程内执行
            exec_result = execute_script_in_process(
                script_path=str(script_path),
                input_files=files,
                output_dir=output_dir,
            )

        if exec_result.success:
            result.status = "success"
            result.metadata["execution_output"] = exec_result.output
            result.metadata["result_file"] = exec_result.result_file

            if is_recognition:
                # 解析 recognition 脚本的 JSON 输出，提取下载 URL
                _parse_recognition_output(exec_result.output, result, output_dir)
            else:
                # 审计类：扫描输出目录中的结果文件
                if output_dir:
                    result_files = []
                    for ext in ["*.xlsx", "*.md", "*.csv"]:
                        result_files.extend(Path(output_dir).glob(ext))
                    result.data["result_files"] = [str(f) for f in result_files]
        else:
            result.status = "error"
            result.error = handle_error(
                "SCRIPT_EXECUTION_FAILED",
                exec_result.error,
                "请检查输入数据和脚本配置"
            )

    except Exception as e:
        result.status = "error"
        result.error = handle_error(
            "UNKNOWN_ERROR",
            f"处理过程中发生异常：{str(e)}",
            "请查看详细日志或联系技术支持"
        )
        result.metadata["traceback"] = traceback.format_exc()

    return result.to_dict()


def _parse_recognition_output(
    output: str,
    result: "AuditDataSkillResult",
    output_dir: str,
) -> None:
    """解析 recognition_rule.py 的 JSON 标准输出，填充结果。

    recognition 脚本将 JSON 结果打印到 stdout，格式为：
    {
        "status": "success",
        "result_files": ["..."],
        "download_urls": ["..."],
        "metadata": {...}
    }
    """
    # 尝试从输出中提取 JSON 块
    try:
        # 找到最后一个完整的 JSON 对象
        json_match = None
        for line in output.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    json_match = json.loads(line)
                except json.JSONDecodeError:
                    pass
        # 尝试整体解析
        if json_match is None:
            import re
            m = re.search(r"\{.*\}", output, re.DOTALL)
            if m:
                json_match = json.loads(m.group())

        if json_match:
            script_status = json_match.get("status", "")
            result.data["result_files"] = json_match.get("result_files", [])
            result.data["download_urls"] = json_match.get("download_urls", [])
            result.metadata.update(json_match.get("metadata", {}))
            if script_status in ("success", "partial_success"):
                result.status = "success"
            elif script_status == "error":
                result.status = "error"
                result.error = json_match.get("error", {})
            return
    except Exception:
        pass

    # 解析失败时，回退到扫描目录
    if output_dir:
        result_files = []
        for ext in ["*.xlsx", "*.md", "*.csv"]:
            result_files.extend(Path(output_dir).glob(ext))
        result.data["result_files"] = [str(f) for f in result_files]


def list_skills() -> list[dict]:
    """列出所有可用的技能（含审计类和核算类）

    返回:
        技能列表
    """
    from .intent_recognizer import list_available_intents
    from .rule_manager import get_rule_manager

    # 获取内置技能（含 recognition_report）
    skills = list_available_intents()

    # 获取用户创建的规则
    try:
        rule_manager = get_rule_manager()
        rules = rule_manager.list_rules()
        for rule in rules:
            skills.append({
                "id": f"user_rule_{rule['name']}",
                "name": f"[用户规则] {rule['name']}",
                "description": rule.get('description', '用户创建的规则')
            })
    except Exception:
        pass  # 忽略规则加载失败

    return skills


def get_skill_detail(skill_id: str) -> dict | None:
    """获取技能详细信息

    参数:
        skill_id: 技能 ID

    返回:
        技能详细信息
    """
    from .intent_recognizer import INTENT_KEYWORDS, RULE_FILE_MAPPING, SCRIPT_FILE_MAPPING, list_available_intents

    intents = list_available_intents()
    skill = next((s for s in intents if s["id"] == skill_id), None)

    if not skill:
        return None

    return {
        "id": skill_id,
        "name": skill["name"],
        "description": f"处理{skill['name']}业务",
        "rule_file": RULE_FILE_MAPPING.get(skill_id),
        "script_file": SCRIPT_FILE_MAPPING.get(skill_id),
        "keywords": INTENT_KEYWORDS.get(skill_id, []),
        "status": "enabled"
    }

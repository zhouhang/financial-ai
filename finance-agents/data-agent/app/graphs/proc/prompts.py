"""proc_agent 子图各节点所需的系统提示词"""

from __future__ import annotations


# ── get_proc_rule_node 提示词 ─────────────────────────────────────────────────

PROC_RULE_NOT_FOUND_PROMPT = """\
未找到名称为「{rule_name}」的数据整理规则。

请确认规则名称是否正确，或联系管理员获取可用的规则列表。
"""

# ── check_file_node 提示词 ────────────────────────────────────────────────────

FILE_CHECK_FAIL_PROMPT = """\
文件校验失败，原因如下：

{reason}

请根据规则要求重新上传文件：
- 支持的文件类型：{allowed_types}
- 需要上传的文件数量：{required_count} 个
- 必需的表头字段：{required_headers}
"""

# ── proc_task_execute_node 提示词 ─────────────────────────────────────────────

PROC_EXECUTING_PROMPT = """\
正在按规则「{rule_name}」执行数据整理任务，请稍候…

当前步骤：{current_step}
"""

# ── result_node 提示词 ────────────────────────────────────────────────────────

PROC_RESULT_SUCCESS_PROMPT = """\
数据整理任务已完成。

**规则：** {rule_name}
**处理文件：** {file_names}
**处理结果：**

{result_summary}

如需重新处理或使用其他规则，请告知。
"""

PROC_RESULT_FAIL_PROMPT = """\
数据整理任务执行失败。

**规则：** {rule_name}
**错误信息：** {error_message}

请检查上传文件是否符合规则要求，或联系管理员排查问题。
"""

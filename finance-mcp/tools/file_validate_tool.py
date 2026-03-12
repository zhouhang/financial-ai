"""
文件校验 MCP 工具定义和实现

根据文件校验 JSON 规则，校验用户上传的文件列表，返回文件与表定义的对应关系。

校验策略：全量列名精确匹配（exact）
- 文件列名集合必须与规则定义的 all_columns 集合完全一致
- 支持列名别名转换
- 支持大小写不敏感、忽略空格（根据 validation_config 配置）
- is_ness=true 的表为必传文件，若全部未匹配则返回错误
"""
import json
import logging
from typing import Dict, Any, List, Optional, Set

from mcp import Tool

# 导入文件校验规则查询函数（从 bus_rules.mcp_server.tools 直接导入）
from bus_rules.mcp_server.tools import get_rule_from_bus

# 配置日志
logger = logging.getLogger("proc.mcp_server.file_validate_tool")


# ════════════════════════════════════════════════════════════════════════════
# 工具定义
# ════════════════════════════════════════════════════════════════════════════

def create_file_validate_tools() -> list[Tool]:
    """创建文件校验工具列表"""
    return [
        Tool(
            name="validate_uploaded_files",
            description=(
                "根据规则编码（rule_code）从数据库获取文件校验规则，校验用户上传的文件列表，判断每个文件属于哪个预定义的表。"
                "返回文件名与表定义（table_name）的对应关系；若必传文件（is_ness=true）未找到对应上传文件，则返回错误提示。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "uploaded_files": {
                        "type": "array",
                        "description": (
                            "用户上传的文件列表，每个元素包含文件名和列名信息。"
                            "格式：[{\"file_name\": \"xxx.xlsx\", \"columns\": [\"列1\", \"列2\", ...]}]"
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_name": {
                                    "type": "string",
                                    "description": "上传文件的文件名"
                                },
                                "columns": {
                                    "type": "array",
                                    "description": "文件的列名列表",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["file_name", "columns"]
                        }
                    },
                    "rule_code": {
                        "type": "string",
                        "description": "文件校验规则编码（rule_code），用于从数据库查询对应的校验规则配置"
                    }
                },
                "required": ["uploaded_files", "rule_code"]
            }
        )
    ]


# ════════════════════════════════════════════════════════════════════════════
# 列名标准化工具函数
# ════════════════════════════════════════════════════════════════════════════

def _normalize_column_name(col_name: str, config: dict) -> str:
    """
    根据 validation_config 标准化单个列名。

    Args:
        col_name: 原始列名
        config: validation_config 配置字典

    Returns:
        标准化后的列名
    """
    normalized = str(col_name).strip()

    if config.get("ignore_whitespace", True):
        normalized = normalized.replace(" ", "").replace("\t", "")

    if not config.get("case_sensitive", False):
        normalized = normalized.lower()

    return normalized


def _normalize_columns_set(columns: List[str], config: dict) -> Set[str]:
    """
    将列名列表标准化为集合。

    Args:
        columns: 列名列表
        config: validation_config 配置字典

    Returns:
        标准化后的列名集合
    """
    return {_normalize_column_name(col, config) for col in columns}


def _build_alias_mapping(table_schema: dict, config: dict) -> Dict[str, str]:
    """
    构建别名到标准列名的映射。

    Args:
        table_schema: 表结构定义
        config: validation_config 配置字典

    Returns:
        别名（标准化）-> 标准列名（标准化）的映射字典
    """
    alias_map: Dict[str, str] = {}
    for original_col, aliases in table_schema.get("column_aliases", {}).items():
        normalized_original = _normalize_column_name(original_col, config)
        for alias in aliases:
            normalized_alias = _normalize_column_name(alias, config)
            alias_map[normalized_alias] = normalized_original
    return alias_map


def _normalize_file_columns(
    file_columns: List[str],
    table_schema: dict,
    config: dict
) -> Set[str]:
    """
    将文件列名标准化，并将别名转换为标准列名。

    Args:
        file_columns: 文件中的列名列表
        table_schema: 表结构定义
        config: validation_config 配置字典

    Returns:
        标准化且别名转换后的列名集合
    """
    alias_map = _build_alias_mapping(table_schema, config)
    normalized_set: Set[str] = set()

    for col in file_columns:
        normalized_col = _normalize_column_name(col, config)
        # 如果是别名，转换为标准列名
        if normalized_col in alias_map:
            normalized_set.add(alias_map[normalized_col])
        else:
            normalized_set.add(normalized_col)

    return normalized_set


# ════════════════════════════════════════════════════════════════════════════
# 文件校验核心逻辑
# ════════════════════════════════════════════════════════════════════════════

def _check_file_match_table(
    file_columns: List[str],
    table_schema: dict,
    config: dict
) -> dict:
    """
    检查文件列名是否与某个表结构全量精确匹配。

    Args:
        file_columns: 文件列名列表
        table_schema: 表结构定义（含 all_columns, column_aliases 等）
        config: validation_config 配置字典

    Returns:
        匹配结果字典，含 is_match, missing_columns, extra_columns
    """
    # 规则定义的全量列名集合（标准化）
    expected_columns = table_schema.get("all_columns", [])
    expected_set = _normalize_columns_set(expected_columns, config)

    # 文件列名标准化（含别名转换）
    file_set = _normalize_file_columns(file_columns, table_schema, config)

    missing_columns = list(expected_set - file_set)
    extra_columns = list(file_set - expected_set)
    is_match = (len(missing_columns) == 0 and len(extra_columns) == 0)

    return {
        "is_match": is_match,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns
    }


def validate_files_against_rules(
    uploaded_files: List[Dict[str, Any]],
    validation_rules: dict
) -> dict:
    """
    核心校验函数：将上传文件列表与文件校验规则逐一匹配。

    Args:
        uploaded_files: 上传文件列表，格式 [{"file_name": "...", "columns": [...]}]
        validation_rules: file_validation_rules 字典（已解析为 dict）

    Returns:
        校验结果字典
    """
    config = validation_rules.get("validation_config", {})
    table_schemas = validation_rules.get("table_schemas", [])

    if not table_schemas:
        return {
            "success": False,
            "error": "校验规则中 table_schemas 为空，无法进行校验"
        }

    # ── 逐文件匹配 ────────────────────────────────────────────────────────
    # file_match_map: file_name -> matched_table (table_id, table_name, is_ness)
    file_match_map: Dict[str, Optional[Dict[str, Any]]] = {}
    # unmatched_files: 未命中任何规则的文件名列表
    unmatched_files: List[str] = []

    for file_info in uploaded_files:
        file_name = file_info.get("file_name", "")
        file_columns = file_info.get("columns", [])

        if not file_name:
            logger.warning("上传文件列表中存在缺少 file_name 的条目，已跳过")
            continue

        matched_table = None
        for table_schema in table_schemas:
            match_result = _check_file_match_table(file_columns, table_schema, config)
            if match_result["is_match"]:
                matched_table = {
                    "table_id": table_schema["table_id"],
                    "table_name": table_schema["table_name"],
                    "is_ness": table_schema.get("is_ness", False)
                }
                logger.info(
                    f"[文件校验] 文件 '{file_name}' 匹配成功: {table_schema['table_name']}"
                )
                break
            else:
                logger.debug(
                    f"[文件校验] 文件 '{file_name}' 与表 '{table_schema['table_name']}' 不匹配 - "
                    f"缺少: {match_result['missing_columns']}, "
                    f"多余: {match_result['extra_columns']}"
                )

        if matched_table:
            file_match_map[file_name] = matched_table
        else:
            file_match_map[file_name] = None
            unmatched_files.append(file_name)
            logger.info(f"[文件校验] 文件 '{file_name}' 未匹配任何表定义")

    # ── 构建匹配结果列表 ───────────────────────────────────────────────────
    matched_results: List[Dict[str, str]] = []
    for file_name, matched_table in file_match_map.items():
        if matched_table:
            matched_results.append({
                "file_name": file_name,
                "table_id": matched_table["table_id"],
                "table_name": matched_table["table_name"]
            })

    # ── 检查必传文件是否覆盖 ──────────────────────────────────────────────
    # 找出所有 is_ness=true 的表
    necessary_tables = [
        ts for ts in table_schemas if ts.get("is_ness", False)
    ]
    # 已命中的 table_id 集合
    matched_table_ids: Set[str] = {
        item["table_id"] for item in matched_results
    }
    # 未被上传文件覆盖的必传表
    missing_necessary_tables = [
        ts for ts in necessary_tables
        if ts["table_id"] not in matched_table_ids
    ]

    if missing_necessary_tables:
        missing_names = [ts["table_name"] for ts in missing_necessary_tables]
        logger.warning(
            f"[文件校验] 必传文件未上传: {missing_names}"
        )
        return {
            "success": False,
            "error": (
                f"必传文件未上传，以下文件类型为必填：{', '.join(missing_names)}。"
                f"请上传对应格式的文件后重试。"
            ),
            "missing_necessary_tables": [
                {"table_id": ts["table_id"], "table_name": ts["table_name"]}
                for ts in missing_necessary_tables
            ],
            "unmatched_files": unmatched_files,
            "matched_results": matched_results
        }

    # ── 全部校验通过 ──────────────────────────────────────────────────────
    total = len(uploaded_files)
    matched_count = len(matched_results)
    logger.info(
        f"[文件校验] 校验完成，共 {total} 个文件，匹配 {matched_count} 个，"
        f"未匹配 {len(unmatched_files)} 个"
    )

    return {
        "success": True,
        "message": (
            f"文件校验完成，共 {total} 个文件，"
            f"{matched_count} 个匹配成功，{len(unmatched_files)} 个未匹配任何表定义。"
        ),
        "matched_results": matched_results,
        "unmatched_files": unmatched_files,
        "total_files": total,
        "matched_count": matched_count,
        "unmatched_count": len(unmatched_files)
    }


# ════════════════════════════════════════════════════════════════════════════
# 工具调用处理函数
# ════════════════════════════════════════════════════════════════════════════

async def handle_file_validate_tool_call(name: str, arguments: dict) -> dict:
    """
    处理文件校验工具调用的统一入口。

    Args:
        name: 工具名称
        arguments: 工具参数

    Returns:
        工具执行结果
    """
    if name == "validate_uploaded_files":
        return await _handle_validate_uploaded_files(arguments)
    else:
        return {"error": f"未知的文件校验工具: {name}"}


async def _handle_validate_uploaded_files(arguments: dict) -> dict:
    """
    处理 validate_uploaded_files 工具调用。

    Args:
        arguments: 工具参数，包含 uploaded_files 和 rule_code

    Returns:
        校验结果字典
    """
    # ── 参数提取与校验 ────────────────────────────────────────────────────
    uploaded_files = arguments.get("uploaded_files")
    rule_code = arguments.get("rule_code", "").strip()

    if not uploaded_files:
        return {
            "success": False,
            "error": "uploaded_files 不能为空，请提供至少一个上传文件信息"
        }

    if not rule_code:
        return {
            "success": False,
            "error": "rule_code 不能为空，请提供文件校验规则编码"
        }

    # ── 根据 rule_code 从数据库获取校验规则（含缓存）────────────────────────
    try:
        rule_record = get_rule_from_bus(rule_code, 1)  # rule_type=1 表示文件校验规则
    except Exception as e:
        logger.error(f"[文件校验] 获取校验规则失败，rule_code={rule_code}: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"获取文件校验规则失败: {str(e)}"
        }

    if rule_record is None:
        return {
            "success": False,
            "error": f"未找到 rule_code 为 '{rule_code}' 的文件校验规则，请确认规则编码是否正确"
        }

    # rule_record["rule"] 是从 bus_rules 表获取的规则内容
    rule_data = rule_record["rule"]
    if isinstance(rule_data, str):
        try:
            rule_data = json.loads(rule_data)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"rule_code='{rule_code}' 对应的规则内容不是有效的 JSON: {e}"
            }

    # 支持两种顶层结构：直接是 file_validation_rules 的值，或包含 file_validation_rules 的外层对象
    if "file_validation_rules" in rule_data:
        validation_rules = rule_data["file_validation_rules"]
    elif "table_schemas" in rule_data:
        validation_rules = rule_data
    else:
        return {
            "success": False,
            "error": (
                f"rule_code='{rule_code}' 对应的规则格式不正确，"
                "需包含 file_validation_rules 或 table_schemas 字段"
            )
        }

    # ── 校验 uploaded_files 格式 ──────────────────────────────────────────
    for idx, file_info in enumerate(uploaded_files):
        if not isinstance(file_info, dict):
            return {
                "success": False,
                "error": f"uploaded_files[{idx}] 格式错误，应为包含 file_name 和 columns 的对象"
            }
        if "file_name" not in file_info:
            return {
                "success": False,
                "error": f"uploaded_files[{idx}] 缺少 file_name 字段"
            }
        if "columns" not in file_info or not isinstance(file_info["columns"], list):
            return {
                "success": False,
                "error": f"uploaded_files[{idx}]（{file_info.get('file_name', '')}）缺少 columns 字段或格式错误"
            }

    # ── 执行校验 ──────────────────────────────────────────────────────────
    try:
        result = validate_files_against_rules(uploaded_files, validation_rules)
        return result
    except Exception as e:
        logger.error(f"[文件校验] 执行校验时发生异常: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"文件校验执行失败: {str(e)}"
        }

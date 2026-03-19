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
from auth.jwt_utils import get_user_from_token

# 导入文件校验规则查询函数
from tools.rules import get_rule
from tools.rule_schema import load_and_validate_rule

# 配置日志
logger = logging.getLogger("proc.mcp_server.file_validate_tool")


# ════════════════════════════════════════════════════════════════════════════
# 工具定义
# ════════════════════════════════════════════════════════════════════════════

def create_file_validate_tools() -> list[Tool]:
    """创建文件校验工具列表"""
    return [
        Tool(
            name="validate_files",
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
                    },
                    "auth_token": {
                        "type": "string",
                        "description": "JWT token，用于校验当前用户是否有权使用该规则"
                    }
                },
                "required": ["uploaded_files", "rule_code", "auth_token"]
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

    # ── 文件数量校验 ──────────────────────────────────────────────────────────────────────
    file_count_config = config.get("file_count", {})
    min_files = file_count_config.get("min", 1)
    max_files = file_count_config.get("max", 0)  # 0 表示不限制
    allow_multiple = file_count_config.get("allow_multiple", True)

    total_uploaded = len(uploaded_files)

    # 检查最小文件数量
    if total_uploaded < min_files:
        logger.warning(
            f"[文件校验] 文件数量不足: 上传 {total_uploaded} 个，最少需要 {min_files} 个"
        )
        return {
            "success": False,
            "error": f"文件数量不足，至少需要上传 {min_files} 个文件，当前上传 {total_uploaded} 个。"
        }

    # 检查最大文件数量（max > 0 时有效）
    if max_files > 0 and total_uploaded > max_files:
        logger.warning(
            f"[文件校验] 文件数量超限: 上传 {total_uploaded} 个，最多允许 {max_files} 个"
        )
        return {
            "success": False,
            "error": f"文件数量超过限制，最多允许上传 {max_files} 个文件，当前上传 {total_uploaded} 个。"
        }

    # 检查是否允许多文件
    if not allow_multiple and total_uploaded > 1:
        logger.warning(
            f"[文件校验] 不允许多文件上传: 尝试上传 {total_uploaded} 个文件"
        )
        return {
            "success": False,
            "error": "当前规则不允许上传多个文件，请只上传一个文件。"
        }

    logger.info(
        f"[文件校验] 文件数量校验通过: 上传 {total_uploaded} 个文件 "
        f"(要求: 最少 {min_files}, 最多 {max_files if max_files > 0 else '无限制'}, "
        f"多文件允许: {allow_multiple})"
    )

    # ── 逐文件匹配 ────────────────────────────────────────────────────────
    # file_to_tables_map: file_name -> List[matched_table_info] (记录每个文件匹配到的所有规则)
    file_to_tables_map: Dict[str, List[Dict[str, Any]]] = {}
    # table_to_files_map: table_id -> List[file_name] (记录每个规则匹配到的所有文件)
    table_to_files_map: Dict[str, List[str]] = {}
    # unmatched_files: 未命中任何规则的文件名列表
    unmatched_files: List[str] = []

    # 过滤出启用的规则（enabled=true 或 enabled 字段不存在时默认为启用）
    enabled_table_schemas = [
        ts for ts in table_schemas
        if ts.get("enabled", True)
    ]

    if not enabled_table_schemas:
        return {
            "success": False,
            "error": "校验规则中所有 table_schemas 规则均被禁用，无法进行校验"
        }

    logger.info(
        f"[文件校验] 启用规则统计: 共 {len(table_schemas)} 个规则，"
        f"启用 {len(enabled_table_schemas)} 个，禁用 {len(table_schemas) - len(enabled_table_schemas)} 个"
    )

    for file_info in uploaded_files:
        file_name = file_info.get("file_name", "")
        file_columns = file_info.get("columns", [])

        if not file_name:
            logger.warning("上传文件列表中存在缺少 file_name 的条目，已跳过")
            continue

        matched_tables: List[Dict[str, Any]] = []
        for table_schema in enabled_table_schemas:
            match_result = _check_file_match_table(file_columns, table_schema, config)
            if match_result["is_match"]:
                table_info = {
                    "table_id": table_schema["table_id"],
                    "table_name": table_schema["table_name"],
                    "is_ness": table_schema.get("is_ness", False),
                    "max_file_match_count": table_schema.get("max_file_match_count", 0)
                }
                matched_tables.append(table_info)

                # 记录到 table_to_files_map
                table_id = table_schema["table_id"]
                if table_id not in table_to_files_map:
                    table_to_files_map[table_id] = []
                table_to_files_map[table_id].append(file_name)

                logger.info(
                    f"[文件校验] 文件 '{file_name}' 匹配成功: {table_schema['table_name']}"
                )
            else:
                logger.debug(
                    f"[文件校验] 文件 '{file_name}' 与表 '{table_schema['table_name']}' 不匹配 - "
                    f"缺少: {match_result['missing_columns']}, "
                    f"多余: {match_result['extra_columns']}"
                )

        if matched_tables:
            file_to_tables_map[file_name] = matched_tables
        else:
            unmatched_files.append(file_name)
            logger.info(f"[文件校验] 文件 '{file_name}' 未匹配任何表定义")

    # ── 检查是否允许多规则匹配同一文件 ─────────────────────────────────────
    allow_multi_rule_match = config.get("allow_multi_rule_match", True)
    if not allow_multi_rule_match:
        # 检测是否有文件匹配了多条规则
        multi_match_errors: List[str] = []
        for file_name, matched_tables in file_to_tables_map.items():
            if len(matched_tables) > 1:
                table_names = [t["table_name"] for t in matched_tables]
                multi_match_errors.append(
                    f"文件 '{file_name}' 同时匹配了多条规则: {', '.join(table_names)}"
                )

        if multi_match_errors:
            error_msg = "文件校验失败，以下文件匹配了多条规则（当前配置不允许）:\n" + "\n".join(multi_match_errors)
            logger.warning(f"[文件校验] {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "multi_match_violations": [
                    {
                        "file_name": file_name,
                        "matched_tables": [
                            {"table_id": t["table_id"], "table_name": t["table_name"]}
                            for t in matched_tables
                        ]
                    }
                    for file_name, matched_tables in file_to_tables_map.items()
                    if len(matched_tables) > 1
                ],
                "unmatched_files": unmatched_files
            }

    # ── 检查每个规则匹配的文件数量是否超过限制 ─────────────────────────────
    max_match_count_violations: List[Dict[str, Any]] = []
    for table_schema in enabled_table_schemas:
        table_id = table_schema["table_id"]
        table_name = table_schema["table_name"]
        max_file_match_count = table_schema.get("max_file_match_count", 0)

        # max_file_match_count = 0 表示不限制
        if max_file_match_count > 0:
            matched_files = table_to_files_map.get(table_id, [])
            if len(matched_files) > max_file_match_count:
                max_match_count_violations.append({
                    "table_id": table_id,
                    "table_name": table_name,
                    "max_allowed": max_file_match_count,
                    "actual_count": len(matched_files),
                    "matched_files": matched_files
                })

    if max_match_count_violations:
        error_details = []
        for violation in max_match_count_violations:
            error_details.append(
                f"规则 '{violation['table_name']}' (限额: {violation['max_allowed']}个) "
                f"实际匹配了 {violation['actual_count']} 个文件: {', '.join(violation['matched_files'])}"
            )
        error_msg = "文件校验失败，以下规则匹配的文件数量超过限额:\n" + "\n".join(error_details)
        logger.warning(f"[文件校验] {error_msg}")

        # 构建匹配结果列表（用于返回）
        matched_results: List[Dict[str, str]] = []
        for file_name, matched_tables in file_to_tables_map.items():
            if matched_tables:
                # 取第一个匹配的规则（如果不允许多规则匹配）或主规则
                primary_table = matched_tables[0]
                matched_results.append({
                    "file_name": file_name,
                    "table_id": primary_table["table_id"],
                    "table_name": primary_table["table_name"]
                })

        return {
            "success": False,
            "error": error_msg,
            "max_match_count_violations": max_match_count_violations,
            "unmatched_files": unmatched_files,
            "matched_results": matched_results
        }

    # ── 构建匹配结果列表 ───────────────────────────────────────────────────
    matched_results: List[Dict[str, str]] = []
    for file_name, matched_tables in file_to_tables_map.items():
        if matched_tables:
            # 如果不允许多规则匹配，取第一个；否则也取第一个作为主匹配
            primary_table = matched_tables[0]
            matched_results.append({
                "file_name": file_name,
                "table_id": primary_table["table_id"],
                "table_name": primary_table["table_name"]
            })

    # ── 检查必传文件是否覆盖 ──────────────────────────────────────────────
    # 找出所有启用的、is_ness=true 的表（禁用的规则不参与必传检查）
    necessary_tables = [
        ts for ts in enabled_table_schemas if ts.get("is_ness", False)
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
    if name == "validate_files":
        return await _handle_validate_files(arguments)
    else:
        return {"error": f"未知的文件校验工具: {name}"}


async def _handle_validate_files(arguments: dict) -> dict:
    """
    处理 validate_files 工具调用。

    Args:
        arguments: 工具参数，包含 uploaded_files 和 rule_code

    Returns:
        校验结果字典
    """
    # ── 参数提取与校验 ────────────────────────────────────────────────────
    uploaded_files = arguments.get("uploaded_files")
    rule_code = arguments.get("rule_code", "").strip()
    auth_token = arguments.get("auth_token", "").strip()

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
    if not auth_token:
        return {
            "success": False,
            "error": "未提供认证 token，请先登录"
        }

    user = get_user_from_token(auth_token)
    if not user:
        return {
            "success": False,
            "error": "token 无效或已过期，请重新登录"
        }

    user_id = str(user.get("user_id") or user.get("id") or "")
    if not user_id:
        return {
            "success": False,
            "error": "token 中缺少用户标识"
        }

    # ── 根据 rule_code 从数据库获取校验规则（含结构校验）────────────────────
    validation_result = load_and_validate_rule(rule_code, expected_kind="file_validation", user_id=user_id)
    if not validation_result.get("success"):
        return validation_result
    validation_rules = validation_result.get("rule", {})

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
        # 调试日志：输出 validation_config 和 file_count 配置
        config = validation_rules.get("validation_config", {})
        file_count_config = config.get("file_count", {})
        logger.info(
            f"[文件校验] 规则配置: rule_code={rule_code}, "
            f"file_count={file_count_config}, "
            f"uploaded_files_count={len(uploaded_files)}"
        )
        result = validate_files_against_rules(uploaded_files, validation_rules)
        return result
    except Exception as e:
        logger.error(f"[文件校验] 执行校验时发生异常: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"文件校验执行失败: {str(e)}"
        }

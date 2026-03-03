"""转换辅助函数模块

包含文件模式扩展、名称翻译、复杂度检查等转换功能。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# 所有支持的文件格式（保存规则时扩展 file_pattern）：Excel + CSV
FILE_PATTERN_EXTENSIONS = (".xlsx", ".xls", ".xlsm", ".xlsb", ".csv")


def _expand_file_patterns(pattern: str) -> list[str]:
    """如果是 Excel 或 CSV 格式的 pattern，扩展为所有支持格式并返回列表"""
    pattern_lower = pattern.lower()
    for ext in FILE_PATTERN_EXTENSIONS:
        if pattern_lower.endswith(ext):
            base = pattern[: -len(ext)]
            return [base + e for e in FILE_PATTERN_EXTENSIONS]
    return [pattern]


def _translate_rule_name_to_english(rule_name_cn: str) -> str:
    """将中文规则名称翻译成英文，用作 type_key 和文件名。

    使用 pypinyin 将中文转为拼音，避免使用 LLM。
    返回格式：小写字母和下划线，例如：direct_sales_reconciliation
    """
    try:
        from pypinyin import pinyin, Style

        # 获取拼音（首字母模式更简洁）
        pinyin_list = pinyin(rule_name_cn, style=Style.NORMAL)

        # 将拼音转为下划线分隔的英文
        pinyin_words = [py[0] for py in pinyin_list if py[0]]  # 每个汉字的拼音
        type_key = "_".join(pinyin_words).lower()

        # 清理结果（只保留小写字母、数字和下划线）
        type_key = re.sub(r"[^a-z0-9_]", "_", type_key)
        type_key = re.sub(r"_+", "_", type_key)  # 多个下划线合并为一个
        type_key = type_key.strip("_")  # 去除首尾下划线

        # 确保以字母开头
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key

        # 如果转换失败或结果为空，使用默认方式
        if not type_key or len(type_key) < 3:
            type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
            if not type_key or type_key[0].isdigit():
                type_key = "rule_" + type_key

        logger.info(f"规则名称转换: {rule_name_cn} → {type_key}")
        return type_key

    except ImportError:
        logger.warning("pypinyin 库未安装，使用默认方式转换规则名称")
        # 降级方案：直接转换
        type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        return type_key

    except Exception as e:
        logger.warning(f"规则名称转换失败: {e}，使用默认方式")
        # 降级方案：直接转换
        type_key = re.sub(r"[^a-zA-Z0-9_]", "_", rule_name_cn.lower())
        if not type_key or type_key[0].isdigit():
            type_key = "rule_" + type_key
        return type_key


def quick_complexity_check(uploaded_files: list) -> str:
    """快速检查文件复杂度

    Returns:
        "simple": 标准场景（2个文件，标准格式）
        "medium": 中等复杂（多sheet或可能有格式问题）
        "complex": 复杂场景（多文件配对、确定有格式问题）
    """
    if not uploaded_files:
        return "simple"

    file_count = len(uploaded_files)

    # 快速判断（原版阈值：>2→complex，==1→medium）
    if file_count > 2:
        return "complex"
    elif file_count == 1:
        return "medium"  # 单文件可能需要拆分或识别
    else:
        # 2个文件，检查是否都是标准格式（简单启发式）
        return "simple"


def _fallback_classify_sheets_by_name(sheets: list) -> dict:
    """降级策略：根据sheet名称简单判断类型。

    输入：sheets 来自 read_excel_sheets，每个元素为 {sheet_name, columns, row_count, sample_data, ...}
    返回：{sheet_name: {type, confidence, reason}}，与 _classify_sheets_with_llm 期望一致
    """
    result = {}

    business_keywords = ["订单", "销售", "交易", "业务", "商品", "order", "sales", "transaction"]
    finance_keywords = ["财务", "账单", "流水", "发票", "finance", "bill", "invoice", "account"]
    summary_keywords = ["汇总", "统计", "总结", "summary", "total"]

    for sheet in sheets:
        if "error" in sheet:
            continue

        sheet_name = sheet.get("sheet_name", "").lower()

        # 判断类型
        if any(kw in sheet_name for kw in business_keywords):
            result[sheet["sheet_name"]] = {"type": "business", "confidence": 0.6, "reason": "根据sheet名称判断"}
        elif any(kw in sheet_name for kw in finance_keywords):
            result[sheet["sheet_name"]] = {"type": "finance", "confidence": 0.6, "reason": "根据sheet名称判断"}
        elif any(kw in sheet_name for kw in summary_keywords):
            result[sheet["sheet_name"]] = {"type": "summary", "confidence": 0.6, "reason": "根据sheet名称判断"}
        else:
            result[sheet["sheet_name"]] = {"type": "other", "confidence": 0.3, "reason": "无法识别"}

    logger.info(f"使用降级策略分类了{len(result)}个sheet")
    return result


def extract_sample_rows(file_path: str, num_rows: int = 3) -> list[dict]:
    """从文件中提取样例数据行

    Args:
        file_path: 文件路径
        num_rows: 要提取的行数（默认 3 行）

    Returns:
        样例数据行列表（每行是一个字典，key 为列名），NaN 填充为空字符串
    """
    try:
        import pandas as pd
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            logger.warning(f"文件不存在: {path}")
            return []

        # 根据文件类型读取
        if path.suffix.lower() == ".csv":
            # CSV 文件需要自动检测编码（原版使用 chardet）
            import chardet

            with open(path, "rb") as f:
                raw_data = f.read()
                detected = chardet.detect(raw_data)
                encoding = detected.get("encoding", "utf-8")

            df = pd.read_csv(path, encoding=encoding, nrows=num_rows)
        else:
            # Excel 文件
            df = pd.read_excel(path, nrows=num_rows)

        # 转换为字典列表，fillna("") 处理空值
        return df.fillna("").to_dict(orient="records")

    except Exception as e:
        logger.error(f"提取样例数据失败 {file_path}: {e}")
        return []


async def delete_uploaded_files(uploaded_files: list, auth_token: str = "") -> None:
    """通过 MCP 工具删除已上传的文件（带用户验证）

    Args:
        uploaded_files: 文件列表，每个元素是字典 {"file_path": "...", "original_filename": "..."}
                       或者字符串（文件路径）
        auth_token: 用户认证 token
    """
    if not uploaded_files:
        return

    if not auth_token:
        logger.warning("删除文件失败：缺少 auth_token，无法验证用户身份")
        return

    # 提取文件路径列表
    file_paths = []
    for item in uploaded_files:
        if isinstance(item, dict):
            file_path = item.get("file_path", "")
        else:
            file_path = item
        
        if file_path:
            file_paths.append(file_path)

    if not file_paths:
        return

    try:
        from app.tools.mcp_client import call_mcp_tool

        result = await call_mcp_tool("file_delete", {
            "auth_token": auth_token,
            "file_paths": file_paths,
        })

        if result.get("success"):
            deleted_count = result.get("deleted_count", 0)
            logger.info(f"通过 MCP 删除了 {deleted_count} 个文件")

            # 记录删除失败的文件
            failed_files = result.get("failed_files", [])
            if failed_files:
                for failed in failed_files:
                    logger.warning(f"删除失败: {failed['file_path']} - {failed['error']}")
        else:
            error = result.get("error", "未知错误")
            logger.error(f"MCP 删除文件失败: {error}")

    except Exception as e:
        logger.error(f"调用 MCP 删除文件失败: {e}")


def _adjust_field_mappings_with_llm(
    current_mappings: dict[str, Any],
    user_instruction: str,
    analyses: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """使用 LLM 根据用户指令调整字段映射。支持 add/update/delete 操作和文件级别的控制。

    返回：(调整后的映射, 执行的操作列表)
    """
    from app.graphs.reconciliation.field_mapping_helpers import _apply_field_mapping_operations
    from app.utils.llm import get_llm

    # 构建当前映射的描述
    current_desc = []
    for source in ("business", "finance"):
        src_map = current_mappings.get(source, {})
        if src_map:
            label = "文件1" if source == "business" else "文件2"
            filename = ""
            for a in analyses:
                if a.get("guessed_source") == source:
                    filename = a.get("original_filename") or a.get("filename", "")
                    break
            current_desc.append(f"{label} ({filename}):")
        for role, col in src_map.items():
            if isinstance(col, list):
                col_str = ", ".join(col)
            else:
                col_str = str(col)
            current_desc.append(f"  {role}: {col_str}")

    current_mapping_str = "\n".join(current_desc)

    # 构建可用列名
    available_cols = []
    for a in analyses:
        filename = a.get("original_filename") or a.get("filename", "")
        cols = a.get("columns", [])
        available_cols.append(f"{filename}: {', '.join(cols[:20])}")

    available_cols_str = "\n".join(available_cols)

    # 增强的 prompt，支持结构化操作（原版完整规则 1-10）
    json_examples = """操作示例（返回此格式的operations数组）：
- {"action": "add", "target": "finance", "role": "status", "column": "订单状态", "description": "在财务文件添加status字段"}
- {"action": "update", "target": "business", "role": "order_id", "column": "新订单号", "description": "更新文件1的订单号映射"}
- {"action": "delete", "target": "business", "role": "status", "description": "删除文件1的status字段"}
- {"action": "delete_column", "target": "business", "role": "amount", "column": "pay_amt", "description": "仅删除文件1的amount字段中的pay_amt列别名，保留其他列"}
"""

    prompt = f"""你是一个字段映射调整助手。用户上传了两个文件，当前的字段映射如下：

{current_mapping_str}

可用的列名：
{available_cols_str}

用户的调整指令：
{user_instruction}

根据用户的指令，生成结构化的操作列表。用户可能会：
1. 只涉及一个文件的调整（如"文件1改为..."或"业务文件添加..."）
2. 同时涉及两个文件的调整（如"两个文件都添加status"）
3. 删除某个字段的列别名（如"去掉pay_amt"、"删除amount中的pay_amt"）⚠️ 重要：如果用户说"删除xxx"且xxx是字段中的某个列名（不是role名），应该使用 delete_column 而不是 delete
4. 删除整个字段（如"删除status字段"）
5. 修改字段映射（如"order_id改为xxx"）

严格按以下 JSON 格式返回，不要添加其他内容：
{{"operations": [操作对象数组]}}

{json_examples}

⚠️ 重要规则：
1. 只生成用户明确指示的操作（不要推断未提到的操作）
2. 如果用户说"文件1"或"业务文件"，target应为"business"
3. 如果用户说"文件2"或"财务文件"，target应为"finance"
4. 如果用户只指定一个文件，只为该文件生成操作
5. 如果用户说"两个文件都..."，为两个文件都生成操作
6. role必须是：order_id、amount、date、status之一（标准定义）
7. column可以是单个列名（如"订单号"）或列名列表（如["订单编号", "订单号"]）
8. 不要生成删除order_id、amount、date整个字段的操作（这些是必需的）
9. ⭐️ 关键区分：
   - 如果用户想删除一个 **role本身**（如"删除status"）→ 使用 action: "delete"，不指定column
   - 如果用户想删除该role下的 **某个列别名**（如"删除pay_amt"）→ 使用 action: "delete_column"，指定column
   - 例：当前amount有["pay_amt", "金额"]两个列，用户说"去掉pay_amt" → delete_column with column="pay_amt"
10. ⭐️ delete_column 严格匹配：每个 delete_column 的 column 必须与用户说的列名**完全一致**。
   - 用户说"去掉喜马订单号、订单号、合单订单号、退款订单号"时，只生成这4个 delete_column，不要多删。
   - "第三方订单号"与"订单号"是不同列，用户没说去掉"第三方订单号"就绝不能删除它。
   - 不要因列名相似或同属某类而推断删除用户未提及的列。
"""

    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()

        # 提取 JSON
        if "```" in content:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)

        parsed = json.loads(content)
        operations = parsed.get("operations", [])

        logger.info(f"LLM 生成的操作: {operations}")

        # 应用操作
        new_mappings = _apply_field_mapping_operations(current_mappings, operations)

        logger.info(f"字段映射调整完成: {new_mappings}")
        return new_mappings, operations

    except Exception as e:
        logger.warning(f"LLM 字段映射调整失败: {e}")
        return current_mappings, []


async def invoke_intelligent_analyzer(uploaded_files: list, complexity_level: str) -> dict:
    """调用智能文件分析器（基于SKILL.md策略）"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info(f"开始智能文件分析，复杂度: {complexity_level}, 文件数: {len(uploaded_files)}")

    try:
        complexity_result = await call_mcp_tool("detect_file_complexity", {"files": uploaded_files})

        if not complexity_result.get("success"):
            logger.error(f"复杂度检测失败: {complexity_result.get('error')}")
            return await _fallback_to_simple_analysis(uploaded_files)

        complexity_info = complexity_result

        if complexity_info.get("file_count", 0) > 2:
            return await _smart_file_pairing(uploaded_files, complexity_info)

        if complexity_info.get("file_count", 0) == 1:
            if complexity_info.get("multi_sheet"):
                return await _analyze_multi_sheet_files(uploaded_files, complexity_info)
            return await _analyze_single_file(uploaded_files[0], complexity_info)

        if complexity_info.get("file_count", 0) == 2 and complexity_info.get("multi_sheet"):
            return await _fallback_to_simple_analysis(uploaded_files)

        if complexity_info.get("non_standard"):
            return await _analyze_with_format_normalization(uploaded_files, complexity_info)

        return await _fallback_to_simple_analysis(uploaded_files)

    except Exception as e:
        logger.error(f"智能分析失败: {e}", exc_info=True)
        return await _fallback_to_simple_analysis(uploaded_files)


async def _analyze_multi_sheet_files(uploaded_files: list, complexity_info: dict) -> dict:
    """分析包含多sheet的Excel文件"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info("处理多sheet文件场景")

    all_analyses = []
    warnings = []

    for multi_sheet_file in complexity_info.get("multi_sheet_files", []):
        file_path = multi_sheet_file["file_path"]

        sheets_result = await call_mcp_tool("read_excel_sheets", {
            "file_path": file_path,
            "sample_rows": 5
        })

        if not sheets_result.get("success"):
            warnings.append(f"无法读取文件 {file_path} 的sheets")
            continue

        sheets = sheets_result.get("sheets", [])
        sheet_types = await _classify_sheets_with_llm(sheets, file_path)

        for sheet_info in sheets:
            if "error" in sheet_info:
                continue

            sheet_name = sheet_info["sheet_name"]
            guessed_type = sheet_types.get(sheet_name, {}).get("type", "unknown")
            confidence = sheet_types.get(sheet_name, {}).get("confidence", 0.5)

            if guessed_type in ["business", "finance"]:
                all_analyses.append({
                    "filename": f"{file_path} - {sheet_name}",
                    "original_filename": f"{multi_sheet_file.get('original_filename', file_path)} - {sheet_name}",
                    "file_path": file_path,
                    "sheet_name": sheet_name,
                    "columns": sheet_info["columns"],
                    "row_count": sheet_info["row_count"],
                    "sample_data": sheet_info["sample_data"],
                    "guessed_source": guessed_type,
                    "confidence": confidence,
                    "processing_notes": f"从多sheet文件中识别（置信度: {int(confidence*100)}%）"
                })
            elif guessed_type == "summary":
                warnings.append(f"{sheet_name}: 识别为汇总表，已跳过")
            else:
                warnings.append(f"{sheet_name}: 类型未知，已跳过")

    has_business = any(a["guessed_source"] == "business" for a in all_analyses)
    has_finance = any(a["guessed_source"] == "finance" for a in all_analyses)

    recommendations = {
        "success": has_business and has_finance,
        "message": ""
    }

    if has_business and has_finance:
        recommendations["message"] = "✅ 成功识别出两个文件"
    elif has_business:
        recommendations["message"] = "⚠️ 只识别到文件1，请补充上传文件2"
    elif has_finance:
        recommendations["message"] = "⚠️ 只识别到文件2，请补充上传文件1"
    else:
        recommendations["message"] = "❌ 未识别到有效的对账数据"

    return {
        "success": True,
        "analyses": all_analyses,
        "recommendations": recommendations,
        "warnings": warnings
    }


async def _classify_sheets_with_llm(sheets: list, file_path: str) -> dict:
    """使用LLM分类sheet类型"""
    from app.utils.llm import get_llm
    import json

    MAX_SHEETS_PER_CALL = 15
    valid_sheets = [s for s in sheets if "error" not in s]

    if len(valid_sheets) > MAX_SHEETS_PER_CALL:
        logger.warning(f"检测到{len(valid_sheets)}个sheet，过多！只分析前{MAX_SHEETS_PER_CALL}个")
        valid_sheets = sorted(valid_sheets, key=lambda s: s.get("row_count", 0), reverse=True)
        valid_sheets = valid_sheets[:MAX_SHEETS_PER_CALL]
        sheets = valid_sheets

    sheets_desc = []
    for sheet in sheets:
        if "error" in sheet:
            continue
        cols_str = ", ".join(sheet.get("columns", [])[:15])
        sheets_desc.append(
            f"Sheet名称: {sheet['sheet_name']}\n"
            f"  列名: {cols_str}\n"
            f"  行数: {sheet.get('row_count', 0)}"
        )

    prompt = f"""你是财务数据分析专家。分析以下Excel文件的sheet，判断每个sheet的数据类型。

文件: {file_path}

Sheet信息（共{len(sheets_desc)}个）：
{chr(10).join(sheets_desc)}

类型定义：
- business: 业务数据（订单、销售、交易等，包含订单号、商品、金额等）
- finance: 财务数据（账单、流水、发票等，包含财务科目、收支等）
- summary: 汇总表（统计、总结类，不包含明细数据）
- other: 其他（说明、模板、空表等）

严格按以下JSON格式回复：
{{"results": [{{"sheet_name": "...", "type": "business|finance|summary|other", "confidence": 0.85, "reason": "..."}}]}}
"""

    try:
        llm = get_llm(temperature=0.1)

        import asyncio
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(llm.invoke, prompt),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error(f"LLM分类sheet超时（30秒），sheet数: {len(sheets_desc)}")
            return _fallback_classify_sheets_by_name(sheets)

        content = resp.content.strip()

        if "```" in content:
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)

        parsed = json.loads(content)
        results = parsed.get("results", [])

        return {
            r["sheet_name"]: {
                "type": r["type"],
                "confidence": r.get("confidence", 0.5),
                "reason": r.get("reason", "")
            }
            for r in results
        }

    except Exception as e:
        logger.error(f"LLM分类sheet失败: {e}", exc_info=True)
        return _fallback_classify_sheets_by_name(sheets)


async def _smart_file_pairing(uploaded_files: list, complexity_info: dict) -> dict:
    """智能文件配对（>2个文件）"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info(f"智能配对场景，共{len(uploaded_files)}个文件")

    file_paths = [f.get("file_path") for f in uploaded_files]
    original_filenames_map = {f.get("file_path"): f.get("original_filename") for f in uploaded_files if f.get("original_filename")}

    result = await call_mcp_tool("analyze_files", {
        "file_paths": file_paths,
        "original_filenames": original_filenames_map
    })

    if not result.get("success"):
        return {
            "success": False,
            "error": "文件分析失败",
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    analyses = result.get("analyses", [])

    business_files = [a for a in analyses if a.get("guessed_source") == "business"]
    finance_files = [a for a in analyses if a.get("guessed_source") == "finance"]

    if not business_files or not finance_files:
        return {
            "success": False,
            "analyses": analyses,
            "recommendations": {
                "message": "❌ 未能识别出有效的文件配对"
            },
            "warnings": [f"文件1: {len(business_files)}个, 文件2: {len(finance_files)}个"]
        }

    selected_business = business_files[0]
    selected_finance = finance_files[0]

    recommended_pair = {
        "business": selected_business,
        "finance": selected_finance,
        "confidence": 0.85,
        "reason": "基于文件类型自动配对"
    }

    selected_filenames = {selected_business['original_filename'], selected_finance['original_filename']}
    excluded_files = [
        a['original_filename']
        for a in analyses
        if a.get('original_filename') not in selected_filenames
    ]

    warning_msgs = [f"检测到{len(uploaded_files)}个文件，已自动选择最佳配对"]
    if excluded_files:
        warning_msgs.append(f"已排除: {', '.join(excluded_files)}")

    return {
        "success": True,
        "analyses": [selected_business, selected_finance],
        "recommendations": {
            "pairing": recommended_pair,
            "message": f"✅ 推荐配对: {selected_business['original_filename']} ↔ {selected_finance['original_filename']}"
        },
        "warnings": warning_msgs
    }


async def _analyze_single_file(uploaded_file: dict, complexity_info: dict) -> dict:
    """分析单个文件"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info("单文件场景，尝试识别类型")

    file_path = uploaded_file.get("file_path")
    result = await call_mcp_tool("analyze_files", {
        "file_paths": [file_path],
        "original_filenames": {file_path: uploaded_file.get("original_filename", "")}
    })

    if not result.get("success"):
        return {
            "success": False,
            "error": "文件分析失败",
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    analyses = result.get("analyses", [])
    if not analyses:
        return {
            "success": False,
            "error": "文件为空",
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    sample_columns = ["订单号", "日期", "金额", "状态"]
    sample_rows = [
        ["20240101", "2024-01-01", "1000.00", "已完成"],
        ["20240102", "2024-01-02", "2000.00", "待确认"],
        ["20240103", "2024-01-03", "1500.00", "处理中"]
    ]

    table_html = ['<table class="text-sm min-w-max">']
    table_html.append('  <thead>')
    table_html.append('    <tr class="bg-gray-50">')
    for col in sample_columns:
        table_html.append(f'      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">{col}</th>')
    table_html.append('    </tr>')
    table_html.append('  </thead>')
    table_html.append('  <tbody>')
    for row in sample_rows:
        table_html.append('    <tr>')
        for cell in row:
            table_html.append(f'      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">{cell}</td>')
        table_html.append('    </tr>')
    table_html.append('  </tbody>')
    table_html.append('</table>')

    error_message = "⚠️ 请重新上传两个文件，文件数据样例如下：\n" + "\n".join(table_html)

    return {
        "success": False,
        "analyses": analyses,
        "recommendations": {
            "message": error_message
        },
        "warnings": []
    }


async def _analyze_with_format_normalization(uploaded_files: list, complexity_info: dict) -> dict:
    """处理非标准格式文件"""
    return await _fallback_to_simple_analysis(uploaded_files)


async def _fallback_to_simple_analysis(uploaded_files: list) -> dict:
    """降级到简单分析"""
    from app.tools.mcp_client import call_mcp_tool

    logger.info("降级到简单文件分析")

    file_paths = [f.get("file_path") for f in uploaded_files]
    original_filenames_map = {f.get("file_path"): f.get("original_filename") for f in uploaded_files if f.get("original_filename")}

    result = await call_mcp_tool("analyze_files", {
        "file_paths": file_paths,
        "original_filenames": original_filenames_map
    })

    if not result.get("success"):
        return {
            "success": False,
            "error": result.get("error", "文件分析失败"),
            "analyses": [],
            "recommendations": {},
            "warnings": []
        }

    return {
        "success": True,
        "analyses": result.get("analyses", []),
        "recommendations": {},
        "warnings": []
    }


__all__ = [
    "FILE_PATTERN_EXTENSIONS",
    "_expand_file_patterns",
    "_translate_rule_name_to_english",
    "quick_complexity_check",
    "_fallback_classify_sheets_by_name",
    "extract_sample_rows",
    "delete_uploaded_files",
    "_adjust_field_mappings_with_llm",
    "invoke_intelligent_analyzer",
]

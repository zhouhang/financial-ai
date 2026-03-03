"""错误消息辅助函数模块

包含验证错误、文件错误、格式错误等消息构建功能。
"""

from __future__ import annotations

import re


def build_validation_error_message(
    validation_result,  # FileValidationResult 对象
    file_paths: list[str],
) -> str:
    """构建文件格式验证失败的错误消息

    Args:
        validation_result: FileValidationResult 对象（来自 file_validation.py）
        file_paths: 文件路径列表

    Returns:
        格式化的错误消息（Markdown 格式）
    """
    msg_parts = ["❌ **文件格式验证失败**\n"]

    # 1. 错误原因
    msg_parts.append(f"**原因：** {validation_result.reason}\n")

    # 2. 要求说明
    msg_parts.append("**要求：**")
    msg_parts.append("- 上传恰好 **2个 Excel 文件**（.xlsx 或 .xls）")
    msg_parts.append("- 每个文件只包含 **1个 sheet**")
    msg_parts.append("- 第一行是 **表头**，其他行是 **数据**\n")

    # 3. 数据格式样例（使用 HTML 表格）
    msg_parts.append("**正确的数据格式样例：**\n")

    # 构造示例表格（不从实际文件读取）
    sample_columns = ["订单号", "日期", "金额", "状态"]
    sample_rows = [
        ["20240101", "2024-01-01", "1000.00", "已完成"],
        ["20240102", "2024-01-02", "2000.00", "待确认"],
        ["20240103", "2024-01-03", "1500.00", "处理中"],
    ]

    # 构建 HTML 表格（参照 MessageBubble.tsx 的格式）
    table_html = ['<table class="text-sm min-w-max">']

    # 表头
    table_html.append("  <thead>")
    table_html.append('    <tr class="bg-gray-50">')
    for col in sample_columns:
        table_html.append(
            f'      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">{col}</th>'
        )
    table_html.append("    </tr>")
    table_html.append("  </thead>")

    # 数据行
    table_html.append("  <tbody>")
    for row in sample_rows:
        table_html.append("    <tr>")
        for cell in row:
            table_html.append(
                f'      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">{cell}</td>'
            )
        table_html.append("    </tr>")
    table_html.append("  </tbody>")
    table_html.append("</table>")

    msg_parts.append("\n".join(table_html))

    msg_parts.append("\n**请重新上传符合要求的文件**")

    return "\n".join(msg_parts)


def build_single_file_error_message() -> str:
    """构建单文件上传错误消息（问题1）

    Returns:
        格式化的错误消息（包含 HTML 表格）
    """
    msg_parts = ["⚠️ 只有一个文件，无法完成对账，请重新上传两个文件，文件数据样例如下：\n"]

    # 构造示例表格
    sample_columns = ["订单号", "日期", "金额", "状态"]
    sample_rows = [
        ["20240101", "2024-01-01", "1000.00", "已完成"],
        ["20240102", "2024-01-02", "2000.00", "待确认"],
        ["20240103", "2024-01-03", "1500.00", "处理中"],
    ]

    # 构建 HTML 表格
    table_html = ['<table class="text-sm min-w-max">']

    # 表头
    table_html.append("  <thead>")
    table_html.append('    <tr class="bg-gray-50">')
    for col in sample_columns:
        table_html.append(
            f'      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">{col}</th>'
        )
    table_html.append("    </tr>")
    table_html.append("  </thead>")

    # 数据行
    table_html.append("  <tbody>")
    for row in sample_rows:
        table_html.append("    <tr>")
        for cell in row:
            table_html.append(
                f'      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">{cell}</td>'
            )
        table_html.append("    </tr>")
    table_html.append("  </tbody>")
    table_html.append("</table>")

    msg_parts.append("\n".join(table_html))
    return "\n".join(msg_parts)


def build_format_error_message(
    validation_result,  # FileValidationResult 对象
    file_paths: list[str],
    original_filenames_map: dict[str, str],
) -> str:
    """构建文件格式错误消息（问题2和问题3）

    Args:
        validation_result: FileValidationResult 对象（来自 file_validation.py）
        file_paths: 文件路径列表
        original_filenames_map: 文件路径到原始文件名的映射

    Returns:
        格式化的错误消息（包含 HTML 表格）
    """
    msg_parts = []

    # 从 validation_result.reason 中提取文件名和错误类型
    reason = validation_result.reason

    # 提取文件名（多种格式兼容）
    filename = None

    # 尝试从 reason 中提取文件名（格式1：文件 'filename' ...）
    filename_match = re.search(r"文件 '([^']+)'", reason)
    if filename_match:
        filename = filename_match.group(1)
    else:
        # 尝试从 reason 中提取文件路径（格式2：文件不存在: /uploads/.../filename）
        path_match = re.search(r"/uploads/.+/([^/]+)$", reason)
        if path_match:
            # 从路径中提取文件名
            filename = path_match.group(1)
            # 尝试从 original_filenames_map 中获取原始文件名
            for file_path, original_name in original_filenames_map.items():
                if filename in file_path:
                    filename = original_name
                    break

    # 如果仍然没有文件名，尝试从 validation_result.details 中获取
    if not filename and validation_result.details:
        for detail in validation_result.details:
            if "filename" in detail:
                filename = detail["filename"]
                # 尝试映射到原始文件名
                for file_path, original_name in original_filenames_map.items():
                    if filename in file_path or detail.get("filepath", "") in file_path:
                        filename = original_name
                        break
                break

    # 最后的降级方案
    if not filename:
        filename = "某个文件"

    # 根据错误类型生成不同的提示消息
    if "包含" in reason and "sheet" in reason:
        # 多 sheet 错误
        msg_parts.append(
            f"⚠️ 检测到文件 {filename} 有多个sheet，每个文件只能有一个sheet，请重新上传两个文件，文件数据样例如下：\n"
        )
    else:
        # 格式错误（缺少表头、没有数据行、文件不存在等）
        msg_parts.append(
            f"⚠️ 检测到文件 {filename} 数据格式不符合规范，请重新上传两个文件，文件数据样例如下：\n"
        )

    # 构造示例表格
    sample_columns = ["订单号", "日期", "金额", "状态"]
    sample_rows = [
        ["20240101", "2024-01-01", "1000.00", "已完成"],
        ["20240102", "2024-01-02", "2000.00", "待确认"],
        ["20240103", "2024-01-03", "1500.00", "处理中"],
    ]

    # 构建 HTML 表格
    table_html = ['<table class="text-sm min-w-max">']

    # 表头
    table_html.append("  <thead>")
    table_html.append('    <tr class="bg-gray-50">')
    for col in sample_columns:
        table_html.append(
            f'      <th class="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-r border-gray-200 last:border-r-0">{col}</th>'
        )
    table_html.append("    </tr>")
    table_html.append("  </thead>")

    # 数据行
    table_html.append("  <tbody>")
    for row in sample_rows:
        table_html.append("    <tr>")
        for cell in row:
            table_html.append(
                f'      <td class="px-3 py-2 text-gray-800 whitespace-nowrap border-r border-gray-100 last:border-r-0">{cell}</td>'
            )
        table_html.append("    </tr>")
    table_html.append("  </tbody>")
    table_html.append("</table>")

    msg_parts.append("\n".join(table_html))
    return "\n".join(msg_parts)


__all__ = [
    "build_validation_error_message",
    "build_single_file_error_message",
    "build_format_error_message",
]

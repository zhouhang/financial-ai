"""文件分析工具 – 读取 Excel/CSV 头部和示例行，使用 LLM 智能判断文件类型。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import chardet
import pandas as pd

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def analyse_file(file_path: str) -> dict[str, Any]:
    """返回文件的列名、行数和一些示例行。

    注意：此函数不调用 LLM，guessed_source 留空。
    LLM 判断由 analyse_files_with_llm() 统一处理。
    """
    p = Path(file_path)
    ext = p.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return {"filename": p.name, "error": f"不支持的扩展名: {ext}"}

    try:
        df = _load_df(file_path)
    except Exception as e:
        return {"filename": p.name, "error": str(e)}

    sample = df.head(5).fillna("").to_dict(orient="records")
    safe_sample = []
    for row in sample:
        safe_sample.append({k: str(v) for k, v in row.items()})

    return {
        "filename": p.name,
        "columns": list(df.columns),
        "row_count": len(df),
        "sample_data": safe_sample,
        "guessed_source": None,
    }


def analyse_files_with_llm(
    analyses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """使用 LLM 智能判断每个文件属于 business 还是 finance。

    接收 analyse_file() 的结果列表，为每个文件填充 guessed_source 字段。
    """
    from app.utils.llm import get_llm

    if not analyses:
        return analyses

    # 构建 prompt
    files_desc = []
    for i, a in enumerate(analyses):
        if "error" in a:
            continue
        cols_str = ", ".join(a.get("columns", [])[:20])
        sample_str = ""
        for row in a.get("sample_data", [])[:2]:
            sample_str += "    " + str(row) + "\n"
        files_desc.append(
            f"文件{i+1}: {a['filename']}\n"
            f"  列名: {cols_str}\n"
            f"  行数: {a.get('row_count', 0)}\n"
            f"  示例数据:\n{sample_str}"
        )

    if not files_desc:
        return analyses

    prompt = (
        "你是一个财务数据分析专家。以下是用户上传的文件信息，"
        "请判断每个文件属于哪种数据源类型。\n\n"
        "类型说明：\n"
        "- business: 业务数据（如订单流水、销售记录、交易明细等，通常包含订单号、商品、销售额等字段）\n"
        "- finance: 财务数据（如财务账单、对账单、银行流水、发票等，通常包含财务科目、借贷金额等字段）\n\n"
        + "\n".join(files_desc)
        + "\n\n请严格按以下 JSON 格式回复，不要添加其他内容：\n"
        '{"results": [{"filename": "文件名", "source": "business 或 finance", "reason": "简短理由"}]}'
    )

    try:
        llm = get_llm(temperature=0.1)
        resp = llm.invoke(prompt)
        content = resp.content.strip()

        # 提取 JSON
        if "```" in content:
            import re
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
            if m:
                content = m.group(1)

        parsed = json.loads(content)
        results = parsed.get("results", [])

        # 将结果写回 analyses
        result_map = {r["filename"]: r["source"] for r in results}
        for a in analyses:
            if "error" not in a:
                a["guessed_source"] = result_map.get(a["filename"])

    except Exception as e:
        logger.warning(f"LLM 文件类型判断失败，将留空 guessed_source: {e}")

    return analyses


def _load_df(file_path: str) -> pd.DataFrame:
    if file_path.endswith(".csv"):
        raw = Path(file_path).read_bytes()
        det = chardet.detect(raw[:10000])
        enc = det.get("encoding") or "utf-8"
        return pd.read_csv(file_path, encoding=enc, index_col=False)
    return pd.read_excel(file_path, index_col=False)

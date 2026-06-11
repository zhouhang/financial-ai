"""差异消化服务：调用 recon_diff_digestion MCP 工具，对已有对账 run 的未关闭差异做重判消化。

采集刷新决策：
  本期跳过采集刷新——worker 的 resolve 分支在日报投递后的当天触发，数据已由常规
  schedule job 采集完成。如果有必要，上游可在入队 resolve job 之前先触发一次采集。
  此处直接对 run 当时的累积数据做消化，失败不阻断。
"""

from __future__ import annotations

import logging
from typing import Any

from tools.mcp_client import call_mcp_tool

logger = logging.getLogger(__name__)


async def run_diff_digestion(
    *,
    auth_token: str,
    run_id: str,
    biz_date: str,
) -> dict[str, Any]:
    """对 run_id 指向的执行记录做差异消化（不重跑全量对账）。

    Returns:
        {
            "ok": bool,
            "summary": dict,          # MCP 工具原始返回
            "collection_refreshed": bool,  # 本期固定为 False（采集刷新已跳过）
            "error": str,
        }
    """
    run_id = str(run_id or "").strip()
    if not run_id:
        return {"ok": False, "summary": {}, "collection_refreshed": False, "error": "run_id 不能为空"}

    # 采集刷新：本期跳过，直接用当前累积数据消化
    logger.warning(
        "[diff_digestion] 未刷新采集，用当前累积数据消化 run_id=%s biz_date=%s",
        run_id,
        biz_date,
    )
    collection_refreshed = False

    # 调用 MCP 工具
    result = await call_mcp_tool(
        "recon_diff_digestion",
        {"worker_token": auth_token, "run_id": run_id},
    )

    ok = bool(result.get("success"))
    error = str(result.get("error") or "") if not ok else ""

    if ok:
        logger.info(
            "[diff_digestion] 消化完成 run_id=%s resolved=%s reclassified=%s kept=%s open_counts=%s",
            run_id,
            result.get("resolved"),
            result.get("reclassified"),
            result.get("kept"),
            result.get("open_counts"),
        )
    else:
        logger.error(
            "[diff_digestion] 消化失败 run_id=%s error=%s",
            run_id,
            error,
        )

    return {
        "ok": ok,
        "summary": result,
        "collection_refreshed": collection_refreshed,
        "error": error,
    }

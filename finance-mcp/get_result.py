#!/usr/bin/env python3
"""
获取对账结果
"""
import asyncio
import json
import time
from reconciliation.mcp_server.tools import handle_tool_call


async def get_results():
    """获取对账结果"""
    # 列出所有任务
    result = await handle_tool_call("reconciliation_list_tasks", {})
    
    print("=" * 80)
    print("【所有对账任务列表】")
    print("=" * 80)
    tasks = result.get("tasks", [])
    if not tasks:
        print("暂无任务")
        return
    
    for task in tasks:
        print(f"- {task['task_id']}: {task['status']}")
    
    # 获取最新任务的结果
    task_id = tasks[0]["task_id"]
    print(f"\n获取任务 {task_id} 的详细结果...")
    
    # 等待任务完成
    for i in range(60):
        status = await handle_tool_call("reconciliation_status", {"task_id": task_id})
        status_val = status.get("status")
        print(f"[{i+1}s] 任务状态: {status_val}")
        
        if status_val == "completed":
            print(f"\n✓ 对账任务完成！\n")
            break
        time.sleep(1)
    
    # 获取结果
    result = await handle_tool_call("reconciliation_result", {"task_id": task_id})
    
    print(json.dumps(result, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    asyncio.run(get_results())

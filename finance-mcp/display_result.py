#!/usr/bin/env python3
"""
获取对账结果展示
"""
import asyncio
import json
import sys
from pathlib import Path

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from reconciliation.mcp_server.task_manager import TaskManager


async def display_results():
    """获取并展示对账结果"""
    task_manager = TaskManager()
    
    # 获取第一个任务（最后创建的）
    tasks = await task_manager.list_tasks()
    
    if not tasks:
        print("没有找到对账任务")
        return
    
    task_id = tasks[0]["task_id"]
    print("=" * 80)
    print(f"【获取对账结果】任务ID: {task_id}")
    print("=" * 80)
    
    # 获取任务结果
    result = await task_manager.get_task_result(task_id)
    
    print("\n【完整对账结果】")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 如果有对账摘要，展示统计信息
    if "reconciliation_summary" in result:
        summary = result["reconciliation_summary"]
        print("\n" + "=" * 80)
        print("【对账统计总结】")
        print("=" * 80)
        print(f"✓ 总记录数: {summary.get('total_records', 0)}")
        print(f"✓ 完全匹配记录数: {summary.get('matched_records', 0)}")
        print(f"✓ 未匹配记录数: {summary.get('unmatched_records', 0)}")
        print(f"✗ 对账问题数: {summary.get('issues_count', 0)}")
        print(f"  - 匹配率: {summary.get('match_rate', 0):.2%}")
    
    # 展示对账问题
    if "issues" in result and result["issues"]:
        print("\n" + "=" * 80)
        print("【对账问题详情】")
        print("=" * 80)
        
        issues_by_type = {}
        for issue in result["issues"]:
            issue_type = issue.get("issue_type", "unknown")
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        for issue_type, issues_list in issues_by_type.items():
            print(f"\n【{issue_type}】共 {len(issues_list)} 条")
            for idx, issue in enumerate(issues_list[:5], 1):
                print(f"  {idx}. {issue.get('detail', issue.get('order_id', 'N/A'))}")
            if len(issues_list) > 5:
                print(f"  ... 还有 {len(issues_list) - 5} 条")


if __name__ == "__main__":
    asyncio.run(display_results())

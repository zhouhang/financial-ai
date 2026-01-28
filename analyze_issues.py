#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
分析对账问题明细
"""
import sys
import asyncio
sys.path.insert(0, '/Users/kevin/workspace/financial-ai/finance-mcp')

from reconciliation.mcp_server.tools import _reconciliation_start, _reconciliation_result
import json

async def main():
    print("="*80)
    print("【对账问题明细分析】")
    print("="*80)

    files = [
        '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/官网.xlsx',
        '/Users/kevin/workspace/financial-ai/finance-mcp/reconciliation/test_data/合单.xlsx'
    ]

    try:
        # 1. 启动对账
        args = {
            "reconciliation_type": "直销对账",
            "files": files
        }
        start_result = await _reconciliation_start(args)
        task_id = start_result.get('task_id')
        
        # 2. 等待完成
        for i in range(60):
            await asyncio.sleep(1)
            result_args = {"task_id": task_id}
            result = await _reconciliation_result(result_args)
            
            if result.get('status') == 'completed':
                break
        
        # 3. 分析问题
        issues = result.get('issues', [])
        
        print(f"\n【问题总数】: {len(issues)}")
        
        # 按问题类型分类
        issue_types = {}
        for issue in issues:
            issue_type = issue.get('issue_type')
            if issue_type not in issue_types:
                issue_types[issue_type] = []
            issue_types[issue_type].append(issue)
        
        # 显示各类型的详细统计
        print(f"\n【问题类型统计】")
        for issue_type in sorted(issue_types.keys()):
            issues_of_type = issue_types[issue_type]
            count = len(issues_of_type)
            print(f"\n  [{issue_type}] - {count} 笔")
            
            # 按订单号前缀统计
            prefix_counts = {}
            for issue in issues_of_type:
                order_id = issue.get('order_id', '')
                prefix = order_id[:3] if order_id else 'unknown'
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            
            print(f"    按订单号前缀统计:")
            for prefix in sorted(prefix_counts.keys()):
                print(f"      {prefix}: {prefix_counts[prefix]}")
            
            # 显示该类型的前3个样本
            print(f"    样本 (前3笔):")
            for i, issue in enumerate(issues_of_type[:3]):
                print(f"      [{i+1}] {issue.get('order_id')}: {issue.get('detail')}")
        
        # 特殊统计
        print(f"\n【特殊统计】")
        
        # L订单统计
        l_issues = [i for i in issues if i.get('order_id', '').startswith('L')]
        print(f"  L开头的订单总数: {len(l_issues)}")
        if l_issues:
            l_by_type = {}
            for issue in l_issues:
                t = issue.get('issue_type')
                l_by_type[t] = l_by_type.get(t, 0) + 1
            print(f"    按问题类型:")
            for t in sorted(l_by_type.keys()):
                print(f"      {t}: {l_by_type[t]}")
        
        # 104订单统计
        order_104_issues = [i for i in issues if i.get('order_id', '').startswith('104')]
        print(f"\n  104开头的订单总数: {len(order_104_issues)}")
        if order_104_issues:
            o104_by_type = {}
            for issue in order_104_issues:
                t = issue.get('issue_type')
                o104_by_type[t] = o104_by_type.get(t, 0) + 1
            print(f"    按问题类型:")
            for t in sorted(o104_by_type.keys()):
                print(f"      {t}: {o104_by_type[t]}")
        
        # 缺失订单详情
        print(f"\n【缺失订单详情】")
        
        if 'missing_in_finance' in issue_types:
            mif = issue_types['missing_in_finance']
            print(f"  missing_in_finance (业务有但财务无): {len(mif)}")
            
            # 按金额分析
            amounts = [float(issue.get('business_value', 0)) for issue in mif if issue.get('business_value')]
            if amounts:
                print(f"    金额统计:")
                print(f"      最小: {min(amounts):.2f}")
                print(f"      最大: {max(amounts):.2f}")
                print(f"      平均: {sum(amounts)/len(amounts):.2f}")
                print(f"      总计: {sum(amounts):.2f}")
        
        if 'missing_in_business' in issue_types:
            mib = issue_types['missing_in_business']
            print(f"\n  missing_in_business (财务有但业务无): {len(mib)}")
            
            # 按金额分析
            amounts = [float(issue.get('finance_value', 0)) for issue in mib if issue.get('finance_value')]
            if amounts:
                print(f"    金额统计:")
                print(f"      最小: {min(amounts):.2f}")
                print(f"      最大: {max(amounts):.2f}")
                print(f"      平均: {sum(amounts)/len(amounts):.2f}")
                print(f"      总计: {sum(amounts):.2f}")
        
        print(f"\n✓ 分析完成")

    except Exception as e:
        print(f"✗ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())

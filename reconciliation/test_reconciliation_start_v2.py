"""
测试优化后的 reconciliation_start 工具
"""
import asyncio
from mcp_server.tools import _reconciliation_start


async def test_reconciliation_start_v2():
    """测试新版本的 reconciliation_start"""
    
    print("=" * 70)
    print("测试 reconciliation_start v2.0")
    print("=" * 70)
    
    # 测试 1: 使用对账类型名称启动对账
    print("\n测试 1: 使用对账类型启动对账")
    print("-" * 70)
    result1 = await _reconciliation_start({
        "reconciliation_type": "直销对账",
        "files": [
            "/Users/kevin/workspace/financial-ai/reconciliation/test_data/business_flow.csv",
            "/Users/kevin/workspace/financial-ai/reconciliation/test_data/ads_finance_d_inc_channel_details_20250101.csv"
        ]
    })
    
    if "error" in result1:
        print(f"❌ 错误: {result1['error']}")
        if "available_types" in result1:
            print(f"  可用类型: {result1['available_types']}")
    else:
        print(f"✅ 任务创建成功")
        print(f"  任务ID: {result1.get('task_id')}")
        print(f"  状态: {result1.get('status')}")
        print(f"  消息: {result1.get('message')}")
    
    # 测试 2: 使用不存在的对账类型
    print("\n测试 2: 使用不存在的对账类型")
    print("-" * 70)
    result2 = await _reconciliation_start({
        "reconciliation_type": "不存在的对账",
        "files": [
            "/Users/kevin/workspace/financial-ai/reconciliation/test_data/business_flow.csv"
        ]
    })
    
    if "error" in result2:
        print(f"✅ 正确返回错误: {result2['error']}")
        if "available_types" in result2:
            print(f"  可用类型: {result2['available_types']}")
    else:
        print(f"❌ 应该返回错误")
    
    # 测试 3: 缺少对账类型参数
    print("\n测试 3: 缺少对账类型参数")
    print("-" * 70)
    result3 = await _reconciliation_start({
        "files": [
            "/Users/kevin/workspace/financial-ai/reconciliation/test_data/business_flow.csv"
        ]
    })
    
    if "error" in result3:
        print(f"✅ 正确返回错误: {result3['error']}")
    else:
        print(f"❌ 应该返回错误")
    
    # 测试 4: 文件不存在
    print("\n测试 4: 文件不存在")
    print("-" * 70)
    result4 = await _reconciliation_start({
        "reconciliation_type": "直销对账",
        "files": [
            "/path/to/nonexistent/file.csv"
        ]
    })
    
    if "error" in result4:
        print(f"✅ 正确返回错误: {result4['error']}")
    else:
        print(f"❌ 应该返回错误")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)
    
    # 显示对比
    print("\n📊 新旧版本对比:")
    print("─" * 70)
    print("v1.0 (旧版本):")
    print("  需要参数: schema, files, callback_url")
    print("  需要先调用 get_reconciliation 获取 schema")
    print("")
    print("v2.0 (新版本): ⭐")
    print("  需要参数: reconciliation_type, files")
    print("  自动获取 schema 和 callback_url")
    print("  简化了调用流程")


if __name__ == "__main__":
    asyncio.run(test_reconciliation_start_v2())


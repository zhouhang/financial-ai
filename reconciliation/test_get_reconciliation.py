"""
测试 get_reconciliation 工具
"""
import asyncio
from mcp_server.tools import _get_reconciliation


async def test_get_reconciliation():
    """测试获取对账配置"""
    
    print("=" * 70)
    print("测试 get_reconciliation 工具")
    print("=" * 70)
    
    # 测试 1: 正常获取直销对账配置
    print("\n测试 1: 获取直销对账配置")
    print("-" * 70)
    result1 = await _get_reconciliation({
        "reconciliation_type": "直销对账"
    })
    
    if "error" in result1:
        print(f"❌ 错误: {result1['error']}")
    else:
        schema = result1.get('schema', {})
        callback_url = result1.get('callback_url', '')
        
        if schema:
            print(f"✅ 成功获取配置")
            print(f"  版本: {schema.get('version')}")
            print(f"  描述: {schema.get('description')}")
            print(f"  回调地址: {callback_url}")
            print(f"  数据源: {list(schema.get('data_sources', {}).keys())}")
            print(f"  主键字段: {schema.get('key_field_role')}")
        else:
            print(f"❌ 返回的 schema 为空")
    
    # 测试 2: 不存在的对账类型
    print("\n测试 2: 不存在的对账类型")
    print("-" * 70)
    result2 = await _get_reconciliation({
        "reconciliation_type": "不存在的类型"
    })
    
    schema2 = result2.get('schema', {})
    callback_url2 = result2.get('callback_url', '')
    
    if not schema2 and not callback_url2:
        print(f"✅ 正确返回空结构")
        print(f"  schema: {{}}")
        print(f"  callback_url: \"\"")
    else:
        print(f"❌ 应该返回空结构")
    
    # 测试 3: 缺少参数
    print("\n测试 3: 缺少参数")
    print("-" * 70)
    result3 = await _get_reconciliation({})
    
    if "error" in result3:
        print(f"✅ 正确返回错误: {result3['error']}")
    else:
        print(f"❌ 应该返回错误但成功了")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_get_reconciliation())


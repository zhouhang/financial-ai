"""
测试优化后的文件上传功能
"""
import asyncio
import base64
from pathlib import Path
from mcp_server.tools import _file_upload

async def test_file_upload():
    """测试文件上传"""
    
    print("=" * 70)
    print("测试优化后的文件上传功能")
    print("=" * 70)
    
    # 准备测试文件
    test_file1 = Path("test_data/business_flow.csv")
    test_file2 = Path("test_data/ads_finance_d_inc_channel_details_20250101.csv")
    
    if not test_file1.exists() or not test_file2.exists():
        print("❌ 测试文件不存在")
        return
    
    # 读取文件内容
    with open(test_file1, 'rb') as f:
        content1 = base64.b64encode(f.read()).decode('utf-8')
    
    with open(test_file2, 'rb') as f:
        content2 = base64.b64encode(f.read()).decode('utf-8')
    
    # 测试 1: 使用 base64，提供文件名
    print("\n测试 1: 使用 base64，提供文件名")
    print("-" * 70)
    result1 = await _file_upload({
        "files": [
            {
                "filename": "业务流水.csv",
                "content": content1
            },
            {
                "filename": "财务流水.csv",
                "content": content2
            }
        ]
    })
    print(f"结果: {result1}")
    
    # 测试 2: 使用 base64，不提供文件名（自动推断）
    print("\n测试 2: 使用 base64，不提供文件名（自动推断）")
    print("-" * 70)
    result2 = await _file_upload({
        "files": [
            {
                "content": content1
            }
        ]
    })
    print(f"结果: {result2}")
    
    # 测试 3: 使用 file_object
    print("\n测试 3: 使用 file_object")
    print("-" * 70)
    result3 = await _file_upload({
        "files": [
            {
                "file_object": {
                    "name": "对账数据.csv",
                    "data": content1  # base64 字符串
                }
            }
        ]
    })
    print(f"结果: {result3}")
    
    # 测试 4: 混合上传（base64 + file_object）
    print("\n测试 4: 混合上传（base64 + file_object）")
    print("-" * 70)
    result4 = await _file_upload({
        "files": [
            {
                "filename": "文件1.csv",
                "content": content1
            },
            {
                "file_object": {
                    "name": "文件2.csv",
                    "data": content2
                }
            }
        ]
    })
    print(f"结果: {result4}")
    
    # 测试 5: 错误情况 - content 和 file_object 都为空
    print("\n测试 5: 错误情况 - content 和 file_object 都为空")
    print("-" * 70)
    result5 = await _file_upload({
        "files": [
            {
                "filename": "空文件.csv"
            }
        ]
    })
    print(f"结果: {result5}")
    
    # 测试 6: 错误情况 - 不支持的文件类型
    print("\n测试 6: 错误情况 - 不支持的文件类型")
    print("-" * 70)
    result6 = await _file_upload({
        "files": [
            {
                "filename": "测试.exe",
                "content": content1
            }
        ]
    })
    print(f"结果: {result6}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_file_upload())


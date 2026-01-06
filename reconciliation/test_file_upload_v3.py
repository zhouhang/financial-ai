"""
测试简化版的文件上传功能
"""
import asyncio
import base64
from pathlib import Path
from mcp_server.tools import _file_upload

async def test_file_upload_v3():
    """测试简化版文件上传"""
    
    print("=" * 70)
    print("测试简化版文件上传功能 (v3)")
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
    
    # 测试 1: 标准格式 - name + data
    print("\n测试 1: 标准格式 - name + data")
    print("-" * 70)
    result1 = await _file_upload({
        "files": [
            {
                "name": "业务流水.csv",
                "data": content1
            },
            {
                "name": "财务流水.xlsx",
                "data": content2
            }
        ]
    })
    print(f"成功: {result1['uploaded_count']}, 失败: {result1['error_count']}")
    if result1['uploaded_files']:
        for f in result1['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    # 测试 2: 使用 filename + content 字段
    print("\n测试 2: 使用 filename + content 字段")
    print("-" * 70)
    result2 = await _file_upload({
        "files": [
            {
                "filename": "数据文件.csv",
                "content": content1
            }
        ]
    })
    print(f"成功: {result2['uploaded_count']}, 失败: {result2['error_count']}")
    if result2['uploaded_files']:
        for f in result2['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    # 测试 3: 不提供文件名（自动推断）
    print("\n测试 3: 不提供文件名（自动推断）")
    print("-" * 70)
    result3 = await _file_upload({
        "files": [
            {
                "data": content1
            }
        ]
    })
    print(f"成功: {result3['uploaded_count']}, 失败: {result3['error_count']}")
    if result3['uploaded_files']:
        for f in result3['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    # 测试 4: 包含 MIME 类型
    print("\n测试 4: 包含 MIME 类型")
    print("-" * 70)
    result4 = await _file_upload({
        "files": [
            {
                "name": "数据.csv",
                "data": content1,
                "type": "text/csv"
            }
        ]
    })
    print(f"成功: {result4['uploaded_count']}, 失败: {result4['error_count']}")
    if result4['uploaded_files']:
        for f in result4['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
            if 'mime_type' in f:
                print(f"    MIME: {f['mime_type']}")
    
    # 测试 5: 混合字段名（fileName + blob）
    print("\n测试 5: 混合字段名（fileName + blob）")
    print("-" * 70)
    result5 = await _file_upload({
        "files": [
            {
                "fileName": "混合字段.csv",
                "blob": content1
            }
        ]
    })
    print(f"成功: {result5['uploaded_count']}, 失败: {result5['error_count']}")
    if result5['uploaded_files']:
        for f in result5['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    # 测试 6: 错误情况 - 缺少数据字段
    print("\n测试 6: 错误情况 - 缺少数据字段")
    print("-" * 70)
    result6 = await _file_upload({
        "files": [
            {
                "name": "空文件.csv"
            }
        ]
    })
    print(f"成功: {result6['uploaded_count']}, 失败: {result6['error_count']}")
    if result6.get('errors'):
        for err in result6['errors']:
            print(f"  - 错误: {err['error']}")
    
    # 测试 7: 二进制数据（bytes）
    print("\n测试 7: 二进制数据（bytes）")
    print("-" * 70)
    with open(test_file1, 'rb') as f:
        binary_data = f.read()
    
    result7 = await _file_upload({
        "files": [
            {
                "name": "二进制文件.csv",
                "data": binary_data
            }
        ]
    })
    print(f"成功: {result7['uploaded_count']}, 失败: {result7['error_count']}")
    if result7['uploaded_files']:
        for f in result7['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)
    
    # 显示总结
    print("\n📊 测试总结:")
    print(f"  测试 1 (name+data):          {'✅' if result1['success'] else '❌'}")
    print(f"  测试 2 (filename+content):   {'✅' if result2['success'] else '❌'}")
    print(f"  测试 3 (自动推断):           {'✅' if result3['success'] else '❌'}")
    print(f"  测试 4 (含MIME类型):         {'✅' if result4['success'] else '❌'}")
    print(f"  测试 5 (混合字段):           {'✅' if result5['success'] else '❌'}")
    print(f"  测试 6 (错误处理):           {'✅' if result6['error_count'] > 0 else '❌'}")
    print(f"  测试 7 (二进制数据):         {'✅' if result7['success'] else '❌'}")

if __name__ == "__main__":
    asyncio.run(test_file_upload_v3())


"""
测试优化后的文件上传功能 - 支持特定 JSON 格式
"""
import asyncio
import base64
from pathlib import Path
from mcp_server.tools import _file_upload

async def test_file_upload_v4():
    """测试新格式的文件上传"""
    
    print("=" * 70)
    print("测试新格式文件上传功能 (v4)")
    print("=" * 70)
    
    # 准备测试文件
    test_file1 = Path("test_data/business_flow.csv")
    test_file2 = Path("test_data/ads_finance_d_inc_channel_details_20250101.csv")
    
    if not test_file1.exists() or not test_file2.exists():
        print("❌ 测试文件不存在")
        return
    
    # 读取文件内容
    with open(test_file1, 'rb') as f:
        binary1 = f.read()
        content1 = base64.b64encode(binary1).decode('utf-8')
        size1 = len(binary1)
    
    with open(test_file2, 'rb') as f:
        binary2 = f.read()
        content2 = base64.b64encode(binary2).decode('utf-8')
        size2 = len(binary2)
    
    # 测试 1: 标准新格式（用户要求的格式）
    print("\n测试 1: 标准新格式 (filename + size + base64 + type)")
    print("-" * 70)
    result1 = await _file_upload({
        "files": [
            {
                "filename": "业务流水.csv",
                "size": size1,
                "base64": content1,
                "type": "text/csv"
            },
            {
                "filename": "财务流水.csv",
                "size": size2,
                "base64": content2,
                "type": "application/octet-stream"
            }
        ]
    })
    print(f"成功: {result1['uploaded_count']}, 失败: {result1['error_count']}")
    if result1['uploaded_files']:
        for f in result1['uploaded_files']:
            print(f"  - {f['original_filename']}")
            print(f"    保存为: {f['saved_filename']}")
            print(f"    大小: {f['file_size']} bytes")
            if 'mime_type' in f:
                print(f"    类型: {f['mime_type']}")
            if 'size_provided' in f:
                print(f"    提供的大小: {f['size_provided']} bytes")
            if 'size_warning' in f:
                print(f"    ⚠️  {f['size_warning']}")
    
    # 测试 2: 只有必填字段（filename + base64）
    print("\n测试 2: 只有必填字段 (filename + base64)")
    print("-" * 70)
    result2 = await _file_upload({
        "files": [
            {
                "filename": "简单文件.csv",
                "base64": content1
            }
        ]
    })
    print(f"成功: {result2['uploaded_count']}, 失败: {result2['error_count']}")
    if result2['uploaded_files']:
        for f in result2['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    # 测试 3: 错误的大小（验证大小检查）
    print("\n测试 3: 错误的大小（验证大小检查）")
    print("-" * 70)
    result3 = await _file_upload({
        "files": [
            {
                "filename": "大小错误.csv",
                "size": 1024,  # 故意给错误的大小
                "base64": content1,
                "type": "text/csv"
            }
        ]
    })
    print(f"成功: {result3['uploaded_count']}, 失败: {result3['error_count']}")
    if result3['uploaded_files']:
        for f in result3['uploaded_files']:
            print(f"  - {f['original_filename']}")
            print(f"    实际大小: {f['file_size']} bytes")
            if 'size_provided' in f:
                print(f"    提供的大小: {f['size_provided']} bytes")
            if 'size_warning' in f:
                print(f"    ⚠️  {f['size_warning']}")
    
    # 测试 4: Excel 文件
    print("\n测试 4: Excel 文件")
    print("-" * 70)
    result4 = await _file_upload({
        "files": [
            {
                "filename": "数据表.xlsx",
                "size": size2,
                "base64": content2,
                "type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            }
        ]
    })
    print(f"成功: {result4['uploaded_count']}, 失败: {result4['error_count']}")
    if result4['uploaded_files']:
        for f in result4['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
            if 'mime_type' in f:
                print(f"    类型: {f['mime_type']}")
    
    # 测试 5: 混合格式（同时上传新旧格式）
    print("\n测试 5: 混合格式")
    print("-" * 70)
    result5 = await _file_upload({
        "files": [
            {
                "filename": "新格式.csv",
                "size": size1,
                "base64": content1,
                "type": "text/csv"
            },
            {
                "name": "旧格式.csv",
                "data": content2
            }
        ]
    })
    print(f"成功: {result5['uploaded_count']}, 失败: {result5['error_count']}")
    if result5['uploaded_files']:
        for f in result5['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['saved_filename']}")
    
    # 测试 6: 错误情况 - 缺少 base64 字段
    print("\n测试 6: 错误情况 - 缺少 base64 字段")
    print("-" * 70)
    result6 = await _file_upload({
        "files": [
            {
                "filename": "空文件.csv",
                "size": 1024,
                "type": "text/csv"
                # 缺少 base64 字段
            }
        ]
    })
    print(f"成功: {result6['uploaded_count']}, 失败: {result6['error_count']}")
    if result6.get('errors'):
        for err in result6['errors']:
            print(f"  - 错误: {err['error']}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)
    
    # 显示总结
    print("\n📊 测试总结:")
    print(f"  测试 1 (完整新格式):       {'✅' if result1['success'] else '❌'}")
    print(f"  测试 2 (必填字段):         {'✅' if result2['success'] else '❌'}")
    print(f"  测试 3 (大小验证):         {'✅' if result3['success'] else '❌'}")
    print(f"  测试 4 (Excel文件):        {'✅' if result4['success'] else '❌'}")
    print(f"  测试 5 (混合格式):         {'✅' if result5['success'] else '❌'}")
    print(f"  测试 6 (错误处理):         {'✅' if result6['error_count'] > 0 else '❌'}")

if __name__ == "__main__":
    asyncio.run(test_file_upload_v4())


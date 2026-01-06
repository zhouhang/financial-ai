"""
测试 Dify 格式的文件上传功能
"""
import asyncio
from mcp_server.tools import _file_upload


async def test_dify_file_upload():
    """测试 Dify 格式的文件上传"""
    
    print("=" * 70)
    print("测试 Dify 格式文件上传功能")
    print("=" * 70)
    
    # 测试 1: 标准 Dify 格式
    print("\n测试 1: 标准 Dify 格式")
    print("-" * 70)
    result1 = await _file_upload({
        "files": [
            {
                "filename": "2025-12-01~2025-12-01对账流水.csv",
                "size": 656084,
                "related_id": "81d354ee-aeff-48ec-8f85-18c4fee306c6",
                "mime_type": "text/csv"
            }
        ],
        "count": 1
    })
    
    print(f"成功: {result1.get('success')}")
    print(f"上传数量: {result1.get('uploaded_count')}")
    if result1.get('uploaded_files'):
        for f in result1['uploaded_files']:
            print(f"  - {f['original_filename']}")
            print(f"    路径: {f['file_path']}")
    if result1.get('errors'):
        print(f"错误: {result1.get('errors')}")
    
    # 测试 2: 批量上传
    print("\n测试 2: 批量上传多个文件")
    print("-" * 70)
    result2 = await _file_upload({
        "files": [
            {
                "filename": "业务流水1.csv",
                "related_id": "test-id-1",
                "mime_type": "text/csv"
            },
            {
                "filename": "业务流水2.csv",
                "related_id": "test-id-2",
                "mime_type": "text/csv"
            }
        ],
        "count": 2
    })
    
    print(f"成功: {result2.get('success')}")
    print(f"上传数量: {result2.get('uploaded_count')}")
    if result2.get('uploaded_files'):
        for f in result2['uploaded_files']:
            print(f"  - {f['original_filename']} -> {f['file_path']}")
    if result2.get('errors'):
        print(f"错误数: {len(result2.get('errors'))}")
        for err in result2.get('errors', []):
            print(f"  - {err}")
    
    # 测试 3: 缺少必填字段
    print("\n测试 3: 缺少必填字段")
    print("-" * 70)
    result3 = await _file_upload({
        "files": [
            {
                "filename": "test.csv",
                # 缺少 related_id
                "mime_type": "text/csv"
            }
        ]
    })
    
    print(f"成功: {result3.get('success')}")
    if result3.get('errors'):
        for err in result3.get('errors', []):
            print(f"  - 错误: {err.get('error')}")
    
    # 测试 4: 不支持的文件类型
    print("\n测试 4: 不支持的文件类型")
    print("-" * 70)
    result4 = await _file_upload({
        "files": [
            {
                "filename": "virus.exe",
                "related_id": "test-id-exe",
                "mime_type": "application/exe"
            }
        ]
    })
    
    print(f"成功: {result4.get('success')}")
    if result4.get('errors'):
        for err in result4.get('errors', []):
            print(f"  - 错误: {err.get('error')}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_dify_file_upload())


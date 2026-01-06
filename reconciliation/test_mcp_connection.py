"""
测试 MCP SSE 连接
"""
import asyncio
import json
import httpx

async def test_sse_connection():
    """测试 SSE 连接"""
    url = "http://localhost:3335/sse"
    
    print(f"测试连接到: {url}")
    print("=" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 发送 SSE 请求
            async with client.stream("GET", url, headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache"
            }) as response:
                print(f"状态码: {response.status_code}")
                print(f"响应头: {dict(response.headers)}")
                print("\n接收到的数据:")
                print("-" * 60)
                
                # 读取前几行数据
                line_count = 0
                async for line in response.aiter_lines():
                    print(f"[{line_count}] {line}")
                    line_count += 1
                    if line_count > 20:  # 只读取前20行
                        break
                
                print("-" * 60)
                print(f"\n✅ SSE 连接成功！接收到 {line_count} 行数据")
    
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_sse_connection())


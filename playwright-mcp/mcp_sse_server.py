#!/usr/bin/env python3
"""
基于官方 MCP SDK 的 Playwright SSE 服务器 - 模块化版本
使用 mcp 官方包实现 SSE 传输

项目结构：
- mcp_server/
  ├── __init__.py          # 模块导出
  ├── config.py            # 配置常量
  ├── models.py            # 数据模型
  ├── browser_manager.py   # 浏览器管理器（核心逻辑）
  └── tools.py             # MCP 工具定义
"""
import asyncio
import json
import logging

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount, Route

# 导入模块化组件
from mcp_server import (
    PlaywrightBrowserManager,
    create_tools,
    handle_tool_call,
    DEFAULT_HOST,
    DEFAULT_PORT,
)

# 全局浏览器管理器实例
browser_manager = PlaywrightBrowserManager()

# 创建 MCP 服务器
app = Server("playwright-mcp-server", version="1.0.0")


# 注册所有工具
@app.list_tools()
async def list_tools():
    """列出所有可用的浏览器工具"""
    return create_tools()


# 注册工具调用处理器
@app.call_tool()
async def call_tool(name: str, arguments: dict):
    """处理工具调用"""
    return await handle_tool_call(browser_manager, name, arguments)


# 创建 SSE 传输
sse_transport = SseServerTransport("/messages/")


# SSE 连接处理器
async def handle_sse(request):
    """处理 SSE 连接"""
    logger = logging.getLogger(__name__)
    
    print(f"[SSE] 收到请求: {request.method} {request.url}")
    logger.info(f"收到 SSE 连接请求: {request.method} {request.url}")
    
    if request.method not in ["GET", "POST"]:
        print(f"[SSE] 方法不允许: {request.method}")
        return Response(
            content=json.dumps({"error": "Method not allowed"}),
            status_code=405,
            media_type="application/json"
        )
    
    try:
        print("[SSE] 开始建立 SSE 连接...")
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            print("[SSE] 连接已建立，启动 MCP 会话...")
            init_options = app.create_initialization_options()
            await app.run(streams[0], streams[1], init_options)
        print("[SSE] MCP 会话已结束")
    except Exception as e:
        import traceback
        error_msg = f"SSE 连接错误: {e}"
        print(f"[SSE] {error_msg}")
        traceback.print_exc()
        logger.error(error_msg, exc_info=True)
        return Response(
            content=json.dumps({"error": str(e)}),
            status_code=500,
            media_type="application/json"
        )


# 创建 Starlette 应用
starlette_app = Starlette(
    debug=True,
    routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
        Route("/mcp", endpoint=handle_sse, methods=["GET", "POST"]),
        Mount("/messages/", app=sse_transport.handle_post_message),
        Route("/health", endpoint=lambda r: Response(content='{"status":"ok"}', media_type="application/json"), methods=["GET"]),
    ]
)


def main():
    """启动 SSE 服务器"""
    import uvicorn
    
    port = DEFAULT_PORT
    host = DEFAULT_HOST
    
    print("=" * 60)
    print("Playwright MCP SSE Server (Modular Version)")
    print("=" * 60)
    print(f"服务器地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
    print(f"SSE 端点: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/sse")
    print(f"消息端点: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/messages/")
    print("\nDify 配置信息:")
    print(f"  MCP 服务器地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/mcp")
    print(f"  备用地址: http://{host if host != '0.0.0.0' else 'localhost'}:{port}/sse")
    print(f"  服务器类型: SSE (Server-Sent Events)")
    print("\n按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    try:
        uvicorn.run(starlette_app, host=host, port=port)
    except KeyboardInterrupt:
        print("\n正在关闭服务器...")
        try:
            asyncio.run(browser_manager.stop())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(browser_manager.stop())
            else:
                loop.run_until_complete(browser_manager.stop())


if __name__ == "__main__":
    main()


"""
Data Preparation MCP SSE Server
数据整理 MCP 服务器 - SSE 传输方式
"""
import sys
import asyncio
from mcp import types
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response, JSONResponse
import uvicorn

# 导入模块
from data_preparation.mcp_server.config import DEFAULT_HOST, DEFAULT_PORT
from data_preparation.mcp_server.tools import create_tools, handle_tool_call


# 创建 MCP Server
mcp_server = Server("data-preparation-mcp-server")


@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    """列出所有工具"""
    tools = create_tools()
    return tools


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """调用工具"""
    try:
        result = await handle_tool_call(name, arguments)
        
        # 转换为字符串
        import json
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        
        return [types.TextContent(type="text", text=result_str)]
    
    except Exception as e:
        error_msg = f"工具调用失败: {str(e)}"
        return [types.TextContent(type="text", text=error_msg)]


# 创建 SSE Transport（全局实例）
sse_transport = SseServerTransport("/messages/")


# 创建 Starlette 应用
async def handle_sse(request):
    """处理 SSE 连接"""
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options()
        )


async def health_check(request):
    """健康检查"""
    return JSONResponse({
        "status": "healthy",
        "service": "data-preparation-mcp-server",
        "version": "1.0.0"
    })


# 路由
routes = [
    Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
    Route("/mcp", endpoint=handle_sse, methods=["GET", "POST"]),
    Mount("/messages/", app=sse_transport.handle_post_message),
    Route("/health", endpoint=health_check),
]

app = Starlette(routes=routes)


async def main():
    """启动服务器"""
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║        Data Preparation MCP Server 启动中...                     ║
╚══════════════════════════════════════════════════════════════════╝

🌐 服务端点:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • SSE 端点:      http://{host}:{port}/sse
  • 消息端点:      http://{host}:{port}/messages/
  • 健康检查:      http://{host}:{port}/health

🛠️  可用工具:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. data_preparation_start       - 开始数据整理任务
  2. data_preparation_status      - 查询任务状态
  3. data_preparation_result      - 获取数据整理结果
  4. data_preparation_list_tasks  - 列出所有任务

📖 使用说明:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  在 Dify 中配置:
    MCP 服务器地址: http://localhost:{port}/sse
    或使用 Docker:   http://host.docker.internal:{port}/sse

  示例 schema 位置:
    {sys.path[0]}/schemas/data_preparation/audit_schema.json

服务器正在运行...
""")
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

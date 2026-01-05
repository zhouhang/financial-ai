"""
Reconciliation MCP SSE Server
对账 MCP 服务器 - SSE 传输方式
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
from mcp_server.config import DEFAULT_HOST, DEFAULT_PORT
from mcp_server.tools import create_tools, handle_tool_call


# 创建 MCP Server
mcp_server = Server("reconciliation-mcp-server")


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


# 创建 Starlette 应用
async def handle_sse(request):
    """处理 SSE 连接"""
    try:
        async with SseServerTransport("/messages/") as transport:
            await transport.connect_sse(request.receive, request._send)
            await mcp_server.run(
                transport.read_stream,
                transport.write_stream,
                mcp_server.create_initialization_options()
            )
    except Exception as e:
        print(f"SSE 连接错误: {e}", file=sys.stderr)
        return Response(f"SSE 连接失败: {str(e)}", status_code=500)


async def handle_messages(request):
    """处理 MCP 消息"""
    try:
        async with SseServerTransport("/messages/") as transport:
            await transport.handle_post_message(request.receive, request._send)
    except Exception as e:
        print(f"消息处理错误: {e}", file=sys.stderr)
        return Response(f"消息处理失败: {str(e)}", status_code=500)


async def health_check(request):
    """健康检查"""
    return JSONResponse({
        "status": "healthy",
        "service": "reconciliation-mcp-server",
        "version": "1.0.0"
    })


# 路由
routes = [
    Route("/sse", endpoint=handle_sse),
    Route("/messages/", endpoint=handle_messages, methods=["POST"]),
    Route("/health", endpoint=health_check),
]

app = Starlette(routes=routes)


async def main():
    """启动服务器"""
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║        Reconciliation MCP Server 启动中...                       ║
╚══════════════════════════════════════════════════════════════════╝

🌐 服务端点:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • SSE 端点:      http://{host}:{port}/sse
  • 消息端点:      http://{host}:{port}/messages/
  • 健康检查:      http://{host}:{port}/health

🛠️  可用工具:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. reconciliation_start      - 开始对账任务
  2. reconciliation_status     - 查询任务状态
  3. reconciliation_result     - 获取对账结果
  4. reconciliation_list_tasks - 列出所有任务
  5. file_upload               - 上传文件

📖 使用说明:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  在 Dify 中配置:
    MCP 服务器地址: http://localhost:{port}/sse
    或使用 Docker:   http://host.docker.internal:{port}/sse

  示例 schema 位置:
    {sys.path[0]}/schemas/example_schema.json

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


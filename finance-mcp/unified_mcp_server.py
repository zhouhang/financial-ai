"""
Financial Agent Unified MCP Server
统一的财务助手 MCP 服务器
"""
import os
import asyncio
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from mcp import types

# 加载环境变量
load_dotenv()
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response, JSONResponse, FileResponse
import uvicorn
import logging
from auth.jwt_utils import get_user_from_token
from security_utils import read_output_metadata

# 导入上传模块
from tools.file_upload_tool import (
    create_file_upload_tools,
    handle_file_upload_tool_call,
)

# 导入认证和规则管理模块
from auth.tools import create_auth_tools, handle_auth_tool_call

# 导入 tools 模块（文件校验和数据同步）
from tools.file_validate_tool import create_file_validate_tools, handle_file_validate_tool_call
from proc.mcp_server.proc_rule import create_proc_rule_tools, handle_proc_rule_tool_call

# 导入 rules 模块（规则查询 + 任务管理）
from tools.rules import create_tools as create_rules_tools, handle_tool_call as handle_rules_call

# 导入对账模块
from recon.mcp_server.recon_tool import create_recon_tools, handle_recon_tool_call

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_HOST = os.getenv("MCP_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.getenv("MCP_PORT", "3335"))

# 创建统一的 MCP Server
mcp_server = Server("financial-mcp-server")


@mcp_server.list_tools()
async def list_tools() -> list[types.Tool]:
    """列出所有工具"""
    try:
        auth_tools = create_auth_tools()
        logger.info(f"认证/规则管理工具数量: {len(auth_tools)}")
    except Exception as e:
        logger.error(f"加载认证工具失败: {str(e)}", exc_info=True)
        auth_tools = []

    try:
        upload_tools = [t for t in create_file_upload_tools() if t.name == "file_upload"]
        logger.info(f"上传工具数量: {len(upload_tools)}")
    except Exception as e:
        logger.error(f"加载上传工具失败: {str(e)}", exc_info=True)
        upload_tools = []
    
    try:
        file_validate_tools = create_file_validate_tools()
        logger.info(f"文件校验工具数量: {len(file_validate_tools)}")
    except Exception as e:
        logger.error(f"加载文件校验工具失败: {str(e)}", exc_info=True)
        file_validate_tools = []

    try:
        proc_tools = create_proc_rule_tools()
        logger.info(f"数据整理规则工具数量: {len(proc_tools)}")
    except Exception as e:
        logger.error(f"加载数据整理规则工具失败: {str(e)}", exc_info=True)
        proc_tools = []

    try:
        rules_tools = create_rules_tools()
        logger.info(f"Rules 工具数量: {len(rules_tools)}")
    except Exception as e:
        logger.error(f"加载 Rules 工具失败: {str(e)}", exc_info=True)
        rules_tools = []

    try:
        recon_tools_2 = create_recon_tools()
        logger.info(f"对账工具数量: {len(recon_tools_2)}")
    except Exception as e:
        logger.error(f"加载对账工具失败: {str(e)}", exc_info=True)
        recon_tools_2 = []
    
    all_tools = auth_tools + upload_tools + file_validate_tools + proc_tools + rules_tools + recon_tools_2
    logger.info(f"总工具数量: {len(all_tools)}")
    return all_tools


# 认证和规则管理工具名集合
_AUTH_TOOL_NAMES = {
    "auth_register", "auth_login", "auth_me",
    "list_reconciliation_rules", "get_reconciliation_rule",
    "delete_reconciliation_rule",
    "copy_reconciliation_rule",
    # 管理员功能
    "admin_login", "create_company", "create_department",
    "list_companies", "get_admin_view",
    "list_companies_public", "list_departments_public",
    # 会话管理
    "create_conversation", "list_conversations", "get_conversation",
    "delete_conversation", "save_message",
}

# 文件校验工具名集合
_FILE_VALIDATE_TOOL_NAMES = {
    "validate_files",
}

# 数据整理规则工具名集合
_PROC_TOOL_NAMES = {
    "proc_execute",
}

# Rules 工具名集合（规则查询 + 任务管理）
_RULES_TOOL_NAMES = {
    "get_rule",
    "list_user_tasks",
}

# 对账工具名集合
_RECON_TOOL_NAMES = {
    "recon_execute",
}

_UPLOAD_TOOL_NAMES = {"file_upload"}


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """调用工具（自动路由到对应模块）"""
    try:
        import json

        # 1) 认证和规则管理工具
        if name in _AUTH_TOOL_NAMES:
            result = await handle_auth_tool_call(name, arguments)

        # 2) 上传工具
        elif name in _UPLOAD_TOOL_NAMES:
            result = await handle_file_upload_tool_call(name, arguments)

        # 3) 文件校验模块
        elif name in _FILE_VALIDATE_TOOL_NAMES:
            result = await handle_file_validate_tool_call(name, arguments)

        # 4) 数据整理规则模块
        elif name in _PROC_TOOL_NAMES:
            result = await handle_proc_rule_tool_call(name, arguments)

        # 5) Rules 模块（规则查询 + 任务管理）
        elif name in _RULES_TOOL_NAMES:
            result = await handle_rules_call(name, arguments)

        # 6) 对账模块
        elif name in _RECON_TOOL_NAMES:
            result = await handle_recon_tool_call(name, arguments)

        else:
            result = {"error": f"未知的工具: {name}"}
        
        result_str = json.dumps(result, ensure_ascii=False, indent=2)
        return [types.TextContent(type="text", text=result_str)]
    
    except Exception as e:
        error_msg = f"工具调用失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return [types.TextContent(type="text", text=error_msg)]


# 创建 SSE Transport
sse_transport = SseServerTransport("/messages/")


# HTTP 端点处理函数
async def handle_sse(request):
    """处理 SSE 连接"""
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options()
        )
    return Response()


async def health_check(request):
    """健康检查"""
    return JSONResponse({
        "status": "healthy",
        "service": "financial-mcp-server",
        "version": "1.0.0",
        "modules": ["auth", "upload", "rules", "proc", "recon"]
    })


# 模块输出目录映射
_MODULE_OUTPUT_DIRS = {
    "proc": None,  # 延迟加载
    "recon": None,  # 延迟加载
}


def _get_module_output_dir(module: str) -> Optional[Path]:
    """获取模块的输出目录（延迟加载）"""
    if module not in _MODULE_OUTPUT_DIRS:
        return None
    
    if _MODULE_OUTPUT_DIRS[module] is not None:
        return _MODULE_OUTPUT_DIRS[module]
    
    try:
        if module == "proc":
            from proc.config.config import OUTPUT_DIR as PROC_OUTPUT_DIR
            _MODULE_OUTPUT_DIRS[module] = Path(PROC_OUTPUT_DIR)
        elif module == "recon":
            from recon.mcp_server.recon_tool import RECON_OUTPUT_DIR
            _MODULE_OUTPUT_DIRS[module] = RECON_OUTPUT_DIR
        return _MODULE_OUTPUT_DIRS[module]
    except ImportError as e:
        logger.error(f"无法导入模块 {module} 的输出目录: {e}")
        return None


async def download_output_file(request):
    """通用文件下载端点。

    路径格式: /output/{module}/{path:path}
    - module: 模块名称（proc/recon）
    - path: 文件相对路径（可包含子目录）

    示例:
    - /output/proc/{rule_code}/{filename} → proc/output/{rule_code}/{filename}
    - /output/recon/{filename} → recon/output/{filename}
    """
    module = request.path_params.get("module", "")
    file_path = request.path_params.get("path", "")
    auth_token = (request.query_params.get("auth_token") or "").strip()
    if not auth_token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            auth_token = auth_header[7:].strip()

    # 参数校验
    if not module or not file_path:
        return JSONResponse({"error": "缺少必要参数"}, status_code=400)
    if not auth_token:
        return JSONResponse({"error": "缺少认证 token"}, status_code=401)

    user = get_user_from_token(auth_token)
    if not user:
        return JSONResponse({"error": "token 无效或已过期"}, status_code=401)

    # 模块白名单校验
    if module not in _MODULE_OUTPUT_DIRS:
        return JSONResponse({"error": f"不支持的模块: {module}"}, status_code=400)

    # 安全校验：禁止路径遍历
    if ".." in file_path:
        return JSONResponse({"error": "无效的文件路径"}, status_code=400)

    # 获取模块输出目录
    output_dir = _get_module_output_dir(module)
    if output_dir is None:
        return JSONResponse({"error": f"模块 {module} 配置错误"}, status_code=500)

    # 构建完整文件路径
    full_path = output_dir / file_path
    logger.info(f"[download] 请求下载: module={module} path={file_path} full_path={full_path}")

    # 安全检查：确保路径在输出目录内
    try:
        full_path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        logger.warning(f"[download] 路径遍历攻击尝试: {file_path}")
        return JSONResponse({"error": "无效的文件路径"}, status_code=400)

    if not full_path.exists() or not full_path.is_file():
        logger.warning(f"[download] 文件不存在: {full_path}")
        return JSONResponse({"error": f"文件不存在: {file_path}"}, status_code=404)

    metadata = read_output_metadata(full_path)
    if not metadata:
        logger.warning(f"[download] 缺少输出元数据，拒绝下载: {full_path}")
        return JSONResponse({"error": "文件缺少鉴权元数据，禁止下载"}, status_code=403)

    owner_user_id = str(metadata.get("owner_user_id") or "")
    current_user_id = str(user.get("user_id") or user.get("id") or "")
    current_role = str(user.get("role") or "")
    if metadata.get("module") != module:
        logger.warning(f"[download] 模块元数据不匹配: path={full_path} meta={metadata}")
        return JSONResponse({"error": "文件元数据非法"}, status_code=403)
    if current_role != "admin" and (not owner_user_id or owner_user_id != current_user_id):
        logger.warning(
            f"[download] 越权下载被拒绝: user_id={current_user_id} owner_user_id={owner_user_id} path={full_path}"
        )
        return JSONResponse({"error": "无权下载该文件"}, status_code=403)

    # 对中文文件名使用 RFC 5987 编码
    from urllib.parse import quote
    filename = full_path.name
    encoded_filename = quote(filename, safe='')

    return FileResponse(
        str(full_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
        },
    )

# 路由配置
routes = [
    Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
    Route("/mcp", endpoint=handle_sse, methods=["GET", "POST"]),
    Mount("/messages/", app=sse_transport.handle_post_message),
    Route("/health", endpoint=health_check),
    Route("/output/{module}/{path:path}", endpoint=download_output_file),
]

app = Starlette(routes=routes)


async def main():
    """启动服务器"""
    host = DEFAULT_HOST
    port = DEFAULT_PORT
    
    # 动态获取工具列表用于显示
    try:
        tools = await list_tools()
        upload_tools = [t for t in tools if t.name in _UPLOAD_TOOL_NAMES]
        proc_tools = [t for t in tools if t.name in _FILE_VALIDATE_TOOL_NAMES or t.name in _PROC_TOOL_NAMES]
        rules_tools = [t for t in tools if t.name in _RULES_TOOL_NAMES]
        recon_tools = [t for t in tools if t.name in _RECON_TOOL_NAMES]
        auth_tools = [t for t in tools if t.name in _AUTH_TOOL_NAMES]
    except Exception as e:
        logger.warning(f"获取工具列表失败: {e}")
        auth_tools = []
        upload_tools = []
        rules_tools = []
        recon_tools = []
        proc_tools = []
    
    def _render_tools(tools_list):
        return "\n".join(
            [f"  {i + 1}. {t.name:<30} - {t.description}" for i, t in enumerate(tools_list)]
        ) or "  (none)"

    auth_tools_text = _render_tools(auth_tools)
    upload_tools_text = _render_tools(upload_tools)
    rules_tools_text = _render_tools(rules_tools)
    proc_tools_text = _render_tools(proc_tools)
    recon_tools_text = _render_tools(recon_tools)
    
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          Financial Agent MCP Server 启动中...                    ║
╚══════════════════════════════════════════════════════════════════╝

🌐 服务端点:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  • SSE 端点:        http://{host}:{port}/sse
  • 消息端点:        http://{host}:{port}/messages/
  • 健康检查:        http://{host}:{port}/health
  • 输出下载:        http://{host}:{port}/output/{{module}}/{{path}}

🛠️  可用工具（认证与规则模块，{len(auth_tools)}个）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{auth_tools_text}

🛠️  可用工具（上传模块，{len(upload_tools)}个）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{upload_tools_text}

🛠️  可用工具（Rules 模块，{len(rules_tools)}个）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{rules_tools_text}

🛠️  可用工具（数据整理规则模块，{len(proc_tools)}个）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{proc_tools_text}

🛠️  可用工具（对账模块，{len(recon_tools)}个）:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{recon_tools_text}

📖 使用说明:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  在 Dify 中配置:
    MCP 服务器地址: http://localhost:{port}/sse
    或使用 Docker:   http://host.docker.internal:{port}/sse

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

#!/bin/bash

# 启动 Reconciliation MCP Server

cd "$(dirname "$0")"

# 激活虚拟环境
source ../.venv/bin/activate

# 启动服务
python mcp_sse_server.py


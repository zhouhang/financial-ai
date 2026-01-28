#!/bin/bash
# 验证架构配置的脚本

echo "=========================================="
echo "  Finance AI - 架构验证"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}1. 检查 finance-ui 配置${NC}"
echo "-------------------------------------------"

# 检查 dify.ts 配置
if grep -q "app-pffBjBphPBhbrSwz8mxku2R3" /Users/kevin/workspace/financial-ai/finance-ui/src/api/dify.ts; then
    echo -e "${GREEN}✓ Dify API Key 配置正确${NC}"
else
    echo -e "${RED}✗ Dify API Key 配置错误${NC}"
fi

# 检查是否删除了不需要的 API 文件
if [ ! -f "/Users/kevin/workspace/financial-ai/finance-ui/src/api/auth.ts" ]; then
    echo -e "${GREEN}✓ auth.ts 已删除${NC}"
else
    echo -e "${RED}✗ auth.ts 仍然存在${NC}"
fi

if [ ! -f "/Users/kevin/workspace/financial-ai/finance-ui/src/api/schemas.ts" ]; then
    echo -e "${GREEN}✓ schemas.ts 已删除${NC}"
else
    echo -e "${RED}✗ schemas.ts 仍然存在${NC}"
fi

if [ ! -f "/Users/kevin/workspace/financial-ai/finance-ui/src/api/files.ts" ]; then
    echo -e "${GREEN}✓ files.ts 已删除${NC}"
else
    echo -e "${RED}✗ files.ts 仍然存在${NC}"
fi

if [ ! -f "/Users/kevin/workspace/financial-ai/finance-ui/src/api/client.ts" ]; then
    echo -e "${GREEN}✓ client.ts 已删除${NC}"
else
    echo -e "${RED}✗ client.ts 仍然存在${NC}"
fi

echo ""
echo -e "${BLUE}2. 检查 finance-mcp 配置${NC}"
echo "-------------------------------------------"

# 检查 API 服务器文件
if [ -f "/Users/kevin/workspace/financial-ai/finance-mcp/api_server.py" ]; then
    echo -e "${GREEN}✓ API 服务器文件存在${NC}"
else
    echo -e "${RED}✗ API 服务器文件不存在${NC}"
fi

# 检查 MCP 服务器文件
if [ -f "/Users/kevin/workspace/financial-ai/finance-mcp/unified_mcp_server.py" ]; then
    echo -e "${GREEN}✓ MCP 服务器文件存在${NC}"
else
    echo -e "${RED}✗ MCP 服务器文件不存在${NC}"
fi

# 检查 API 目录
if [ -d "/Users/kevin/workspace/financial-ai/finance-mcp/api" ]; then
    echo -e "${GREEN}✓ API 目录存在${NC}"
else
    echo -e "${RED}✗ API 目录不存在${NC}"
fi

echo ""
echo -e "${BLUE}3. 检查服务端口${NC}"
echo "-------------------------------------------"

# 检查端口 8000 (finance-mcp API)
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠ 端口 8000 已被占用 (finance-mcp API 可能正在运行)${NC}"
else
    echo -e "${GREEN}✓ 端口 8000 可用${NC}"
fi

# 检查端口 3335 (finance-mcp MCP)
if lsof -Pi :3335 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠ 端口 3335 已被占用 (finance-mcp MCP 可能正在运行)${NC}"
else
    echo -e "${GREEN}✓ 端口 3335 可用${NC}"
fi

# 检查端口 5173 (finance-ui)
if lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠ 端口 5173 已被占用 (finance-ui 可能正在运行)${NC}"
else
    echo -e "${GREEN}✓ 端口 5173 可用${NC}"
fi

echo ""
echo -e "${BLUE}4. 检查数据库连接${NC}"
echo "-------------------------------------------"

if mysql -h 127.0.0.1 -u aiuser -p123456 -e "USE finance-ai;" 2>/dev/null; then
    echo -e "${GREEN}✓ 数据库连接成功${NC}"
else
    echo -e "${RED}✗ 数据库连接失败${NC}"
fi

echo ""
echo -e "${BLUE}5. 架构验证总结${NC}"
echo "-------------------------------------------"
echo ""
echo "架构配置:"
echo "  用户 → finance-ui → Dify API → finance-mcp (API + MCP)"
echo ""
echo "Dify API 配置:"
echo "  URL: http://localhost/v1/chat-messages"
echo "  Key: app-pffBjBphPBhbrSwz8mxku2R3"
echo ""
echo "服务地址:"
echo "  - finance-ui:     http://localhost:5173"
echo "  - Dify API:       http://localhost/v1"
echo "  - finance-mcp API: http://localhost:8000"
echo "  - finance-mcp MCP: http://localhost:3335"
echo ""
echo -e "${GREEN}架构验证完成！${NC}"
echo ""
echo "下一步:"
echo "  1. 启动所有服务: ./START_ALL_SERVICES.sh"
echo "  2. 测试 Dify API 连接"
echo "  3. 在 Dify 中配置 finance-mcp 集成"
echo "  4. 测试完整流程"
echo ""

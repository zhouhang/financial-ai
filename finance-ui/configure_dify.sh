#!/bin/bash

# Dify API 配置脚本
# 用于快速配置 Dify API Key

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                    Dify API 配置向导                                         ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# 项目路径
PROJECT_DIR="/Users/kevin/workspace/financial-ai/finance-ui"
BACKEND_DIR="$PROJECT_DIR/backend"
ENV_FILE="$BACKEND_DIR/.env"

echo -e "${BLUE}步骤 1: 获取 Dify API Key${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "请访问 Dify 开发页面获取 API Key："
echo "  http://localhost/app/1ab05125-5865-4833-b6a1-ebfd69338f76/develop"
echo ""
echo "在页面中找到 'API 密钥' 或 'API Key'，复制完整的密钥"
echo "（应该是以 app- 开头的长字符串）"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 读取 API Key
read -p "请输入您的 Dify API Key: " api_key

# 验证输入
if [ -z "$api_key" ]; then
    echo -e "${RED}错误: API Key 不能为空${NC}"
    exit 1
fi

if [[ ! "$api_key" =~ ^app- ]]; then
    echo -e "${YELLOW}警告: API Key 通常以 'app-' 开头，请确认您输入的是正确的 API Key${NC}"
    read -p "是否继续？(y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "已取消配置"
        exit 0
    fi
fi

echo ""
echo -e "${BLUE}步骤 2: 配置 API Key${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 创建 .env 文件
cat > "$ENV_FILE" << EOF
# Dify API Configuration
# Generated on $(date)

DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=$api_key
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 配置文件已创建: $ENV_FILE${NC}"
else
    echo -e "${RED}✗ 创建配置文件失败${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}步骤 3: 测试 Dify API 连接${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 测试 Dify API
echo "正在测试 Dify API 连接..."
response=$(curl -s -X POST http://localhost/v1/chat-messages \
  -H "Authorization: Bearer $api_key" \
  -H "Content-Type: application/json" \
  -d '{"inputs":{},"query":"你好","response_mode":"blocking","user":"test_user"}' 2>&1)

# 检查响应
if echo "$response" | grep -q '"answer"'; then
    echo -e "${GREEN}✓ Dify API 连接成功！${NC}"
    echo ""
    echo "AI 回复："
    echo "$response" | grep -o '"answer":"[^"]*"' | sed 's/"answer":"\(.*\)"/\1/'
    echo ""
elif echo "$response" | grep -q "unauthorized"; then
    echo -e "${RED}✗ API Key 无效，请检查并重新配置${NC}"
    echo ""
    echo "错误信息："
    echo "$response"
    echo ""
    exit 1
else
    echo -e "${YELLOW}⚠ 无法连接到 Dify API${NC}"
    echo ""
    echo "响应信息："
    echo "$response"
    echo ""
    echo "请检查："
    echo "  1. Dify 服务是否正常运行"
    echo "  2. API 端点是否正确: http://localhost/v1"
    echo "  3. 网络连接是否正常"
    echo ""
    exit 1
fi

echo ""
echo -e "${BLUE}步骤 4: 重启后端服务${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 重启后端服务
cd "$PROJECT_DIR"

# 停止后端
echo "正在停止后端服务..."
pkill -f "python3 main.py" 2>/dev/null
sleep 2

# 启动后端
echo "正在启动后端服务..."
cd "$BACKEND_DIR"
nohup python3 main.py > backend.log 2>&1 &
backend_pid=$!

sleep 3

# 检查后端是否启动成功
if ps -p $backend_pid > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 后端服务启动成功 (PID: $backend_pid)${NC}"
else
    echo -e "${RED}✗ 后端服务启动失败${NC}"
    echo ""
    echo "查看日志："
    tail -20 "$BACKEND_DIR/backend.log"
    exit 1
fi

echo ""
echo -e "${BLUE}步骤 5: 测试后端 API${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 等待后端完全启动
sleep 2

# 测试后端 API
echo "正在测试后端 API..."
backend_response=$(curl -s -X POST http://localhost:8000/api/dify/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"你好","streaming":false}' 2>&1)

if echo "$backend_response" | grep -q '"answer"'; then
    echo -e "${GREEN}✓ 后端 API 测试成功！${NC}"
    echo ""
    echo "AI 回复："
    echo "$backend_response" | grep -o '"answer":"[^"]*"' | sed 's/"answer":"\(.*\)"/\1/'
    echo ""
else
    echo -e "${RED}✗ 后端 API 测试失败${NC}"
    echo ""
    echo "响应信息："
    echo "$backend_response"
    echo ""
    echo "查看后端日志："
    echo "  tail -f $BACKEND_DIR/backend.log"
    echo ""
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                    ✅ 配置完成！系统已准备就绪                               ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 访问地址："
echo ""
echo "  前端应用: http://localhost:5173"
echo "  后端 API: http://localhost:8000"
echo "  API 文档: http://localhost:8000/docs"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🚀 开始使用："
echo ""
echo "  1. 打开浏览器访问: http://localhost:5173"
echo "  2. 直接在 AI 对话框中输入消息"
echo "  3. 无需登录注册，立即开始对话"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 配置信息已保存到: $ENV_FILE"
echo ""
echo "如需重新配置，请再次运行此脚本："
echo "  ./configure_dify.sh"
echo ""

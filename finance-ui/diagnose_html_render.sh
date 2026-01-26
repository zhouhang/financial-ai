#!/bin/bash

# HTML 渲染诊断脚本
# 用于诊断 Finance-UI 中 HTML 内容无法渲染的问题

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                              ║"
echo "║                    HTML 渲染诊断工具                                         ║"
echo "║                                                                              ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 测试计数
PASS=0
FAIL=0

echo -e "${BLUE}步骤 1: 检查服务状态${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查前端服务
if curl -s http://localhost:5173 > /dev/null; then
    echo -e "${GREEN}✓ 前端服务运行正常${NC}"
    ((PASS++))
else
    echo -e "${RED}✗ 前端服务无法访问${NC}"
    ((FAIL++))
fi

# 检查后端服务
if curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${GREEN}✓ 后端服务运行正常${NC}"
    ((PASS++))
else
    echo -e "${RED}✗ 后端服务无法访问${NC}"
    ((FAIL++))
fi

echo ""
echo -e "${BLUE}步骤 2: 测试后端 API 返回内容${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 测试后端返回
RESPONSE=$(curl -s -X POST http://localhost:8000/api/dify/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"你好","streaming":false}')

# 检查是否包含 HTML
if echo "$RESPONSE" | jq -r '.answer' | grep -q '<form'; then
    echo -e "${GREEN}✓ 后端返回包含 HTML 表单${NC}"
    ((PASS++))

    # 显示返回的 HTML
    echo ""
    echo "返回的 HTML 内容:"
    echo "$RESPONSE" | jq -r '.answer'
    echo ""
else
    echo -e "${RED}✗ 后端返回不包含 HTML 表单${NC}"
    ((FAIL++))
    echo "实际返回:"
    echo "$RESPONSE" | jq -r '.answer'
fi

echo ""
echo -e "${BLUE}步骤 3: 检查前端文件${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查 Home.tsx 是否使用 dangerouslySetInnerHTML
if grep -q "dangerouslySetInnerHTML" src/components/Home/Home.tsx; then
    echo -e "${GREEN}✓ Home.tsx 使用 dangerouslySetInnerHTML${NC}"
    ((PASS++))
else
    echo -e "${RED}✗ Home.tsx 未使用 dangerouslySetInnerHTML${NC}"
    ((FAIL++))
fi

# 检查 Home.tsx 是否包含内联样式
if grep -q ".message-content form" src/components/Home/Home.tsx; then
    echo -e "${GREEN}✓ Home.tsx 包含内联 CSS 样式${NC}"
    ((PASS++))
else
    echo -e "${RED}✗ Home.tsx 缺少内联 CSS 样式${NC}"
    ((FAIL++))
fi

# 检查 Home.css 是否存在
if [ -f "src/components/Home/Home.css" ]; then
    echo -e "${GREEN}✓ Home.css 文件存在${NC}"
    ((PASS++))
else
    echo -e "${RED}✗ Home.css 文件不存在${NC}"
    ((FAIL++))
fi

# 检查 chatStore.ts 是否累加答案
if grep -q "fullAnswer += data.answer" src/stores/chatStore.ts; then
    echo -e "${GREEN}✓ chatStore.ts 正确累加答案${NC}"
    ((PASS++))
else
    echo -e "${RED}✗ chatStore.ts 未正确累加答案${NC}"
    ((FAIL++))
    echo "  提示: 应该使用 'fullAnswer += data.answer' 而不是 'fullAnswer = data.answer'"
fi

echo ""
echo -e "${BLUE}步骤 4: 测试流式响应${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 测试流式响应
STREAM_RESPONSE=$(curl -s -X POST http://localhost:8000/api/dify/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"你好","streaming":true}' | grep "data:" | tail -5)

if echo "$STREAM_RESPONSE" | grep -q "workflow_finished"; then
    echo -e "${GREEN}✓ 流式响应包含 workflow_finished 事件${NC}"
    ((PASS++))
else
    echo -e "${YELLOW}⚠ 流式响应可能不完整${NC}"
fi

# 检查是否有多个 message 事件
MESSAGE_COUNT=$(echo "$STREAM_RESPONSE" | grep -c '"event":"message"')
if [ "$MESSAGE_COUNT" -ge 2 ]; then
    echo -e "${GREEN}✓ 检测到多个 message 事件 (数量: $MESSAGE_COUNT)${NC}"
    echo "  这是正常的，答案会被累加"
    ((PASS++))
else
    echo -e "${YELLOW}⚠ 只检测到 $MESSAGE_COUNT 个 message 事件${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}诊断结果${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "通过: ${GREEN}$PASS${NC}"
echo -e "失败: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ 所有检查通过！${NC}"
    echo ""
    echo "如果 HTML 仍然无法渲染，请尝试以下步骤:"
    echo "1. 在浏览器中按 Cmd+Shift+R (Mac) 或 Ctrl+Shift+R (Windows) 强制刷新"
    echo "2. 打开浏览器开发者工具 (F12)"
    echo "3. 查看 Console 标签是否有错误"
    echo "4. 查看 Elements 标签中的 .message-content 元素"
    echo "5. 查看 Network 标签中的 /api/dify/chat 响应"
else
    echo -e "${RED}✗ 发现 $FAIL 个问题，请检查上述失败项${NC}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "详细调试指南: HTML_RENDER_DEBUG_GUIDE.md"
echo "测试页面: file:///tmp/test_html_render.html"
echo ""

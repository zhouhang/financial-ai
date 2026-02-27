#!/bin/bash
# 验证脚本配置

echo "=========================================="
echo "🔍 验证 Financial AI 配置"
echo "=========================================="
echo ""

PROJECT_ROOT="/Users/fanyuli/Desktop/workspace/financial-ai"

# 检查项目根目录
echo "📁 检查项目目录..."
if [ -d "$PROJECT_ROOT" ]; then
    echo "✅ 项目目录存在: $PROJECT_ROOT"
else
    echo "❌ 项目目录不存在: $PROJECT_ROOT"
    exit 1
fi
echo ""

# 检查子目录
echo "📂 检查服务目录..."
DIRS=("finance-mcp" "finance-agents/data-agent" "finance-web")
for dir in "${DIRS[@]}"; do
    if [ -d "$PROJECT_ROOT/$dir" ]; then
        echo "✅ $dir"
    else
        echo "❌ $dir (不存在)"
    fi
done
echo ""

# 检查虚拟环境
echo "🐍 检查 Python 虚拟环境..."
if [ -d "$PROJECT_ROOT/.venv" ]; then
    echo "✅ 虚拟环境存在: .venv"
else
    echo "❌ 虚拟环境不存在"
fi
echo ""

# 检查关键文件
echo "📄 检查关键文件..."
FILES=(
    "finance-mcp/unified_mcp_server.py"
    "finance-agents/data-agent/app/server.py"
    "finance-web/package.json"
    "START_ALL_SERVICES.sh"
    "STOP_ALL_SERVICES.sh"
)
for file in "${FILES[@]}"; do
    if [ -f "$PROJECT_ROOT/$file" ]; then
        echo "✅ $file"
    else
        echo "❌ $file (不存在)"
    fi
done
echo ""

# 检查脚本权限
echo "🔐 检查脚本权限..."
if [ -x "$PROJECT_ROOT/START_ALL_SERVICES.sh" ]; then
    echo "✅ START_ALL_SERVICES.sh 可执行"
else
    echo "⚠️  START_ALL_SERVICES.sh 没有执行权限"
    echo "   运行: chmod +x START_ALL_SERVICES.sh"
fi

if [ -x "$PROJECT_ROOT/STOP_ALL_SERVICES.sh" ]; then
    echo "✅ STOP_ALL_SERVICES.sh 可执行"
else
    echo "⚠️  STOP_ALL_SERVICES.sh 没有执行权限"
    echo "   运行: chmod +x STOP_ALL_SERVICES.sh"
fi
echo ""

# 检查端口占用
echo "🔌 检查端口占用..."
PORTS=(3335 8100 5173)
for port in "${PORTS[@]}"; do
    if lsof -i:$port > /dev/null 2>&1; then
        echo "⚠️  端口 $port 已被占用"
    else
        echo "✅ 端口 $port 可用"
    fi
done
echo ""

echo "=========================================="
echo "✅ 配置验证完成"
echo "=========================================="
echo ""
echo "如果所有检查都通过，可以运行："
echo "  ./START_ALL_SERVICES.sh"
echo ""

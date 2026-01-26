#!/bin/bash

# Finance-UI 一键启动脚本

echo "=================================="
echo "Finance-UI 启动脚本"
echo "=================================="
echo ""

# 检查是否在正确的目录
if [ ! -f "package.json" ]; then
    echo "❌ 错误：请在 finance-ui 目录下运行此脚本"
    exit 1
fi

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ 错误：未安装 Node.js"
    echo "请访问 https://nodejs.org/ 安装 Node.js"
    exit 1
fi

# 检查 Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "❌ 错误：未安装 Python"
    echo "请访问 https://www.python.org/ 安装 Python 3"
    exit 1
fi

# 检查 MySQL
if ! command -v mysql &> /dev/null; then
    echo "⚠️  警告：未检测到 MySQL，请确保 MySQL 已安装并运行"
fi

echo "✅ 环境检查通过"
echo ""

# 安装后端依赖
echo "📦 安装后端依赖..."
cd backend
if [ ! -d ".venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv .venv 2>/dev/null || python -m venv .venv
fi

source .venv/bin/activate 2>/dev/null || .venv\\Scripts\\activate

pip install -r requirements.txt -q
if [ $? -ne 0 ]; then
    echo "❌ 后端依赖安装失败"
    exit 1
fi
echo "✅ 后端依赖安装完成"
echo ""

# 初始化数据库
echo "🗄️  初始化数据库..."
python init_db.py
if [ $? -ne 0 ]; then
    echo "❌ 数据库初始化失败"
    echo "请检查 MySQL 是否运行，以及 .env 配置是否正确"
    exit 1
fi
echo "✅ 数据库初始化完成"
echo ""

# 启动后端
echo "🚀 启动后端服务..."
python main.py &
BACKEND_PID=$!
echo "后端进程 PID: $BACKEND_PID"
echo ""

# 等待后端启动
sleep 3

# 安装前端依赖
cd ..
echo "📦 安装前端依赖..."
if [ ! -d "node_modules" ]; then
    npm install
    if [ $? -ne 0 ]; then
        echo "❌ 前端依赖安装失败"
        kill $BACKEND_PID
        exit 1
    fi
fi
echo "✅ 前端依赖安装完成"
echo ""

# 启动前端
echo "🚀 启动前端服务..."
npm run dev &
FRONTEND_PID=$!
echo "前端进程 PID: $FRONTEND_PID"
echo ""

echo "=================================="
echo "✅ 启动完成！"
echo "=================================="
echo ""
echo "📍 访问地址："
echo "   前端: http://localhost:5173"
echo "   后端: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "💡 提示："
echo "   - 按 Ctrl+C 停止服务"
echo "   - 首次使用请先注册账号"
echo ""
echo "📚 文档："
echo "   - 快速开始: cat QUICKSTART.md"
echo "   - 部署指南: cat DEPLOYMENT_GUIDE.md"
echo ""

# 等待用户中断
trap "echo ''; echo '🛑 停止服务...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT

wait

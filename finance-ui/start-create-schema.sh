#!/bin/bash

# Create Schema Canvas - 快速启动脚本

echo "🚀 Create Schema Canvas - 快速启动"
echo "=================================="
echo ""

# 检查当前目录
if [ ! -f "package.json" ]; then
    echo "❌ 错误: 请在 finance-ui 目录下运行此脚本"
    exit 1
fi

# 检查后端服务
echo "1️⃣ 检查后端服务..."
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "   ✅ 后端服务运行正常: http://localhost:8000"
else
    echo "   ❌ 后端服务未运行"
    echo "   请在另一个终端运行:"
    echo "   cd backend && python3 -m uvicorn main:app --reload --port 8000"
    echo ""
fi

# 检查前端服务
echo ""
echo "2️⃣ 检查前端服务..."
if curl -s http://localhost:5175/ > /dev/null 2>&1; then
    echo "   ✅ 前端服务运行正常: http://localhost:5175"
else
    echo "   ❌ 前端服务未运行"
    echo "   请在另一个终端运行:"
    echo "   npm run dev"
    echo ""
fi

# 检查依赖
echo ""
echo "3️⃣ 检查依赖..."
if [ -d "node_modules/lodash" ]; then
    echo "   ✅ lodash 已安装"
else
    echo "   ❌ lodash 未安装"
    echo "   正在安装..."
    npm install lodash
fi

# 显示文档
echo ""
echo "=================================="
echo "📚 文档导航"
echo "=================================="
echo ""
echo "快速开始:"
echo "  📖 CREATE_SCHEMA_README.md"
echo ""
echo "技术文档:"
echo "  📖 CREATE_SCHEMA_IMPLEMENTATION.md"
echo "  📖 CREATE_SCHEMA_DEPLOYMENT.md"
echo ""
echo "测试文档:"
echo "  📖 CREATE_SCHEMA_TEST_GUIDE.md"
echo "  📖 CREATE_SCHEMA_CHECKLIST.md"
echo ""
echo "其他文档:"
echo "  📖 CREATE_SCHEMA_DEMO_SCRIPT.md"
echo "  📖 PROJECT_STATUS_REPORT.md"
echo "  📖 CREATE_SCHEMA_SUMMARY.md"
echo ""

# 显示使用说明
echo "=================================="
echo "🎯 快速测试"
echo "=================================="
echo ""
echo "1. 打开浏览器访问: http://localhost:5175/"
echo ""
echo "2. 在聊天界面输入:"
echo "   \"帮我创建一个销售数据整理规则\""
echo ""
echo "3. 点击\"开始创建规则\"按钮"
echo ""
echo "4. 按照向导完成配置"
echo ""

# 显示 API 端点
echo "=================================="
echo "🔗 API 端点"
echo "=================================="
echo ""
echo "后端 API:"
echo "  📍 http://localhost:8000/docs"
echo ""
echo "新增端点:"
echo "  POST /schemas/generate-type-key"
echo "  GET  /schemas/check-name-exists"
echo "  POST /schemas/validate-content"
echo "  POST /schemas/test"
echo ""

# 显示注意事项
echo "=================================="
echo "⚠️  注意事项"
echo "=================================="
echo ""
echo "1. 新的 API 端点需要用户认证"
echo "   请确保已登录后再使用创建规则功能"
echo ""
echo "2. 文件上传限制:"
echo "   - 格式: .xlsx, .xls"
echo "   - 大小: 最大 100MB"
echo ""
echo "3. 如遇到问题:"
echo "   - 查看浏览器控制台 (F12)"
echo "   - 查看后端日志"
echo "   - 参考文档: CREATE_SCHEMA_DEPLOYMENT.md"
echo ""

# 完成
echo "=================================="
echo "✅ 检查完成"
echo "=================================="
echo ""
echo "🎉 Create Schema Canvas 已准备就绪！"
echo ""

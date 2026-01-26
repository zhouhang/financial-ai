#!/bin/bash

# 登录表单功能验证脚本

echo "🧪 登录表单功能验证"
echo "===================="
echo ""

# 检查前端服务
echo "1️⃣ 检查前端服务..."
if curl -s http://localhost:5175/ > /dev/null 2>&1; then
    echo "   ✅ 前端服务运行正常: http://localhost:5175/"
else
    echo "   ❌ 前端服务未运行"
    echo "   请运行: cd /Users/kevin/workspace/financial-ai/finance-ui && npm run dev"
fi
echo ""

# 检查后端服务
echo "2️⃣ 检查后端服务..."
if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
    echo "   ✅ 后端服务运行正常: http://localhost:8000/"
else
    echo "   ❌ 后端服务未运行"
    echo "   请运行: cd /Users/kevin/workspace/financial-ai/finance-ui/backend && python3 -m uvicorn main:app --reload --port 8000"
fi
echo ""

# 检查关键文件
echo "3️⃣ 检查关键文件..."
files=(
    "/Users/kevin/workspace/financial-ai/finance-ui/backend/services/dify_service.py"
    "/Users/kevin/workspace/financial-ai/finance-ui/src/types/dify.ts"
    "/Users/kevin/workspace/financial-ai/finance-ui/src/stores/chatStore.ts"
    "/Users/kevin/workspace/financial-ai/finance-ui/src/components/Home/Home.tsx"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $(basename $file)"
    else
        echo "   ❌ $(basename $file) 不存在"
    fi
done
echo ""

# 检查 [login_form] 指令是否已添加
echo "4️⃣ 检查 [login_form] 指令..."
if grep -q "login_form" "/Users/kevin/workspace/financial-ai/finance-ui/backend/services/dify_service.py"; then
    echo "   ✅ 后端已添加 login_form 指令检测"
else
    echo "   ❌ 后端未添加 login_form 指令检测"
fi
echo ""

# 检查 updateMessage 方法
echo "5️⃣ 检查 updateMessage 方法..."
if grep -q "updateMessage" "/Users/kevin/workspace/financial-ai/finance-ui/src/stores/chatStore.ts"; then
    echo "   ✅ chatStore 已添加 updateMessage 方法"
else
    echo "   ❌ chatStore 未添加 updateMessage 方法"
fi
echo ""

# 检查 renderLoginForm 函数
echo "6️⃣ 检查 renderLoginForm 函数..."
if grep -q "renderLoginForm" "/Users/kevin/workspace/financial-ai/finance-ui/src/components/Home/Home.tsx"; then
    echo "   ✅ Home 组件已添加 renderLoginForm 函数"
else
    echo "   ❌ Home 组件未添加 renderLoginForm 函数"
fi
echo ""

# 检查 loading-spinner 样式
echo "7️⃣ 检查加载动画样式..."
if grep -q "loading-spinner" "/Users/kevin/workspace/financial-ai/finance-ui/src/components/Home/Home.tsx"; then
    echo "   ✅ 已添加 loading-spinner 样式"
else
    echo "   ❌ 未添加 loading-spinner 样式"
fi
echo ""

# 测试文档
echo "8️⃣ 测试文档..."
docs=(
    "/Users/kevin/workspace/financial-ai/finance-ui/LOGIN_FORM_TEST.md"
    "/Users/kevin/workspace/financial-ai/finance-ui/LOGIN_FORM_FINAL.md"
    "/Users/kevin/workspace/financial-ai/finance-ui/IMPLEMENTATION_SUMMARY.md"
    "/Users/kevin/workspace/financial-ai/finance-ui/public/test-login-form.html"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        echo "   ✅ $(basename $doc)"
    else
        echo "   ❌ $(basename $doc) 不存在"
    fi
done
echo ""

echo "===================="
echo "✅ 验证完成！"
echo ""
echo "📝 下一步操作："
echo "1. 打开浏览器访问: http://localhost:5175/"
echo "2. 或打开测试页面: file:///Users/kevin/workspace/financial-ai/finance-ui/public/test-login-form.html"
echo "3. 在 Dify 中配置返回包含 [login_form] 的消息"
echo "4. 测试登录功能"
echo ""
echo "📚 查看文档："
echo "- LOGIN_FORM_FINAL.md - 最终实现说明"
echo "- LOGIN_FORM_TEST.md - 测试指南"
echo "- IMPLEMENTATION_SUMMARY.md - 完整实现总结"

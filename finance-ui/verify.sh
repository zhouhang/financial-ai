#!/bin/bash

# Finance-UI 项目验证脚本

echo "=================================="
echo "Finance-UI 项目验证"
echo "=================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 (缺失)"
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1/"
        return 0
    else
        echo -e "${RED}✗${NC} $1/ (缺失)"
        return 1
    fi
}

# 统计变量
total_checks=0
passed_checks=0

# 1. 检查后端文件
echo "1. 检查后端文件..."
echo "-----------------------------------"

backend_files=(
    "backend/main.py"
    "backend/config.py"
    "backend/database.py"
    "backend/init_db.py"
    "backend/requirements.txt"
    "backend/.env.example"
    "backend/README.md"
    "backend/models/__init__.py"
    "backend/models/user.py"
    "backend/models/schema.py"
    "backend/schemas/__init__.py"
    "backend/schemas/auth.py"
    "backend/schemas/schema.py"
    "backend/schemas/file.py"
    "backend/routers/__init__.py"
    "backend/routers/auth.py"
    "backend/routers/schemas.py"
    "backend/routers/files.py"
    "backend/routers/dify.py"
    "backend/services/__init__.py"
    "backend/services/auth_service.py"
    "backend/services/schema_service.py"
    "backend/services/file_service.py"
    "backend/services/dify_service.py"
    "backend/utils/__init__.py"
    "backend/utils/security.py"
    "backend/utils/pinyin.py"
    "backend/utils/excel.py"
)

for file in "${backend_files[@]}"; do
    total_checks=$((total_checks + 1))
    if check_file "$file"; then
        passed_checks=$((passed_checks + 1))
    fi
done

echo ""

# 2. 检查前端文件
echo "2. 检查前端文件..."
echo "-----------------------------------"

frontend_files=(
    "src/main.tsx"
    "src/App.tsx"
    "src/index.css"
    "index.html"
    "package.json"
    "tsconfig.json"
    "tsconfig.node.json"
    "vite.config.ts"
    ".env"
    ".gitignore"
    "src/api/client.ts"
    "src/api/auth.ts"
    "src/api/schemas.ts"
    "src/api/files.ts"
    "src/api/dify.ts"
    "src/components/Auth/Login.tsx"
    "src/components/Auth/Register.tsx"
    "src/components/Home/Home.tsx"
    "src/components/Common/ProtectedRoute.tsx"
    "src/stores/authStore.ts"
    "src/stores/schemaStore.ts"
    "src/stores/chatStore.ts"
    "src/types/auth.ts"
    "src/types/schema.ts"
    "src/types/dify.ts"
)

for file in "${frontend_files[@]}"; do
    total_checks=$((total_checks + 1))
    if check_file "$file"; then
        passed_checks=$((passed_checks + 1))
    fi
done

echo ""

# 3. 检查文档文件
echo "3. 检查文档文件..."
echo "-----------------------------------"

doc_files=(
    "README_FINAL.md"
    "QUICKSTART.md"
    "USER_MANUAL.md"
    "DEPLOYMENT_GUIDE.md"
    "PROJECT_SUMMARY.md"
    "FINAL_SUMMARY.md"
    "PROJECT_COMPLETION_REPORT.md"
    "DELIVERY.md"
    "PROJECT_CHECKLIST.md"
    "README.md"
)

for file in "${doc_files[@]}"; do
    total_checks=$((total_checks + 1))
    if check_file "$file"; then
        passed_checks=$((passed_checks + 1))
    fi
done

echo ""

# 4. 检查脚本文件
echo "4. 检查脚本文件..."
echo "-----------------------------------"

total_checks=$((total_checks + 1))
if check_file "start.sh"; then
    passed_checks=$((passed_checks + 1))
    if [ -x "start.sh" ]; then
        echo -e "  ${GREEN}✓${NC} start.sh 可执行"
    else
        echo -e "  ${YELLOW}!${NC} start.sh 不可执行（运行 chmod +x start.sh）"
    fi
fi

echo ""

# 5. 统计结果
echo "=================================="
echo "验证结果"
echo "=================================="
echo ""
echo "总检查项: $total_checks"
echo -e "通过: ${GREEN}$passed_checks${NC}"
echo -e "失败: ${RED}$((total_checks - passed_checks))${NC}"
echo ""

if [ $passed_checks -eq $total_checks ]; then
    echo -e "${GREEN}✅ 所有文件检查通过！${NC}"
    echo ""
    echo "项目已准备就绪，可以开始使用："
    echo "  ./start.sh"
    exit 0
else
    echo -e "${RED}❌ 有文件缺失，请检查上述列表${NC}"
    exit 1
fi

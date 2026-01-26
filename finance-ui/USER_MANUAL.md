# Finance-UI 使用手册

## 📖 目录

1. [快速开始](#快速开始)
2. [用户指南](#用户指南)
3. [API 使用](#api-使用)
4. [开发指南](#开发指南)
5. [常见问题](#常见问题)

---

## 🚀 快速开始

### 第一次使用

#### 1. 启动系统

**使用一键启动脚本（推荐）：**
```bash
cd finance-ui
./start.sh
```

**或手动启动：**
```bash
# 终端 1 - 后端
cd finance-ui/backend
pip install -r requirements.txt
python init_db.py
python main.py

# 终端 2 - 前端
cd finance-ui
npm install
npm run dev
```

#### 2. 注册账号

1. 打开浏览器访问：http://localhost:5173
2. 点击"立即注册"
3. 填写信息：
   - 用户名：至少 3 个字符
   - 邮箱：有效的邮箱地址
   - 密码：至少 6 个字符
4. 点击"注册"按钮
5. 自动跳转到主页

#### 3. 开始使用

注册成功后，您将看到：
- 欢迎卡片（显示用户名）
- AI 助手聊天界面
- 快速开始按钮

---

## 👤 用户指南

### 1. 登录和登出

#### 登录
1. 访问 http://localhost:5173/login
2. 输入用户名和密码
3. 点击"登录"
4. 登录成功后跳转到主页

#### 登出
1. 点击右上角用户头像（待实现）
2. 选择"登出"
3. 返回登录页面

**提示：** Token 有效期为 24 小时，过期后需要重新登录。

### 2. 与 AI 对话

#### 发送消息
1. 在聊天框中输入消息
2. 按 Enter 或点击"发送"按钮
3. AI 会自动回复

**快捷键：**
- `Enter` - 发送消息
- `Shift + Enter` - 换行

#### 查看历史
- 所有对话历史会自动保存
- 向上滚动查看历史消息
- 每条消息显示时间戳

#### 命令检测
当 AI 回复包含特殊命令时，系统会自动识别：
- `[create_schema]` - 创建新规则
- `[update_schema]` - 更新规则
- `[schema_list]` - 查看规则列表

**示例对话：**
```
用户: 帮我创建一个货币资金数据整理的规则
AI: 好的，我来帮你创建货币资金数据整理规则。[create_schema]
系统: 检测到命令 create_schema
```

### 3. 创建 Schema（通过 API）

#### 使用 API 创建
```bash
# 获取 Token
TOKEN=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_username","password":"your_password"}' \
  | jq -r '.access_token')

# 创建 Schema
curl -X POST http://localhost:8000/api/schemas \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name_cn": "货币资金数据整理",
    "work_type": "data_preparation",
    "description": "从科目余额表中提取银行存款数据"
  }'
```

#### 查看创建的 Schema
```bash
# 列表查询
curl -X GET http://localhost:8000/api/schemas \
  -H "Authorization: Bearer $TOKEN"

# 获取详情
curl -X GET http://localhost:8000/api/schemas/1 \
  -H "Authorization: Bearer $TOKEN"
```

### 4. 上传文件

#### 使用 API 上传
```bash
# 上传单个文件
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/path/to/file.xlsx"

# 上传多个文件
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@/path/to/file1.xlsx" \
  -F "files=@/path/to/file2.xlsx"
```

#### 预览文件
```bash
# 获取 Excel 预览
curl -X GET "http://localhost:8000/api/files/preview?file_path=/uploads/2026/1/26/file.xlsx" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🔌 API 使用

### API 基础信息

**Base URL:** `http://localhost:8000/api`

**认证方式:** Bearer Token

**请求头：**
```
Authorization: Bearer YOUR_ACCESS_TOKEN
Content-Type: application/json
```

### 认证 API

#### 1. 注册用户
```http
POST /api/auth/register
Content-Type: application/json

{
  "username": "testuser",
  "email": "test@example.com",
  "password": "test123456"
}
```

**响应：**
```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com",
  "created_at": "2026-01-26T10:00:00"
}
```

#### 2. 用户登录
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "testuser",
  "password": "test123456"
}
```

**响应：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "testuser",
    "email": "test@example.com"
  }
}
```

#### 3. 获取当前用户
```http
GET /api/auth/me
Authorization: Bearer YOUR_TOKEN
```

**响应：**
```json
{
  "id": 1,
  "username": "testuser",
  "email": "test@example.com"
}
```

### Schema API

#### 1. 创建 Schema
```http
POST /api/schemas
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "name_cn": "货币资金数据整理",
  "work_type": "data_preparation",
  "callback_url": "http://example.com/webhook",
  "description": "从科目余额表中提取银行存款数据"
}
```

**响应：**
```json
{
  "id": 1,
  "user_id": 1,
  "name_cn": "货币资金数据整理",
  "type_key": "huo_bi_zi_jin_shu_ju_zheng_li",
  "work_type": "data_preparation",
  "schema_path": "data_preparation/schemas/1/huo_bi_zi_jin_shu_ju_zheng_li.json",
  "config_path": "data_preparation/config/1/data_preparation_schemas.json",
  "version": "1.0",
  "status": "draft",
  "is_public": false,
  "created_at": "2026-01-26T10:00:00"
}
```

#### 2. 列表查询
```http
GET /api/schemas?work_type=data_preparation&status=published&skip=0&limit=10
Authorization: Bearer YOUR_TOKEN
```

**响应：**
```json
{
  "total": 5,
  "schemas": [
    {
      "id": 1,
      "name_cn": "货币资金数据整理",
      "type_key": "huo_bi_zi_jin_shu_ju_zheng_li",
      "work_type": "data_preparation",
      "status": "published",
      "version": "1.0"
    }
  ]
}
```

#### 3. 获取详情
```http
GET /api/schemas/1
Authorization: Bearer YOUR_TOKEN
```

**响应：**
```json
{
  "id": 1,
  "name_cn": "货币资金数据整理",
  "type_key": "huo_bi_zi_jin_shu_ju_zheng_li",
  "work_type": "data_preparation",
  "schema_content": {
    "version": "1.0",
    "schema_type": "step_based",
    "metadata": {
      "project_name": "货币资金数据整理",
      "author": "testuser"
    },
    "processing_steps": []
  }
}
```

#### 4. 更新 Schema
```http
PUT /api/schemas/1
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "name_cn": "货币资金数据整理（更新）",
  "status": "published",
  "schema_content": {
    "version": "1.1",
    "processing_steps": [...]
  }
}
```

#### 5. 删除 Schema
```http
DELETE /api/schemas/1
Authorization: Bearer YOUR_TOKEN
```

**响应：**
```json
{
  "message": "Schema deleted successfully"
}
```

### 文件 API

#### 1. 上传文件
```http
POST /api/files/upload
Authorization: Bearer YOUR_TOKEN
Content-Type: multipart/form-data

files: [File1, File2, ...]
```

**响应：**
```json
{
  "uploaded_files": [
    {
      "filename": "test.xlsx",
      "path": "/uploads/2026/1/26/test.xlsx",
      "size": 102400,
      "sheets": ["Sheet1", "Sheet2"]
    }
  ]
}
```

#### 2. 预览文件
```http
GET /api/files/preview?file_path=/uploads/2026/1/26/test.xlsx&max_rows=100
Authorization: Bearer YOUR_TOKEN
```

**响应：**
```json
{
  "filename": "test.xlsx",
  "sheets": [
    {
      "name": "Sheet1",
      "headers": ["列1", "列2", "列3"],
      "rows": [
        ["值1", "值2", "值3"],
        ["值4", "值5", "值6"]
      ],
      "total_rows": 100,
      "total_columns": 3
    }
  ]
}
```

### Dify API

#### 发送消息
```http
POST /api/dify/chat
Authorization: Bearer YOUR_TOKEN
Content-Type: application/json

{
  "query": "帮我创建一个货币资金数据整理的规则",
  "conversation_id": "optional-conversation-id",
  "streaming": false
}
```

**响应：**
```json
{
  "event": "message",
  "message_id": "msg-123",
  "conversation_id": "conv-456",
  "answer": "好的，我来帮你创建货币资金数据整理规则。[create_schema]",
  "metadata": {
    "command": "create_schema"
  }
}
```

---

## 💻 开发指南

### 前端开发

#### 添加新页面

1. **创建组件文件**
```tsx
// src/components/MyPage/MyPage.tsx
import React from 'react';
import { Card } from 'antd';

const MyPage: React.FC = () => {
  return (
    <Card title="我的页面">
      <p>页面内容</p>
    </Card>
  );
};

export default MyPage;
```

2. **添加路由**
```tsx
// src/App.tsx
import MyPage from '@/components/MyPage/MyPage';

// 在 Routes 中添加
<Route path="/my-page" element={
  <ProtectedRoute>
    <MyPage />
  </ProtectedRoute>
} />
```

#### 使用状态管理

```tsx
// 使用认证状态
import { useAuthStore } from '@/stores/authStore';

const MyComponent = () => {
  const { user, logout } = useAuthStore();

  return (
    <div>
      <p>用户：{user?.username}</p>
      <button onClick={logout}>登出</button>
    </div>
  );
};
```

#### 调用 API

```tsx
import { schemaApi } from '@/api/schemas';

const MyComponent = () => {
  const [schemas, setSchemas] = useState([]);

  useEffect(() => {
    const fetchSchemas = async () => {
      try {
        const response = await schemaApi.getSchemas();
        setSchemas(response.schemas);
      } catch (error) {
        console.error('Failed to fetch schemas:', error);
      }
    };

    fetchSchemas();
  }, []);

  return <div>{/* 渲染 schemas */}</div>;
};
```

### 后端开发

#### 添加新端点

1. **创建路由**
```python
# backend/routers/my_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from routers.auth import get_current_user

router = APIRouter(prefix="/my-endpoint", tags=["My Endpoint"])

@router.get("/")
def get_data(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return {"message": "Hello World"}
```

2. **注册路由**
```python
# backend/main.py
from routers.my_router import router as my_router

app.include_router(my_router, prefix=settings.API_PREFIX)
```

#### 添加数据库模型

```python
# backend/models/my_model.py
from sqlalchemy import Column, Integer, String
from database import Base

class MyModel(Base):
    __tablename__ = "my_table"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
```

---

## ❓ 常见问题

### 1. 如何重置密码？

目前系统不支持密码重置功能。如需重置，请：

**方式 1：通过数据库**
```sql
-- 连接数据库
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456

-- 删除用户（谨慎操作）
USE finance-ai;
DELETE FROM users WHERE username = 'your_username';

-- 重新注册
```

**方式 2：联系管理员**

### 2. Token 过期怎么办？

Token 默认有效期为 24 小时。过期后：
1. 系统会自动跳转到登录页
2. 重新登录获取新 Token
3. 继续使用

### 3. 如何查看 Schema 文件？

Schema 文件存储在文件系统中：

```bash
# 数据整理 Schema
ls finance-mcp/data_preparation/schemas/{user_id}/

# 对账 Schema
ls finance-mcp/reconciliation/schemas/{user_id}/

# 查看内容
cat finance-mcp/data_preparation/schemas/1/huo_bi_zi_jin_shu_ju_zheng_li.json
```

### 4. 如何备份数据？

**备份数据库：**
```bash
mysqldump -h 127.0.0.1 -P 3306 -u aiuser -p123456 finance-ai > backup.sql
```

**恢复数据库：**
```bash
mysql -h 127.0.0.1 -P 3306 -u aiuser -p123456 finance-ai < backup.sql
```

**备份 Schema 文件：**
```bash
tar -czf schemas_backup.tar.gz finance-mcp/
```

### 5. 如何更改端口？

**后端端口：**
```python
# backend/main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001)  # 改为 8001
```

**前端端口：**
```typescript
// vite.config.ts
export default defineConfig({
  server: {
    port: 5174,  // 改为 5174
  },
})
```

### 6. 如何配置 Dify？

1. 获取 Dify API Key
2. 更新后端配置：
```env
# backend/.env
DIFY_API_URL=http://your-dify-server/v1
DIFY_API_KEY=app-your-api-key
```
3. 重启后端服务

### 7. 如何查看日志？

**后端日志：**
- 终端输出
- 或配置日志文件

**前端日志：**
- 浏览器控制台（F12）
- Network 面板查看 API 请求

**数据库日志：**
```bash
# MySQL 日志
tail -f /var/log/mysql/error.log
```

### 8. 如何部署到生产环境？

详细步骤请参考 `DEPLOYMENT_GUIDE.md` 中的"生产环境部署"章节。

简要步骤：
1. 更换 SECRET_KEY
2. 配置 HTTPS
3. 使用 Gunicorn + Nginx
4. 配置防火墙
5. 定期备份

---

## 📞 获取帮助

### 文档资源
- **快速开始**: `QUICKSTART.md`
- **部署指南**: `DEPLOYMENT_GUIDE.md`
- **项目总结**: `PROJECT_SUMMARY.md`
- **完成报告**: `PROJECT_COMPLETION_REPORT.md`

### API 文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 在线资源
- FastAPI: https://fastapi.tiangolo.com/
- React: https://react.dev/
- Ant Design: https://ant.design/

---

**最后更新**: 2026-01-26
**版本**: v1.0.0

祝使用愉快！🎉

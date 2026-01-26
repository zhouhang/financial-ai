# Finance-UI 项目总结

## 项目概述

Finance-UI 是一个全栈 Web 应用程序，为财务数据处理提供可视化的 Schema 管理界面。用户可以通过与 Dify AI 对话来创建、编辑和管理数据整理和对账规则。

---

## ✅ 已完成的工作

### 1. 后端 API（100% 完成）

#### 1.1 项目结构
```
finance-ui/backend/
├── main.py                 # FastAPI 应用入口
├── config.py              # 配置管理
├── database.py            # 数据库连接
├── init_db.py            # 数据库初始化脚本
├── requirements.txt       # Python 依赖
├── models/               # SQLAlchemy 模型
│   ├── user.py          # 用户模型
│   └── schema.py        # Schema 模型
├── schemas/              # Pydantic 验证模型
│   ├── auth.py          # 认证相关
│   ├── schema.py        # Schema 相关
│   └── file.py          # 文件相关
├── routers/              # API 路由
│   ├── auth.py          # 认证端点
│   ├── schemas.py       # Schema CRUD
│   ├── files.py         # 文件上传
│   └── dify.py          # Dify 集成
├── services/             # 业务逻辑
│   ├── auth_service.py
│   ├── schema_service.py
│   ├── file_service.py
│   └── dify_service.py
└── utils/                # 工具函数
    ├── security.py       # JWT & 密码哈希
    ├── pinyin.py        # 中文转拼音
    └── excel.py         # Excel 处理
```

#### 1.2 核心功能

**认证模块**
- ✅ 用户注册（用户名、邮箱唯一性验证）
- ✅ 用户登录（JWT Token 生成）
- ✅ 密码加密（bcrypt）
- ✅ Token 验证中间件
- ✅ 获取当前用户信息

**Schema 管理模块**
- ✅ 创建 Schema（自动生成 type_key）
- ✅ 列表查询（支持过滤、分页）
- ✅ 获取详情（包含 JSON 内容）
- ✅ 更新 Schema（版本自动递增）
- ✅ 删除 Schema（级联删除文件）
- ✅ 中文名称唯一性验证
- ✅ 文件系统操作（JSON 文件和配置文件）

**文件上传模块**
- ✅ 多文件上传
- ✅ 文件类型验证（.xlsx, .xls, .csv）
- ✅ 文件大小限制（100MB）
- ✅ 日期目录组织（YYYY/M/D）
- ✅ Excel 文件解析
- ✅ Sheet 名称提取
- ✅ 预览数据生成（表头 + 前100行）

**Dify 集成模块**
- ✅ Chat API 代理
- ✅ 命令检测（[create_schema], [update_schema], [schema_list]）
- ✅ 流式响应支持
- ✅ 阻塞式响应支持
- ✅ 错误处理和重试

#### 1.3 数据库设计

**users 表**
```sql
- id (主键)
- username (唯一)
- email (唯一)
- password_hash
- created_at
- updated_at
```

**user_schemas 表**
```sql
- id (主键)
- user_id (外键 → users.id)
- name_cn (中文名称)
- type_key (英文标识)
- work_type (data_preparation | reconciliation)
- schema_path (JSON 文件路径)
- config_path (配置文件路径)
- version (版本号)
- status (draft | published)
- is_public (是否公开)
- callback_url (回调 URL)
- description (描述)
- created_at
- updated_at
- UNIQUE (user_id, name_cn)
```

#### 1.4 API 端点

| 端点 | 方法 | 功能 | 认证 |
|------|------|------|------|
| `/api/auth/register` | POST | 注册用户 | ❌ |
| `/api/auth/login` | POST | 登录获取 Token | ❌ |
| `/api/auth/me` | GET | 获取当前用户 | ✅ |
| `/api/schemas` | GET | 列表查询 | ✅ |
| `/api/schemas` | POST | 创建 Schema | ✅ |
| `/api/schemas/{id}` | GET | 获取详情 | ✅ |
| `/api/schemas/{id}` | PUT | 更新 Schema | ✅ |
| `/api/schemas/{id}` | DELETE | 删除 Schema | ✅ |
| `/api/files/upload` | POST | 上传文件 | ✅ |
| `/api/files/preview` | GET | 预览 Excel | ✅ |
| `/api/dify/chat` | POST | Dify 对话 | ✅ |

### 2. 前端项目结构（已初始化）

```
finance-ui/
├── package.json          # 项目配置
├── tsconfig.json        # TypeScript 配置
├── vite.config.ts       # Vite 配置
├── .env                 # 环境变量
└── README.md            # 前端文档
```

**已配置的依赖：**
- React 18
- TypeScript
- Ant Design 5
- Zustand
- Axios
- SheetJS (xlsx)
- React Router
- Vite

### 3. 文档

- ✅ **DEPLOYMENT_GUIDE.md** - 完整部署指南
  - 后端部署步骤
  - 前端部署步骤
  - 数据库初始化
  - API 测试方法
  - 故障排查
  - 生产环境配置

- ✅ **backend/README.md** - 后端文档
  - 安装说明
  - API 文档
  - 测试方法

- ✅ **frontend/README.md** - 前端文档
  - 项目结构
  - 开发指南
  - 待实现功能

---

## 🚧 待完成的工作

### 前端开发（优先级：高）

#### Phase 1: 基础设施
1. **API 客户端层**
   - `src/api/client.ts` - Axios 实例配置（拦截器、Token 管理）
   - `src/api/auth.ts` - 认证 API 封装
   - `src/api/schemas.ts` - Schema API 封装
   - `src/api/files.ts` - 文件 API 封装
   - `src/api/dify.ts` - Dify API 封装

2. **类型定义**
   - `src/types/auth.ts` - 用户、Token 类型
   - `src/types/schema.ts` - Schema 相关类型
   - `src/types/dify.ts` - Dify 消息类型
   - `src/types/file.ts` - 文件相关类型

3. **状态管理**
   - `src/stores/authStore.ts` - 认证状态（用户、Token、登录/登出）
   - `src/stores/schemaStore.ts` - Schema 列表状态
   - `src/stores/chatStore.ts` - 聊天历史状态
   - `src/stores/canvasStore.ts` - 画布编辑状态

#### Phase 2: 认证界面
1. **登录页面** (`src/components/Auth/Login.tsx`)
   - 用户名/密码表单
   - 表单验证
   - 错误提示
   - 跳转到注册

2. **注册页面** (`src/components/Auth/Register.tsx`)
   - 用户名/邮箱/密码表单
   - 密码强度验证
   - 邮箱格式验证
   - 注册成功跳转

3. **受保护路由** (`src/components/Common/ProtectedRoute.tsx`)
   - Token 验证
   - 未登录重定向

#### Phase 3: 主布局
1. **应用布局** (`src/components/Common/Layout.tsx`)
   - 顶部导航栏
   - 侧边栏菜单
   - 用户信息下拉
   - 登出功能

2. **路由配置** (`src/App.tsx`)
   - 登录/注册路由
   - 主页路由
   - Schema 列表路由
   - 404 页面

#### Phase 4: 聊天界面
1. **聊天窗口** (`src/components/Chat/ChatWindow.tsx`)
   - 消息列表显示
   - 输入框
   - 发送按钮
   - 加载状态

2. **消息组件** (`src/components/Chat/MessageList.tsx`)
   - 用户消息气泡
   - AI 消息气泡
   - Markdown 渲染
   - 时间戳

3. **命令检测**
   - 监听 Dify 响应
   - 检测 `[create_schema]` 等命令
   - 触发相应的 UI 操作

#### Phase 5: Schema 列表
1. **列表页面** (`src/components/SchemaList/SchemaList.tsx`)
   - 卡片/列表视图切换
   - 筛选器（工作类型、状态）
   - 搜索框
   - 分页

2. **Schema 卡片** (`src/components/SchemaList/SchemaCard.tsx`)
   - 显示基本信息
   - 状态徽章
   - 操作按钮（编辑、删除、复制）

#### Phase 6: Schema 编辑器（核心功能）
1. **画布模态框** (`src/components/Canvas/CanvasModal.tsx`)
   - 两步向导
   - 步骤指示器
   - 上一步/下一步按钮

2. **初始化表单** (`src/components/Canvas/SchemaInitForm.tsx`)
   - 工作类型选择
   - 中文名称输入
   - 唯一性验证
   - type_key 自动生成预览

3. **可视化编辑器** (`src/components/Canvas/VisualEditor.tsx`)
   - 左侧：Excel 预览
   - 右侧：步骤配置表单
   - 底部：JSON 预览

4. **Excel 预览** (`src/components/Canvas/ExcelPreview.tsx`)
   - 文件上传（拖拽）
   - 多文件分屏显示
   - Sheet 标签切换
   - 虚拟滚动表格
   - 列头高亮选择

5. **步骤编辑器** (`src/components/Canvas/StepEditor.tsx`)
   - 步骤类型选择器
   - 文件模式输入
   - 列映射界面
   - 条件规则构建器
   - 模板操作配置

6. **字段映射** (`src/components/Canvas/FieldMapper.tsx`)
   - 拖拽字段映射
   - 源字段列表
   - 目标字段列表
   - 映射关系可视化

7. **条件构建器** (`src/components/Canvas/ConditionBuilder.tsx`)
   - 可视化条件编辑
   - 模板填空："如果 ___ 是 ___，则取 ___ 中 ___"
   - AND/OR 逻辑组合
   - 正则表达式支持

8. **Schema 生成和保存**
   - 表单数据 → JSON Schema 转换
   - 实时 JSON 预览
   - 验证 Schema 格式
   - 保存到后端

9. **Schema 测试**
   - 使用上传的文件测试
   - 显示处理结果
   - 错误反馈
   - 发布 Schema

#### Phase 7: 高级功能（优先级：中）
1. **撤销/重做**
   - 命令模式实现
   - 历史栈管理
   - 快捷键支持

2. **智能推荐**
   - 字段名称建议
   - 文件模式建议
   - 模板建议

3. **导入/导出**
   - 导出 Schema JSON
   - 导入现有 Schema
   - 复制 Schema

---

## 📋 下一步行动计划

### 立即开始（推荐顺序）

#### 第1步：安装和测试后端（15分钟）
```bash
# 1. 安装后端依赖
cd finance-ui/backend
pip install -r requirements.txt

# 2. 初始化数据库
python init_db.py

# 3. 启动后端服务
python main.py

# 4. 测试 API
curl http://localhost:8000/health
```

#### 第2步：初始化前端项目（10分钟）
```bash
# 1. 安装前端依赖
cd finance-ui
npm install

# 2. 启动开发服务器
npm run dev

# 3. 访问 http://localhost:5173
```

#### 第3步：实现认证界面（2-3小时）
1. 创建 API 客户端和类型定义
2. 实现认证状态管理（Zustand）
3. 创建登录页面
4. 创建注册页面
5. 实现受保护路由

#### 第4步：实现主布局（1-2小时）
1. 创建应用布局组件
2. 添加导航栏和侧边栏
3. 配置路由

#### 第5步：实现聊天界面（2-3小时）
1. 创建聊天窗口组件
2. 集成 Dify API
3. 实现命令检测
4. 测试对话流程

#### 第6步：实现 Schema 列表（2-3小时）
1. 创建列表页面
2. 实现筛选和搜索
3. 添加操作按钮

#### 第7步：实现 Schema 编辑器（核心，5-8小时）
1. 创建画布模态框
2. 实现初始化表单
3. 实现 Excel 预览
4. 实现步骤编辑器
5. 实现 Schema 生成
6. 测试完整流程

---

## 🎯 关键技术点

### 1. 中文转拼音
使用 `pypinyin` 库自动生成 type_key：
```python
from utils.pinyin import generate_type_key
type_key = generate_type_key("货币资金数据整理")
# 结果: "huo_bi_zi_jin_shu_ju_zheng_li"
```

### 2. JWT 认证流程
```
1. 用户登录 → 后端验证 → 返回 JWT Token
2. 前端存储 Token（localStorage）
3. 每次请求携带 Token（Authorization: Bearer <token>）
4. 后端验证 Token → 返回用户信息
```

### 3. Schema 文件组织
```
finance-mcp/
├── data_preparation/
│   ├── schemas/
│   │   └── {user_id}/
│   │       └── {type_key}.json
│   └── config/
│       └── {user_id}/
│           └── data_preparation_schemas.json
└── reconciliation/
    ├── schemas/
    │   └── {user_id}/
    └── config/
        └── {user_id}/
```

### 4. Dify 命令检测
```python
# 后端检测
def detect_command(text: str) -> Optional[str]:
    if '[create_schema]' in text:
        return 'create_schema'
    elif '[update_schema]' in text:
        return 'update_schema'
    elif '[schema_list]' in text:
        return 'schema_list'
    return None

# 前端处理
if (response.metadata.command === 'create_schema') {
    openCanvasModal();
}
```

### 5. Excel 文件处理
```python
# 后端解析
from utils.excel import parse_excel_file
preview_data = parse_excel_file(file_path, max_rows=100)

# 前端显示
import * as XLSX from 'xlsx';
const workbook = XLSX.read(data, { type: 'array' });
```

---

## 📚 参考资源

### 后端
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [JWT 文档](https://jwt.io/)

### 前端
- [React 文档](https://react.dev/)
- [Ant Design 文档](https://ant.design/)
- [Zustand 文档](https://docs.pmnd.rs/zustand)
- [SheetJS 文档](https://docs.sheetjs.com/)
- [Vite 文档](https://vitejs.dev/)

### 数据库
- [MySQL 文档](https://dev.mysql.com/doc/)

---

## 🔧 开发工具推荐

- **API 测试**: Postman / Insomnia / curl
- **数据库管理**: MySQL Workbench / DBeaver / phpMyAdmin
- **代码编辑器**: VS Code
- **浏览器开发工具**: Chrome DevTools / React DevTools

---

## 📝 注意事项

1. **安全性**
   - 生产环境必须更换 `SECRET_KEY`
   - 使用 HTTPS
   - 启用 CORS 白名单
   - 实施 API 速率限制

2. **性能优化**
   - Excel 预览限制行数（默认100行）
   - 使用虚拟滚动处理大数据
   - 前端实现防抖和节流
   - 后端使用数据库索引

3. **用户体验**
   - 加载状态提示
   - 错误信息友好
   - 表单验证实时反馈
   - 操作确认对话框

4. **测试**
   - 单元测试（后端）
   - 集成测试（API）
   - E2E 测试（前端）
   - 手动测试完整流程

---

## 🎉 总结

### 已完成
- ✅ 完整的后端 API 实现
- ✅ 数据库设计和初始化
- ✅ 认证和授权系统
- ✅ Schema CRUD 操作
- ✅ 文件上传和预览
- ✅ Dify 集成和命令检测
- ✅ 完整的部署文档

### 待完成
- ⏳ 前端 React 应用实现
- ⏳ Schema 可视化编辑器
- ⏳ Excel 预览组件
- ⏳ 聊天界面

### 预计工作量
- 前端基础功能：8-12 小时
- Schema 编辑器：8-12 小时
- 测试和优化：4-6 小时
- **总计：20-30 小时**

---

## 📞 支持

如有问题，请参考：
1. `DEPLOYMENT_GUIDE.md` - 部署指南
2. `backend/README.md` - 后端文档
3. `README.md` - 前端文档
4. API 文档：http://localhost:8000/docs

祝开发顺利！🚀

# Finance-UI Frontend

财务 AI 助手前端应用 - 基于 React 18 + TypeScript + Ant Design

## 功能特性

- 🔐 用户认证（注册/登录）
- 💬 Dify AI 对话界面
- 📊 Schema 可视化编辑器
- 📁 Excel 文件预览
- 🎨 响应式设计

## 技术栈

- React 18
- TypeScript
- Ant Design 5
- Zustand (状态管理)
- Axios (HTTP 客户端)
- SheetJS (Excel 处理)
- React Router (路由)
- Vite (构建工具)

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8000/api
VITE_DIFY_API_URL=http://localhost:8000/api/dify
```

### 3. 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:5173

### 4. 构建生产版本

```bash
npm run build
```

构建产物在 `dist/` 目录

## 项目结构

```
src/
├── api/                    # API 客户端
│   ├── client.ts          # Axios 实例
│   ├── auth.ts            # 认证 API
│   ├── schemas.ts         # Schema API
│   ├── files.ts           # 文件 API
│   └── dify.ts            # Dify API
├── components/            # React 组件
│   ├── Auth/             # 认证组件
│   ├── Chat/             # 聊天组件
│   ├── Canvas/           # Schema 编辑器
│   ├── SchemaList/       # Schema 列表
│   └── Common/           # 通用组件
├── stores/               # Zustand 状态管理
│   ├── authStore.ts      # 认证状态
│   ├── chatStore.ts      # 聊天状态
│   ├── canvasStore.ts    # 画布状态
│   └── schemaStore.ts    # Schema 状态
├── types/                # TypeScript 类型
│   ├── auth.ts
│   ├── schema.ts
│   └── dify.ts
├── utils/                # 工具函数
│   ├── excel.ts          # Excel 处理
│   └── api.ts            # API 辅助
├── App.tsx               # 根组件
└── main.tsx              # 入口文件
```

## 开发指南

### 状态管理

使用 Zustand 进行状态管理：

```typescript
// 使用认证状态
import { useAuthStore } from '@/stores/authStore';

function MyComponent() {
  const { user, login, logout } = useAuthStore();
  // ...
}
```

### API 调用

```typescript
import { authApi } from '@/api/auth';

// 登录
const response = await authApi.login({
  username: 'user',
  password: 'pass'
});
```

### 路由

```typescript
import { BrowserRouter, Routes, Route } from 'react-router-dom';

<Routes>
  <Route path="/login" element={<Login />} />
  <Route path="/" element={<ProtectedRoute><Home /></ProtectedRoute>} />
</Routes>
```

## 待实现功能

当前后端已完成，前端需要实现：

### Phase 1: 基础功能
- [ ] 登录/注册页面
- [ ] 主布局和导航
- [ ] 受保护路由

### Phase 2: 核心功能
- [ ] Dify 聊天界面
- [ ] 命令检测和处理
- [ ] Schema 列表页面

### Phase 3: Schema 编辑器
- [ ] 画布模态框
- [ ] Excel 文件上传
- [ ] Excel 预览组件
- [ ] 步骤配置表单
- [ ] Schema 生成和保存

### Phase 4: 高级功能
- [ ] 撤销/重做
- [ ] 智能字段推荐
- [ ] Schema 验证和测试
- [ ] 导出/导入功能

## 参考文档

- [React 文档](https://react.dev/)
- [Ant Design 文档](https://ant.design/)
- [Zustand 文档](https://docs.pmnd.rs/zustand)
- [Vite 文档](https://vitejs.dev/)

## 后端 API

后端 API 文档：http://localhost:8000/docs

主要端点：
- `POST /api/auth/register` - 注册
- `POST /api/auth/login` - 登录
- `GET /api/auth/me` - 获取当前用户
- `GET /api/schemas` - 获取 Schema 列表
- `POST /api/schemas` - 创建 Schema
- `POST /api/files/upload` - 上传文件
- `POST /api/dify/chat` - Dify 对话

## 部署

参考根目录的 `DEPLOYMENT_GUIDE.md` 文件

# Create Schema Canvas - 部署和使用说明

## 🎉 实现完成

`[create_schema]` 画布功能已全部开发完成并可以使用！

## 📦 已安装的依赖

```json
{
  "lodash": "^4.17.23"  // 用于防抖功能
}
```

## 🚀 启动服务

### 1. 启动后端服务

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui/backend
python3 -m uvicorn main:app --reload --port 8000
```

**验证**: 访问 http://localhost:8000/docs

### 2. 启动前端服务

```bash
cd /Users/kevin/workspace/financial-ai/finance-ui
npm run dev
```

**验证**: 访问 http://localhost:5175/

## 🎯 快速测试

### 方法 1: 通过 Dify 触发

1. 在 Dify 工作流中配置一个节点返回包含 `[create_schema]` 的消息
2. 在聊天界面触发该工作流
3. 点击"开始创建规则"按钮

### 方法 2: 直接测试（开发模式）

如果 Dify 还未配置，可以临时修改代码测试：

**临时测试代码** (在 `src/components/Home/Home.tsx` 中添加):

```typescript
// 在欢迎界面添加测试按钮
<Button
  type="text"
  onClick={() => {
    // 模拟 Dify 返回 create_schema 命令
    const testMessage = {
      id: `test-${Date.now()}`,
      role: 'assistant',
      content: '您好！我可以帮您创建数据处理规则。',
      timestamp: new Date(),
      command: 'create_schema'
    };
    // 手动添加到消息列表
    useChatStore.setState((state) => ({
      messages: [...state.messages, testMessage]
    }));
  }}
  style={{
    color: '#4a9eff',
    border: '1px solid #2a2a2a',
    background: '#1a1a1a',
    height: 'auto',
    padding: '12px 24px'
  }}
>
  🧪 测试创建规则（开发模式）
</Button>
```

## 📋 完整功能清单

### ✅ 后端功能

- [x] Type key 生成 API (`POST /schemas/generate-type-key`)
- [x] 名称唯一性检查 API (`GET /schemas/check-name-exists`)
- [x] Schema 验证 API (`POST /schemas/validate-content`)
- [x] Schema 测试 API (`POST /schemas/test`)
- [x] Schema CRUD API (已有)

### ✅ 前端功能

#### 步骤 1: 元数据表单
- [x] 工作类型选择（数据整理/对账）
- [x] 中文名称输入
- [x] 实时 type_key 生成（防抖 500ms）
- [x] 名称唯一性验证
- [x] 描述输入（可选）
- [x] 表单验证

#### 步骤 2: 画布工作区
- [x] 3 列布局（步骤列表 | Excel 预览 | 配置面板）
- [x] 文件上传（拖拽/点击）
- [x] 多文件支持
- [x] 多 Sheet 预览
- [x] Ant Design Table 展示
- [x] 步骤添加
- [x] 步骤编辑
- [x] 步骤删除
- [x] 步骤选择
- [x] 撤销/重做（最多 50 步）
- [x] 6 种步骤类型配置
- [x] Schema 验证
- [x] Schema 测试
- [x] Schema 保存

#### UI/UX
- [x] 深色主题
- [x] 响应式布局
- [x] 加载状态
- [x] 错误提示
- [x] 成功提示
- [x] 按钮悬停效果
- [x] 表单验证反馈

## 🎨 UI 预览

### 聊天界面 - 检测到命令
```
┌─────────────────────────────────────────────┐
│ 🤖 Finance AI                               │
│                                             │
│ 您好！我可以帮您创建数据处理规则。         │
│                                             │
│ [ 开始创建规则 ]                            │
│                                             │
│ 🔍 检测到命令: create_schema                │
└─────────────────────────────────────────────┘
```

### 步骤 1 - 元数据表单
```
┌─────────────────────────────────────────────┐
│ 创建规则 - 基本信息                         │
├─────────────────────────────────────────────┤
│                                             │
│ 工作类型                                    │
│ ○ 数据整理  ○ 数据对账                     │
│                                             │
│ 规则名称（中文）                            │
│ [销售数据整理___________________]           │
│                                             │
│ 规则标识（自动生成）                        │
│ [xiao_shou_shu_ju_zheng_li______] (禁用)   │
│                                             │
│ 描述（可选）                                │
│ [整理每月销售数据________________]          │
│ [________________________________]          │
│                                             │
│                    [ 取消 ]  [ 下一步 ]     │
└─────────────────────────────────────────────┘
```

### 步骤 2 - 画布工作区
```
┌─────────────────────────────────────────────────────────────────────┐
│ ← 返回  销售数据整理              [ 测试 ] [ 保存 ] [ 取消 ]        │
├──────────┬──────────────────────────────────┬───────────────────────┤
│          │                                  │                       │
│ 操作步骤 │     Excel 文件预览               │  步骤配置             │
│ ━━━━━━━ │     ━━━━━━━━━━━━━━━━━━━━━━━━━━ │  ━━━━━━━━━━━━━━━━━ │
│          │                                  │                       │
│ ↻ ↺      │  📁 sales.xlsx  📁 data.xlsx    │  步骤配置             │
│          │  ┌────────────────────────────┐ │  ━━━━━━━━━━━━━━━━━ │
│ ▶ 步骤1  │  │ Sheet1  Sheet2             │ │                       │
│   步骤2  │  │ ┌────────────────────────┐ │ │  步骤名称             │
│   步骤3  │  │ │ 姓名 | 金额 | 日期     │ │ │  [提取销售数据____]   │
│          │  │ │ 张三 | 1000 | 2024-01 │ │ │                       │
│ + 添加   │  │ │ 李四 | 2000 | 2024-01 │ │ │  步骤类型             │
│          │  │ └────────────────────────┘ │ │  [数据提取 ▼]         │
│          │  └────────────────────────────┘ │                       │
│          │                                  │  源文件               │
│          │  共 100 行 × 10 列               │  [sales.xlsx ▼]       │
│          │                                  │                       │
│          │                                  │  目标名称             │
│          │                                  │  [sales_data_____]    │
│          │                                  │                       │
│          │                                  │  [ 保存配置 ]         │
└──────────┴──────────────────────────────────┴───────────────────────┘
```

## 🔧 配置 Dify 工作流

### 1. 创建触发节点

在 Dify 中创建一个 LLM 节点，配置提示词：

```
当用户请求创建数据处理规则时，返回以下内容：

您好！我可以帮您创建数据处理规则。请点击下方按钮开始配置。

[create_schema]
```

### 2. 配置登录处理节点

如果需要登录验证，可以在返回 `[create_schema]` 之前先返回 `[login_form]`：

```
您好，我是一名AI财务助手，能为您完成excel数据整理和对账的工作，为了更好的理解你的工作并帮您完成工作，请先登录

[login_form]
```

登录成功后再返回：

```
登录成功！现在您可以创建数据处理规则了。

[create_schema]
```

## 📊 数据流程

```
用户输入
  ↓
Dify 工作流
  ↓
返回 [create_schema] 指令
  ↓
前端检测命令
  ↓
渲染"开始创建规则"按钮
  ↓
用户点击按钮
  ↓
打开全屏模态框
  ↓
步骤 1: 填写元数据
  ├─ 调用 /schemas/generate-type-key
  ├─ 调用 /schemas/check-name-exists
  └─ 验证通过 → 下一步
  ↓
步骤 2: 配置画布
  ├─ 上传文件
  ├─ 添加步骤
  ├─ 配置步骤
  ├─ 测试 (可选) → /schemas/test
  └─ 保存 → /schemas (POST)
  ↓
保存成功
  ├─ 创建数据库记录
  ├─ 生成 JSON 文件
  ├─ 更新配置文件
  └─ 更新聊天消息
```

## 🗂️ 文件存储结构

### 数据整理规则
```
data_preparation/
├── schemas/
│   └── {user_id}/
│       └── {type_key}.json
└── config/
    └── {user_id}/
        └── data_preparation_schemas.json
```

### 对账规则
```
reconciliation/
├── schemas/
│   └── {user_id}/
│       └── {type_key}.json
└── config/
    └── {user_id}/
        └── reconciliation_schemas.json
```

### Schema JSON 格式

```json
{
  "version": "1.0",
  "schema_type": "step_based",
  "metadata": {
    "project_name": "销售数据整理",
    "author": "username",
    "description": "整理每月销售数据"
  },
  "processing_steps": [
    {
      "step_name": "提取销售数据",
      "step_type": "extract",
      "config": {
        "source_file": "file-123",
        "target_name": "sales_data"
      },
      "order": 0
    }
  ],
  "uploaded_files": [
    {
      "filename": "sales.xlsx",
      "path": "/uploads/sales.xlsx",
      "sheets": ["Sheet1", "Sheet2"]
    }
  ]
}
```

## 🔍 调试技巧

### 1. 查看后端日志

```bash
# 后端服务日志会显示所有 API 调用
tail -f backend.log
```

### 2. 查看浏览器控制台

打开浏览器开发者工具（F12）：
- Console: 查看错误和日志
- Network: 查看 API 请求和响应
- React DevTools: 查看组件状态

### 3. 检查 Zustand 状态

在浏览器控制台执行：

```javascript
// 查看画布状态
window.__ZUSTAND_DEVTOOLS__?.getState()

// 查看聊天状态
useChatStore.getState()
```

### 4. 测试 API 端点

使用 curl 或 Postman 测试：

```bash
# 生成 type_key
curl -X POST http://localhost:8000/schemas/generate-type-key \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"name_cn": "销售数据整理"}'

# 检查名称存在性
curl -X GET "http://localhost:8000/schemas/check-name-exists?name_cn=销售数据整理" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🐛 常见问题

### Q1: 点击"开始创建规则"按钮没反应

**解决方案**:
1. 检查浏览器控制台是否有错误
2. 确认事件监听器已正确绑定
3. 检查 `createSchemaModalVisible` 状态

### Q2: 文件上传失败

**解决方案**:
1. 检查文件大小（< 100MB）
2. 检查文件格式（.xlsx, .xls）
3. 检查后端文件上传配置
4. 查看网络请求错误信息

### Q3: 名称唯一性验证不工作

**解决方案**:
1. 检查防抖是否正常（500ms）
2. 检查 API 调用是否成功
3. 检查用户是否已登录
4. 查看后端日志

### Q4: 保存失败

**解决方案**:
1. 检查 Schema 验证是否通过
2. 检查文件系统权限
3. 检查数据库连接
4. 查看后端错误日志

### Q5: 样式显示不正确

**解决方案**:
1. 清除浏览器缓存
2. 检查 CSS 文件是否正确导入
3. 检查 Ant Design 主题配置
4. 使用浏览器开发者工具检查样式

## 📈 性能优化建议

### 1. 文件上传优化

```typescript
// 使用分片上传处理大文件
const uploadLargeFile = async (file: File) => {
  const chunkSize = 1024 * 1024; // 1MB
  const chunks = Math.ceil(file.size / chunkSize);

  for (let i = 0; i < chunks; i++) {
    const chunk = file.slice(i * chunkSize, (i + 1) * chunkSize);
    await uploadChunk(chunk, i, chunks);
  }
};
```

### 2. 历史记录优化

```typescript
// 使用 IndexedDB 持久化历史记录
import { openDB } from 'idb';

const db = await openDB('canvas-history', 1, {
  upgrade(db) {
    db.createObjectStore('history');
  },
});

await db.put('history', historyState, 'current');
```

### 3. 虚拟滚动

```typescript
// 对于大量步骤，使用虚拟滚动
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={steps.length}
  itemSize={60}
  width="100%"
>
  {({ index, style }) => (
    <div style={style}>
      <StepItem step={steps[index]} />
    </div>
  )}
</FixedSizeList>
```

## 🎓 学习资源

### 相关文档
- [CREATE_SCHEMA_IMPLEMENTATION.md](CREATE_SCHEMA_IMPLEMENTATION.md) - 完整实现总结
- [CREATE_SCHEMA_TEST_GUIDE.md](CREATE_SCHEMA_TEST_GUIDE.md) - 测试指南
- [LOGIN_FORM_FINAL_V3.md](LOGIN_FORM_FINAL_V3.md) - 登录表单实现

### 技术栈文档
- [React 18](https://react.dev/)
- [TypeScript](https://www.typescriptlang.org/)
- [Ant Design](https://ant.design/)
- [Zustand](https://zustand-demo.pmnd.rs/)
- [FastAPI](https://fastapi.tiangolo.com/)

## 🎉 总结

`[create_schema]` 画布功能已完全实现并可以投入使用！

### 核心亮点
- ✅ 完整的两步向导流程
- ✅ 直观的 3 列布局
- ✅ 6 种步骤类型支持
- ✅ 实时验证和测试
- ✅ 撤销/重做功能
- ✅ 深色主题 UI
- ✅ 响应式设计

### 下一步
1. 在 Dify 中配置工作流
2. 测试完整流程
3. 收集用户反馈
4. 持续优化改进

**祝使用愉快！** 🚀

# MCP Playwright Server - 代码重构说明

## 重构目标

将原有的 1404 行单文件代码 (`mcp_sse_official.py`) 拆分为清晰的模块化结构，便于维护和扩展。

## 新的目录结构

```
playwright/
├── mcp_server/                 # 核心模块目录
│   ├── __init__.py            # 模块导出
│   ├── config.py              # 配置常量 (20行)
│   ├── models.py              # 数据模型 (35行)
│   ├── browser_manager.py     # 浏览器管理器核心类 (900行)
│   └── tools.py               # MCP 工具定义 (350行)
├── mcp_sse_server.py          # 新的模块化入口 (150行)
├── mcp_sse_official.py        # 原始文件（保持不变，继续使用）
└── mcp_sse_official_backup.py # 原始文件备份
```

## 模块说明

### 1. `mcp_server/config.py`
- 服务器配置常量（HOST, PORT）
- 截图目录配置
- Playwright 路径修复逻辑

### 2. `mcp_server/models.py`
- `BrowserSession` 数据类
- 会话状态管理

### 3. `mcp_server/browser_manager.py`
- `PlaywrightBrowserManager` 类
- 所有 23 个浏览器操作方法
- 会话生命周期管理
- 辅助方法（选择器判断等）

### 4. `mcp_server/tools.py`
- `create_tools()`: 创建 23 个 MCP 工具定义
- `handle_tool_call()`: 工具调用分发处理

### 5. `mcp_sse_server.py`
- SSE 服务器主入口
- MCP 服务器初始化
- Starlette 应用配置
- 路由定义

## 使用方式

### 继续使用原版本（推荐，已稳定）
```bash
python playwright/mcp_sse_official.py
```

### 使用模块化版本（测试中）
```bash
python playwright/mcp_sse_server.py
```

## 重构优势

1. **可维护性**: 每个模块职责单一，易于理解和修改
2. **可扩展性**: 新增工具只需修改 `browser_manager.py` 和 `tools.py`
3. **可测试性**: 各模块可独立测试
4. **代码复用**: 浏览器管理器可被其他项目导入使用

## 注意事项

- 原始文件 `mcp_sse_official.py` 保持不变，继续稳定运行
- 模块化版本需要测试验证后才能替代原版本
- 两个版本功能完全一致，只是代码组织方式不同

## 下一步

1. 测试模块化版本的功能完整性
2. 验证所有 23 个工具正常工作
3. 确认无性能退化
4. 逐步迁移到模块化版本

# Playwright MCP Server

基于 Playwright 的 MCP (Model Context Protocol) 服务器，提供浏览器自动化功能，可通过 Dify Agent 调用。

## 功能特性

- ✅ 支持 23 种浏览器自动化操作
- ✅ 自动管理浏览器会话（无需手动传递 session_id）
- ✅ 智能定位器（支持 CSS 选择器、文本定位、placeholder 定位）
- ✅ 异步 API，兼容 Dify 的异步环境
- ✅ SSE (Server-Sent Events) 传输协议

## 核心文件

- `mcp_sse_official.py` - MCP SSE 服务器主程序
- `login_yunpian.py` - 云片网登录示例脚本

## 启动服务器

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动 MCP SSE 服务器
python playwright/mcp_sse_official.py
```

服务器将在 `http://localhost:3334` 启动，提供以下端点：
- `/sse` - SSE 连接端点（用于 Dify）
- `/mcp` - SSE 连接端点别名
- `/health` - 健康检查端点

## Dify 配置

在 Dify 的 MCP 工具配置中：
- **服务器端点 URL**: `http://host.docker.internal:3334/sse`
- **传输方式**: SSE (Server-Sent Events)

## 可用工具

### 浏览器操作
- `browser_launch` - 启动浏览器
- `browser_close` - 关闭浏览器
- `browser_navigate` - 导航到指定 URL
- `browser_navigate_back` - 返回上一页
- `browser_resize` - 调整窗口大小

### 页面交互
- `browser_click` - 点击元素（支持 CSS 选择器、文本定位）
- `browser_type` - 输入文本（支持 CSS 选择器、placeholder 定位）
- `browser_hover` - 悬停元素
- `browser_drag` - 拖拽元素
- `browser_select_option` - 选择下拉选项
- `browser_press_key` - 按键操作

### 页面信息
- `browser_snapshot` - 获取页面快照
- `browser_take_screenshot` - 截图
- `browser_console_messages` - 获取控制台消息
- `browser_network_requests` - 获取网络请求

### 高级功能
- `browser_wait_for` - 等待条件
- `browser_evaluate` - 执行 JavaScript
- `browser_run_code` - 运行 Playwright 代码
- `browser_fill_form` - 批量填写表单
- `browser_file_upload` - 文件上传
- `browser_handle_dialog` - 处理对话框
- `browser_tabs` - 标签页管理
- `browser_install` - 安装浏览器

## 使用示例

### 在 Dify Agent 中使用

提示词示例：
```
访问 https://www.yunpian.com/entry，使用邮箱登录，用账号 2006zhouhang@163.com 和密码 19861201zh 进行登录，并把欢迎页主要信息返回给我
```

LLM 会自动调用以下工具：
1. `browser_navigate({"url": "https://www.yunpian.com/entry"})`
2. `browser_click({"selector": "邮箱登录"})` - 自动使用文本定位
3. `browser_type({"selector": "输入注册邮箱地址", "text": "2006zhouhang@163.com"})` - 自动使用 placeholder 定位
4. `browser_type({"selector": "8-24位，至少包含数字、英文、符号中的两种", "text": "19861201zh"})`
5. `browser_click({"selector": "登 录"})`
6. `browser_snapshot()` - 获取欢迎页信息

## 定位器说明

### CSS 选择器
```json
{"selector": "#button"}
{"selector": ".class-name"}
{"selector": "button[type='submit']"}
```

### 文本定位器
```json
{"selector": "邮箱登录"}  // 自动匹配包含该文本的元素
```

### Placeholder 定位器
```json
{"selector": "输入注册邮箱地址"}  // 自动匹配 placeholder 属性
```

## 注意事项

1. 所有工具调用无需传递 `session_id`，系统会自动管理浏览器会话
2. 使用文本定位器时，会先尝试精确匹配，失败后尝试模糊匹配
3. 服务器默认在非无头模式下运行，可以看到浏览器操作过程
4. 如果 Dify 运行在 Docker 中，使用 `host.docker.internal` 访问宿主机服务


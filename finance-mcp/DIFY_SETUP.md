# Dify MCP 配置指南

## ✅ 问题已解决！

对账 MCP 服务器现在已经可以正常连接了。

## 🌐 服务器信息

- **服务器地址**: `http://localhost:3335`
- **SSE 端点**: `http://localhost:3335/sse`
- **MCP 端点**: `http://localhost:3335/mcp` (别名)
- **健康检查**: `http://localhost:3335/health`
- **消息端点**: `http://localhost:3335/messages/`

## 📝 在 Dify 中配置 MCP

### 方法 1: 使用 SSE 端点（推荐）

```
MCP 服务器地址: http://host.docker.internal:3335/sse
```

### 方法 2: 使用 MCP 端点

```
MCP 服务器地址: http://host.docker.internal:3335/mcp
```

### 如果 Dify 在本地运行（非 Docker）

```
MCP 服务器地址: http://localhost:3335/sse
```

## 🔧 修复的问题

### 原始错误

1. **`Failed to connect to MCP server:`**
   - 原因: `SseServerTransport` 使用方式不正确
   - 解决: 修改为正确的 `async with` 语法并传递 `request.scope`

2. **`code=32600 message='Session terminated by server'`**
   - 原因: 缺少 `/mcp` 端点
   - 解决: 添加 `/mcp` 作为 `/sse` 的别名

### 修复后的代码

```python
# 创建 SSE Transport（全局实例）
sse_transport = SseServerTransport("/messages/")

# 处理 SSE 连接
async def handle_sse(request):
    """处理 SSE 连接"""
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options()
        )

# 路由配置
routes = [
    Route("/sse", endpoint=handle_sse, methods=["GET", "POST"]),
    Route("/mcp", endpoint=handle_sse, methods=["GET", "POST"]),  # 添加别名
    Mount("/messages/", app=sse_transport.handle_post_message),
    Route("/health", endpoint=health_check),
]
```

## 🛠️ 可用工具

配置成功后，Dify 可以使用以下 5 个工具：

1. **reconciliation_start** - 开始对账任务
2. **reconciliation_status** - 查询任务状态
3. **reconciliation_result** - 获取对账结果
4. **reconciliation_list_tasks** - 列出所有任务
5. **file_upload** - 上传文件

## 📊 测试连接

### 1. 健康检查

```bash
curl http://localhost:3335/health
```

预期返回:
```json
{"status":"healthy","service":"reconciliation-mcp-server","version":"1.0.0"}
```

### 2. SSE 连接测试

```bash
curl -N -H "Accept: text/event-stream" http://localhost:3335/sse
```

应该看到 SSE 流数据（不会立即关闭连接）

### 3. Python 测试脚本

```bash
cd /Users/kevin/workspace/financial-ai/reconciliation
source ../.venv/bin/activate
python test_mcp_connection.py
```

## 🚀 启动服务器

### 方法 1: 使用启动脚本

```bash
cd /Users/kevin/workspace/financial-ai/reconciliation
./start_server.sh
```

### 方法 2: 直接运行

```bash
cd /Users/kevin/workspace/financial-ai/reconciliation
source ../.venv/bin/activate
python mcp_sse_server.py
```

### 方法 3: 后台运行

```bash
cd /Users/kevin/workspace/financial-ai/reconciliation
source ../.venv/bin/activate
python mcp_sse_server.py > /tmp/reconciliation_server.log 2>&1 &
```

## 📋 管理命令

### 查看日志

```bash
tail -f /tmp/reconciliation_server.log
```

### 停止服务器

```bash
lsof -ti:3335 | xargs kill -9
```

### 检查服务器状态

```bash
lsof -ti:3335
# 如果有输出，说明服务器正在运行
```

## 🎯 在 Dify Agent 中使用

### 示例提示词

```
请帮我对账两个文件：
1. 业务流水文件：/path/to/business_flow.csv
2. 财务流水文件：/path/to/finance_flow.csv

对账规则：
- 按订单号匹配
- 金额差异容差为 2 元
- 财务金额需要从分转换为元（除以100）
```

### Agent 会自动调用工具

1. `reconciliation_start` - 创建对账任务
2. `reconciliation_status` - 查询任务进度
3. `reconciliation_result` - 获取对账结果

## ⚠️ 常见问题

### Q1: 连接超时

**原因**: 服务器未启动或端口被占用

**解决**:
```bash
# 检查服务器是否运行
curl http://localhost:3335/health

# 如果没有响应，重启服务器
lsof -ti:3335 | xargs kill -9
cd /Users/kevin/workspace/financial-ai/reconciliation
source ../.venv/bin/activate
python mcp_sse_server.py > /tmp/reconciliation_server.log 2>&1 &
```

### Q2: Docker 容器无法访问 host.docker.internal

**原因**: Docker 网络配置问题

**解决**:
1. 确保 Docker Desktop 已启动
2. 使用 `host.docker.internal` 而不是 `localhost`
3. 如果还不行，使用宿主机的实际 IP 地址

### Q3: 工具列表为空

**原因**: MCP 连接未成功建立

**解决**:
1. 检查服务器日志: `tail -f /tmp/reconciliation_server.log`
2. 确认 Dify 配置的地址正确
3. 重新连接 MCP 服务器

## 📚 相关文档

- [README.md](README.md) - 项目完整文档
- [OPTIMIZATION_SUMMARY.md](OPTIMIZATION_SUMMARY.md) - 优化说明
- [schemas/example_schema.json](schemas/example_schema.json) - Schema 示例

## ✅ 验证清单

- [ ] 服务器已启动 (`curl http://localhost:3335/health`)
- [ ] SSE 端点返回 200 (`curl http://localhost:3335/sse`)
- [ ] Dify 配置地址为 `http://host.docker.internal:3335/sse`
- [ ] Dify 中可以看到 5 个工具
- [ ] 测试工具调用成功

---

**最后更新**: 2026-01-06  
**服务器版本**: 1.0.0  
**状态**: ✅ 正常运行


# Dify MCP 配置指南

## 地址

- 推荐：`http://host.docker.internal:3335/sse`
- 本地：`http://localhost:3335/sse`
- 别名：`http://host.docker.internal:3335/mcp`

## 服务端点

- SSE: `http://localhost:3335/sse`
- MCP: `http://localhost:3335/mcp`
- Health: `http://localhost:3335/health`

## 当前工具分组

- 认证与规则：`auth_*`、规则查询、会话管理
- 上传：`file_upload`
- 文件校验：`validate_files`
- 数据整理规则：`proc_execute`
- 对账：`recon_execute`

## 快速检查

```bash
curl http://localhost:3335/health
curl -N -H "Accept: text/event-stream" http://localhost:3335/sse
```

## 启动

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

## 注意

- 旧的 `reconciliation_*`、`data_preparation_*` 工具已经移除。
- `file_upload` 现在是公共工具，位于 `finance-mcp/tools/file_upload_tool.py`。

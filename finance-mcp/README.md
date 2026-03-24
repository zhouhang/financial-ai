# Finance MCP

统一的财务 MCP 服务，当前只保留以下运行时模块：

- `auth`：认证、组织管理、会话管理
- `tools/file_upload_tool.py`：公共文件上传
- `tools/file_validate_tool.py`：文件校验
- `tools/rules.py`：规则读取与任务列表
- `proc`：数据整理规则执行
- `recon`：对账执行

## 服务地址

- SSE: `http://localhost:3335/sse`
- MCP: `http://localhost:3335/mcp`
- Health: `http://localhost:3335/health`
- Output: `http://localhost:3335/output/{module}/{path}`

其中 `module` 仅支持：

- `proc`
- `recon`

## 当前 MCP 工具

| 工具名称 | 描述 |
| --- | --- |
| `auth_register` | 注册 |
| `auth_login` | 登录 |
| `auth_me` | 获取当前用户 |
| `create_conversation` | 创建会话 |
| `list_conversations` | 查询会话列表 |
| `get_conversation` | 查询会话详情 |
| `delete_conversation` | 删除会话 |
| `save_message` | 保存消息 |
| `list_company` | 查询公司 |
| `list_departments` | 查询部门 |
| `admin_login` | 管理员登录 |
| `create_company` | 创建公司 |
| `create_department` | 创建部门 |
| `get_admin_view` | 查询管理视图 |
| `file_upload` | 上传文件 |
| `validate_files` | 校验文件 |
| `get_rule` | 查询规则内容 |
| `list_user_tasks` | 查询用户任务 |
| `proc_execute` | 执行数据整理规则 |
| `recon_execute` | 执行对账规则 |

## 启动

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

## 说明

- 旧的 `reconciliation` 与 `data_preparation` 独立 MCP 工作流已移除。
- `file_upload` 已迁移到公共目录 `finance-mcp/tools/`。

## Why

管理员登录成功后以及输入"创建公司"/"创建部门"时，前端显示原始 JSON 而不是渲染表单。这是因为前端提交的 `form_type` 使用连字符（如 `admin-login`），而后端期望下划线（如 `admin_login`），导致表单提交无法被正确识别处理。

## What Changes

- 修复前端表单 ID 与后端 form_type 的命名不一致问题
- 统一使用下划线命名（符合 Python 命名规范）
- 确保管理员表单（登录、创建公司、创建部门）能正确渲染和提交

## Capabilities

### New Capabilities

无

### Modified Capabilities

- `admin-form-handling`: 修复管理员表单的 form_type 命名，使前后端一致

## Impact

- **前端**: `finance-agents/data-agent/app/graphs/main_graph/forms.py` - 修改表单 ID
- **后端**: 无需修改（已使用下划线命名）
- **测试**: 需要验证管理员登录、创建公司、创建部门功能正常工作

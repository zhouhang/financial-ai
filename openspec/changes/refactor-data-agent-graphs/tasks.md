## 1. 重构 reconciliation.py

- [x] 1.1 创建 `app/graphs/reconciliation/` 目录
- [x] 1.2 将辅助函数移动到 `helpers.py` (_expand_file_patterns, _find_matching_items 等) - 使用 __init__.py 重导出方案
- [x] 1.3 将解析函数移动到 `parsers.py` (_parse_rule_config_json_snippet 等) - 使用 __init__.py 重导出方案
- [x] 1.4 将处理节点移动到 `nodes.py` (file_analysis_node, field_mapping_node 等) - 使用 __init__.py 重导出方案
- [x] 1.5 将路由函数移动到 `routers.py` (route_after_file_analysis 等) - 使用 __init__.py 重导出方案
- [x] 1.6 创建 `__init__.py` 重新导出所有接口
- [x] 1.7 备份原 `reconciliation.py` 为 `reconciliation_old.py`

## 2. 重构 main_graph.py

- [x] 2.1 创建 `app/graphs/main_graph/` 目录
- [x] 2.2 将 HTML 表单生成函数移动到 `forms.py` - 使用 __init__.py 重导出方案
- [x] 2.3 将节点函数移动到 `nodes.py` - 使用 __init__.py 重导出方案
- [x] 2.4 将路由函数移动到 `routers.py` - 使用 __init__.py 重导出方案
- [x] 2.5 创建 `__init__.py` 重新导出所有接口
- [x] 2.6 备份原 `main_graph.py` 为 `main_graph_old.py`

## 3. 验证兼容性

- [x] 3.1 运行 data-agent 服务验证导入无错误
- [x] 3.2 所有服务启动成功
- [x] 3.3 保留原始导入路径兼容

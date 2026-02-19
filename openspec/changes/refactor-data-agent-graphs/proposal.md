## Why

`main_graph.py` (1007行) 和 `reconciliation.py` (2535行) 代码行数过多,导致:
- 代码难以阅读和理解
- 维护困难,修改一个功能需要理解整个文件
- 难以进行单元测试
- 新成员上手成本高

通过重构将大型文件拆分为职责清晰的模块,可以提升代码可维护性,同时不影响现有功能。

## What Changes

- 将 `reconciliation.py` 拆分为多个模块:
  - `reconciliation/nodes.py`: 各个处理节点 (file_analysis_node, field_mapping_node 等)
  - `reconciliation/routers.py`: 路由函数 (route_after_file_analysis 等)
  - `reconciliation/helpers.py`: 辅助函数 (_expand_file_patterns, _find_matching_items 等)
  - `reconciliation/parsers.py`: 解析函数 (_parse_rule_config_json_snippet 等)
  - `reconciliation/__init__.py`: 导出接口,保持向后兼容
- 将 `main_graph.py` 拆分为多个模块:
  - `main_graph/forms.py`: HTML表单生成函数
  - `main_graph/nodes.py`: 节点函数
  - `main_graph/routers.py`: 路由函数
  - `main_graph/__init__.py`: 导出接口,保持向后兼容
- 确保所有导入路径兼容,现有代码无需修改

## Capabilities

### New Capabilities
- `graph-modularization`: 图模块化重构,将大型图文件拆分为独立模块

### Modified Capabilities
- (无)

## Impact

- **受影响代码**: 
  - `finance-agents/data-agent/app/graphs/main_graph.py` → 拆分为 `main_graph/` 目录
  - `finance-agents/data-agent/app/graphs/reconciliation.py` → 拆分为 `reconciliation/` 目录
- **相关模块**: 无
- **依赖**: 无新增外部依赖
- **兼容性**: 保持原有导入路径兼容,确保不破坏现有功能

## Context

当前 `main_graph.py` (1007行) 和 `reconciliation.py` (2535行) 是两个大型单文件模块,包含:
- 多个处理节点 (node functions)
- 多个路由函数 (router functions)
- 大量辅助函数和解析函数
- HTML 表单生成

需要拆分为职责清晰的模块,保持向后兼容。

## Goals / Non-Goals

**Goals:**
- 拆分 reconciliation.py 为 5 个模块文件 + __init__.py
- 拆分 main_graph.py 为 4 个模块文件 + __init__.py
- 保持原有导入路径兼容,现有代码无需修改
- 提升代码可读性和可维护性
- 确保重构后功能完全不变

**Non-Goals:**
- 不修改任何业务逻辑
- 不添加新功能
- 不改变外部 API 或导入接口

## Decisions

### Decision 1: 目录结构设计

**选择**: 将原 `.py` 文件转为目录,并创建多个模块文件

**理由**:
- Python 支持将 `module.py` 转为 `module/__init__.py`
- 只需在 `__init__.py` 中重新导出原有接口,即可保持兼容
- 用户无需修改任何导入路径

**结构**:
```
graphs/
├── reconciliation/
│   ├── __init__.py      # 重新导出所有接口
│   ├── nodes.py         # 处理节点
│   ├── routers.py       # 路由函数
│   ├── helpers.py        # 辅助函数
│   └── parsers.py       # 解析函数
├── main_graph/
│   ├── __init__.py      # 重新导出所有接口
│   ├── forms.py         # HTML 表单生成
│   ├── nodes.py         # 节点函数
│   └── routers.py       # 路由函数
└── ...
```

### Decision 2: 拆分粒度

**选择**: 按函数类型分类,不按功能拆分

**理由**:
- 辅助函数与节点函数数量相近,按功能拆分会导致某个文件仍过大
- 按类型拆分更清晰: 节点处理逻辑、路由决策、辅助工具、解析逻辑
- 便于理解代码职责

### Decision 3: 兼容策略

**选择**: 在 `__init__.py` 中使用 `from .xxx import *` 重新导出

**理由**:
- 最简单直接
- 无需修改调用方代码
- 原有 `from app.graphs.reconciliation import xxx` 仍然有效

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| 循环导入 | 拆分后可能出现循环导入 | 仔细规划导入顺序,必要时使用延迟导入 |
| 遗漏导出 | 某个函数未在 __init__.py 导出 | 编写测试验证所有导出可用 |
| 路径冲突 | 新目录与现有文件冲突 | 先备份原文件,再创建目录结构 |

## Migration Plan

1. **创建目录结构**: 创建 `reconciliation/` 和 `main_graph/` 目录
2. **移动代码**: 将原文件内容按类型拆分到各模块
3. **创建 __init__.py**: 重新导出所有接口
4. **备份原文件**: 将原 `.py` 文件移动为 `.bak` 备份
5. **验证兼容**: 运行测试确保导入路径兼容
6. **清理**: 删除备份文件

## Open Questions

1. **是否需要保留原文件作为代理?**
   - 建议保留 `reconciliation.py` 和 `main_graph.py` 作为兼容层,导入新模块
   - 这样最安全,即使有遗漏也能被发现

2. **是否需要更新其他导入这两个文件的地方?**
   - 不需要,重构设计为完全兼容

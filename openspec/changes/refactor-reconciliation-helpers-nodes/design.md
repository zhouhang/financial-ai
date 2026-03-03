## Context

当前 reconciliation 子图的 `helpers.py` (1992行) 和 `nodes.py` (2048行) 文件过大,难以维护:
- 单个文件超过2000行,难以阅读和导航
- 所有函数混在一起,职责不清晰
- 新开发者需要理解整个文件才能找到相关函数

`__init__.py` 已经使用 re-export 模式,所有公共接口都已导出,这为拆分提供了良好的基础。

## Goals / Non-Goals

**Goals:**
- 拆分 helpers.py 为 6 个职责单一的文件
- 拆分 nodes.py 为 8 个职责单一的文件
- 保持现有功能完全不变
- 保持向后兼容 (通过 __init__.py 重新导出)

**Non-Goals:**
- 不修改任何函数的内部实现
- 不添加新功能
- 不改变任何 API 接口

## Decisions

### Decision 1: 保持 __init__.py 不变作为兼容层

**选择**: 保留现有的 `__init__.py` re-export 模式

**理由**:
- 外部代码 (如 `server.py`, `workflow_intent.py`) 通过 `from app.graphs.reconciliation import ...` 导入
- 修改 __init__.py 的导入来源即可,无需修改调用方
- 这是最低风险的重构方式

### Decision 2: 使用子模块拆分 helpers.py

**选择**: 创建 `field_mapping_helpers.py`, `rule_config_helpers.py` 等子模块

**理由**:
- 每个文件专注单一职责
- 函数命名空间更清晰
- 便于未来添加相关功能

### Decision 3: 先拆分 helpers 再拆分 nodes

**选择**: 先拆分 helpers.py,再拆分 nodes.py

**理由**:
- nodes.py 依赖 helpers.py 中的函数
- 先拆分 helpers 可以减少后续的循环依赖问题

## Migration Plan

### Phase 1: 拆分 helpers.py

1. 创建新的子模块文件
2. 移动对应的函数到新文件
3. 更新 __init__.py 的导入来源
4. 运行测试验证功能不变
5. 删除原 helpers.py 中的函数(保留文件用于错误提示)

### Phase 2: 拆分 nodes.py

1. 创建新的子模块文件
2. 移动对应的函数到新文件
3. 更新 __init__.py 的导入来源
4. 运行测试验证功能不变
5. 删除原 nodes.py 中的函数

### Phase 3: 清理和验证

1. 删除空的或仅包含重定向的原始文件
2. 运行完整测试套件
3. 验证所有导入正常工作

## Risks / Trade-offs

- **风险**: 拆分过程中可能引入导入错误
- **缓解**: 
  - 每拆分一部分就运行测试
  - 保持 __init__.py 的兼容层
  - 使用 grep 确保没有遗漏的导入

- **权衡**: 重构期间代码库处于不稳定状态
- **缓解**: 快速完成重构,不要拖太久

## Open Questions

- 是否需要为新文件添加类型注解文件 (.pyi)?
  - 决定: 暂不需要,保持简单
  
- 是否需要更新文档?
  - 决定: 暂不需要,代码即文档

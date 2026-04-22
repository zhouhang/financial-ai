# Requirements: 财务对账方案创建体验重构

**Defined:** 2026-04-22
**Core Value:** 让财务人员以接近业务配置的方式，稳定生成可执行的 `proc json` 和 `recon json`，并能通过试跑快速修正到可用。

## v1 Requirements

### Workflow

- [ ] **FLOW-01**: 用户可以在固定 4 步向导中创建对账方案，第一步只填写方案名称和对账目的
- [ ] **FLOW-02**: 用户可以在第四步查看左右数据准备、对账规则和校验状态摘要后保存方案

### Dataset Preparation

- [ ] **DATA-01**: 用户可以在第二步分别选择左侧数据集和右侧数据集作为方案输入
- [ ] **DATA-02**: 用户可以分别管理左侧输出表和右侧输出表的输出字段列表，包括新增、删除和调整顺序
- [ ] **DATA-03**: 用户可以为每个输出字段自定义输出字段名
- [ ] **DATA-04**: 用户可以为每个输出字段配置取值方式，包括源字段映射、固定值、简单公式和多字段拼接
- [ ] **DATA-05**: 用户可以在第二步看到“筛选数据 / 行数据操作”区域作为后续能力预留，即使 v1 暂不支持实际编辑

### Proc Trial

- [ ] **PROC-01**: 用户可以让 AI 基于所选数据集推荐一版左右输出字段配置
- [ ] **PROC-02**: 用户可以手动修改 AI 推荐的字段配置，并保留修改结果作为后续试跑与保存依据
- [ ] **PROC-03**: 用户可以基于最新一次字段配置试跑 `proc`，并查看对应的左右侧输出样例数据，不混入旧结果
- [ ] **PROC-04**: 用户可以获得左右输出字段尽量对齐的提示，帮助后续 AI 生成更可靠的对账规则

### Reconciliation Rules

- [ ] **RECN-01**: 用户可以让 AI 基于第二步输出结构生成一版对账规则草稿
- [ ] **RECN-02**: 用户可以手动修改匹配字段、对比字段、时间字段等核心对账规则内容
- [ ] **RECN-03**: 用户可以基于最新一次对账规则试跑 `recon`，并查看对应的试跑结果与异常样例，不混入旧结果

### Controls

- [ ] **CTRL-01**: 用户可以在高级视图中查看生成的 `proc json` 和 `recon json`，但默认编辑界面不是 JSON
- [ ] **CTRL-02**: 用户只有在 `proc` 与 `recon` 都试跑成功后才能保存方案

## v2 Requirements

### Dataset Preparation

- **DATA-06**: 用户可以可视化配置真正生效的筛选数据条件
- **DATA-07**: 用户可以可视化配置真正生效的行数据操作链路

### Reuse

- **REUS-01**: 用户可以复用已有的数据整理模板和对账规则模板，减少重复配置

## Out of Scope

| Feature | Reason |
|---------|--------|
| 替换现有 `proc DSL` / `recon DSL` 底层模型 | 本次目标是改善财务配置体验，不重做执行引擎 |
| 让财务以 JSON 作为默认编辑界面 | 不符合财务用户心智，且会显著提高使用成本 |
| 在 v1 内完成完整的筛选数据 / 行数据操作可视化编辑器 | 当前先保留结构和入口，避免范围膨胀 |
| 脱离现有试跑执行链路另起一套生成、校验和保存机制 | 会制造双轨逻辑，增加维护和排障复杂度 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FLOW-01 | Phase 1 | Pending |
| FLOW-02 | Phase 5 | Pending |
| DATA-01 | Phase 2 | Pending |
| DATA-02 | Phase 2 | Pending |
| DATA-03 | Phase 2 | Pending |
| DATA-04 | Phase 2 | Pending |
| DATA-05 | Phase 2 | Pending |
| PROC-01 | Phase 3 | Pending |
| PROC-02 | Phase 3 | Pending |
| PROC-03 | Phase 3 | Pending |
| PROC-04 | Phase 3 | Pending |
| RECN-01 | Phase 4 | Pending |
| RECN-02 | Phase 4 | Pending |
| RECN-03 | Phase 4 | Pending |
| CTRL-01 | Phase 5 | Pending |
| CTRL-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---
*Requirements defined: 2026-04-22*
*Last updated: 2026-04-22 after initial definition*

# Roadmap: 财务对账方案创建体验重构

## Overview

这次路线图不是重做 `proc` / `recon` 引擎，而是围绕财务用户的使用路径，逐步把“新建对账方案”从技术导向的配置过程，收敛成“AI 推荐 + 人工修正 + 样例试跑 + 验证保存”的业务化工作流。路线会先稳定 4 步向导和草稿状态，再完成左右输出表配置、`proc` 试跑闭环、对账规则闭环，以及最终保存门禁与高级视图。

## Phases

- [ ] **Phase 1: Wizard Foundation** - 固化 4 步向导框架和方案草稿状态模型
- [ ] **Phase 2: Dataset Output Editor** - 完成第二步左右数据集选择与输出字段配置
- [ ] **Phase 3: Proc Recommendation Loop** - 打通 AI 推荐字段配置与 `proc` 试跑修正闭环
- [ ] **Phase 4: Recon Rule Loop** - 打通 AI 对账规则生成、人工修正与 `recon` 试跑闭环
- [ ] **Phase 5: Save Gate And Hardening** - 完成确认保存门禁、高级 JSON 视图与回归加固

## Phase Details

### Phase 1: Wizard Foundation
**Goal**: 建立新建对账方案的 4 步向导骨架、草稿状态模型和基础交互约束
**Depends on**: Nothing (first phase)
**Requirements**: [FLOW-01]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以进入新的 4 步对账方案向导，并清楚看到当前步骤与后续步骤
  2. 用户可以在第一步填写方案名称和对账目的，并在步骤切换时保留草稿状态
  3. 向导状态模型可以承接后续第二步和第三步配置，不要求用户直接编辑 JSON
**Plans**: 3 plans

Plans:
- [ ] 01-01: 梳理并改造新建方案草稿的数据模型、接口契约和页面入口
- [ ] 01-02: 实现 4 步向导框架、步骤切换与第一步表单
- [ ] 01-03: 搭建第四步确认页骨架与跨步骤状态同步机制

### Phase 2: Dataset Output Editor
**Goal**: 在第二步完成左右数据集选择、左右输出字段配置和能力预留区展示
**Depends on**: Phase 1
**Requirements**: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以分别选择左侧和右侧数据集，并加载各自字段元数据
  2. 用户可以分别管理左右输出字段列表，自定义字段名并配置映射、固定值、公式或拼接
  3. “筛选数据 / 行数据操作”区域在页面中可见但明确标记为后续版本能力
**Plans**: 3 plans

Plans:
- [ ] 02-01: 接入左右数据集选择、字段元数据加载和草稿持久化
- [ ] 02-02: 实现左右输出字段编辑器，支持增删字段、字段名编辑、顺序调整和取值方式配置
- [ ] 02-03: 增加筛选数据 / 行数据操作占位区，并统一第二步布局与交互反馈

### Phase 3: Proc Recommendation Loop
**Goal**: 让第二步具备 AI 推荐字段配置、人工修正和基于最新配置的 `proc` 试跑闭环
**Depends on**: Phase 2
**Requirements**: [PROC-01, PROC-02, PROC-03, PROC-04]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以触发 AI 推荐并得到一版左右输出字段建议
  2. 用户修改后的字段配置会成为当前权威版本，后续 `proc` 试跑只基于最新配置执行
  3. 用户可以查看左右侧试跑输出样例，并根据字段对齐提示快速修正配置
**Plans**: 3 plans

Plans:
- [ ] 03-01: 实现第二步 AI 字段推荐入口、生成契约和结果回填逻辑
- [ ] 03-02: 处理 AI 推荐与人工修改的合并规则，确保字段顺序和手工调整不被覆盖
- [ ] 03-03: 打通 `proc` 试跑、样例输出展示、旧结果清空和失败反馈

### Phase 4: Recon Rule Loop
**Goal**: 让第三步具备 AI 对账规则生成、人工修正和基于最新规则的 `recon` 试跑闭环
**Depends on**: Phase 3
**Requirements**: [RECN-01, RECN-02, RECN-03]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以基于第二步输出结构让 AI 生成一版对账规则草稿
  2. 用户可以手动调整匹配字段、对比字段和时间字段等核心规则内容
  3. `recon` 试跑始终使用最新规则配置，并返回可供财务判断的样例结果
**Plans**: 3 plans

Plans:
- [ ] 04-01: 设计并实现第三步对账规则编辑器的数据结构和交互形态
- [ ] 04-02: 打通 AI 对账规则生成、人工修正回写和规则状态管理
- [ ] 04-03: 打通 `recon` 试跑、样例结果展示和最新版本校验

### Phase 5: Save Gate And Hardening
**Goal**: 在第四步收口确认与保存逻辑，并补齐高级视图、门禁校验和回归验证
**Depends on**: Phase 4
**Requirements**: [FLOW-02, CTRL-01, CTRL-02]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以在第四步看到左右数据准备、对账规则和试跑状态摘要
  2. 只有当 `proc` 与 `recon` 都试跑成功时，保存按钮才可用
  3. 用户可以查看生成的 `proc json` 与 `recon json` 高级视图，同时主流程仍保持业务化编辑体验
**Plans**: 3 plans

Plans:
- [ ] 05-01: 完成第四步确认页、状态摘要和保存门禁逻辑
- [ ] 05-02: 增加高级 JSON 视图与配置一致性检查
- [ ] 05-03: 补齐端到端回归、自测脚本和关键交互验收清单

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Wizard Foundation | 0/3 | Not started | - |
| 2. Dataset Output Editor | 0/3 | Not started | - |
| 3. Proc Recommendation Loop | 0/3 | Not started | - |
| 4. Recon Rule Loop | 0/3 | Not started | - |
| 5. Save Gate And Hardening | 0/3 | Not started | - |

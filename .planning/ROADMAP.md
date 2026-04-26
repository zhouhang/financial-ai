# Roadmap: 财务对账方案创建体验重构

## Overview

这次路线图不是重做 `proc` / `recon` 引擎，而是分两条相互兼容的改造线推进。第一条是围绕财务用户的使用路径，逐步把“新建对账方案”从技术导向的配置过程，收敛成“AI 推荐 + 人工修正 + 样例试跑 + 验证保存”的业务化工作流。第二条是补齐文件型 `proc` / `recon` 的多 sheet 上传输入层，让单个工作簿也能在不改 DSL 的前提下接入现有 file_check、proc 和 recon 执行链路。

## Phases

- [x] **Phase 1: Wizard Foundation** - 固化 4 步向导框架和方案草稿状态模型
- [x] **Phase 2: Dataset Output Editor** - 完成第二步左右数据集选择与输出字段配置
- [x] **Phase 3: Proc Recommendation Loop** - 打通 AI 推荐字段配置与 `proc` 试跑修正闭环
- [x] **Phase 4: Recon Rule Loop** - 打通 AI 对账规则生成、人工修正与 `recon` 试跑闭环
- [x] **Phase 5: Save Gate And Hardening** - 完成确认保存门禁、高级 JSON 视图与回归加固
- [x] **Phase 6: Multi-Sheet Upload Intake** - 为文件型 `proc` / `recon` 增加多 sheet 拆分、预筛选和稳定命名

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
**Plans**: 1 plan

Plans:
- [x] 02-01: 接入左右数据集选择、左右输出字段编辑器和第二步占位能力区

### Phase 3: Proc Recommendation Loop
**Goal**: 让第二步具备 AI 推荐字段配置、人工修正和基于最新配置的 `proc` 试跑闭环
**Depends on**: Phase 2
**Requirements**: [PROC-01, PROC-02, PROC-03, PROC-04]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以触发 AI 推荐并得到一版左右输出字段建议
  2. 用户修改后的字段配置会成为当前权威版本，后续 `proc` 试跑只基于最新配置执行
  3. 用户可以查看左右侧试跑输出样例，并根据字段对齐提示快速修正配置
**Plans**: 1 plan

Plans:
- [x] 03-01: 打通 AI 字段推荐、人工修正保留和 `proc` 试跑闭环

### Phase 4: Recon Rule Loop
**Goal**: 让第三步具备 AI 对账规则生成、人工修正和基于最新规则的 `recon` 试跑闭环
**Depends on**: Phase 3
**Requirements**: [RECN-01, RECN-02, RECN-03]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以基于第二步输出结构让 AI 生成一版对账规则草稿
  2. 用户可以手动调整匹配字段、对比字段和时间字段等核心规则内容
  3. `recon` 试跑始终使用最新规则配置，并返回可供财务判断的样例结果
**Plans**: 1 plan

Plans:
- [x] 04-01: 打通结构化对账规则编辑、AI 生成回写和 `recon` 试跑闭环

### Phase 5: Save Gate And Hardening
**Goal**: 在第四步收口确认与保存逻辑，并补齐高级视图、门禁校验和回归验证
**Depends on**: Phase 4
**Requirements**: [FLOW-02, CTRL-01, CTRL-02]
**UI hint**: yes
**Success Criteria** (what must be TRUE):
  1. 用户可以在第四步看到左右数据准备、对账规则和试跑状态摘要
  2. 只有当 `proc` 与 `recon` 都试跑成功时，保存按钮才可用
  3. 用户可以查看生成的 `proc json` 与 `recon json` 高级视图，同时主流程仍保持业务化编辑体验
**Plans**: 1 plan

Plans:
- [x] 05-01: 收口第四步确认保存、JSON 高级视图、时间口径持久化与回归验证

### Phase 6: Multi-Sheet Upload Intake
**Goal**: 让文件型 `proc` / `recon` 可以直接消费单个 Excel 多 sheet 工作簿，通过上传输入层拆分、预筛选和稳定命名接入现有 file_check 与执行链路
**Depends on**: Nothing (shared backend capability)
**Requirements**: [FILE-01, FILE-02, FILE-03, FILE-04]
**UI hint**: no
**Success Criteria** (what must be TRUE):
  1. 上传单个多 sheet 工作簿后，系统会先拆成 sheet 级逻辑文件，再进入正式 `validate_files`，且现有 `proc` / `recon` DSL 无需改动
  2. 空白 sheet、说明 sheet 和明显不可能命中 schema 的 sheet 不会参与正式 schema 唯一映射，但真实歧义仍会保留并返回候选提示
  3. 拆分出的逻辑文件具备唯一稳定命名和原工作簿 / sheet 可追溯信息，`proc` 与 `recon` 共享同一套输入处理路径
**Plans**: 3 plans

Plans:
- [x] 06-01: 在共享上传入口增加多 sheet 工作簿拆分和临时逻辑文件生命周期管理
- [x] 06-02: 实现 sheet 级预筛选、唯一稳定命名，以及歧义候选映射的上抛与展示契约
- [x] 06-03: 为文件型 `proc` / `recon` 增加多 sheet 回归覆盖，包括说明页、空白页、宽松 schema 歧义和重名 sheet 场景

## Progress

**Execution Order:**
Phases 1 → 6 已全部完成本轮 v1 里程碑。Phase 6 以共享上传输入层方式交付了多 sheet 拆分、预筛选和稳定命名能力，未改动既有 `proc` / `recon` DSL。

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Wizard Foundation | 3/3 | Completed | 2026-04-22 |
| 2. Dataset Output Editor | 1/1 | Completed | 2026-04-22 |
| 3. Proc Recommendation Loop | 1/1 | Completed | 2026-04-22 |
| 4. Recon Rule Loop | 1/1 | Completed | 2026-04-22 |
| 5. Save Gate And Hardening | 1/1 | Completed | 2026-04-22 |
| 6. Multi-Sheet Upload Intake | 3/3 | Completed | 2026-04-23 |

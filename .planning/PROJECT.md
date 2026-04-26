# 财务对账方案创建体验重构

## What This Is

这是一个面向财务团队的 Financial AI 平台，现有系统已经支持数据库连接、数据集治理、数据整理 `proc` 执行、数据对账 `recon` 执行，以及对账方案、运行计划、运行记录和异常结果查看。当前工作是在现有底层能力之上，重构“新建对账方案”的交互，让财务人员不需要理解 JSON，也能更快地配置出可执行、可试跑、可修正的自动化对账方案。

## Core Value

让财务人员以接近业务配置的方式，稳定生成可执行的 `proc json` 和 `recon json`，并能通过试跑快速修正到可用。

## Requirements

### Validated

- ✓ 已支持数据库连接、数据发现和数据集治理流程，用户可以把业务数据接入平台并形成可选数据集 — existing
- ✓ 已支持 `proc` 数据整理执行和 `recon` 对账执行，底层已有可运行的规则引擎与输出产物 — existing
- ✓ 已支持对账方案、运行计划、运行记录和异常结果查看，平台已具备完整的执行链路骨架 — existing
- ✓ 已形成 React + FastAPI/LangGraph + MCP + PostgreSQL 的多服务架构，现有前后端与调度链路可承载增量重构 — existing
- ✓ 文件型 `proc` / `recon` 已支持单个 Excel 多 sheet 工作簿自动拆成 sheet 级逻辑文件，并继续复用现有规则执行链路 — Phase 6
- ✓ 多 sheet 输入已在正式 `file_check` 前执行保守预筛选，说明页、空白页和明显不命中 schema 的 sheet 不再干扰正式匹配 — Phase 6
- ✓ 拆分后的逻辑文件已具备稳定命名、工作簿 / sheet 溯源与歧义候选透传，`proc` / `recon` 共享同一套 intake 路径 — Phase 6

### Active

- [ ] 将“新建对账方案”重构为 4 步流程：第一步填写方案名称和对账目的；第二步选择左右数据集并配置左右输出表；第三步基于第二步输出配置和修正对账规则；第四步确认并保存
- [ ] 第二步分别配置左侧输出表和右侧输出表，支持动态增删输出字段，输出字段名由用户定义，字段值支持源字段映射、固定值、简单公式和多字段拼接
- [ ] 第二步由 AI 先生成一版左右输出字段推荐，财务可手动调整，并通过样例试跑快速验证和修正配置
- [ ] 第三步根据第二步输出结果由 AI 先生成一版对账规则，财务可手动修改匹配字段、对比字段和时间字段等核心内容，并通过样例试跑修正
- [ ] 左右两侧输出字段名尽量对齐，帮助第三步 AI 生成更可靠的对账规则，同时保留人工兜底能力
- [ ] `proc` 和 `recon` 都至少试跑成功后，才允许保存方案，避免保存不可执行配置
- [ ] 保留 JSON 作为高级查看或兜底能力，但不把 JSON 作为财务用户的主编辑入口
- [ ] 第二步中的“筛选数据 / 行数据操作”在 v1 先作为页面占位和结构预留，不实现实际编辑能力

### Out of Scope

- 重新设计或替换现有 `proc DSL` / `recon DSL` 底层模型 — 现有 DSL 已是平台真实执行底座，本次重构聚焦财务可用性，不重做引擎
- 让财务用户直接以 JSON 作为默认编辑面板完成方案配置 — 学习成本高、易出错，不符合本次体验目标
- 在 v1 中实现完整的行级筛选、行数据操作可视化编辑器 — 当前先保留页面结构，避免范围膨胀影响主流程上线
- 脱离现有试跑与执行链路另起一套生成或校验机制 — 会增加维护成本，并与既有执行能力脱节
- 为多 sheet 上传改造现有 `proc DSL` / `recon DSL` 语义或要求规则显式声明 sheet 名称 — 本次改造限定在上传输入层完成兼容

## Context

当前仓库是一个 brownfield 多服务单体仓：前端使用 React + Vite，后端由 `finance-agents/data-agent` 提供 FastAPI 与 LangGraph 编排，`finance-mcp` 提供数据源、规则、`proc`、`recon` 等能力，`finance-cron` 负责自动调度。现有系统已经跑通数据接入、方案配置、执行与结果查看等主链路，因此这次工作不是从零设计对账产品，而是在已有执行能力上重构“新建对账方案”的业务交互。

用户反馈已经明确指出，当前新建对账方案流程过度暴露底层技术细节，AI 生成与手工修正之间衔接差，财务用户难以稳定地产出可执行配置。尤其是数据整理规则和对账规则目前仍然过于接近 JSON / DSL 视角，导致财务需要理解系统内部结构，试跑后的修正成本也偏高。

本次重构的核心不是让 AI 完全替代人，而是让 AI 先给出一版建议，再让财务围绕样例结果快速校正。也就是说，页面需要围绕“推荐、试跑、修正、再试跑”的闭环来设计，保证最终产物仍然能自然编译到现有 `proc json` 与 `recon json`，并由既有执行引擎消费。

除了方案创建体验，当前又新增了一条共享底层能力需求：文件型 `proc` / `recon` 需要兼容单个 Excel 多 sheet 上传。现状是文件校验入口按“一个上传文件 = 一个可匹配输入”处理，Excel 读取表头时默认只看活动 sheet，这会让多 sheet 工作簿既无法被完整识别，也容易因为额外 sheet 干扰 schema 唯一映射和后续执行。

因此多 sheet 兼容的解法必须落在上传输入层，而不是改写现有 DSL。具体方向是：在正式 `validate_files` 前先把工作簿拆成多个临时逻辑文件，对每个 sheet 做轻量预筛选，只把候选 sheet 送入正式 file_check；随后用稳定且可追溯的命名把 sheet 文件接到现有 `table_name -> file_path` 映射，让 `proc` 和 `recon` 继续按原方式消费。

## Constraints

- **Tech stack**: 必须基于现有 `finance-web`、`finance-agents/data-agent`、`finance-mcp`、`finance-cron` 演进 — 这是已在线下验证过的主架构，不能为重构交互而推翻
- **Model compatibility**: 新交互最终必须落到现有 `proc DSL` 和 `recon DSL` — 现有执行、试跑、运行计划和结果查看都依赖这套底层模型
- **User profile**: 主用户是财务人员，不熟悉 JSON 和底层 DSL — 配置界面必须业务化、所见即所得、可通过试跑纠偏
- **Workflow shape**: 总体仍保持 4 步新建流程 — 用户已经确认这一操作结构更接近目标心智
- **Validation gate**: 保存前必须保证 `proc` 试跑成功且 `recon` 试跑成功 — 否则上线后仍会把不可执行配置带入运行链路
- **Scope control**: v1 只重构创建体验主链路，不同时展开完整筛选编辑器或底层 DSL 改造 — 避免范围失控导致交付延迟
- **Input-layer only**: 多 sheet 兼容必须在上传输入层解决，不改 `proc DSL` / `recon DSL`、不改现有规则描述方式
- **Shared path**: 文件型 `proc` 与文件型 `recon` 必须复用同一套拆分、预筛选和命名逻辑，避免后续两套行为漂移
- **Traceability**: 拆分出的逻辑文件必须能反查原始工作簿和 sheet 名称，便于报错提示、日志定位和人工排查

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 保留现有 `proc` / `recon` 底层 DSL，不新造一层替代模型 | 用户明确指出现有 `proc json` 就是底座，重构目标是改善财务交互而不是推翻执行模型 | — Pending |
| 新建对账方案保持 4 步，但把数据集选择移动到第二步 | 第一步只保留业务意图，第二步集中完成左右数据准备，更符合财务配置心智 | — Pending |
| 第二步分别配置左侧输出表和右侧输出表 | `proc` 的本质是把多数据源整理成可逐行对账的输出层，左右分开配置更贴近最终执行模型 | — Pending |
| 第二步输出字段支持源字段映射、固定值、简单公式和多字段拼接 | 这些能力已经被现有 `proc DSL` 支持，应该直接体现在面向财务的可视化配置里 | — Pending |
| AI 负责先生成推荐，人工负责接受、修改和兜底 | 用户明确不接受纯 AI 黑盒，必须让财务能在样例和结果反馈下修正 | — Pending |
| 左右输出字段名尽量对齐 | 有利于第三步 AI 生成更稳定的对账规则，也降低人工理解成本 | — Pending |
| 保存方案前必须先完成 `proc` 与 `recon` 试跑验证 | 目标不是“生成一份草稿”，而是“产出可执行方案” | — Pending |
| JSON 只保留为高级视图，不作为默认编辑面板 | 财务用户的主路径应是业务配置，不应被 DSL 细节绑架 | — Pending |
| 多 sheet 兼容放在上传输入层，不改现有 `proc` / `recon` DSL | 运行时本质上依赖 `table_name -> file_path`，问题在于上传入口无法正确拆分和识别工作簿 | Implemented in Phase 6 |
| 多 sheet 工作簿先拆 sheet 再做正式 file_check | 如果把全部 sheet 直接当上传文件，会放大宽松 schema 的唯一映射歧义，也会让正式匹配输入掺入噪音 sheet | Implemented in Phase 6 |
| 预筛选只负责过滤明显无效 sheet，不直接替代正式 schema 匹配 | 需要保留现有 `validate_files` 作为权威匹配器，同时把真正的歧义继续暴露给用户 | Implemented in Phase 6 |
| 拆分后的逻辑文件名需唯一稳定，并带原工作簿与 sheet 追踪信息 | 既要避免同名 sheet / 多工作簿冲突，也要保证报错、日志和调试能回溯来源 | Implemented in Phase 6 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-23 after completing multi-sheet upload intake*

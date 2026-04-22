# Phase 1: Wizard Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 01-Wizard Foundation
**Areas discussed:** Step framing, Draft authority, Wizard shell, API boundary, JSON surface

---

## Step Framing

| Option | Description | Selected |
|--------|-------------|----------|
| 保持当前 1/2 步分布 | Step 1 继续承载方案目标、左右数据选择和口径描述 | |
| Step 1 只保留业务意图，数据集移到 Step 2 | Step 1 只填名称与对账目的；Step 2 进入数据准备主流程 | ✓ |
| 压缩为 3 步 | 合并确认页或规则页，减少显式步骤数 | |

**User's choice:** Step 1 只保留业务意图，左右数据集选择与后续配置全部移到 Step 2。
**Notes:** 用户已明确要求仍保持 4 步，但把数据集选择放到第二步，第四步保留确认保存。

---

## Draft Authority

| Option | Description | Selected |
|--------|-------------|----------|
| 继续扩张当前扁平 `schemeDraft` | 名称、数据、规则、试跑结果和 JSON 全部混在一个对象里 | |
| 分成步骤切片 + 派生工件版本 | 用户业务配置为权威数据，JSON / 试跑结果作为带版本的派生工件 | ✓ |
| 每次编辑都立即持久化到后端草稿 | 前端状态尽量薄，把草稿管理转给后端 | |

**User's choice:** 采用步骤切片 + 派生工件版本的模型。
**Notes:** 用户反复强调“试跑必须基于最新配置”“不能混用上一次结果”，因此需要显式失效和版本边界。

---

## Wizard Shell

| Option | Description | Selected |
|--------|-------------|----------|
| 复用现有 `ReconWorkspace` 弹窗 | 在当前工作区内重构向导壳和步骤内容 | ✓ |
| 改成独立页面 | 把创建方案抽离出当前 modal / workspace 结构 | |
| 改成侧边抽屉流 | 在右侧或底部做新的分步容器 | |

**User's choice:** 复用现有 `ReconWorkspace` 弹窗作为 Phase 1 壳。
**Notes:** 当前代码和交互都已沉淀在现有 modal 里，Phase 1 重点是框架和状态收口，不是迁移入口。

---

## API Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| 为新向导另起一套后端协议 | 先改保存模型和设计接口，再改前端 | |
| 继续复用 design session + `/schemes` 保存接口 | 前端通过适配层把新草稿模型编译到现有接口 | ✓ |
| 前端跳过 design session 直接本地生成 | 弱化后端会话层，主要在前端拼装 | |

**User's choice:** 继续复用现有设计会话和保存接口。
**Notes:** 用户明确要求不要推翻底层 `proc` / `recon` 体系，因此 Phase 1 不能先重写后端契约。

---

## JSON Surface

| Option | Description | Selected |
|--------|-------------|----------|
| JSON 作为默认编辑面板 | 财务直接编辑 `proc json` / `recon json` | |
| 业务配置为主，JSON 仅高级查看 | 默认面向财务，JSON 作为补充或兜底查看面 | ✓ |
| 完全隐藏 JSON | 不再让用户看到底层 JSON | |

**User's choice:** 业务配置为主，JSON 仅保留高级查看能力。
**Notes:** 用户已明确表示财务不懂 JSON，主路径必须业务化；但底层 JSON 仍需保留为高级视图和对齐现有引擎的出口。

---

## the agent's Discretion

- 前端状态容器最终采用 reducer、拆分 hooks 还是保持父组件 helper，留到 planning 决定。
- Step badge 和摘要卡片的视觉细节沿用现有 ReconWorkspace 风格即可。

## Deferred Ideas

- 真正可执行的筛选数据 / 行数据操作编辑器
- 更深度的整理规则 / 对账逻辑模板复用能力

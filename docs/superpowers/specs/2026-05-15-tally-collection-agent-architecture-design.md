# Tally 浏览器采集架构设计（顶层）

## 背景

`2026-05-07-auto-recon-platform-collection-design.md` 已经把数据库、淘宝/天猫、支付宝三类来源统一进 `collection_driver` 框架，但其中明确把"网页抓取或浏览器辅助采集"列为非目标。

首个 Tally 客户是淘宝/天猫商家，有 30+ 店铺，需要的核心数据：

- 淘宝订单
- 千牛资金（非支付宝渠道）

这两类数据的官方获取方式是淘宝 ISV 授权，但 ISV 申请门槛高，短期内无法落地。

2026-05-15 已经实证：用 Playwright + 真 Chrome + 持久化 profile + 受控访问节奏，能从千牛"财务-收支账单-日汇总"导出 T-1 资金明细 CSV。本次设计基于这次实证产出，确立 Tally 浏览器采集的顶层架构。

## 合规边界（实施前提）

本架构是 ISV 授权落地前的过渡方案，所有设计取舍受以下合规边界约束：

1. **仅采集商家自己的经营数据**，经商家书面授权，且 Tally 与商家之间签订《委托数据处理协议》。
2. **不做任何对抗或规避平台风控的技术手段**：不伪造浏览器指纹、不绕过验证码/短信/安全验证。遇到平台验证一律转人工完成。
3. **以"低频、错峰、固定身份"为访问原则**：每店采集低频次、时段分散、出口身份固定可识别，不隐藏、不伪装。
4. **数据全程境内**：采集节点、Tally 服务、数据库、LLM 调用均在中国境内；含买家个人信息的数据不出境。
5. **个人信息最小化**：只采集对账必需字段，买家个人信息能不存则不存、能脱敏则脱敏。
6. **ISV 是长期主线**：本方案定位为过渡，ISV 落地后迁回官方接口。

正式实施前须由网络法/数据合规专业律师出具法律意见。本文档不替代法律意见。

## 概念定义

三个概念职责不同，实现时不可混用：

| 概念 | 形态 | 职责 | 谁产出 / 谁消费 |
|---|---|---|---|
| **Authoring Skill** | Markdown | 给创作 agent 看的操作原则与避坑经验（如何稳定地操作某类站点） | 人工维护；创作 agent 读 |
| **Playbook** | JSON / DSL | 生产执行的确定性采集步骤定义 | 创作 agent 产出；采集节点解释执行 |
| **Runtime Profile** | 结构化记录 + 本地文件 | 一个店铺的运行上下文：账号凭证、cookie、浏览器 user-data-dir、出口分组绑定、下载目录、店铺绑定 | 采集节点本地生成与维护；生产采集时装配 |

**生产采集真正下发的是：`playbook` + `runtime profile` 引用 + `params`。**
- 只有 skill 不够：skill 是原则不是步骤，不能确定性重放。
- 只有 profile 不够：profile 是运行上下文，没有采集动作。
- 三者各司其职：skill 用于创作期，playbook + runtime profile 用于生产期。
- **Playbook JSON v1 必须在首店实施前冻结**：字段固定为 `schema_version` / `playbook_id` / `target` / `params_schema` / `steps` / `output` / `quality_gate` / `accounting_policy` / `failure_mapping`；生产 Runner 只接受通过 JSON Schema/Pydantic 校验的 playbook。AI 编码工具生成 playbook 时也必须以该 schema 为输出合同，不得输出自然语言步骤、凭证、cookie 或写死"昨天"。

## 目标

1. 用一套架构同时支撑两个能力：
   - **生产采集**：每天定时从千牛/天猫等浏览器端站点抓数据
   - **采集配方创作**：遇到新站点 / 新指标 / 站点改版时，靠 AI agent 探索并写出可重放的 playbook
2. 接入现有 `auto_scheme_run` / `sync_jobs` 任务契约，浏览器采集结果通过独立存储表发布到 `data_source_datasets`，不改 recon 上游消费方式。
3. 把"采集步骤"做成机器可执行 playbook，不让 LLM 进生产链路。
4. 创作与执行严格隔离：profile、出口 IP、运行时机互不污染。
5. 多店铺隔离：每店一份持久化 profile；出口按分组共享 2-3 条商业宽带。
6. Operator 是创作产物的最终质量门，自动校验只是辅助。

## 非目标

本设计不实现以下内容：

- 客户侧 Chrome 扩展或本地 agent 安装（拒绝客户侧部署，避免感知问题与安装成本）
- 任何对抗/规避平台风控的技术手段（指纹伪造、验证码绕过等一律不做，参见合规边界）
- LLM 实时驱动生产采集（生产链路必须确定性，不接 LLM API）
- 多 AI 模型混合编排（先单一选型 DeepSeek-V4 Pro + browser-use）
- 商家自助配置/提交 playbook（创作权限仅在 Operator 手中）
- 千牛 / 淘宝以外的浏览器站点适配（首期只验证千牛闭环；其他平台沿用本架构后续接入）

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      Tally Cloud                         │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Tally Main（Python 进程）                           │ │
│  │  ├─ recon engine（现有）                            │ │
│  │  ├─ auto_scheme_run / scheduler（现有，扩展）        │ │
│  │  ├─ Operator UI（现有后台，加 playbook / job 页）    │ │
│  │  ├─ Playbook Registry & Verification（新）          │ │
│  │  ├─ Agent Connection Manager(WS hub)（新）          │ │
│  │  └─ Production Push Dispatcher（新）                 │ │
│  └────────────────────────────────────────────────────┘ │
│                          │ 通过 authoring_jobs 表解耦     │
│  ┌───────────────────────▼────────────────────────────┐ │
│  │ Authoring Worker（独立 Python 进程，同 repo 同部署） │ │
│  │  - browser-use + DeepSeek-V4 Pro SDK                │ │
│  │  - Chrome + Xvfb                                    │ │
│  │  - 一次性临时 profile                                │ │
│  │  进程隔离：Chrome 卡死 / LLM 长任务 / 内存暴涨        │ │
│  │  不波及 Tally Main                                   │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │ WebSocket（cloud 推任务）
                          ▼
┌─────────────────────────────────────────────────────────┐
│         固定采集节点 ×N（唯一的 local agent）              │
│  - Python daemon                                         │
│  - Chrome + Xvfb + Playwright                            │
│  - 每店持久 Runtime Profile（/var/lib/tally-agent/...）   │
│  - 2-3 条商业宽带出口，店铺分组共享                        │
│  - Playbook Interpreter（解释 playbook → Playwright）     │
└─────────────────────────────────────────────────────────┘
```

部署形态：
- MVP：Tally Main 与 Authoring Worker 都在开发机以独立进程跑。
- 生产：同 repo 构建，docker-compose 内 `tally-main` 与 `tally-authoring` 为两个 service（或同镜像两个进程），不共用 Python 进程。

## 设计原则

1. **两平面分离**：系统分两个互不混淆的平面。**无人采集平面**（cron）只跑 profile 健康的店，100% 确定性、禁用 LLM、无任何人工介入；**创作平面**（白天交互）用 LLM 探索生成 playbook，可失败可重试。任何需要人的动作都归创作平面或异常处理，绝不塞进 cron。
2. **Runtime Profile 不可迁移**：profile 在哪台采集节点原生成长，任务就路由到哪台。Cloud 永远不持有 profile 文件。
3. **Playbook 是 cloud 资产**：playbook 在 Tally cloud DB 集中存储 + 版本管理。采集节点不存盘，每次任务消息里带。
4. **Push 触发模型**：cloud 主动 WebSocket 推任务到采集节点。节点启动后主动出 WS 上行连接，cloud 通过同一连接下推。
5. **Operator 是终审**：playbook 上线、approve 永远人工卡点；自动校验只过滤明显错误。
6. **进程隔离**：Authoring Worker 与 Tally Main 不共进程，浏览器/LLM 故障不拖垮主服务。
7. **采集与对账解耦**：浏览器采集 5-10min 长任务不得让 recon worker 同步阻塞等待。对账任务发现数据未就绪即置 `waiting_data` 让出 worker；采集由 Production Push Dispatcher 独立链路承载，完成后对账任务再被调度。
8. **YAGNI**：拒绝 Chrome 扩展、风控对抗工程、多模型编排、queue 中间件。在没遇到具体业务信号前不拆。

## 数据模型

### 新增表

#### `playbooks`
存 playbook 仓库 + 版本 + 生命周期。

| 列 | 说明 |
|---|---|
| `playbook_id` | 业务 ID（如 `qianniu-daily-bill-export`） |
| `version` | semver |
| `title` / `description` | Operator 可读说明 |
| `playbook_body` | JSONB，确定性步骤定义 |
| `status` | `draft` / `replayed` / `approved` / `canary` / `active` / `deprecated` |
| `schema_check_result` | JSONB |
| `replay_result` | JSONB |
| `sample_data_path` | 创作时附带的样本数据存储路径 |
| `transcript_path` | 创作会话 transcript |
| `created_by` / `approved_by` / `approved_at` | 审计字段 |
| `canary_started_at` / `canary_completed_at` | Canary 期记录 |
| `canary_shop_ids` | JSONB，本次灰度的店铺集合（默认 3 个，Operator 可调） |
| `emergency_page_changed` | bool，是否走页面改版紧急旁路（`approved → active` 直切，跳过 canary） |
| `bypass_canary_reason` | 紧急旁路时必填：跳过 canary 的原因 + 验证样本日期 + 审批人 |

#### `agents`
注册的固定采集节点。

| 列 | 说明 |
|---|---|
| `agent_id` | cloud 颁发，本机不可改 |
| `hostname` | 部署主机名 |
| `version` | daemon 版本 |
| `last_heartbeat_at` | 最近 ping 时间 |
| `status` | `online` / `offline` / `draining` |
| `capabilities` | JSONB（CPU / 内存等） |

#### `shop_runtime_bindings`
shop ↔ 采集节点 ↔ 出口分组 ↔ profile 状态绑定。

| 列 | 说明 |
|---|---|
| `company_id` | 租户，FK `company`——作用域字段，不靠模糊 `shop_id` 做全局隔离 |
| `data_source_id` | FK `data_sources`（每店一条，见「与现有采集框架的集成契约」）|
| `shop_id` | 商家店铺 ID |
| `agent_id` | 该店分配到的固定采集节点 |
| `egress_group` | 该店所属出口分组（对应一条商业宽带，长期稳定；30 店分组共享 2-3 条线） |
| `credential_ref` | 加密凭证引用（子账号用户名/密码，KMS 加密） |
| `profile_status` | `none` / `verifying` / `active` / `needs_reauth` / `risk_blocked`——**仅描述登录态/风控态**：`verifying`=注册中、首次验证尚未通过（不进 cron）；`needs_reauth`=登录失效（`AUTH_EXPIRED`）；`risk_blocked`=风控拦截（`RISK_VERIFICATION`）|
| `playbook_status` | `ok` / `stale`——`stale`=该店当前 playbook 因页面改版失效（`PAGE_CHANGED`），需重跑创作。页面改版与登录态无关，不写 `profile_status` |
| `cron_pause_reason` | 可空，人读原因码（`auth_expired` / `risk_blocked` / `page_changed`）：记录该店最近一次被移出 cron 的原因，供 Operator UI 展示 |
| `last_collection_at` | 最近一次成功采集时间 |

唯一约束：`UNIQUE (company_id, data_source_id)`——每店一条 data_source，绑定一一对应。凭证引用与 profile 路由必须在租户 + 数据源作用域内隔离。

**Playbook 注册时的首次验证流程**（决定 `profile_status` 从 `verifying` 进 `active` 的唯一路径）：

1. Operator 在 finance-web 的 **数据连接 → 浏览器** 页面(`BrowserPlaybookPanel`,复用了之前 `source_kind='browser'` 占位卡的位置)提交：playbook JSON body + 商家分配的"具有订单和资金数据下载权限的"子账号用户名/密码 + 验证用的 `biz_date`(默认最近 T-1)。
2. Tally 服务端：
   - 落 `playbooks` 行（`status='draft'`）和 `shop_runtime_bindings` 行（`profile_status='verifying'`、`playbook_status='ok'`、`credential_ref` 写入 KMS 加密的凭证引用）。
   - 同步触发**一次性验证采集** sync_job（同生产 RUN_PLAYBOOK 链路，下发 playbook + 凭证给绑定的 browser-agent），但带 `verification=true` 标志，让 agent 知道这是首次验证。
   - 等待该 sync_job 终态（成功 / 失败）。
3. 验证通过（sync_job `success` + 数据质量门过）→ `playbooks.status='active'`、`shop_runtime_bindings.profile_status='active'`。**profile 由 browser-agent 在采集节点本地用凭证登录并落盘**，后续生产采集直接复用这个 profile（凭证只在 profile 失效 / 风控拦截 / 显式 re-verify 时再次使用）。
4. 验证失败：
   - `AUTH_EXPIRED`（凭证错）→ 返回错误给 Operator 让其重填凭证，`playbooks.status='draft'`，binding 保持 `verifying`。
   - `PAGE_CHANGED` / `DATA_MISMATCH`（playbook 错）→ 返回错误让 Operator 重写 playbook，binding 保持 `verifying`。
   - `RISK_VERIFICATION` → binding 转 `risk_blocked`、`cron_pause_reason='risk_verification'`，提示 Operator 暂缓后人工处理（首店 v1 没有 noVNC，需人工到采集节点处理一次后重试注册）。
5. **Operator 看不到原始凭证 ↔ profile 的对应关系**：凭证存 KMS、profile 落 agent 本地磁盘，云端只持 `credential_ref` + `runtime_profile_ref` 两个引用。

**生产采集时的凭证下发**：每次 RUN_PLAYBOOK 消息都携带 `credential_ref`，agent 在执行前向 cloud 解密获取明文凭证（凭证读取走审计日志，见「凭证读取审计」）；优先复用本地持久 profile，profile 失效或缺失则用明文凭证现登录。这保证 profile 漂移、设备更换、二次首登（如 `needs_reauth`）等场景都不需要 Operator 重新跑注册流程，只需 Operator 在 Tally UI 触发一次 re-verify。

**`playbook_status` / `cron_pause_reason` 的恢复转换**（只定义进入不定义恢复会导致改完没人翻状态）：
- **进 `stale`**：`PAGE_CHANGED` 失败 → `playbook_status=stale`、`cron_pause_reason=page_changed`、移出 cron。
- **回 `ok`（主路径）**：重跑创作产出的新 playbook 版本 promote 到 `active` 后，**批量清理**受该 `playbook_id` 影响、且 `cron_pause_reason=page_changed` 的所有绑定 → `playbook_status=ok`、`cron_pause_reason=null`、重新进 cron。
- **回 `ok`（兜底）**：下一次成功采集也自动清 `stale`。
- 此清理**只针对 `page_changed`**：`auth_expired` / `risk_blocked` 不受 playbook promote 影响，须各自经 re-auth / 人工过验证后单独恢复。

#### `authoring_jobs`
创作任务（Operator 触发或失败自愈触发；MVP 仅 Operator）。Tally Main 与 Authoring Worker 通过此表解耦：Main 插入 `queued` 行，Worker 轮询领取。

| 列 | 说明 |
|---|---|
| `job_id` | UUID |
| `task_description` | Operator 输入的自然语言描述 |
| `authoring_skill_ref` | 注入到 system prompt 的 Authoring Skill 文件引用 |
| `parent_failure_id` | 关联的失败 sync_job（自愈用，Phase 2） |
| `status` | `queued` / `running` / `uploaded` / `approved` / `rejected` |
| `reject_reason` | rejected 时的原因（schema 校验失败、replay 失败、LLM 失败等） |
| `output_playbook_id` | 关联的 playbooks 表条目（成功后） |
| `llm_tokens_used` | 计费用 |
| `started_at` / `completed_at` | 审计 |

#### `browser_collection_records`
浏览器采集的结构化记录表（按采集方式独立存储，与 `dataset_collection_records`、支付宝结构化表平行）。**schema 与 `dataset_collection_records` 对齐**，直接复用其已验证的 `item_key` upsert 幂等模型（见下文「幂等写入模型」），不自造行身份机制。

| 列 | 说明 |
|---|---|
| `id` | 主键 uuid |
| `company_id` | 租户，FK `company` |
| `data_source_id` | FK `data_sources`（每店一条，见「与现有采集框架的集成契约」）|
| `dataset_id` / `dataset_code` | FK `data_source_datasets` |
| `resource_key` | 编码 `<playbook_id>@<version>`（店铺已由 `data_source_id` 隔离，见集成契约）|
| `shop_id` / `playbook_id` / `biz_date` | 业务维度（冗余列，便于按店/按 playbook 查询）|
| `item_key` | 单行业务主键，由 playbook 声明（如千牛账单流水号）|
| `item_key_values` | JSONB，主键字段拆解 |
| `item_hash` | 行内容指纹，用于判定 `unchanged` / `updated` |
| `payload` | JSONB，单行结构化数据 |
| `record_status` | `active` / `updated` / `unchanged` / `deleted` |
| `first_seen_job_id` / `latest_seen_job_id` | FK `sync_jobs`，`ON DELETE SET NULL` |
| `first_seen_at` / `latest_seen_at` | 审计 |
| `captured_at` / `created_at` / `updated_at` | 审计 |

唯一约束：`UNIQUE (company_id, dataset_id, biz_date, item_key)`——与 `dataset_collection_records` 一致。

> **唯一约束为何不含 `resource_key`**：`resource_key`（`<playbook_id>@<version>`）是 `sync_jobs` 的任务级 TTL 键，不是数据分区维度。Dispatcher 按店路由——`shop ∈ canary_shop_ids` 跑 canary 版本、否则跑 active 版本，二选一——所以**同一 `(shop, biz_date)` 不会被两个 playbook 版本同时写入**，`browser_collection_records` 始终是该店该日的单一生产真相。版本变更后的重采按 `item_key` latest-wins upsert（见「幂等写入模型」），即期望行为。canary 店的数据是这些店的真实经营数据、**正常进入 recon**；canary 隔离的是「哪些店用新 playbook 版本」，不是「扣住数据不发布」。

#### `browser_capture_files`
浏览器采集的原始文件（导出的 CSV/Excel 等），作为审计资产，不直接进 recon。

| 列 | 说明 |
|---|---|
| `file_id` | 主键 |
| `company_id` | 租户，FK `company`——审计文件同样按租户作用域隔离，不靠模糊 `shop_id` |
| `data_source_id` | FK `data_sources`（每店一条）|
| `dataset_id` | FK `data_source_datasets` |
| `sync_job_id` | 关联 `sync_jobs`，`ON DELETE SET NULL` |
| `resource_key` | 编码 `<playbook_id>@<version>`，便于按 playbook 版本审计 |
| `shop_id` / `playbook_id` / `biz_date` | 业务维度（冗余列，便于查询）|
| `storage_path` | 文件存储路径 |
| `encoding` / `checksum` / `row_count` | 文件元信息 |

### 存储与读取约定

- 浏览器采集结果写 `browser_collection_records`（结构化）+ `browser_capture_files`（原始文件审计）。
- 采集完成后统一发布到 `data_source_datasets`，recon loader 增加 `browser_collection_records` 数据类型即可消费。
- **表独立、模型复用**：不复用 `dataset_collection_records` 表本身（沿用 2026-05-07"按采集方式分存储"约定），但**复用其 `item_key` upsert 幂等模型与写入函数语义**（`finance-mcp/auth/db.py: upsert_dataset_collection_records`），不另造一套。
- `sync_jobs`、`dataset_bindings`、`data_source_datasets` 复用，写入方式与现有 driver 等价。

### 幂等写入模型

对账数据必须支持同一天重复采集、补采、覆盖更新。`browser_collection_records` 直接沿用 `dataset_collection_records` 的 `item_key` upsert 模型，不自造机制：

- **写入**：driver 拿到节点回传的明细行后，逐行算 `item_key`（playbook 声明的业务主键）+ `item_hash`（行内容指纹），按 `ON CONFLICT (company_id, dataset_id, biz_date, item_key)` upsert。
- **状态语义**：`item_hash` 未变 → `record_status = unchanged`，payload 不动；变了 → `updated`，写新 payload；首次出现 → 插入 `active`。`first_seen_job_id` 保留，`latest_seen_job_id` 每次刷新。
- **删除**：本次采集到的 `item_key` 集合相比上次缺失的行 → 标 `deleted`（软标记，不物理删，留审计）。**soft delete 只在一次完整成功采集后执行**——下载、解析、行数/金额质量门全部通过后，才允许据本次 `item_key` 集合计算缺失行并标 `deleted`；任何中途失败、部分文件解析异常的任务都**不触发** soft delete，避免误删有效历史行。MVP 可只做软标记。
- **playbook 约束**：`qianniu-daily-bill-export` 类 playbook 必须在 schema 里声明 `item_key` 字段（账单流水号等天然唯一列）。若页面无稳定行级唯一键，playbook 须以稳定列组合 hash 兜底，并在创作期 Sandbox Replay 校验 `item_key` 在样本内无碰撞。
- **重复采集幂等**：同店同 `biz_date` 二次采集（如重新对账触发补采）走同一 upsert，不产生重复行、不覆盖错误数据。
- **recon 读取规则**：recon 读 `record_status != 'deleted'` 的全部行——`active` / `updated` / `unchanged` **都要读**。`unchanged` 表示「上次采过、本次未变」的有效数据，绝不可漏读；只过滤 `deleted`。不依赖 sync_job 维度去重。

## 组件职责

### Cloud 端

#### Playbook Registry & Verification（Tally Main 内）

- 接受 Authoring Worker 上传的 3 件套（playbook / sample / transcript）+ replay 结果
- 跑 2 层云端校验：JSON Schema validator、Sample Data Checker
- Sandbox Replay 不在 Tally Main 跑（这里没有浏览器会话）——由 Authoring Worker 用确定性解释器执行后回传结果，Registry 据此推进状态机
- 维护 playbook 生命周期状态机：标准路径 `draft → replayed → approved → canary → active → deprecated`；**紧急旁路**：页面改版全量断采时允许 `approved → active` 直切，仅当 `emergency_page_changed=true`，且必须记录 `bypass_canary_reason`（跳过原因 + 验证样本 + 审批人），见「故障处理 / 页面改版紧急修复通道」
- 提供 Operator UI 数据查询接口

#### Agent Connection Manager（Tally Main 内 async 模块）

- 持有 `agent_id → WebSocket conn` 映射（进程内 dict）
- 接受采集节点主动连入（WSS upgrade，API Token 鉴权）
- 心跳保活 30s / 次，断连后更新 `agents.status`
- 上层 driver 调 `dispatch(agent_id, message, timeout)` 同步等结果
- 重连容忍（节点短断不丢任务）

跟 Tally Main 同进程同 event loop；用 asyncio task 跑 WS server。规模到多 replica Tally Main 时（不在 MVP 范围）再考虑外移成 sticky-session 服务或加 Redis 协调。

#### `browser_playbook_remote` collection_driver（Tally Main 内）

接现有 `BaseConnector` / factory 模式，挂到 `finance-mcp/connectors/providers/`，注册为新 `source_kind = browser_playbook`（**不进 `AGENT_ASSISTED_KINDS`**，路由细节见「与现有采集框架的集成契约」）。

- 由 `auto_scheme_run` / `data_source_trigger_dataset_collection` 触发
- **健康门（与 Dispatcher 对称）**：创建/复用采集 job 前先查 `shop_runtime_bindings`——若 `profile_status != active` 或 `playbook_status != ok`，**不创建 `pending` job**，直接给对账任务返回 `unavailable` + 原因码（`auth_expired` / `risk_blocked` / `page_changed`），对账任务记「数据不可用、人工处理中」失败，不进 `waiting_data` 空等
- **不同步等采集结果**（见「采集与对账解耦」）：健康门通过后，`create_or_reuse_dataset_collection_sync_job` 落一条 `pending` 采集 `sync_job` 后立即返回，对账任务置 `waiting_data`、让出 recon worker
- 实际下推 `RUN_PLAYBOOK`、收 `TASK_RESULT`、解析回传数据由 Production Push Dispatcher 链路承担——driver 不持有 5-10min 的长 `await`
- 数据回写：写 `browser_collection_records` + `browser_capture_files`，发布 `data_source_datasets`

#### Authoring Worker（独立 Python 进程，**v2**）

> **v1 / v2 分级**:
> - **v1（首店阶段）**：Operator 本机用 AI 编码工具(Claude Code 或 codex)+ DeepSeek-V4 Pro 协助跑出 playbook JSON;然后通过 finance-web 的「数据连接 → 浏览器」页面(`BrowserPlaybookPanel`)粘贴 JSON + 凭证手动提交;首次验证由 Tally 服务端异步触发(见「Playbook 注册时的首次验证流程」),前端轮询 sync_job 状态后调 finalize 激活。Operator 本机的 AI 编码工具部分是个人开发工具流、**不属于生产架构组件**;前端注册页面**是 v1 必备**。
> - **v2**：自研 Authoring Worker,**封装 Claude Agent SDK + DeepSeek-V4 Pro**,在 Tally 内置 web UI 提供与 v1 一致的自然语言生成 playbook 体验,但移除"Operator 本机依赖外部 AI IDE"。Authoring Worker 仍独立进程跑,首次验证仍走 v1 同一通道。

模块路径(v2)：`finance-authoring/`。同 repo、同部署单元,但**独立 OS 进程**,不与 Tally Main 共用 Python 进程。

进程隔离理由：Authoring Worker 跑 Chrome + 长时 LLM 任务,存在卡死、内存暴涨风险;隔离后不波及 Tally Main 的 recon / 调度 SLA。

与 Tally Main 通过 `authoring_jobs` 表解耦：Worker 轮询 `status=queued` 的行领取任务。

v2 职责:
- **Claude Agent SDK + DeepSeek-V4 Pro 封装**：在 server 端复刻 v1 Claude Code/codex 的自然语言→playbook 能力。Operator 在 Tally web UI 用自然语言描述"我要采千牛日账单",worker 自动规划 + 浏览器探索 + 合成 playbook。
- 控制 Chrome + Xvfb 生命周期(一次任务一抛弃临时 profile);同采集节点装按需 `x11vnc` + `noVNC`,创作时若遇平台验证可由 Operator 经浏览器人工介入。
- **探索期**：Claude Agent + DeepSeek 自由探索目标站点,trace 记录每个实际生效动作(resolved selector / url / 输入值 + 足够的 DOM 信息)。
- **合成期**：一次合成 pass 从 trace 挑成功路径、丢试错,产出 schema 约束的确定性 playbook;对每个步骤做确定性 selector 加固。
- **Sandbox Replay**：用确定性 Playbook Interpreter 把合成出的 playbook 端到端重放一遍,校验复现样本数据。
- 产 3 件套 + replay 结果,调用 Playbook Registry 接口入库,Operator 在 web UI 提交凭证后进入「首次验证流程」。
- 计 token 消耗。

**playbook 生成方式（先探索后合成）**：探索本身是乱的（agent 会走死路、回退、重试），所以探索与产出分离——trace 只记实际生效的动作，合成 pass 再从 trace 挑出成功路径产出干净 playbook。合成不是凭空编 selector，而是从真实点中过的动作里挑选清理。

**selector 加固规则**：合成时不直接采用 browser-use 解析出的原始 selector（可能是脆弱的位置型 xpath）。按稳定性优先级重挑：`id` → `data-*` → `aria-label` → 唯一可见文本 → 位置型 xpath（兜底）。纯确定性规则，不经 LLM。

**replay 的边界**：Sandbox Replay 只证明 playbook「此刻可确定性重放」，不保证未来页面改版后仍可用；改版由生产期 `PAGE_CHANGED` 失败 → 重跑创作来兜。

#### Production Push Dispatcher（Tally Main 内）

**进程归属**：Dispatcher 运行在 Tally Main 进程内——它要调用 Agent Connection Manager 的 `dispatch(...)`，而后者持有的 `agent_id → WebSocket conn` 映射是 **Tally Main 进程内 dict**，独立进程够不到。`finance-cron` 不直接持有 WS、不下推 `RUN_PLAYBOOK`，只按 cron 配置在到点时调用 Tally Main 的 API/MCP 工具触发 Dispatcher 建采集计划；下推与结果回收全在 Tally Main 内完成。

职责：
- 调度时段 06:00-09:00 错峰，每店在窗口内随机分散起跑，不在同一刻齐发
- **按店解析 playbook 版本**：店 ∈ 对应 playbook 的 `canary_shop_ids` → 跑 `canary` 版本；否则跑 `active` 版本。调度整体同时覆盖 canary 店与 active 店；但**单个店同一 `biz_date` 只跑一个版本**
- **进 cron 的条件**：`profile_status = active` **且** `playbook_status = ok`。任一不满足即跳过该店——`needs_reauth` / `risk_blocked`（登录或风控问题）或 `stale`（playbook 因页面改版失效）都不进 cron
- 低频原则：同店每日采集次数受控，避免高频访问
- 失败重试按类型分级（见故障处理）：瞬时失败窗口内有限重试，确定性失败不重试；单店连续 3 次失败 → 暂停 + 告警飞书/钉钉

#### Operator UI

> **v1 实际实现位置**:`finance-web/src/components/BrowserPlaybookPanel.tsx`,通过 `数据连接 → 浏览器` 卡片进入。该卡片复用了原 `source_kind='browser'` 的预留位 —— v1 阶段 `browser` 占位卡彻底替换为 `browser_playbook` 真实功能。
>
> 「Playbooks」/「Authoring Jobs」/「Agents」/「Shops」4 个独立运营页面是 v2 范围;v1 通过 `数据连接 → 浏览器` 单一入口完成首店上线所需的全部 Operator 操作(注册 playbook + 凭证 + 触发首验 + 激活)。

**v1(已实现)**:`数据连接 → 浏览器` 页面提供:
- 列出当前公司所有 `source_kind='browser_playbook'` 的数据源,Operator 选一个作业。
- 列出该数据源下所有已发布的 `browser_collection_records` 数据集(首验需要选一个作为采集落地)。
- 表单录入:`playbook_id` / `version` / `title` / `playbook_body`(粘贴 Claude Code 或 codex 生成的 JSON 对象)+ `egress_group`(可选) + 商家子账号 `username` / `password` + `verification_biz_date`(默认昨天) + 选一个已发布的 browser dataset。**`shop_id` / `agent_id` 不在表单里**:`shop_id` 由后端从 `data_source.code` 派生;`agent_id` 由后端从 env `BROWSER_AGENT_DEFAULT_AGENT_ID`(默认 `browser-agent-local`)派生。v1 单节点无需 Operator 选 agent;Tally 直接把 sync_job 丢进队列,对应 `agent_id` 的 browser-agent 自己来 claim。
- 提交后调 `POST /api/data-sources/{source_id}/browser-playbook/register`,展示 `verification_sync_job_id`,**前端每 5s 轮询 sync_job 状态**(轮询上限 20 分钟)。
- `job_status='success'` 时显示「激活」按钮 → 调 `POST /api/data-sources/browser-playbook/finalize` 原子激活 `playbook=active + binding=active`。
- `job_status='failed'` 时直接展示 `browser_fail_reason` + `error_message`,Operator 修完表单重新提交即可(失败的 sync_job 沉淀为审计记录,不被生产 claim)。

**v2(后续)**:在 `BrowserPlaybookPanel` 基础上扩出独立 Playbooks / Authoring Jobs / Agents / Shops 4 个页面 + 自研 Authoring Worker 在 web UI 提供自然语言生成 playbook(详见决策记录与子项目拆分 P4 / P5)。

### Local Browser Agent（固定采集节点，`finance-agents/browser-agent/`）

`finance-agents/browser-agent/` 是浏览器采集的执行面：部署在固定采集节点上，负责解释 playbook、驱动 Playwright/Chrome、下载并解析文件、跑数据质量门、向 Tally Main 回传 `TASK_RESULT`。它不直接写 recon，不管理数据源配置，也不维护 playbook 生命周期。

`finance-mcp/browser_playbook/` 是 Tally Cloud 控制面：负责 playbook schema/注册、店铺绑定、`sync_jobs` 调度、结果入库、dataset 发布和 recon loader。两者通过 Agent Connection Manager 的 `RUN_PLAYBOOK` / `TASK_RESULT` 消息通信。

#### OS 底座
Ubuntu 22.04 LTS（无图形界面）+ Xvfb（systemd 自启，虚拟显示器）+ Chrome stable + 中文字体（noto-cjk、wqy-zenhei）+ Asia/Shanghai 时区。

另装 `x11vnc` + `noVNC`：平时不启动、零开销；仅当出现 `RISK_VERIFICATION` 需人工介入时按需拉起，Operator 用自己电脑的浏览器经 noVNC 连入 Xvfb 显示、人工过验证，处理完关闭。无图形界面的服务器靠这套即可被人工临时操作，不需要物理屏幕或 VNC 客户端。

#### Tally Production Daemon
- Python 3.11+ async event loop
- 启动时连 cloud（WSS，API Token 鉴权）
- 收 `RUN_PLAYBOOK` 消息执行任务
- 心跳 30s / 次
- 自带 `/health` endpoint 给 systemd watchdog

#### Playbook Interpreter
- 解析 playbook `steps` 数组
- 每个 `action` 类型映射到 Playwright 调用。v1 只允许线性动作白名单：`navigate` / `click` / `fill` / `set_date` / `wait_for` / `extract_text` / `extract_summary` / `download` / `parse_table` / `assert`。v1 不支持 branch / loop / LLM 指令；需要分支时升 playbook 新版本单独评审。
- 下载产物后跑**数据质量门**（见下节），未过门即快速失败、产物不上报
- 检测异常并以明确原因码快速失败：登录态失效 → `AUTH_EXPIRED`；步骤 selector 缺失 / 页面结构不符 → `PAGE_CHANGED`；中途出现风控验证 → `RISK_VERIFICATION`；数据质量门合计对不上 → `DATA_MISMATCH`。一律不等待、不做对抗、不在 cron 内引入人工环节
- 产 sync_jobs 风格的执行记录，失败时带原因码

#### 数据质量门
浏览器采集结果在节点本地、下载后 / 上报前过门；**失败即关闭——坏数据绝不进 recon / `data_source_datasets`**。这是对账产品，采错数据 = 直接产出错对账结果。

- **Layer 1 结构校验**：预期列名 / 列数 / 列类型（日期列可解析为日期、金额列可解析为数字）、编码无乱码、非空。playbook 自带预期 schema。失败归 `PAGE_CHANGED`。
- **Layer 2 完整性交叉校验**：playbook 除下载明细外，同时抓「收支账单-日汇总」页给出的当日**笔数 + 金额合计**；断言下载明细的行数与金额合计**归一化后精确等于**日汇总（财务数据，无容差），并断言数据日期 == 请求的 `biz_date`。失败归 `DATA_MISMATCH`。
- 历史合理区间校验（按店日笔数/金额对比历史区间软告警）不进 v1。

**金额口径定义**（Layer 2 比对前必须先归一化，否则会出现「字段口径错但总额碰巧对上」或「采集正确但校验失败」）：

- **数值类型**：所有金额转 `Decimal`，固定 2 位小数；字符串金额先去千分位分隔符、货币符号、首尾空白。禁止用 `float`。
- **正负号**：按千牛账单原始记账符号——收入为正、支出（退款 / 手续费 / 扣款）为负；日合计 = Σ(带符号金额)。playbook 须声明各业务类型的符号映射。
- **纳入范围**：playbook 显式声明哪些业务类型计入日合计——口径必须与千牛「日汇总」页一致：日汇总算什么，明细就比什么（订单货款、退款、平台手续费、优惠 / 补贴等逐项对齐）。
- **日期口径**：`biz_date` 以千牛账单的**入账日期 / 账务日期**为准（非下单日期）；时区 `Asia/Shanghai`；跨日入账归入实际入账日。
- **口径随 playbook 走**：不同 playbook（不同站点 / 报表）各自声明口径，质量门按 playbook 声明执行；口径定义是 playbook schema 的一部分，进 Operator review。

**playbook 创作约束**：`qianniu-daily-bill-export` 类 playbook 必须含「抓日汇总合计」步骤、声明预期 schema；且不得写死「下载昨天」，须接 `biz_date` 参数（使现有重新对账能补采指定日期，无需单建 backfill 组件）。

**Layer 2 可行性验收**：创作期必须用**至少 2-3 个真实日期样本**验证「下载明细 Σ 精确等于日汇总」确实可达——若千牛页面汇总口径与导出明细无法稳定精确对齐，该 playbook **不准进入生产**。生产侧坚持无容差（对账产品不可随意引入容差），可行性问题在创作期堵死，不留到生产期反复 `DATA_MISMATCH`。

#### Runtime Profile Manager
- 按 shop_id 装载 `/var/lib/tally-agent/profiles/<shop_id>/`
- **首次缺 profile**：用 cloud 下发的加密凭证（子账号用户名/密码）在本节点完成登录，创建持久化 profile。**profile 只在采集节点本地生成与落盘，云端 Tally 不生成、不持有 profile**；Tally 只下发 `playbook + 凭证`，登录与 profile 维护全部在节点本地完成。
- 探测 cookies 时效性（Cookies 文件 mtime + token 过期推断），失效即以 `AUTH_EXPIRED` 快速失败，标 `profile_status=needs_reauth`、移出 cron，等创作平面重跑创作
- 采集中途遇风控验证（验证码 / 滑块 / 安全验证）：不等待、不对抗，立即以 `RISK_VERIFICATION` 快速失败（见故障处理）

#### Egress 分组路由
- 采集节点置于 Tally 办公室，接 2-3 条 Tally 实名的商业宽带；30 店分组，每组挂一条线
- 按店的 `egress_group` 把该店 Playwright 流量路由到对应宽带线路（多 WAN 节点级路由，或每线一个本地转发）
- 出口长期稳定、不做轮换、不用商业代理（借陌生人住宅 IP 与「不伪装」合规边界冲突）
- 一个出口后挂若干授权店铺——这正是「代运营办公室」的正常画像，比一店一 IP 的孤立访问风控信号更低；分组的意义是炸开范围与冗余，某条线被风控波及时只影响该组

## 通信协议

### 传输
- WebSocket over TLS（WSS）
- 采集节点主动外出连接（hardpoint 在 cloud 公网/内网域名）
- 单条消息 JSON，最大 10MB（超过用 HTTP 旁路上传 + WS 传 URL）

### 两个超时（区分语义，勿混用）
- **ack_timeout（默认 30s）**：dispatch 后等节点确认收到 `RUN_PLAYBOOK` 的时间。超时即判节点离线/不可达 → `sync_jobs` failed。
- **task_timeout（browser playbook 默认 15min，可在 `RUN_PLAYBOOK` 用 `timeout_ms` 覆盖）**：节点已确认、正在执行 playbook，等 `TASK_RESULT` 的时间。超时即判任务卡死。默认值取 15min，是因为 v1 唯一关键场景（千牛日账单导出）耗时 5-10min，默认 5min 会频繁误判卡死。

### 鉴权
- API Token：cloud 颁发，节点部署时配置在 `/etc/tally-agent/config.yaml`
- Token 长期有效（手动 rotate）
- 后期需要时再加 mTLS（不在 MVP）

### 消息类型

#### Cloud → Agent

```
HELLO_ACK              # 鉴权握手成功
RUN_PLAYBOOK           # 推一次采集任务
  body:
    job_id, shop_id, playbook_body, params, runtime_profile_ref,
    egress_group, credential_ref, biz_date, timeout_ms
UPGRADE                # 推升级版本号 + 下载 URL
DRAIN                  # 准备下线，跑完手头任务后断开
```

#### Agent → Cloud

```
HELLO                  # 启动握手，带 agent_id + token + version
HEARTBEAT              # 30s / 次
TASK_RESULT            # RUN_PLAYBOOK 的结果
  body:
    job_id, status (success/failed),
    fail_reason (AUTH_EXPIRED / PAGE_CHANGED / RISK_VERIFICATION / DATA_MISMATCH / OTHER),
    data_url, error_info
HEALTH                 # CPU / 内存 / 磁盘
```

采集节点不存在「暂停等人工」的消息：遇验证 / 登录失效 / selector 缺失一律 `TASK_RESULT failed` 带 `fail_reason` 快速返回，人工动作发生在 cron 之外。

### 生命周期

```
agent boot
  → 连 cloud → HELLO
  → 收 HELLO_ACK
  → 进入心跳 + 监听任务 loop

采集触发（采集段，Dispatcher 主导）:
  finance-cron 到点 → 触发 Production Push Dispatcher
  → driver 健康门通过 → create_or_reuse pending 采集 sync_job
  → Dispatcher 领取 pending → dispatch(agent_id, RUN_PLAYBOOK)
  ↓ WebSocket
agent 收到：
  - 装载 / 首次创建 Runtime Profile（缺则用加密凭证登录）
  - 启 Playwright（持久 profile + egress_group 对应宽带出口）
  - 解释执行 playbook
  - 遇验证 / 登录失效 / selector 缺失 → 立即快速失败，带 fail_reason
  - 下载产物 → 过数据质量门 → 未过门即快速失败 DATA_MISMATCH
  - 成功则上传产物
  ↓
agent → TASK_RESULT（success，或 failed + fail_reason）
  ↓
Dispatcher 链路 → 写 sync_jobs / browser_collection_records / browser_capture_files
              → 发布 data_source_datasets（采集段结束）

对账段（独立、异步）:
  对账任务 auto_scheme_run → driver 检查数据 → ready 继续 / waiting 等待 / unavailable 失败

升级:
  cloud → UPGRADE
  agent → 下载 → 替换 → systemd 拉起新版本 → 重新 HELLO
```

## 数据流（端到端）

### 生产采集

```
═══ 采集段（Production Push Dispatcher 独立链路，不占 recon worker）═══

[06:00-09:00 错峰时段]
finance-cron 到点 → 调 Tally Main API/MCP 工具 → 触发 Production Push Dispatcher
  ↓
Dispatcher 遍历店铺：跳过 profile_status≠active 或 playbook_status≠ok 的店；
按店解析 playbook 版本（canary / active）→ create_or_reuse 一条 pending 采集 sync_job
  ↓
Dispatcher 按 agent 并发槽（默认 2）领取 pending（SELECT FOR UPDATE SKIP LOCKED），每店窗口内随机起跑
  ↓
查 shop_runtime_bindings → 取 agent_id + egress_group + credential_ref
  ↓
Agent Connection Manager.dispatch(agent_id, RUN_PLAYBOOK)  ──WebSocket──▶ 采集节点
  ↓
采集节点：装载 Runtime Profile（首次用凭证登录）→ 启 Chrome（持久 profile + egress_group 出口）
         → 解释执行 playbook → download CSV / 抓数据 → 过数据质量门
  ↓
节点 → cloud TASK_RESULT（含数据 URL）
  ↓
driver 拉取数据 → 解析 → 写 browser_collection_records + browser_capture_files
  ↓
发布 data_source_datasets → 采集 sync_jobs.status = success

═══ 对账段（recon worker 独立调度，与采集段异步）═══

对账任务 auto_scheme_run 启动 → resolve_plan_inputs → data_source_trigger_dataset_collection
  ↓
collection_driver = browser_playbook_remote → 健康门检查 shop_runtime_bindings
  ├─ profile/playbook 不健康 → 不建 job，对账任务 failed「数据不可用」+ 原因码
  └─ 健康 → create_or_reuse 采集 sync_job
       ├─ 采集未就绪 → recon_execution_queue job 置 waiting_data、让出 recon worker → poller 兜底恢复
       └─ 采集已 success、dataset 已发布 → 继续
  ↓
auto_scheme_run 继续 → proc/recon
```

### 采集配方创作

```
Operator 在 UI 点「新建 Authoring Job」，填任务描述
  ↓
Tally Main 插入 authoring_jobs 行（status=queued）
  ↓
Authoring Worker 轮询领取 → status=running → 启动 browser-use Agent
  ↓
Agent 多轮调用 Playwright → 探索目标站点 → 试错（探索期记 action trace）
  ↓ (Phase 2：中途需 Operator 介入 → 通过 Operator UI 聊天框打通)
探索成功 → 收敛出 sample-data + transcript
  ↓
Worker 合成 pass：从 trace 挑成功路径 → 产出确定性 playbook + selector 加固
  ↓
Worker 本地跑 Sandbox Replay（确定性解释器端到端重放，复现样本数据）
  ↓
Worker 调 Playbook Registry 接口入库 3 件套 + replay 结果 → status=draft
  ↓
Tally Main 跑云端校验：JSON Schema Validator + Sample Data Checker
  ↓ 通过（replay 已由 Worker 完成）
status=replayed
  ↓
Operator UI 出现 review 卡片
  ↓
Operator 审 sample / transcript / steps → Approve
  ↓
status=approved → Operator 设 canary_shop_ids（默认 3 店）→ status=canary
  ↓ Dispatcher 对 canary 店跑 canary 版本、其余店仍跑 active 版本，灰度 7 天（可调）
Operator review 灰度期数据 → 人工 promote
  ↓
canary 版本 → status=active，旧 active 版本 → status=deprecated，全量切换
```

## 并发与队列模型

v1 目标是 30 店每日自动 T-1 采集，单次浏览器任务耗时 5-10min。必须明确并发与隔离契约，否则浏览器长任务会拖垮现有 recon SLA。MVP 不引入独立 queue 中间件（YAGNI），用 `sync_jobs` 表 + 每 agent in-flight 计数 + dispatcher 错峰起跑实现软队列。

### v1 容量公式与默认值

```
窗口耗时 ≈ 店铺数 × 单任务平均耗时 ÷ agent_max_concurrency
```

- 取均值耗时 7.5min、窗口 06:00-09:00（180min）：30 店 ÷ 并发 1 = 225min **装不下**；÷ 并发 2 = 112min **装得下**。
- **v1 默认 `agent_max_concurrency = 2`，单采集节点**。Mac mini M2 16GB 同时跑 2 个 Chrome（各 ~2GB）有余量。
- **扩容触发条件**：店铺数或单任务耗时上涨到公式结果逼近窗口（如 > 150min）时，提升并发槽 / 扩窗口 / 加第二采集节点（加节点同时消除单节点 SPOF，见「容量规划」）。

### 采集与对账解耦（recon worker 不阻塞等浏览器采集）

浏览器采集单任务 5-10min。若让 recon worker 同步 `await` 采集结果，4 个 worker 会被长任务占满空转。故**采集与对账解耦，分两段独立调度**：

- **采集段**：Production Push Dispatcher 独立消费 `pending` 采集 `sync_job`——按 agent 并发槽 `SELECT ... FOR UPDATE SKIP LOCKED` 领取、下推 `RUN_PLAYBOOK`、收 `TASK_RESULT`、解析回写 `browser_collection_records` / `browser_capture_files`、发布 `data_source_datasets`。这条链路走独立 asyncio 任务组，**不从 recon / 数据库采集的 worker 池取槽**。
- **对账段**：`auto_scheme_run` 跑到需要浏览器数据的步骤时，`browser_playbook_remote` driver **不同步等结果**——先过健康门（见 driver 职责），通过则 `create_or_reuse` 采集 `sync_job`；若数据未就绪，把当前 recon 队列 job 从 `running` 改成新增的 `waiting_data` 态后**退出、立即释放 recon worker**。
- **`waiting_data` 的落点**：自动对账主链路走 `recon_execution_queue`（现状态 `queued / running / done / failed`，worker 领取后同步跑完即 `done`，**无挂起-恢复模型**）。故不复用旧 `recon_auto_runs`，而是给 `recon_execution_queue` **新增 `waiting_data` 队列态**及字段：`next_retry_at`、`wait_deadline_at`、`waiting_reason`、`waiting_datasets`、`collection_job_ids`。worker 遇浏览器数据未就绪即把 job 置 `waiting_data` 并退出。
- **对账段调度时机与恢复**：自动对账默认排在采集窗口之后起跑（如 09:30 之后），降低首跑即 `waiting_data` 的概率。`waiting_data` job 由**专门的 poller 兜底恢复**——每 5-10min 检查一次：数据就绪 → 改回 `queued` 等 worker 重领；超过 `wait_deadline_at`（**= 采集窗口结束后 60-90min，约 10:30**）仍无数据 → 置 `failed`、`waiting_reason` 记「采集未就绪」、告警 Operator。**兜底轮询是必做机制；采集成功事件即时唤醒为后续优化项**，MVP 不引入 PG `LISTEN/NOTIFY` 或事件总线。
- **汇合**：采集 `sync_job` 成功、dataset 发布后，poller 把对应 `waiting_data` job 改回 `queued`，recon worker 重新领取，这次读到数据、继续 `proc/recon`。

效果：4 个 recon worker 永不阻塞在浏览器采集上；浏览器长任务全部由 Dispatcher + 采集节点并发槽这条独立链路承载，与 recon 执行池物理分离。即使 30 店采集同时挂起等 `TASK_RESULT`，也不消耗 recon 并发额度。

### 并发槽与串行锁

- **每 agent 并发槽**：单采集节点同时执行的 playbook 任务数有上限（配置项 `agent_max_concurrency`，**v1 默认 `2`**，依据见「v1 容量公式与默认值」）。cloud 侧 Agent Connection Manager 维护每 `agent_id` 的 in-flight 计数，超限任务在 cloud 侧排队等槽，不下推。
- **每 shop 串行锁**：同一 `shop_id` 同时只允许一个浏览器采集任务在跑（`sync_jobs` inflight 检查 + advisory lock）。同店 profile / Chrome user-data-dir 不可被并发会话写，违反会损坏 profile。
- **错峰起跑**：Production Push Dispatcher 在 06:00-09:00 窗口内为每店随机起跑时刻，避免 30 店齐发；与并发槽叠加，进一步压平峰值。

### sync_jobs 状态流转

```
pending → (dispatcher 领取：置 running + 写 dispatched_at，下推 RUN_PLAYBOOK)
        → running[未 ACK] → (节点 ACK：写 started_at) → running[执行中]
        → success / failed
   └─ running 且 started_at 为空、now > dispatched_at + ack_timeout → failed（节点离线/不可达）
   └─ running 且 started_at 有值、now > started_at + task_timeout    → failed（任务卡死）
```

状态保持现有 `sync_jobs` 枚举（`pending/running/...`），不新增状态；「已领取未 ACK」与「执行中」靠 `dispatched_at` / `started_at` 两个时间戳区分——避免改动与数据库采集共用的 `sync_jobs` 状态枚举。

### 持久化队列语义

`sync_jobs` 表本身即 durable queue，不另引中间件：

- **`pending` = 待派队列**：Dispatcher 触发采集时插入 `pending` 行；该行落库即任务持久化，cloud 进程崩溃不丢。
- **领取**：Dispatcher 按 agent 可用并发槽领取 `pending` 行——在事务内 `SELECT ... FOR UPDATE SKIP LOCKED` 取一行、置 `running`、写 `agent_id` 与 `dispatched_at`，再下推 `RUN_PLAYBOOK`。`SKIP LOCKED` 在 MVP 单 Tally Main 内即用于防止并发 task 重复领取；多 replica 为未来预留。节点 ACK 后写 `started_at`（状态不变，仍 `running`）。
- **lease**：分两段——`started_at` 为空时 lease = `ack_timeout`（默认 30s，从 `dispatched_at` 起算），超时即判节点离线 `failed`；`started_at` 有值后 lease = `task_timeout`（默认 15min，可被 `timeout_ms` 覆盖，从 `started_at` 起算），超时即判任务卡死 `failed`。
- **cloud 重启恢复**：重启后扫描 `sync_jobs`——`running` 且超对应 lease 的判 `failed` 走瞬时失败重试；仍是 `pending`（已插入但未领取下推）的留在队列，下一轮 Dispatcher 正常领取，不丢任务。

### 超时、心跳与恢复

- `ack_timeout` 默认 30s，从 `dispatched_at` 起算（节点未 ACK 即超时）；`task_timeout` 默认 15min、从 `started_at` 起算，特殊大数据 playbook 可用 `RUN_PLAYBOOK.timeout_ms` 进一步覆盖。
- 采集节点 30s 心跳；连续丢心跳 → `agents.status=offline`，该 agent 的待派任务暂缓。
- **cloud 重启恢复**：重启后扫描 `sync_jobs` 中 `running` 且超对应 lease（`started_at` 空看 `ack_timeout`、否则看 `task_timeout`）的任务，判 `failed` 并按瞬时失败策略重试（最多 3 次）；in-flight 计数据存活任务重建。
- **节点重连**：节点短断重连不丢任务（WS 重连容忍，见通信协议）；任务结果以 `job_id` 幂等回传。

### 生产链路

重试策略按失败类型分级：**瞬时失败**（节点离线 / Chrome 崩溃 / 网络抖动）窗口内有限重试；**确定性失败**（`AUTH_EXPIRED` / `PAGE_CHANGED` / `RISK_VERIFICATION` / `DATA_MISMATCH`）不重试——原因不会自己好，重试 `RISK_VERIFICATION` 还会加重风控。确定性失败一次即 flag、留白天人工处理，修复后由现有重新对账补采。

| 故障 | 处置 |
|---|---|
| 采集节点离线 | ack_timeout（30s）→ sync_jobs.status=failed → 告警 + 自动重试（最多 3 次，间隔 30min，瞬时失败） |
| Chrome 进程崩溃 | 节点重启该任务（最多 1 次，瞬时失败）→ 仍失败上报 |
| 登录态失效（cookie/账号过期）| 快速失败 `AUTH_EXPIRED`、不重试 → profile 标 `needs_reauth`、移出 cron → 创作平面重跑创作 |
| 页面改版 / selector 缺失 | playbook 内部 retry 2 次 → 仍失败则快速失败 `PAGE_CHANGED`、不再重试 → 标 `playbook_status=stale`（**不动 `profile_status`**——登录态没问题）、`cron_pause_reason=page_changed`、移出 cron → 重跑创作重新生成 playbook（自愈 self-heal 为 Phase 2，MVP 告警 Operator）。改版导致全量断采时走「页面改版紧急修复通道」（见下）|
| 数据质量门未过 | 快速失败 `DATA_MISMATCH`、不重试，产物不发布（坏数据不进 recon）→ 告警 Operator 排查（页面改版或导出不完整）|
| 采集中途风控弹验证 | 快速失败 `RISK_VERIFICATION`，不等待、不对抗、不重试 → profile 标 `risk_blocked`、移出 cron → Operator 经 noVNC 连肉机人工过验证一次；某店月计触发 3 次+ → 升级复盘访问策略，或判定该店浏览器采集走不通、推回 ISV/人工录入 |
| 首次登录失败 | 快速失败 `AUTH_EXPIRED` → 上报 Operator 核对凭证 |
| 出口宽带线路不可用 | 上报 cloud → 运维修复网络 → 重试任务（瞬时失败）|
| 长任务超时 | task_timeout 默认 15min；特殊大数据 playbook 可在 RUN_PLAYBOOK 消息里加 `timeout_ms` 覆盖 |

**页面改版紧急修复通道**：`PAGE_CHANGED` 导致同一 playbook 下全部店铺断采时，重跑创作产出的新 playbook 走状态机**紧急旁路**——`approved → active` 直切、跳过 7 天 canary。前置条件：① **Operator 在 Playbook Review/Approve UI 主动勾选「页面改版紧急修复」**，置 `emergency_page_changed=true`，并必填 `bypass_canary_reason`（跳过原因）、验证店铺、验证日期、审批人；② 经 Operator 人工 review + 1-3 店当天真实样本验证（含 Layer 2 精确交叉校验）通过。后端在 `approved → active` 直切前**校验上述字段齐全**，否则拒绝直切。promote 到 `active` 后，按「`playbook_status` / `cron_pause_reason` 的恢复转换」批量清理受影响店的 `stale`、恢复全量采集；灰度观察期在 promote 之后补做。普通版本升级仍走标准 `approved → canary → active`。

**紧急修复后的对账闭环**：改版当天受影响的对账任务，若已因 `waiting_data` 超过 `wait_deadline_at`（约 10:30）判 `failed`，而紧急 playbook promote + 重采往往晚于此。故紧急 playbook promote、重采成功后，须对受影响的 `shop_id` + `biz_date` 自动（或由 Operator 一键）触发**重新对账**——生成 `trigger_mode=rerun` 的新对账任务，把已 `failed` 的当日对账补回。

### 创作链路

| 故障 | 处置 |
|---|---|
| LLM 调用失败 | browser-use 内置 retry；3 次失败 → authoring_jobs.status=rejected + 告警 |
| Agent 死循环（token 烧光预算）| 每个 job 设置 token 上限（默认 50k）→ 超出 → 强制停 + 告警 |
| 创作时遇平台验证 | Worker 暂停 + transcript → Operator 经 noVNC 连 Worker 人工过验证后继续，或看 transcript 决定换站点路径 |
| Schema 校验失败 | authoring_jobs.status=rejected，原因写入 reject_reason；Operator 看后决定重跑 |
| Sandbox replay 失败 / 数据与样本不精确匹配 | 同上，附 replay 详细 log（财务数据要求精确匹配，无容差）|

## 与现有采集框架的集成契约

浏览器采集必须明确如何接入 `finance-mcp` 既有的 `data_source` / `sync_jobs` / collection_driver 框架，否则触发链路会在现有短路逻辑里直接失败。本节是落地前必须冻结的契约。

### 触发路由：新增 `browser_playbook` source_kind

**现状**：`_handle_data_source_trigger_sync`（`finance-mcp/tools/data_sources.py`）对 `source_kind ∈ AGENT_ASSISTED_KINDS = {browser, desktop_cli}` 直接短路——构造占位 `BrowserConnector`、调 `trigger_sync()` 返回 `agent_assisted_required`，**不进入 dataset collection 主流程**。沿用现有 `browser` kind，`browser_playbook_remote` driver 永远收不到任务。

**决策**：新增独立 `source_kind = browser_playbook`，与现有 `browser`（`agent_assisted` 占位，保持不动）区分。

- `browser_playbook` **不进** `AGENT_ASSISTED_KINDS`；`execution_mode = deterministic`——playbook 重放是确定性的，语义上等同数据库采集而非 agent loop。
- factory 按 `(source_kind, provider_code)` 注册：新增 `("browser_playbook", "qianniu") → BrowserPlaybookRemoteConnector`。
- 触发后正常落入 `data_source_trigger_dataset_collection → create_or_reuse_dataset_collection_sync_job` 主流程，写 `sync_jobs`，与数据库采集等价。
- 现有 `browser` kind 与 `BrowserConnector` 占位不动，避免影响既有行为。

> 备选（已否决）：保留 `browser` kind、按 `execution_mode` 拆 `data_sources.py` 的短路分支。否决理由：短路条件从 `source_kind` 单一判断变成 `source_kind × execution_mode` 复合判断，占位与生产 driver 共用一个 kind，后续易误路由。
>
> 注：本决策在岔路澄清中按推荐项选定，翻转成本低（仅影响 factory 注册与 `AGENT_ASSISTED_KINDS` 一行）。

### 店铺与 data_source 映射：每店一条 data_source

**现状**：`create_or_reuse_dataset_collection_sync_job`（`finance-mcp/auth/db.py`）的复用键是 `company_id + data_source_id + resource_key + dataset_id + biz_date`，**不含店铺维度**。

**决策**：**每个店铺对应一条独立 `data_source` 行**（各有 `data_source_id`）。

- 复用键已含 `data_source_id`，30 店天然按店隔离，不存在跨店错误复用 TTL 结果的风险。
- `resource_key` 强制编码为 `<playbook_id>@<version>`，**作用域仅限 `sync_jobs` 任务级 TTL 复用**：当某店解析出的 playbook 版本变化（如灰度调整 `canary_shop_ids`），`resource_key` 随之变化、令 TTL 缓存失效、强制重采。它**不是 `browser_collection_records` 的数据分区维度**，故不进该表唯一约束（理由见数据模型一节）。
- `shop_runtime_bindings.shop_id` 与 `data_sources` 一一绑定；Operator UI 的 Shops 页展示该映射。

> 防御性约束：即使未来出现多店共享一条 `data_source` 的场景，`resource_key` 也须额外编码 `shop_id`，确保复用键在店铺维度始终隔离。
>
> 注：本决策在岔路澄清中按推荐项选定。

### TTL 复用语义

- 同店、同 playbook 版本、同 `biz_date`，在 TTL 窗口内复用上次成功 `sync_job`——与数据库采集行为一致。
- 重新对账补采指定 `biz_date`：playbook 接 `biz_date` 参数（见数据质量门一节），走同一复用/采集逻辑，无需单建 backfill 组件。
- 浏览器采集单任务耗时长（导出 5-10min），`inflight` 复用窗口（默认 900s）足够覆盖；`task_timeout` 可用 `RUN_PLAYBOOK.timeout_ms` 覆盖。

## 现有 Tally 集成点

### finance-mcp/

- `connectors/providers/browser_playbook_remote.py`：新 driver（`source_kind = browser_playbook`、`execution_mode = deterministic`），遵循 BaseConnector 接口
- `connectors/factory.py`：注册 `("browser_playbook", "qianniu") → BrowserPlaybookRemoteConnector`
- `tools/data_sources.py`：`browser_playbook` 不加入 `AGENT_ASSISTED_KINDS`，正常落入 `data_source_trigger_dataset_collection` 主流程（见「与现有采集框架的集成契约」）
- `auth/migrations/`：新增 `browser_collection_records` / `browser_capture_files` 建表迁移；前者 schema 对齐 `dataset_collection_records`
- 写 `sync_jobs`、`browser_collection_records`（复用 `item_key` upsert 幂等逻辑）、`browser_capture_files`，发布 `data_source_datasets`

### finance-cron/

- `run_scheduler.py`：到点时调用 Tally Main 的 API/MCP 工具触发采集计划——**不直接持有 WS、不下推 `RUN_PLAYBOOK`**（Production Push Dispatcher 本体在 Tally Main 进程内，见「组件职责」）
- 错峰调度配置在 `config/` 下新增 YAML

### finance-agents/browser-agent/（新建，采集节点执行面）

- `runner.py`：production daemon / CLI 入口，接收 `RUN_PLAYBOOK`，输出 `TASK_RESULT`
- `finance_browser_agent/playbook_interpreter.py`：解释 playbook `steps`，映射到 Playwright 调用
- `finance_browser_agent/quality_gate.py`：字段、日期、金额、日汇总一致性校验
- `tests/`：playbook interpreter contract 与 quality gate 测试

放在 `finance-agents/` 下是目录约束：该模块是 agent/runner 子系统；仓库根目录不再新增 `finance-browser-agent/`。

### finance-authoring/（新建，独立进程）

- `worker.py`：authoring 入口（轮询 authoring_jobs 表）
- `llm_client.py`：DeepSeek-V4 Pro SDK 封装
- `browser_use_agent.py`：browser-use 配置 + skill 注入 + schema 约束
- `action_trace.py`：探索期记录每个生效动作（resolved selector / url / 输入值 / DOM 信息）
- `playbook_synthesizer.py`：从 trace 合成确定性 playbook + selector 加固
- `sandbox_replay.py`：用确定性 Playbook Interpreter 重放合成出的 playbook、复现样本数据
- `output_validator.py`：JSON Schema + sample data 校验
- `playwright_runner.py`：Chrome lifecycle（一次性 profile）
- `skills/`：Authoring Skill 文件目录

### recon 消费层

新增 `browser_collection_records` 数据类型支持：recon loader 识别该类型并读取。`data_source_datasets` 发布方式不变。

**loader 过滤规则**（不可照搬 `dataset_collection_records` loader 的默认行为）：

- 现有 `dataset_collection_records` loader（`finance-mcp/recon/mcp_server/dataset_loader.py`）默认按 `resource_key`（缺省 `"default"`）过滤。`browser_collection_records` 的 `resource_key` 是 `<playbook_id>@<version>` 任务级 TTL 键，**生产对账 loader 不得按 `resource_key` 过滤**——否则 canary promote / 版本变化后会读不到数据或读到旧版本条件。
- 生产对账查询条件固定为：`company_id` + `data_source_id` / `dataset_id` + `biz_date` + `record_status != 'deleted'`。
- `resource_key` 仅在显式审计查询（如「查某 playbook 版本采过哪些数据」）时作为过滤条件，不进生产对账路径。

## 安全 / 凭据 / 鉴权

本系统会**保存商家子账号密码并代其操作账号**，安全控制不是工程细节而是 P0 要求，落地前必须冻结本节契约。

| 范畴 | 方案 |
|---|---|
| Agent ↔ Cloud | API Token（cloud 颁发，节点配置文件保存）+ WSS |
| 商家千牛凭证 | 加密存储（DB 加密列 / KMS）；不入 git；下发给采集节点用于本地登录 |
| Runtime Profile（含 cookie）| 仅采集节点本地存储，不传输；落**加密磁盘卷**（LUKS 或同等），`.gitignore` 默认排除 `profiles/` |
| 买家个人信息 | 最小化采集；存储加密；不出境；按《委托数据处理协议》处理 |
| DeepSeek API Key | 环境变量 `DEEPSEEK_API_KEY`；不入 git |
| Operator UI 鉴权 | 接现有 Tally 后台登录体系 + 下述 RBAC |

### Operator RBAC

Operator UI 操作按最小权限分级授权，不同角色拿不同权限位：

- **查看**：看 playbook / job / 采集状态。
- **创作审批**：approve playbook、设 `canary_shop_ids`、promote 版本。
- **凭证管理**：录入 / 轮换 / 回收商家凭证。
- **noVNC 接入**：申请并使用 noVNC 人工介入会话。

凭证管理与 noVNC 接入是高敏权限，须独立授予、与普通运营角色分离。

### 凭证读取审计

- 每次解密 / 下发商家凭证记**审计日志**：谁（Operator / 系统）、何时、关联哪个 `job_id` / `shop_id`、用途。
- 凭证明文绝不进普通运行日志、不进 transcript、不进 LLM 上下文。
- 审计日志独立留存，与业务库分权限。

### noVNC 临时授权

noVNC 是挂着商家已登录会话的高危入口，**不得常开**：

- 平时不监听端口、零开销。
- 需人工过验证时，Operator 经 UI 申请 → cloud 颁发**短时一次性令牌**（如 30min）→ 节点临时拉起 noVNC，绑定该令牌 + **IP 白名单**（限 Operator 出口 IP）。
- 会话结束或令牌超时 → 自动关闭 noVNC、销毁令牌。
- noVNC 人工介入会话记**操作日志**（起止时间、Operator、目标店、操作摘要）；敏感操作可录屏留审计。

### 凭证轮换与回收

- 商家子账号密码定期轮换；轮换流程经凭证管理权限执行并审计。
- 客户停止授权 / 店铺下线 → **立即删除凭证 + profile + cookie**，记回收审计。
- 凭证使用范围严格限于《委托数据处理协议》约定的采集动作，不得用于协议外的账号操作；授权边界写入协议并在 Operator 培训中明确。

## 容量规划

| 项 | 配置 |
|---|---|
| 固定采集节点数量 v1 | 1 台（置于 Tally 办公室）|
| 采集节点配置 | Mac mini M2 16GB / 512GB SSD（~5500 元）或 Ubuntu 16GB+ |
| 单节点并发与容量 | `agent_max_concurrency=2`；30 店错峰约 112min 跑完 06:00-09:00 窗口（公式见「并发与队列模型」）|
| 创作 Chrome 资源 | 单任务 1.5-2GB RAM（独立进程，不占 Tally Main）|
| 出口宽带 | 2-3 条 Tally 实名商业宽带，30 店分组共享；约 ¥1-2k/月 |
| DeepSeek API | 单次创作 ¥3-15；每月预算 ¥500 兜底 |
| v1 总硬件投入 | ~6000 元（不含宽带月费）|

**单节点可用性风险（v1 接受，但须有预案）**：v1 只有 1 台采集节点，节点宕机 = 当天全部浏览器采集不可用。v1 不立即上双节点，但预案须明确：① 节点宕机即告警 Operator；② 当天缺采的店次日由「重新对账」补采指定 `biz_date`；③ 关键店可人工导出录入兜底；④ 备用机冷启动 SOP（重装 daemon + 重新登录建 profile——profile 不可迁移）。店铺数或单任务耗时达扩容触发条件时，加第二采集节点同时消除该 SPOF。

## 子项目拆分（每个独立 spec + 实施计划）

| 序号 | 子项目 | 依赖 | 估时 |
|---|---|---|---|
| **P0** | Playbook JSON Schema 定义 + 解释器实现 | 无 | 1 周 |
| **P1** | 采集节点 daemon 骨架（WS + 心跳 + Playwright + Runtime Profile 登录）| P0 | 1-2 周 |
| **P2** | Cloud 端 Playbook Registry / Verification / 6 张 DB 表 + `playbook_status`/`cron_pause_reason` 恢复转换（promote 后批量清理 `stale`）| 无（与 P0/P1 并行）| 1 周 |
| **P3** | Cloud 端 `browser_playbook_remote` driver + Agent Connection Manager | P1 + P2 | 1 周 |
| **P3.5** | Recon waiting-data orchestration：driver 的 ready/waiting/unavailable 返回契约 + 健康门、`recon_execution_queue` 的 `waiting_data` 队列态与字段、worker 释放、poller 恢复、最大等待失败、测试 | P3 | 1 周 |
| **P4** | Authoring Worker（独立进程；browser-use + DeepSeek 集成）| P0 + P2 | 1-2 周 |
| **P5** | Operator UI（4 个页面）+ 紧急旁路审批（勾选「页面改版紧急修复」设 `emergency_page_changed`、必填 `bypass_canary_reason`/验证店/验证日期/审批人）| 最小版 P2 + P3；完整版另需 P4（Authoring Jobs 页）| 1 周 |
| **P6** | Production Push Dispatcher（错峰调度 + 消费 `pending` 浏览器采集 `sync_job`）| P3 | 0.5 周 |
| **P7** | Self-Heal Dispatcher（自动从失败创建 authoring job）| 全套上线后 | 1 周（Phase 2） |

### v1 范围与上线节奏

**v1 目标是服务 30 个店铺。**「首店端到端」只是内部验证里程碑，不是 v1 发布。

依赖路径：P0 → P1 → P2 + P3 → P3.5 + P6 → P5（最小版）→ 首店端到端跑通（约 4-5 周，P3.5 与 P6 在关键路径上）。
首店跑通后经 canary 机制分批 onboard：首批 playbook 的 `canary_shop_ids` = 首批 3 店，灰度通过后逐步扩到 30 店全量。

P4 / P7 可放到首店跑通之后 sprint。

**首店阶段 (v1) 的 playbook 生成流程**:Operator 本机用 **Claude Code 或 codex** + DeepSeek-V4 Pro 协助跑出 playbook JSON,然后**在 finance-web 的「数据连接 → 浏览器」页面**(`BrowserPlaybookPanel`)粘贴 JSON 并填入商家分配的子账号用户名/密码,前端调 `POST /api/data-sources/{source_id}/browser-playbook/register` 触发服务端同步首验流程(见「Playbook 注册时的首次验证流程」)。Operator 的本机 AI 编码部分**不属于生产架构组件**,但 finance-web 上的注册/验证/激活页面**是 v1 必备前端**——没有它,Operator 没法通过 UI 持久化凭证。

**P4 (v2) 升级目标**:自研 Authoring Worker,**封装 Claude Agent SDK + DeepSeek-V4 Pro**,在 Tally 内置 web UI 提供与 v1 一致的"自然语言→playbook"能力,但移除"Operator 本机依赖外部 AI IDE"。首次验证流程不变,仍走 v1 同一通道。

## 决策记录

| 决策 | 备选 | 选择理由 |
|---|---|---|
| 不做 Chrome 扩展 | 客户装扩展 | 客户感知问题 + 安装阻力 |
| 不做风控对抗工程 | 指纹伪造 / 验证码绕过 | 合规边界：对抗技术措施会把法律风险推向刑事 |
| Tally Main 与 Authoring Worker 独立进程 | 同进程 monolith | 浏览器/LLM 故障隔离，不拖垮 recon SLA |
| Push 而非 Pull 触发 | Agent 主动拉 | 跟现有 auto_scheme_run 同步生命周期一致 |
| WebSocket 而非 HTTP RPC | 队列 / VPN | 最简基础设施，节点不需公网 |
| DeepSeek-V4 Pro + browser-use | Qwen-Max / 自写 agent loop | DeepSeek 性价比 + 国内合规 + browser-use 现成 |
| skill / playbook / runtime profile 三概念分立 | 混为一谈 | 职责不同：skill 创作期、playbook + profile 生产期 |
| 浏览器采集独立存储表，但复用 item_key upsert 幂等模型 | 复用 dataset_collection_records 表 / 自造行身份机制 | 表分存沿用 2026-05-07"按采集方式分存储"约定；幂等模型已在 dataset_collection_records 验证，重造无收益且易出错 |
| 新增 `browser_playbook` source_kind | 复用 `browser` kind 按 execution_mode 拆短路分支 | 占位与生产 driver 分 kind，避免短路逻辑复合判断与误路由；翻转成本低 |
| 每店一条独立 data_source 行 | 多店共享 data_source 靠 shop_id 参数区分 | 复用键已含 data_source_id，天然按店隔离 TTL，无跨店错误复用风险 |
| Runtime Profile 本地存储 | 云端管理 | profile 含设备绑定信息，跨机迁移破坏稳定性 |
| 首次登录由采集节点完成 | cloud 侧登录 | 凭证只在采集节点本地使用，登录环境与采集环境一致 |
| Playbook 注册时由 Tally 同步触发首次验证(`profile_status=verifying → active`) | Operator SSH 采集机本地手动首登 | 验证发生在 cloud + agent 真实生产链路,自动覆盖凭证正确性、playbook 可重放、Layer 2 口径,且能向 Operator 返回结构化错误。手动 SSH 流程依赖单点知识、无法审计、与生产链路脱节 |
| v1 必须提供前端注册页面(`BrowserPlaybookPanel`),复用 `browser` 预留卡的位置改成 `browser_playbook` | v1 走 MCP / 命令行 / 等 v2 一起做 web UI | 没有前端 Operator 无法把商家凭证持久化进系统;`browser` 占位卡本就是给浏览器留的位,直接换成 `browser_playbook` 比并存两个卡片清晰 |
| v1 用 Claude Code / codex(Operator 本机 AI 编码工具) 手工生成 playbook;v2 用自研 Authoring Worker 封装 Claude Agent SDK + DeepSeek-V4 Pro 在 Tally 内置 web UI 完成 | v1 直接上自研 agent / v2 一直用外部 AI IDE | 首店 v1 不值得为单店投入 web 端 agent;30 店扩展或多平台 onboard 时,Operator 本机依赖外部 IDE 的方案不可扩展,需要切到自研封装 |
| 2-3 条商业宽带分组共享 | 一店一固定出口 IP | 一台物理机本就需代理才能多出口；多店共享出口是「代运营办公室」正常画像，风控信号低于一店一 IP 的孤立访问；成本从 30 个 IP 塌缩成 2-3 条线 |
| Operator 强制 review approve | LLM 自审 / 自动 promote | 数据错误代价高，必须人卡点 |
| cron 链路零人工介入 | mid-cron 暂停等人工 | 凌晨无人值守；人工动作归创作平面或异常处理，否则体验不连贯 |
| 失败用明确原因码（AUTH_EXPIRED / PAGE_CHANGED / RISK_VERIFICATION / DATA_MISMATCH）| 笼统 failed | 让 Operator 知道去哪、做什么；可重跑创作解 / 需人工 / 需排查各不同 |
| RISK_VERIFICATION 经 noVNC 人工过验证 | 建浏览器流转发产品流程 / 打码平台 | 低频异常事件，不值得建专门基础设施；打码违合规边界 |
| playbook 先探索后合成 | 边探索边吐 playbook / 人工录制 | 探索的乱与产出的净分离；保留 AI 探索新站点能力 |
| Sandbox Replay 在 Authoring Worker 跑 | 在 Tally Main 跑 | Tally Main 无浏览器会话；Worker 本就有 Chrome + 活会话 |
| canary 按 playbook 版本灰度 | 无灰度 / 全量直切 | 30 店共用 playbook，新版本先灰度 3 店再全量，避免一次打挂全部 |
| 数据质量门失败即关闭 + 日汇总精确交叉校验 | 无运行时校验 / 容差校验 | 对账产品采错数据代价最高；用千牛自报合计精确验完整性，坏数据不进 recon |
| 错峰时段 06:00-09:00 | 02:00-06:00 | 早班、T-1 数据已就绪，比深夜更贴近代运营正常批处理节奏 |
| 不单建 backfill 组件 | 专门补采流程 | 漏采日复用已实现的「重新对账」重跑，前提是 playbook 接 `biz_date` |
| 采集与对账解耦，recon worker 不阻塞 | driver 同步 `await` 采集结果 | 浏览器任务 5-10min，同步 `await` 会占满 recon worker 空转；解耦后 worker 只管对账，采集走 Dispatcher 独立链路 |
| Production Push Dispatcher 在 Tally Main 内，finance-cron 仅触发 | Dispatcher 在 finance-cron 独立进程 | WS 连接 dict 在 Tally Main 进程内，独立进程下推不了 `RUN_PLAYBOOK`；finance-cron 只到点触发计划 |
| `PAGE_CHANGED` 用独立 `playbook_status`，不动 `profile_status` | 复用 `profile_status=needs_reauth` | 页面改版与登录态无关，混用会导致重跑创作后仍需手动翻状态、语义错乱 |
| `waiting_data` 扩展 `recon_execution_queue` 队列态，不复用 `recon_auto_runs` | 复用旧 `recon_auto_runs` 的 `waiting_data` 态 | 自动对账主链路已迁到 `recon_execution_queue`；新增队列态 + poller，比维护两套 recon 任务模型简单 |

## 后续工作（Out of Scope）

- Multi-agent fleet 编排（采集节点超 5 台时考虑）
- Authoring Worker 独立成可独立扩缩容的 service（监控指标支持后再做）
- 自动化 self-heal pipeline（生产稳定 3 月后启动）
- 商家自助绑定流程 UI（早期人工 onboard）
- ISV 授权落地后迁回官方接口（长期主线）

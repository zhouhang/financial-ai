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
| **Runtime Profile** | 结构化记录 + 本地文件 | 一个店铺的运行上下文：账号凭证、cookie、浏览器 user-data-dir、固定出口 IP、下载目录、店铺绑定 | 采集节点本地生成与维护；生产采集时装配 |

**生产采集真正下发的是：`playbook` + `runtime profile` 引用 + `params`。**
- 只有 skill 不够：skill 是原则不是步骤，不能确定性重放。
- 只有 profile 不够：profile 是运行上下文，没有采集动作。
- 三者各司其职：skill 用于创作期，playbook + runtime profile 用于生产期。

## 目标

1. 用一套架构同时支撑两个能力：
   - **生产采集**：每天定时从千牛/天猫等浏览器端站点抓数据
   - **采集配方创作**：遇到新站点 / 新指标 / 站点改版时，靠 AI agent 探索并写出可重放的 playbook
2. 接入现有 `auto_scheme_run` / `sync_jobs` 任务契约，浏览器采集结果通过独立存储表发布到 `data_source_datasets`，不改 recon 上游消费方式。
3. 把"采集步骤"做成机器可执行 playbook，不让 LLM 进生产链路。
4. 创作与执行严格隔离：profile、出口 IP、运行时机互不污染。
5. 多店铺隔离：每店一份持久化 profile + 一个固定出口 IP。
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
│  - 每店固定出口 IP                                        │
│  - Playbook Interpreter（解释 playbook → Playwright）     │
└─────────────────────────────────────────────────────────┘
```

部署形态：
- MVP：Tally Main 与 Authoring Worker 都在开发机以独立进程跑。
- 生产：同 repo 构建，docker-compose 内 `tally-main` 与 `tally-authoring` 为两个 service（或同镜像两个进程），不共用 Python 进程。

## 设计原则

1. **创作与执行分离**：创作链路用 LLM，可失败可重试；生产链路 100% 确定性，禁用 LLM。
2. **Runtime Profile 不可迁移**：profile 在哪台采集节点原生成长，任务就路由到哪台。Cloud 永远不持有 profile 文件。
3. **Playbook 是 cloud 资产**：playbook 在 Tally cloud DB 集中存储 + 版本管理。采集节点不存盘，每次任务消息里带。
4. **Push 触发模型**：cloud 主动 WebSocket 推任务到采集节点。节点启动后主动出 WS 上行连接，cloud 通过同一连接下推。
5. **Operator 是终审**：playbook 上线、approve 永远人工卡点；自动校验只过滤明显错误。
6. **进程隔离**：Authoring Worker 与 Tally Main 不共进程，浏览器/LLM 故障不拖垮主服务。
7. **YAGNI**：拒绝 Chrome 扩展、风控对抗工程、多模型编排、queue 中间件。在没遇到具体业务信号前不拆。

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
shop ↔ 采集节点 ↔ 固定出口 IP ↔ profile 状态绑定。

| 列 | 说明 |
|---|---|
| `shop_id` | 商家店铺 ID |
| `agent_id` | 该店分配到的固定采集节点 |
| `egress_ip` | 该店固定出口 IP（每店专属、长期稳定） |
| `credential_ref` | 加密凭证引用（子账号用户名/密码，KMS 加密） |
| `profile_status` | `none` / `initialized` / `expired` / `needs_human_verify` |
| `last_collection_at` | 最近一次成功采集时间 |

#### `authoring_jobs`
创作任务（Operator 触发或失败自愈触发；MVP 仅 Operator）。Tally Main 与 Authoring Worker 通过此表解耦：Main 插入 `queued` 行，Worker 轮询领取。

| 列 | 说明 |
|---|---|
| `job_id` | UUID |
| `task_description` | Operator 输入的自然语言描述 |
| `authoring_skill_ref` | 注入到 system prompt 的 Authoring Skill 文件引用 |
| `parent_failure_id` | 关联的失败 sync_job（自愈用，Phase 2） |
| `status` | `queued` / `running` / `uploaded` / `approved` / `rejected` |
| `output_playbook_id` | 关联的 playbooks 表条目（成功后） |
| `llm_tokens_used` | 计费用 |
| `started_at` / `completed_at` | 审计 |

#### `browser_collection_records`
浏览器采集的结构化记录表（按采集方式独立存储，与 `dataset_collection_records`、支付宝结构化表平行）。

| 列 | 说明 |
|---|---|
| `record_id` | 主键 |
| `sync_job_id` | 关联 `sync_jobs` |
| `shop_id` / `playbook_id` / `biz_date` | 业务维度 |
| `row_payload` | JSONB，单行结构化数据 |
| `captured_at` | 采集时间 |

#### `browser_capture_files`
浏览器采集的原始文件（导出的 CSV/Excel 等），作为审计资产，不直接进 recon。

| 列 | 说明 |
|---|---|
| `file_id` | 主键 |
| `sync_job_id` | 关联 `sync_jobs` |
| `shop_id` / `playbook_id` / `biz_date` | 业务维度 |
| `storage_path` | 文件存储路径 |
| `encoding` / `checksum` / `row_count` | 文件元信息 |

### 存储与读取约定

- 浏览器采集结果写 `browser_collection_records`（结构化）+ `browser_capture_files`（原始文件审计）。
- 采集完成后统一发布到 `data_source_datasets`，recon loader 增加 `browser_collection_records` 数据类型即可消费。
- **不复用** `dataset_collection_records`（该表对应数据库通用采集）。沿用 2026-05-07 设计"按来源/采集方式分存储"的约定。
- `sync_jobs`、`dataset_bindings`、`data_source_datasets` 复用，写入方式与现有 driver 等价。

## 组件职责

### Cloud 端

#### Playbook Registry & Verification（Tally Main 内）

- 接受 Authoring Worker 上传的 3 件套（playbook / sample / transcript）
- 跑 3 层校验：JSON Schema validator、Sample Data Checker、Sandbox Replay Orchestrator
- 维护 playbook 生命周期状态机：`draft → replayed → approved → canary → active → deprecated`
- 提供 Operator UI 数据查询接口

#### Agent Connection Manager（Tally Main 内 async 模块）

- 持有 `agent_id → WebSocket conn` 映射（进程内 dict）
- 接受采集节点主动连入（WSS upgrade，API Token 鉴权）
- 心跳保活 30s / 次，断连后更新 `agents.status`
- 上层 driver 调 `dispatch(agent_id, message, timeout)` 同步等结果
- 重连容忍（节点短断不丢任务）

跟 Tally Main 同进程同 event loop；用 asyncio task 跑 WS server。规模到多 replica Tally Main 时（不在 MVP 范围）再考虑外移成 sticky-session 服务或加 Redis 协调。

#### `browser_playbook_remote` collection_driver（Tally Main 内）

接现有 `BaseConnector` / factory 模式，挂到 `finance-mcp/connectors/providers/`。

- 由 `auto_scheme_run` / `data_source_trigger_dataset_collection` 触发
- 查 `shop_runtime_bindings` 找目标采集节点
- 调 Agent Connection Manager `dispatch(...)` 推 `RUN_PLAYBOOK` 消息
- 同步等节点回结果（默认 5min 超时）
- 写 `sync_jobs` + `browser_collection_records` + `browser_capture_files`，发布 `data_source_datasets`

#### Authoring Worker（独立 Python 进程）

模块路径：`finance-authoring/`。同 repo、同部署单元，但**独立 OS 进程**，不与 Tally Main 共用 Python 进程。

进程隔离理由：browser-use 跑 Chrome + 长时 LLM 任务，存在卡死、内存暴涨风险；隔离后不波及 Tally Main 的 recon / 调度 SLA。

与 Tally Main 通过 `authoring_jobs` 表解耦：Worker 轮询 `status=queued` 的行领取任务。

职责：
- 实例化 browser-use Agent，注入 Authoring Skill 作 system prompt
- 调用 DeepSeek-V4 Pro（OpenAI 兼容协议）
- 控制 Chrome + Xvfb 生命周期（一次任务一抛弃临时 profile）
- 产 3 件套，调用 Playbook Registry 接口入库
- 计 token 消耗

#### Production Push Dispatcher（Tally Main 内）

`finance-cron` 现有 scheduler 的扩展。
- 按 `playbooks.status=active` + 调度时段（02:00-06:00 错峰）触发 `auto_scheme_run`
- 低频原则：同店每日采集次数受控，避免高频访问
- 失败重试：单店连续 3 次失败 → 暂停 + 告警飞书/钉钉

#### Operator UI

接现有 Tally 后台，加 4 个页面：
- 「Playbooks」列表 + 创建 + Review + Approve
- 「Authoring Jobs」列表 + 详情 + transcript 查看
- 「Agents」状态板（在线/离线/最近心跳）
- 「Shops」绑定表（shop ↔ 采集节点 ↔ 固定出口 IP ↔ profile 状态）

### Local Agent（固定采集节点）

#### OS 底座
Ubuntu 22.04 LTS + Xvfb（systemd 自启）+ Chrome stable + 中文字体（noto-cjk、wqy-zenhei）+ Asia/Shanghai 时区。

#### Tally Production Daemon
- Python 3.11+ async event loop
- 启动时连 cloud（WSS，API Token 鉴权）
- 收 `RUN_PLAYBOOK` 消息执行任务
- 心跳 30s / 次
- 自带 `/health` endpoint 给 systemd watchdog

#### Playbook Interpreter
- 解析 playbook `steps` 数组
- 每个 `action` 类型映射到 Playwright 调用（navigate / click / type / wait / snapshot / assert / branch / download）
- 处理 `error_handlers`（遇平台验证 → 转人工流程；登录失效 → 重新登录流程）
- 产 sync_jobs 风格的执行记录

#### Runtime Profile Manager
- 按 shop_id 装载 `/var/lib/tally-agent/profiles/<shop_id>/`
- **首次缺 profile**：用 cloud 下发的加密凭证（子账号用户名/密码）在本节点完成登录，创建持久化 profile。登录在采集节点本地完成，凭证不在 cloud 侧使用。
- **仅当遇到验证码 / 短信验证 / 扫码 / 安全验证**：上报 `NEEDS_HUMAN_VERIFY`，进入人工验证流程，由人工完成验证后继续。
- 探测 cookies 时效性（Cookies 文件 mtime + token 过期推断），失效走重新登录流程

#### Egress IP Adapter
- 每个采集节点为其绑定的店铺提供固定出口 IP
- 注入 Playwright `launch_persistent_context(proxy={"server": ...})` 或节点级网络配置
- 固定出口 IP 长期稳定、每店专属，目的是店铺间隔离与身份一致，不做 IP 轮换

## 通信协议

### 传输
- WebSocket over TLS（WSS）
- 采集节点主动外出连接（hardpoint 在 cloud 公网/内网域名）
- 单条消息 JSON，最大 10MB（超过用 HTTP 旁路上传 + WS 传 URL）

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
    egress_ip, credential_ref, timeout_ms
UPGRADE                # 推升级版本号 + 下载 URL
DRAIN                  # 准备下线，跑完手头任务后断开
```

#### Agent → Cloud

```
HELLO                  # 启动握手，带 agent_id + token + version
HEARTBEAT              # 30s / 次
TASK_RESULT            # RUN_PLAYBOOK 的结果
  body:
    job_id, status (success/failed), data_url, error_info
NEEDS_HUMAN_VERIFY     # 遇平台验证（验证码/短信/扫码/安全验证），需人工介入
HEALTH                 # CPU / 内存 / 磁盘
```

### 生命周期

```
agent boot
  → 连 cloud → HELLO
  → 收 HELLO_ACK
  → 进入心跳 + 监听任务 loop

cloud trigger:
  driver → dispatch(agent_id, RUN_PLAYBOOK)
  ↓ WebSocket
agent 收到：
  - 装载 / 首次创建 Runtime Profile（缺则用加密凭证登录）
  - 启 Playwright（持久 profile + 固定出口 IP）
  - 解释执行 playbook
  - 遇平台验证 → NEEDS_HUMAN_VERIFY → 等人工
  - 上传产物
  ↓
agent → TASK_RESULT
  ↓
cloud driver → 写 sync_jobs / browser_collection_records / browser_capture_files
            → 发布 data_source_datasets → 返回 auto_scheme_run

升级:
  cloud → UPGRADE
  agent → 下载 → 替换 → systemd 拉起新版本 → 重新 HELLO
```

## 数据流（端到端）

### 生产采集

```
[02:00-06:00 错峰时段]
  ↓
Production Push Dispatcher 扫描 `playbooks.active`
  ↓ for each shop × playbook：
auto_scheme_run 启动
  ↓
resolve_plan_inputs → 找到 dataset_binding
  ↓
data_source_trigger_dataset_collection
  ↓
collection_driver = browser_playbook_remote
  ↓
查 shop_runtime_bindings → 取 agent_id + egress_ip + credential_ref
  ↓
Agent Connection Manager.dispatch(agent_id, RUN_PLAYBOOK)
  ↓ WebSocket
采集节点：装载 Runtime Profile（首次用凭证登录）→ 启 Chrome（持久 profile + 固定出口 IP）→ 解释执行 playbook
  ↓ download CSV / 抓数据
节点 → cloud TASK_RESULT（含数据 URL）
  ↓
driver 拉取数据 → 解析 → 写 browser_collection_records + browser_capture_files
  ↓
发布 data_source_datasets
  ↓
sync_jobs.status = success
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
Agent 多轮调用 Playwright → 探索目标站点 → 试错
  ↓ (Phase 2：中途需 Operator 介入 → 通过 Operator UI 聊天框打通)
Agent 收敛产物：playbook + sample-data + transcript
  ↓
Worker 调 Playbook Registry 接口入库 → status=draft
  ↓
Verification 跑：
  1. JSON Schema Validator
  2. Sample Data Checker
  3. Sandbox Replay（再跑一遍 playbook 验证）
  ↓ 通过
status=replayed
  ↓
Operator UI 出现 review 卡片
  ↓
Operator 审 sample / transcript / steps → Approve
  ↓
status=approved → 进 Canary 7 天 / 3 店
  ↓ 通过
status=active → Production Push Dispatcher 拉取使用
```

## 故障处理

### 生产链路

| 故障 | 处置 |
|---|---|
| 采集节点离线 | dispatch 超时（30s）→ sync_jobs.status=failed → 告警 + 自动重试（最多 3 次，间隔 30min） |
| Chrome 进程崩溃 | 节点重启该任务（最多 1 次）→ 仍失败上报 |
| Playbook 步骤 selector 缺失 | playbook 内部 retry 2 次 → 失败 → 触发 self-heal job（Phase 2）/ 告警 Operator（MVP） |
| 遇平台验证（验证码/短信/扫码/安全验证）| 立即暂停，上报 `NEEDS_HUMAN_VERIFY` → 进人工验证流程，人工完成后继续 |
| 首次登录失败 | 上报 Operator，核对凭证 |
| 固定出口 IP 不可用 | 上报 cloud → 运维修复网络 → 重试任务 |
| 长任务超时 | dispatch 默认 5min；导出大数据 playbook 可在 RUN_PLAYBOOK 消息里加 `timeout_ms` 覆盖 |

### 创作链路

| 故障 | 处置 |
|---|---|
| LLM 调用失败 | browser-use 内置 retry；3 次失败 → authoring_jobs.status=rejected + 告警 |
| Agent 死循环（token 烧光预算）| 每个 job 设置 token 上限（默认 50k）→ 超出 → 强制停 + 告警 |
| 创作时遇平台验证 | Worker 报告 + transcript → Operator 看 transcript 决定（转人工验证或换站点路径）|
| Schema 校验失败 | authoring_jobs.status=rejected，原因写入 reject_reason；Operator 看后决定重跑 |
| Sandbox replay 失败 / 数据偏差 > 5% | 同上，附 replay 详细 log |

## 现有 Tally 集成点

### finance-mcp/

- `connectors/providers/browser_playbook_remote.py`：新 driver，遵循 BaseConnector 接口
- `connectors/factory.py`：注册新 driver
- 写 `sync_jobs`、`browser_collection_records`、`browser_capture_files`，发布 `data_source_datasets`

### finance-cron/

- `run_scheduler.py`：扩展 Production Push Dispatcher 逻辑
- 错峰调度配置在 `config/` 下新增 YAML

### finance-authoring/（新建，独立进程）

- `worker.py`：authoring 入口（轮询 authoring_jobs 表）
- `llm_client.py`：DeepSeek-V4 Pro SDK 封装
- `browser_use_agent.py`：browser-use 配置 + skill 注入 + schema 约束
- `output_validator.py`：JSON Schema + sample data 校验
- `playwright_runner.py`：Chrome lifecycle（一次性 profile）
- `skills/`：Authoring Skill 文件目录

### recon 消费层

新增 `browser_collection_records` 数据类型支持：recon loader 识别该类型并读取。`data_source_datasets` 发布方式不变。

## 安全 / 凭据 / 鉴权

| 范畴 | 方案 |
|---|---|
| Agent ↔ Cloud | API Token（cloud 颁发，节点配置文件保存）+ WSS |
| 商家千牛凭证 | 加密存储（DB 加密列 / KMS）；不入 git；下发给采集节点用于本地登录 |
| Runtime Profile（含 cookie）| 仅采集节点本地存储，不传输；`.gitignore` 默认排除 `profiles/` |
| 买家个人信息 | 最小化采集；存储加密；不出境；按《委托数据处理协议》处理 |
| DeepSeek API Key | 环境变量 `DEEPSEEK_API_KEY`；不入 git |
| Operator UI 鉴权 | 接现有 Tally 后台登录体系 |

## 容量规划

| 项 | 配置 |
|---|---|
| 固定采集节点数量 MVP | 1 台 |
| 采集节点配置 | Mac mini M2 16GB / 512GB SSD（~5500 元）或 Ubuntu 16GB+ |
| 单节点可 host 的 profile 数 | 串行 10-15 店稳；30 店错峰运行 OK |
| 创作 Chrome 资源 | 单任务 1.5-2GB RAM（独立进程，不占 Tally Main）|
| 固定出口 IP | 30 店各一个固定 IP |
| DeepSeek API | 单次创作 ¥3-15；每月预算 ¥500 兜底 |
| MVP 总硬件投入 | ~6000 元 |

## 子项目拆分（每个独立 spec + 实施计划）

| 序号 | 子项目 | 依赖 | 估时 |
|---|---|---|---|
| **P0** | Playbook JSON Schema 定义 + 解释器实现 | 无 | 1 周 |
| **P1** | 采集节点 daemon 骨架（WS + 心跳 + Playwright + Runtime Profile 登录）| P0 | 1-2 周 |
| **P2** | Cloud 端 Playbook Registry / Verification / 6 张 DB 表 | 无（与 P0/P1 并行）| 1 周 |
| **P3** | Cloud 端 `browser_playbook_remote` driver + Agent Connection Manager | P1 + P2 | 1 周 |
| **P4** | Authoring Worker（独立进程；browser-use + DeepSeek 集成）| P0 + P2 | 1-2 周 |
| **P5** | Operator UI（4 个页面）| P2 + P3 + P4 | 1 周 |
| **P6** | Production Push Dispatcher（错峰调度）| P3 | 0.5 周 |
| **P7** | Self-Heal Dispatcher（自动从失败创建 authoring job）| 全套上线后 | 1 周（Phase 2） |

### MVP 第一切片（首店端到端）

依赖路径：P0 → P1 → P2 + P3 → P5（最小版）→ 串起来一店跑通。
预计：3-4 周到首店生产数据。

P4 / P6 / P7 可放到 MVP 之后 sprint。MVP 阶段创作 playbook 走临时人工流程：Operator 本机用 AI 编码工具（如 Cline + DeepSeek-V4 Pro）跑出 playbook + sample，手动上传给 Playbook Registry。这是 Operator 个人开发工具流，**不属于生产架构组件**。P4 上线后切换到 Authoring Worker 自动化。

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
| 浏览器采集独立存储表 | 复用 dataset_collection_records | 沿用 2026-05-07"按采集方式分存储"约定 |
| Runtime Profile 本地存储 | 云端管理 | profile 含设备绑定信息，跨机迁移破坏稳定性 |
| 首次登录由采集节点完成 | cloud 侧登录 | 凭证只在采集节点本地使用，登录环境与采集环境一致 |
| 一店一固定出口 IP | 共享出口 IP | 店铺间网络身份隔离，避免互相影响 |
| Operator 强制 review approve | LLM 自审 / 自动 promote | 数据错误代价高，必须人卡点 |

## 后续工作（Out of Scope）

- Multi-agent fleet 编排（采集节点超 5 台时考虑）
- Authoring Worker 独立成可独立扩缩容的 service（监控指标支持后再做）
- 自动化 self-heal pipeline（生产稳定 3 月后启动）
- 商家自助绑定流程 UI（早期人工 onboard）
- ISV 授权落地后迁回官方接口（长期主线）

# Tally 浏览器采集架构设计（顶层）

## 背景

`2026-05-07-auto-recon-platform-collection-design.md` 已经把数据库、淘宝/天猫、支付宝三类来源统一进 `collection_driver` 框架，但其中明确把"网页抓取或浏览器辅助采集"列为非目标。

首个 Tally 客户是淘宝/天猫商家，有 30+ 店铺，需要的核心数据：

- 淘宝订单
- 千牛资金（非支付宝渠道）

这两类数据的官方获取方式是淘宝 ISV 授权，但 ISV 申请门槛高，短期内无法落地。

2026-05-15 已经在 Claude Code 会话中实证：用本机 Playwright + 真 Chrome + 持久化 profile + 拟人化节奏，能从千牛"财务-收支账单-日汇总"导出 T-1 资金明细 CSV。本次设计基于这次实证产出，确立 Tally 浏览器采集的顶层架构。

## 目标

1. 用一套架构同时支撑两个能力：
   - **生产采集**：每天定时从千牛/天猫等浏览器端站点抓数据
   - **采集配方创作**：遇到新站点 / 新指标 / 站点改版时，靠 AI agent 探索并写出可重放的采集脚本
2. 接入现有 `auto_scheme_run` / `sync_jobs` / `dataset_collection_records` 数据契约，不改 recon 上游。
3. 把"采集步骤"做成机器可执行 JSON（playbook），不让 LLM 进生产链路。
4. 创作与执行严格隔离：profile、出口 IP、运行时机互不污染。
5. 多店铺隔离：每店一份持久化 profile + 一个住宅出口 IP。
6. Operator 是创作产物的最终质量门，自动校验只是辅助。

## 非目标

本设计不实现以下内容：

- 客户侧 Chrome 扩展或本地 agent 安装（拒绝客户侧部署，避免感知问题与安装成本）
- 自建 stealth MCP server（指纹层反检测留作 future work，撞墙后再做，参考 memory `future_stealth_mcp_server`）
- LLM 实时驱动生产采集（生产链路必须确定性，不接 LLM API）
- 多 AI 模型混合编排（先单一选型 DeepSeek-V4 Pro + browser-use）
- 商家自助配置/提交 playbook（创作权限仅在 Operator 手中）
- 千牛 / 淘宝以外的浏览器站点适配（首期只验证千牛闭环；其他平台沿用本架构后续接入）

## 整体架构

```
┌─────────────────────────────────────────────────────────┐
│              Tally Cloud（Python monolith）              │
│                                                          │
│  ├─ recon engine（现有）                                 │
│  ├─ auto_scheme_run / scheduler（现有，扩展）             │
│  ├─ Operator UI（现有后台，加 playbook / job 管理页）     │
│  ├─ Playbook Registry & Verification（新）               │
│  ├─ Agent Connection Manager(WS hub)（新）               │
│  ├─ Production Push Dispatcher（新；调用 collection_driver）│
│  └─ Authoring Worker（新；同进程模块）                    │
│      - browser-use + DeepSeek-V4 Pro SDK                 │
│      - Chrome + Xvfb（镜像内）                            │
│      - 一次性临时 profile                                 │
│                                                          │
│  MVP：本机 Python 进程直接运行                            │
│  生产：单 Docker 镜像（recon + authoring 同容器）          │
└─────────────────────────────────────────────────────────┘
                          │ WebSocket（cloud 推任务）
                          ▼
┌─────────────────────────────────────────────────────────┐
│              生产肉机 ×N（唯一的 local agent）              │
│  - Python daemon                                         │
│  - Chrome + Xvfb + Playwright                            │
│  - 每店持久 profile（/var/lib/tally-agent/profiles/）     │
│  - 每店住宅出口 IP（住宅代理）                            │
│  - Playbook Interpreter（解释 JSON action → Playwright）  │
└─────────────────────────────────────────────────────────┘
```

## 设计原则

1. **创作与执行分离**：创作链路用 LLM，可失败可重试；生产链路 100% 确定性，禁用 LLM。
2. **Profile 不可迁移**：profile 在哪台机器原生成长，任务就路由到哪台。Cloud 永远不持有 profile 文件。
3. **Playbook 是 cloud 资产**：playbook 在 Tally cloud DB 集中存储 + 版本管理。Local agent 不存盘，每次任务消息里带。
4. **Push 触发模型**：cloud 主动 WebSocket 推任务到 agent。Agent 启动后主动出 WS 上行连接，cloud 通过同一连接下推。
5. **Operator 是终审**：playbook 上线、approve 永远人工卡点；自动校验只过滤明显错误。
6. **YAGNI**：拒绝 Chrome 扩展、stealth MCP、多模型编排、queue 中间件、独立 microservice 拆分。在没遇到具体业务信号前不拆。

## 数据模型

### 新增表

#### `playbooks`
存 playbook 仓库 + 版本 + 生命周期。

| 列 | 说明 |
|---|---|
| `playbook_id` | 业务 ID（如 `qianniu-daily-bill-export`） |
| `version` | semver |
| `title` / `description` | Operator 可读说明 |
| `playbook_json` | JSONB，主体 |
| `status` | `draft` / `replayed` / `approved` / `canary` / `active` / `deprecated` |
| `schema_check_result` | JSONB |
| `replay_result` | JSONB |
| `sample_data_path` | 创作时附带的样本数据存储路径 |
| `transcript_path` | 创作会话 transcript |
| `created_by` / `approved_by` / `approved_at` | 审计字段 |
| `canary_started_at` / `canary_completed_at` | Canary 期记录 |

#### `agents`
注册的生产肉机。

| 列 | 说明 |
|---|---|
| `agent_id` | cloud 颁发，本机不可改 |
| `hostname` | 部署主机名 |
| `version` | daemon 版本 |
| `last_heartbeat_at` | 最近 ping 时间 |
| `status` | `online` / `offline` / `draining` |
| `capabilities` | JSONB（CPU / 内存 / 已配置代理池等） |

#### `shop_agent_bindings`
shop ↔ agent ↔ proxy 三方绑定。

| 列 | 说明 |
|---|---|
| `shop_id` | 商家店铺 ID |
| `agent_id` | 该店分配到的生产肉机 |
| `proxy_endpoint` | 住宅代理 URI（按店分配）|
| `profile_status` | `none` / `initialized` / `expired` |
| `last_collection_at` | 最近一次成功采集时间 |

#### `authoring_jobs`
创作任务（Operator 触发或失败自愈触发；MVP 仅 Operator）。

| 列 | 说明 |
|---|---|
| `job_id` | UUID |
| `task_description` | Operator 输入的自然语言描述 |
| `target_skill` | 注入到 system prompt 的 skill 文件 |
| `parent_failure_id` | 关联的失败 sync_job（自愈用，Phase 2） |
| `status` | `queued` / `running` / `uploaded` / `approved` / `rejected` |
| `output_playbook_id` | 关联的 playbooks 表条目（成功后） |
| `llm_tokens_used` | 计费用 |
| `started_at` / `completed_at` | 审计 |

### 复用现有表

`sync_jobs`、`dataset_collection_records`、`dataset_bindings` 一行不动。新 `collection_driver` 写这些表的方式跟现有 driver 等价。

## 组件职责

### Cloud 端

#### Playbook Registry & Verification

- 接受 Authoring Worker 上传的 3 件套（playbook.json / sample / transcript）
- 跑 3 层校验：JSON Schema validator、Sample Data Checker、Sandbox Replay Orchestrator
- 维护 playbook 生命周期状态机：`draft → replayed → approved → canary → active → deprecated`
- 提供 Operator UI 数据查询接口

#### Agent Connection Manager（Tally main 内 async 模块）

- 持有 `agent_id → WebSocket conn` 映射（进程内 dict）
- 接受 agent 主动连入（WSS upgrade，API Token 鉴权）
- 心跳保活 30s / 次，断连后更新 `agents.status`
- 上层 driver 调 `dispatch(agent_id, message, timeout)` 同步等结果
- 重连容忍（agent 短断不丢任务）

跟 Tally main 同进程同 event loop；用 asyncio task 跑 WS server。规模到多 replica Tally main 时（不在 MVP 范围）再考虑外移成 sticky-session 服务或加 Redis 协调。

#### `browser_playbook_remote` collection_driver

接现有 `BaseConnector` / factory 模式，挂到 `finance-mcp/connectors/providers/`。

- 由 `auto_scheme_run` / `data_source_trigger_dataset_collection` 触发
- 查 `shop_agent_bindings` 找目标 agent
- 调 Agent Connection Manager `dispatch(...)` 推 `RUN_PLAYBOOK` 消息
- 同步等 agent 回结果（默认 5min 超时）
- 写 `sync_jobs` + `dataset_collection_records`

#### Authoring Worker（同进程模块）

模块路径：`finance-authoring/`。

MVP 阶段：Tally main 直接 import + async function call。
生产 Docker：单容器内同进程跑，HTTP 接口暴露给前端 / Operator UI。

职责：
- 实例化 browser-use Agent，注入 `qianniu-automation` skill 作 system prompt
- 调用 DeepSeek-V4 Pro（OpenAI 兼容协议）
- 控制 Chrome + Xvfb 生命周期（一次任务一抛弃临时 profile）
- 产 3 件套，调用 Playbook Registry 接口入库
- 计 token 消耗

#### Production Push Dispatcher

`finance-cron` 现有 scheduler 的扩展。
- 按 `playbooks.status=active` + 调度时段（02:00-06:00 错峰）触发 `auto_scheme_run`
- 失败重试：单店连续 3 次失败 → 暂停 + 告警飞书/钉钉

#### Operator UI

接现有 Tally 后台，加 4 个页面：
- 「Playbooks」列表 + 创建 + Review + Approve
- 「Authoring Jobs」列表 + 详情 + transcript 查看
- 「Agents」状态板（在线/离线/最近心跳）
- 「Shops」绑定表（shop ↔ agent ↔ proxy ↔ profile 状态）

### Local Agent（生产肉机）

#### OS 底座
Ubuntu 22.04 LTS + Xvfb（systemd 自启）+ Chrome stable + 中文字体（noto-cjk、wqy-zenhei）+ Asia/Shanghai 时区。

#### Tally Production Daemon
- Python 3.11+ async event loop
- 启动时连 cloud（WSS，API Token 鉴权）
- 收 `RUN_PLAYBOOK` 消息执行任务
- 心跳 30s / 次
- 自带 `/health` endpoint 给 systemd watchdog

#### Playbook Interpreter
- 解析 JSON `steps` 数组
- 每个 `action` 类型映射到 Playwright 调用（navigate / click / type / wait / snapshot / assert / branch / download）
- 处理 `error_handlers`（短信验证 → 立即 STOP；登录失效 → request_relogin）
- 产 sync_jobs 风格的执行记录

#### Profile Manager
- 按 shop_id 装载 `/var/lib/tally-agent/profiles/<shop_id>/`
- 首次缺 profile → 上报 cloud `NEEDS_RELOGIN`（不自己 init）
- 探测 cookies 时效性（Cookies 文件 mtime + token 过期推断）

#### Proxy Adapter
- 从消息体或 cloud config 拿到该 shop 的住宅代理 URI
- 注入 Playwright `launch_persistent_context(proxy={"server": ...})`

## 通信协议

### 传输
- WebSocket over TLS（WSS）
- Agent 主动外出连接（hardpoint 在 cloud 公网/内网域名）
- 单条消息 JSON，最大 10MB（超过用 HTTP 旁路上传 + WS 传 URL）

### 鉴权
- API Token：cloud 颁发，agent 部署时配置在 `/etc/tally-agent/config.yaml`
- Token 长期有效（手动 rotate）
- 后期需要时再加 mTLS（不在 MVP）

### 消息类型

#### Cloud → Agent

```
HELLO_ACK              # 鉴权握手成功
RUN_PLAYBOOK           # 推一次采集任务
  body:
    job_id, shop_id, playbook_json, params, proxy_endpoint, timeout_ms
SHIP_PROFILE           # 首次扫码后 cloud 通知 agent 接受 profile 初始化（MVP 不实现，先 SSH 手动）
UPGRADE                # 推升级版本号 + 下载 URL
DRAIN                  # 准备下线，跑完手头任务后断开
```

#### Agent → Cloud

```
HELLO                  # 启动握手，带 agent_id + token + version
HEARTBEAT              # 30s / 次
TASK_RESULT            # RUN_PLAYBOOK 的结果
  body:
    job_id, status (success/failed), data_url (下载链接 / 内嵌 base64), error_info
NEEDS_RELOGIN          # profile 失效告警，触发 Operator 介入流程
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
  ↓
  WS 推送
  ↓
agent 收到 → 启 Playwright → 跑 playbook → 上传产物
  ↓
agent → TASK_RESULT
  ↓
cloud driver → 写 sync_jobs / dataset_collection_records → 返回 auto_scheme_run

升级:
  cloud → UPGRADE
  agent → 下载 → 替换 → systemd 拉起新版本 → 重新 HELLO
```

## 数据流（端到端）

### 生产采集

```
[02:00 错峰时段]
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
查 shop_agent_bindings → 取 agent_id + proxy
  ↓
Agent Connection Manager.dispatch(agent_id, RUN_PLAYBOOK)
  ↓ WebSocket
agent: 启 Chrome（用 shop 持久 profile + 该店住宅代理）→ 跑 playbook
  ↓ download CSV / 抓数据
agent → cloud TASK_RESULT（含数据 URL）
  ↓
driver 拉取数据 → 解析 → 写 dataset_collection_records
  ↓
sync_jobs.status = success
  ↓
auto_scheme_run 继续 → proc/recon
```

### 采集配方创作

```
Operator 在 UI 点「新建 Authoring Job」，填任务描述
  ↓
authoring_jobs.queued
  ↓
Authoring Worker 拉队列 → 启动 browser-use Agent
  ↓
Agent 多轮调用 Playwright → 探索目标站点 → 试错
  ↓ (Phase 2：中途需 Operator 介入 → 通过 Operator UI 聊天框打通)
Agent 收敛产物：playbook.json + sample-data + transcript.md
  ↓
Worker 调 Playbook Registry 接口入库 → status=draft
  ↓
Verification Service 跑：
  1. JSON Schema Validator
  2. Sample Data Checker
  3. Sandbox Replay（Worker 再跑一遍 playbook 验证）
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
| Agent 离线 | dispatch 超时（30s）→ sync_jobs.status=failed → 告警 + 自动重试（最多 3 次，间隔 30min） |
| Chrome 进程崩溃 | agent 重启该任务（最多 1 次）→ 仍失败上报 |
| Playbook 步骤 selector 缺失 | playbook 内部 retry 2 次 → 失败 → 触发 self-heal job（Phase 2）/ 告警 Operator（MVP） |
| 短信验证 popup | 立即 STOP，上报 `NEEDS_RELOGIN` → Operator 介入 |
| 出口住宅 IP 失效 | 上报 cloud → cloud 重新分配代理 → 重试任务 |
| 长任务超时 | dispatch 默认 5min；导出大数据 playbook 可在 RUN_PLAYBOOK 消息里加 `timeout_ms` 覆盖 |

### 创作链路

| 故障 | 处置 |
|---|---|
| LLM 调用失败 | browser-use 内置 retry；3 次失败 → authoring_jobs.status=rejected + 告警 |
| Agent 死循环（token 烧光预算）| 每个 job 设置 token 上限（默认 50k）→ 超出 → 强制停 + 告警 |
| 创作时撞风控（短信验证）| Worker 报告失败 + transcript → Operator 看 transcript 决定怎么办（可能换站点路径） |
| Schema 校验失败 | authoring_jobs.status=rejected，原因写入 reject_reason；Operator 看后决定重跑 |
| Sandbox replay 失败 | 同上，附 replay 详细 log |
| Sandbox replay 数据偏差 > 5% | 同上 |

## 现有 Tally 集成点

### finance-mcp/

- `connectors/providers/browser_playbook_remote.py`：新 driver，遵循 BaseConnector 接口
- `connectors/factory.py`：注册新 driver
- 仍然写 `sync_jobs` 表、`dataset_collection_records` 表

### finance-cron/

- `run_scheduler.py`：扩展 Production Push Dispatcher 逻辑
- 错峰调度配置在 `config/` 下新增 YAML

### finance-authoring/（新建）

- `worker.py`：authoring 入口
- `llm_client.py`：DeepSeek-V4 Pro SDK 封装
- `browser_use_agent.py`：browser-use 配置 + skill 注入 + schema 约束
- `output_validator.py`：JSON Schema + sample data 校验
- `playwright_runner.py`：Chrome lifecycle（一次性 profile）
- `skills/qianniu-automation.md`：操作宪法（从 `.claude/skills/` 拷或软链）

### 数据集消费层

不需要改动。`dataset_collection_records` 写入后，recon 自动消费。

## 安全 / 凭据 / 鉴权

| 范畴 | 方案 |
|---|---|
| Agent ↔ Cloud | API Token（cloud 颁发，agent 配置文件保存）+ WSS |
| 商家千牛凭据 | 加密存储（DB 加密列 / KMS）；不入 git；扫码后实际生效的是 cookies（不是密码） |
| Profile 内含 cookies | 仅本机存储，不传输；`.gitignore` 默认排除 `profiles/` |
| DeepSeek API Key | 环境变量 `DEEPSEEK_API_KEY`；不入 git |
| Operator UI 鉴权 | 接现有 Tally 后台登录体系（默认） |

## 容量规划

| 项 | 配置 |
|---|---|
| 生产肉机数量 MVP | 1 台 |
| 生产肉机配置 | Mac mini M2 16GB / 512GB SSD（~5500 元）或 Ubuntu 16GB+ |
| 生产肉机能 host 的 profile 数 | 串行 10-15 店稳；30 店错峰运行 OK |
| 创作 Chrome 资源 | 单任务 1.5-2GB RAM；同进程 Tally 镜像总占 3-4GB |
| 住宅代理 | 30 店 × $5-15/月 ≈ $200-400/月 |
| DeepSeek API | 单次创作 ¥3-15；每月预算 ¥500 兜底 |
| MVP 总硬件投入 | ~6000 元 |
| MVP 总月度运营 | ~¥3000（代理 + LLM + 电费） |

## 子项目拆分（每个独立 spec + 实施计划）

| 序号 | 子项目 | 依赖 | 估时 |
|---|---|---|---|
| **P0** | Playbook JSON Schema 定义 + 解释器实现 | 无 | 1 周 |
| **P1** | Local agent daemon 骨架（WS + 心跳 + Playwright 集成）| P0 | 1-2 周 |
| **P2** | Cloud 端 Playbook Registry / Verification / 4 张 DB 表 | 无（与 P0/P1 并行）| 1 周 |
| **P3** | Cloud 端 `browser_playbook_remote` driver + Agent Connection Manager | P1 + P2 | 1 周 |
| **P4** | Authoring Worker（browser-use + DeepSeek 集成）| P0 + P2 | 1-2 周 |
| **P5** | Operator UI（4 个页面）| P2 + P3 + P4 | 1 周 |
| **P6** | Production Push Dispatcher（错峰调度）| P3 | 0.5 周 |
| **P7** | Self-Heal Dispatcher（自动从失败创建 authoring job）| 全套上线后 | 1 周（Phase 2） |

### MVP 第一切片（首店端到端）

依赖路径：P0 → P1 → P2 + P3 → P5（最小版）→ 串起来一店跑通。
预计：3-4 周到首店生产数据。

P4 / P6 / P7 可放到 MVP 之后 sprint。MVP 阶段创作 playbook 走临时人工流程：Operator 本机用 Claude Code（或国内替代如 Cline + DeepSeek-V4 Pro）跑出 playbook.json + sample，手动上传给 Playbook Registry。这是 Operator 个人开发工具流，**不属于生产架构组件**。P4 上线后切换到 cloud Authoring Worker 自动化。

## 决策记录

| 决策 | 备选 | 选择理由 |
|---|---|---|
| 不做 Chrome 扩展 | 客户装扩展 | 客户感知问题 + 安装阻力 |
| Tally 单 monolith | recon / authoring 拆服务 | 当前规模无 ops 需求拆 |
| Push 而非 Pull 触发 | Agent 主动拉 | 跟现有 auto_scheme_run 同步生命周期一致 |
| WebSocket 而非 HTTP RPC | 队列 / VPN | 最简基础设施，agent 不需公网 |
| DeepSeek-V4 Pro + browser-use | Qwen-Max + browser-use / 自写 agent loop | DeepSeek 性价比 + 国内合规 + browser-use 现成 |
| Playbook JSON + Skill Markdown 双形态 | 全 Markdown / 全 JSON | JSON 给机器跑稳，Markdown 给人/AI 读懂操作原则 |
| Profile 本地存储 | Profile 云端管理 | Profile 含设备指纹 / IP-bound，跨机迁移破坏 trust |
| 一店一住宅代理 | 共享出口 IP | 多店同源 = 风控关联标记 |
| Operator 强制 review approve | LLM 自审 / 自动 promote | 数据错误代价高，必须人卡点 |

## 后续工作（Out of Scope）

- 自建 stealth MCP server（参考 memory `future_stealth_mcp_server`）
- Multi-agent fleet 编排（生产肉机超 5 台时考虑）
- Cloud 端 authoring worker 独立成微服务（监控指标支持后再做）
- 自动化 self-heal pipeline（生产稳定 3 月后启动）
- 商家自助绑定流程 UI（早期人工 onboard）

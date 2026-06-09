# 对账日报（周/月预留）+ 归因引擎 + 资金安全预警 — 设计文档

- 日期：2026-06-06
- 状态：已确认设计，待写实现计划
- 目标版本：v2（产品已上线，本功能随下一版发布，不追赶单周临时版）

## 1. 背景与价值

Tally 已上线，首个验证客户为**武汉福游网络科技有限公司**（淘系 34 个对账任务，订单对账 + 资金对账）。当前能力是"每天 T-1 跑对账、产出差异"，但差异是一堆原始数据，客户仍需人工判断"为什么差、要不要紧"。

本功能把对账从**差异检测**升级为**给财务负责人/老板一份「今天发现了哪些问题、归因是什么、预警了哪些资金安全」的钉钉日报**，放大自动对账的价值，支撑付费验证。周报/月报仅做架构预留，本期不投递。

### 1.1 首要交付目标 = 老板三件套 + 财务底稿

**本设计的首要价值产物，是面向老板/财务的两组报表**；自动对账差异检测是**底座**，三件套+底稿是建在底座上的**面向人的价值产物**。两者关系：差异检测产出逐行配对结果与四类配对状态（matched / matched_with_diff / source_only / target_only），三件套+底稿在其**全量聚合**之上提炼老板/财务真正关心的资金健康指标。

**老板三件套（`view=老板摘要`）**：

| 代号 | 名称 | 一句话 | 可行性 |
|---|---|---|---|
| T1 | 资金到账总览（漏斗） | 本期 买家实付总额 → 退款总额 → 已到账 → 正常在途 → 待核查超期未到账 | 部分（货款口径） |
| T2 | 平台综合净扣减率 | 在「已到账订单」上 买家实付−退款−实际到账 = 平台扣减总额；扣减率=扣减/应收（环比本期暂缓，见 §11） | 部分（差额倒算，非精确佣金） |
| T3 | 钱卡住预警 | sold-orders 付款时间 vs bill-details 打款时间，超 N 天未到账 → 信号级预警 | 可（信号级） |

**财务底稿（`view=财务明细`）**：

| 代号 | 名称 | 一句话 | 可行性 |
|---|---|---|---|
| F1 | 自动对账差异清单 + 归因 | 差异行（matched_with_diff ∪ source_only ∪ target_only）+ 规则引擎归因 | 可 |
| F2 | 回款周期 | 打款时间 − 付款时间（matched 行，按资金计划均值/分布） | 部分（需引擎级全量落点） |
| F3 | 资金计划回款健康度排名 | 在途占比 + 退款率 + 挂账天数 → 红黄绿（环比本期暂缓，见 §11） | 部分（货款口径） |

> **关键可行性约束（设计依据）**：所有金额型指标（T1/T2/F2/F3）都依赖一个**当前 0 实现的「run 级 / biz_date 级 全量聚合落点」**——现状 `canonical_recon_line` 只落差异行，平账（matched_exact）行的金额/时间**从不离开配对引擎**，summary 仅四类计数，`execution_run_exceptions` 在异常 >1000 时被采样截断。因此本设计**新增 `recon_period_rollup` 表（§6.2）作为唯一可信金额源**，并在配对引擎内对全量行做 SUM（§6.4）。digest 金额**绝不复用** `execution_run_exceptions` 计数。第一版不建独立店铺/主体映射表，老板三件套以**资金对账计划 `plan_code`** 为最小汇总单元，公司总览 = scope 内资金对账计划 rollup 求和。

### 核心原则（贯穿全文）

- **数字确定性、措辞 LLM 化**：运行时的 normalize / 归因 / 预警**全部确定性规则**，金额与结论一律由确定性层计算；LLM（DeepSeek）只出现在①离线字段映射提案 ②离线归因规则提案 ③运行时日报叙事生成（数字只传不算）。这是财务 AI 的防幻觉主心骨。
- **引擎通用、知识分包**：引擎与 canonical 核心通用；字段映射 / 归因规则 / 预警指标按**对账域**分包配置，是产品的可积累 IP。
- **失败安全**：每步幂等可重跑；LLM 失败退回模板；完整性缺口阻断老板/财务正式投递，只通知内部数据责任人。

## 2. 关键决策（brainstorming 确认）

| # | 决策 | 取值 |
|---|---|---|
| 1 | spec 范围 | 完整产品（含 Web 管理界面），一份大 spec，v2 发布 |
| 2 | LLM 角色 | DeepSeek v4（`LLM_PROVIDER=deepseek`）；仅离线提案（映射/规则）+ 运行时叙事；运行时归因/预警全确定性 |
| 3 | 配置面 | 全套 Web 管理界面 |
| 4 | 触发与取数 | 由「订阅(subscription)」定义 scope；本期只做 T-1 日报，周/月按 `biz_date` 区间预留 |
| 5 | 周期锚点 | 自然周 / 自然月（可配） |
| 6 | 架构 | 方案 A：物化层（新建 canonical/归因/预警/digest 表） |
| 7 | 跨行业抽象 | 留「对账域(recon_domain)」接缝 + 本期只做电商域；metric 做成可配置公式 |

## 3. 现状事实（实测，设计依据）

### 3.1 三份数据（资金/订单对账输入）

- **财务中台交易订单明细** = `public.ods_yxst_trd_order_di_o`（外部 DB 连接同步入 `dataset_collection_records`，~300 万行）。字段含 `customer_order_no/custom_order_no、amt_out_sale、tax_sale_amount、order_finish_time` 等。
- **店铺订单 (sold-orders)** = 浏览器采集，存 `browser_collection_records`。字段：`订单编号、总金额、买家实付金额、退款金额、订单状态(交易成功)、支付单号、订单付款时间、订单创建时间`。
- **店铺收支明细 (bill-details)** = 浏览器采集，存 `browser_collection_records`。字段：`订单号、订单实际金额（元）、退款金额（元）、退款单号、打款时间、业务大类、账单大类、收/付渠道、业务流水号、商户订单号` 等。
- **支付宝资金账单** (`platform_alipay_bill_lines`) 暂未用于对账（仅支付宝单通道，不全）。

### 3.2 对账绑定

- **订单对账**：left = `ods_yxst_trd_order_di_o`（财务中台），right = `sold-orders`（店铺订单）。
- **资金对账**：left = `sold-orders`（店铺订单），right = `bill-details`（收支明细）。

### 3.3 可行性边界（诚实）

- 收支明细当前**只采了「业务大类=交易货款 / 账单大类=货款收入」**，没有手续费/营销/退款支出/提现的独立台账行；`收/付渠道` 为 `支付宝 / 聚合结算账户渠道`（**多渠道**，非单支付宝）。
- **现三份能做**：跨期在途、退款（净额）、**总扣减额**、订单↔货款勾稽差异、少打款**信号**、长期挂账。
- **现三份做不到**：把差额**细分到佣金/营销/技术服务费**（无费用明细行）、少打款**确诊**（不知应扣多少）、**提现是否到账**（无银行流水，超范围）。
- **解锁路径**：补采「千牛费用明细」（把收支明细从只采货款收入扩展到全业务大类）+「平台结算单/银行流水」——作为增值/付费解锁点，规则包预留 reason_code。

#### 3.3.1 三件套口径降级（诚实命名，必须贯穿文案）

- **T2 不是「平台真实抽成/佣金率」**，降级命名为 **「平台综合净扣减率（差额倒算）」**——无独立手续费/佣金/营销台账，差额法把技术服务费+佣金+营销扣款+优惠券分摊**全塞进「综合扣减」**。卡片/叙事文案禁止宣称是精确佣金率，须标「含手续费/营销，非精确佣金」。
- **T1 「实际到账总额」是「货款口径净到账」，不是资金账户真实净到账**——bill-details 只采货款收入一类，不含补贴/活动返款/保证金及任何资金支出。因此**漏斗非商家真实净资金**。老板卡片不再展示笼统残差式「待核查缺口」，而是展示**超期未到账净应收**（疑似卡单/漏结，见 §9.1）。
- **两侧 biz_date 语义不同**：sold-orders 为**付款日**，bill-details 为**账期/到账日**。跨期漏斗（T1）与回款周期（F2）须显式声明**以付款日为锚**。
- **成本/毛利/利润/费用拆分/提现到账：本期谨慎拆分**。财务中台 `ods_yxst_trd_order_di_o` 有 `tax_cost_amount`（含税成本）与 `tax_sale_amount`（含税销售）字段，可作为**中台口径含税毛利**候选；但净利润仍缺平台费用明细、营销/人工/银行等费用与银行流水。因此本期老板摘要不承诺净利润，产品上区分「中台口径毛利（待验证）」与「净利润灰显占位」（见 §15）。

#### 3.3.2 bill-details 数据契约（join 与聚合，避免金额高估）

1. **预聚合**：bill-details 须**按订单号预聚合**（子订单多行 → SUM，跨收/付渠道全量求和）**再 join**；否则 outer merge 一对多炸行使 T1/T2 金额高估。
2. **join 键归一**：sold-orders `订单编号` vs bill-details `订单号` 两侧 `strip` + 统一；`商户订单号 / 子订单号` 不可作主键。
3. **biz_date 锁定**：sold-orders=付款日、bill-details=账期/到账日；跨期漏斗与 F2 回款周期以**付款日 cohort** 为锚，不复用同日双边过滤的资金对账结果直接算金额。
4. **截至时间（`as_of_ts`）**：`as_of_ts` 不是业务表字段，而是系统生成 rollup/digest 时的截止时间（如 T-1 日报在 2026-06-06 09:00 生成，则 `as_of_ts=2026-06-06 09:00`）。T1/F2 先取付款日 cohort，再查这些订单截至 `as_of_ts` 的到账情况。
5. **到账回查窗口**：bill-details 以 `订单号` 回查，`打款时间 <= as_of_ts` 为到账事实；`账期` 只作性能过滤窗口（`period_start <= 账期 <= as_of_ts 日期`），`打款时间` 缺失时才 fallback 到 `账期`。

### 3.4 复用的现有能力

- LLM 客户端：`finance-agents/data-agent/utils/llm.py` `get_llm()`（LangChain `ChatOpenAI`，OpenAI 兼容），`config.py` 的 `LLM_PROVIDER=deepseek` + `DEEPSEEK_MODEL`。
- 既有 `finance-agents/data-agent/graphs/rule_generation/`：规则提案可在其上扩展。
- 对账主链路：`finance-agents/data-agent/graphs/recon/auto_scheme_run/`，产出差异并已有 owner 富化（`_resolve_owner_for_anomaly` 读 `owner_mapping_json` 的 `default_owner / anomaly_type_to_owner / mappings`）。
- 异常存储：`execution_run_exceptions`（归因结果回填于此，打通现有闭环）。
- 钉钉投递：`company_channel_configs`（安徽纳迈，`provider=dingtalk_dws`，`robot_code=dingmm03p1to5dq1jq1q`）+ dws CLI（contact/chat/doc/sheet）。
- DB 迁移运行器：`finance-mcp/auth/migrate.py`（schema_migrations 追踪，幂等，advisory lock）。新表用迁移 039+。

## 4. 总体架构

### 4.1 模块与落点

| 模块 | 职责 | 落点 |
|---|---|---|
| `normalize` | 配对结果按 `field_mapping` → `canonical_recon_line` | data-agent/graphs/recon/normalize/ |
| `attribution` | 差异行跑规则库 → 原因码；回填 `execution_run_exceptions` | data-agent/graphs/recon/attribution/ |
| `alerts` | 结果+基线跑检测器 → `recon_alert` | data-agent/graphs/recon/alerts/ |
| `digest` | 按订阅 scope×biz_date 聚合 + DeepSeek 叙事 | data-agent/graphs/recon/digest/ + utils/llm |
| `delivery` | 钉钉 ActionCard 多选推送 + 回写入口 | 复用 company_channel_configs + dws |
| 数据模型+API | 新表迁移 + 规则/映射/订阅 读写（MCP tools） | finance-mcp（migrations 039+，tools/） |
| 调度 | 日报发送窗口 + 完整性硬闸门 + 重试 | finance-cron/run_scheduler |
| Web 管理 | 字段映射 / 规则库 / 订阅&接收人 / 日报详情 | finance-web/src |

### 4.2 数据流（日报）

```
T-1 对账批次(现有) → 配对结果
  → 配对引擎全量 SUM(§6.4) → recon_period_rollup  (全量金额/回款周期·三件套+底稿金额源)
  → normalize  →  canonical_recon_line          (按 field_mapping，仅差异行)
  → attribution → recon_attribution + 回填 execution_run_exceptions
  → alerts     →  recon_alert                   (含 per-plan 基线)
  ── 调度到点 + 完整性硬闸门(expected_run_plans 全部 success + 后处理完成) ──
  → digest 聚合(scope×biz_date) → DeepSeek 叙事 → recon_digest
  → delivery: 钉钉 ActionCard → 订阅接收人(多选) + 详情页链接
  → 接收人点[标记已核销/转人工] → 回写 recon_alert / execution_run_exceptions
```

normalize / attribution / alerts 作为**每个对账 run 完成后的后置步**执行（data-agent 内），基线每日更新。周报/月报本期暂缓，仅在 `period` 与 `biz_date` 区间上预留接缝，后续增量扩展。

## 5. 对账域（recon_domain）抽象

一个对账域 = `{canonical 语义别名 + 字段映射模板 + 归因规则包 + 预警指标包}`。

- 引擎与 canonical **核心字段**（`left_amount/right_amount/diff_amount/order_no/biz_date/各时间/match_status`）通用。
- `receivable_amount / settled_amount / refund_amount` 等是**电商域语义别名**，靠 field_mapping 落上去。
- `field_mapping / attribution_rule / alert_rule / canonical_recon_line / metric_definition` 均带 `domain` 维度。
- **本期只产出一个域：`电商对账`（含 order / fund 两类）**；不构建其他域，但接缝（domain 维度 + metric 可配置）就位，传统企业接入 = 加域包不重写。

## 6. 数据模型（新表，迁移 039+；表名加前缀避免冲突）

> 规模约束：订单行约 300 万，**`canonical_recon_line` 只落差异行**（mismatch / 单边缺失），平账只在 run 级汇总计数。差异行与 `execution_run_exceptions` 一一对应。
>
> **金额聚合口径修正（关键）**：`canonical_recon_line` 只落差异行的设计成立，但**三件套+底稿的金额绝不能从它取**——它只有差异行，缺全部平账（matched_exact）金额。**全量金额/时间聚合唯一可信源 = §6.2 新增 `recon_period_rollup` 表**。digest 金额一律从 rollup 取，**绝不复用** `execution_run_exceptions` 行 SUM（异常 >1000 时该表被分层采样截断，`auto_scheme_run/nodes.py:3684-3705`）；差异**计数**取 summary 四类 count（采样前全量），差异**金额**取 rollup。

### 6.1 配置表（Web 管理界面读写，JSONB 驱动）

- **`field_mapping`**：`mapping_code, domain, scope{platform,dataset_kind}, fields(jsonb), version, status, created_at`
- **`attribution_rule`**：`rule_code, domain, scope{platform,recon_type}, priority, when(jsonb), then(jsonb), enabled, version`
- **`metric_definition`**：`metric_code, domain, formula(jsonb **作用于 `recon_period_rollup` 全量字段 / canonical 字段**，不作用于 exceptions 计数), description`
  - 三件套+底稿初始 metric（公式见 §9.1，全部以付款日 cohort 为 biz_date 锚、货款口径）：`receivable_total / refund_total / net_receivable_total / settled_total / normal_in_transit_amount / stuck_amount / net_deduction_total / net_deduction_rate / payback_days_avg / refund_ratio / stale_diff_days`。
- **`alert_rule`**：`rule_code, domain, scope, metric_code→metric_definition, condition(jsonb), severity, alert_template, enabled`
- **`digest_subscription`**：`id, company_id, period(daily|weekly|monthly), scope(jsonb，老板/财务日报默认 `{"mode":"company_all"}`，即当前公司当天所有启用对账任务), recipients(jsonb 钉钉userId数组), view(老板摘要|财务明细), schedule, anchor(jsonb), send_window(jsonb: start/end/retry_interval_minutes，默认5分钟), failure_recipients(jsonb 内部数据责任人/运维userId数组，可继承公司默认), enabled`

### 6.2 运行结果表（引擎确定性写入）

- **`canonical_recon_line`**（仅差异行）：`id, company_id, domain, execution_run_id, exception_id→execution_run_exceptions, plan_code, plan_name_snapshot, recon_type, biz_date, order_no, channel, receivable_amount, settled_amount, refund_amount, left_amount, right_amount, diff_amount, pay_time, settle_time, finish_time, match_status, order_status`
  - 索引：`(company_id,biz_date)`、`(plan_code,biz_date)`
- **`recon_attribution`**：`id, line_id→canonical_recon_line, rule_code, reason_code, is_true_diff, confidence, explain_text, created_at`
- **`recon_shop_baseline`**：`company_id, plan_code, metric_code, window, value, stddev, sample_count, updated_at`
- **`recon_alert`**：`id, company_id, domain, biz_date, plan_code, plan_name_snapshot, alert_code, severity, amount, evidence(jsonb), status(open|ack|resolved), first_seen_biz_date, last_seen_biz_date, created_at`
- **`recon_period_rollup`**（**全量聚合落点 / 三件套+底稿唯一可信金额源**）：`id, company_id, domain, plan_code, plan_name_snapshot, recon_type, biz_date, as_of_ts,`
  - 金额（从 jsonb 文本 `::numeric` cast，排除 `record_status='deleted'`）：`receivable_amount_total`(买家实付合计) `refund_amount_total`(退款合计) `net_receivable_amount_total`(买家实付-退款) `settled_amount_total`(截至 as_of 已到账合计) `normal_in_transit_amount_total`(未到账且未超 N 天净应收) `stuck_amount_total`(未到账且超 N 天净应收/待核查) `net_deduction_total`(matched 净应收-到账) `net_deduction_rate`(扣减/已到账订单净应收)
  - 计数：`cohort_order_count, settled_order_count, normal_in_transit_count, stuck_order_count, matched_with_diff_count, source_only_count, target_only_count, diff_amount_total`
  - 回款周期（matched 行 daydiff 引擎内算）：`payback_days_sum, payback_days_count`（均值=sum/count，分布另落或抽样）
  - **唯一约束：`(company_id, plan_code, biz_date, recon_type)`**；索引 `(company_id,biz_date)`、`(plan_code,biz_date)`
  - **此表覆盖全量付款日 cohort（含 matched_exact），与会被采样的 anomaly/exceptions 解耦**；由配对引擎/资金 rollup 回查全量 SUM 写入（§6.4）。
- **`recon_digest`**：`id, subscription_id, company_id, period, period_start, period_end, structured(jsonb), narrative(text), completeness(jsonb), status, delivered_at`
  - 唯一约束：`(subscription_id, period_start, period_end)` —— 一订阅×一周期幂等一条

### 6.3 与现有表关系

`canonical_recon_line.exception_id → execution_run_exceptions.id`；归因的 `reason_code/is_true_diff` 回填到 `execution_run_exceptions`，现有异常闭环 UI 直接显示归因。平账总量走 `execution_run` 汇总，不落明细。**全量金额走 `recon_period_rollup`**（§6.2），与 `canonical_recon_line`（只差异行）/`execution_run_exceptions`（采样）解耦。

### 6.4 配对引擎全量聚合改动（金额落点的实现接缝）

三件套+底稿的所有金额，**当前 0 实现**：`matched_exact` 行的金额/时间从不离开配对引擎，`build_recon_observation.summary` 只有四类 count（`execution_service.py:706-712`），`_persist_execution_run`（`auto_scheme_run/nodes.py:1584-1633`）无金额列。落地接缝：

1. **`finance-mcp/recon/mcp_server/recon_tool.py` `execute_single_recon`**：在 `_compare_dataframes` 之后（此处仍持有 `matched_exact`/`matched_with_diff`/`source_only`/`target_only`，含 `source_`/`target_` 前缀金额列），新增**全量 SUM**：`sum(source_买家实付)`/`sum(target_订单实际金额)`/`sum(退款)`/`source_only 在途金额`/`matched 行 (打款时间−付款时间) daydiff sum/count`，与配对计数并列塞入返回 dict。**次选（data-agent 侧重载求和）不可行**——matched_exact 行从不离开引擎。
2. **`execution_service.py build_recon_observation.summary`**：扩出上述金额聚合字段。
3. **`auto_scheme_run/nodes.py _persist_execution_run`**：把金额聚合打通持久化到 `recon_period_rollup`（按 `(company_id,plan_code,biz_date,recon_type)` upsert，幂等重跑覆盖），同时保存 `plan_name_snapshot` 作为展示名来源。
4. **bill-details 侧**按订单号预聚合（子订单多行→SUM，跨渠道全量）再参与 SUM（见 §3.3.2），避免一对多炸行高估。
5. **资金三件套专用 cohort 回查**：T1/T2/F2 不直接复用当前“左右两侧同日过滤”的资金对账结果。实现需先取 sold-orders 付款日 cohort，再用 cohort 的 `订单编号` 回查 bill-details 中 `打款时间 <= as_of_ts` 的到账记录，聚合后写 `recon_period_rollup`。
6. **第一版不建独立主体映射表**：公司/老板总览按订阅 scope 内 `recon_type='fund'` 的资金对账 `plan_code` 求和；财务底稿把资金对账计划和订单对账计划分区展示。若未来需要把“xx订单对账 + xx资金对账 + 毛利”合并成一张经营主体卡，再在订阅配置里加轻量 plan 分组，而不是先做通用主体映射表。

## 7. 规范化模型 + 字段映射

### 7.1 canonical 字段集

| 概念字段 | 含义 | 淘宝来源示例 |
|---|---|---|
| `order_no` | 关联键 | 订单编号 / 订单号 / customer_order_no |
| `plan_code`,`plan_name_snapshot`,`biz_date`,`recon_type`,`channel` | 维度 | 运行计划 / 展示名 / 付款日 / order\|fund / 收·付渠道 |
| `receivable_amount` | 应收 | 店铺订单·买家实付金额 |
| `settled_amount` | 实收/到账 | 收支明细·订单实际金额 |
| `refund_amount` | 退款 | 退款金额 |
| `left_amount`/`right_amount`/`diff_amount` | 两侧值与差额 | 配对计算 |
| `pay_time`/`settle_time`/`finish_time` | 付款/打款/完成 | 订单付款时间 / 打款时间 / order_finish_time |
| `match_status`,`order_status` | matched/amount_mismatch/left_only/right_only；交易成功→success | 订单状态(value_map) |

### 7.2 字段映射 JSON（按 平台×dataset_kind 一份，全店铺复用）

```json
{ "mapping_code": "taobao.sold_orders.v1",
  "domain": "ecom",
  "scope": {"platform":"taobao","dataset_kind":"sold_orders"},
  "fields": {
    "order_no":          {"from":"订单编号","type":"id","role":"join_key"},
    "receivable_amount": {"from":"买家实付金额","type":"money"},
    "refund_amount":     {"from":"退款金额","type":"money"},
    "pay_time":          {"from":"订单付款时间","type":"datetime"},
    "order_status":      {"from":"订单状态","type":"enum",
                          "value_map":{"交易成功":"success","交易关闭":"closed"}} } }
```

### 7.3 自动提案 + 人工确认流

1. 打开映射页 → 读真实列名 + 样本值（collection records）。
2. 启发式预匹配：复用 `semantic_type/business_role` + 同义词。
3. DeepSeek 离线提案：`{列名+样本+规范字段表+dataset_kind}` → `{规范字段:{from,confidence}}`。
4. Web 确认页：提案与样本并排，低置信高亮，人确认/改。
5. 存版本化 `field_mapping`（按平台 scope）→ 全平台店铺复用；新平台才重新提案。

normalize：对账产出差异行后，按源平台 `field_mapping` 投影 payload → canonical（value_map 归一化枚举）。**无映射的平台 → 跳过并在日报标"未配置映射"**（映射是前置闸门）。

> 待实现期确认：财务中台订单 `order_no`/金额取哪列（`custom_order_no` vs `customer_order_no`、`amt_out_sale` vs `tax_sale_amount`）连真表二次核对。

## 8. 归因引擎 + 规则库

### 8.1 规则 JSON 与求值

```json
{ "rule_code":"cross_period_in_transit", "domain":"ecom", "priority":10,
  "scope":{"platform":"taobao","recon_type":"fund"},
  "when":{"all":[
     {"field":"match_status","op":"eq","value":"right_only"},
     {"field":"pay_time","op":"within_days","ref":"as_of","days":2}]},
  "then":{"reason_code":"跨期在途","is_true_diff":false,"severity":"info",
          "explain":"订单{order_no}付款于{pay_time},货款未结算,跨期在途"} }
```

求值：按 `scope`(platform+recon_type) 过滤 enabled → 按 `priority` 排序 → **首条命中即采用**（emit + 渲染 explain）；无命中 → `未归因/需人工`。算子集固定文档化：`eq/ne/gt/lt/gte/lte/in/within_days/abs_diff_ratio_lt/present/absent/between`。

### 8.2 淘系初始规则包 v1

| reason_code | 触发 | is_true_diff |
|---|---|---|
| 跨期在途 | 订单有·收支无打款 + 付款≤N天 | 否(正常) |
| 退款相关 | refund_amount>0 且 diff≈退款 | 视情况 |
| 平台扣减(含手续费) | 金额不符 且 应收>实收 且 扣减率在常见带内 | 否(正常·只给总扣减) |
| 久未结算/疑漏结 | 订单有·收支无 + 付款>N天 | 是(待关注) |
| 收支有·订单无 | 资金侧单边 | 是(需人工) |
| 未归因 | 无规则命中 | 是(需人工) |

订单对账同构：漏同步 / 金额不符 / 状态不符 / 跨期。佣金/营销细分预留 reason_code，待第 4 份数据。

### 8.3 DeepSeek 规则提案（离线）

复用 `graphs/rule_generation/`：定期/手动把一批 `未归因` 差异 + 上下文喂 DeepSeek → 提议 `{模式→reason_code+when条件}` → 人在规则库编辑页 review/改 → 晋升为 `attribution_rule`(enabled)。**运行时永远确定性引擎，LLM 不参与归因判定。**

### 8.4 输出

每条差异写 `recon_attribution`；回填 `execution_run_exceptions`。digest 按 reason_code 分组，`is_true_diff=true(真异常/待关注)` 与 `false(已归因正常)` 分开统计。

## 9. 资金安全预警引擎

**顺序**：预警在归因**之后**跑，已归因正常项（跨期/扣减）从"未解释残差"剔除，只对真异常残差报警。

### 9.1 检测器 + metric 可配置

```json
{ "rule_code":"platform_underpay", "domain":"ecom",
  "scope":{"platform":"taobao","recon_type":"fund"},
  "metric_code":"residual_gap_ratio",
  "condition":{"op":"gt","threshold":{"type":"baseline_sigma","k":2}},
  "severity":"high",
  "alert":"{plan_name}货款缺口{gap}元(应收{receivable}的{pct}),超历史均值,疑似少打款" }
```

初始 metric（`metric_definition`，公式作用于 `recon_period_rollup` 全量字段，按 `plan_code × biz_date × recon_type`；金额从 `browser_collection_records.payload` jsonb `::numeric`，排除 `deleted`）：

**三件套（老板）**
- **T1 `receivable_total`** = Σ`(sold-orders.payload->>'买家实付金额')::numeric` over 付款日 cohort。
- **T1 `refund_total`** = Σ`(sold-orders.payload->>'退款金额')::numeric` over 付款日 cohort。
- **T1 `net_receivable_total`** = Σ`max(买家实付金额 − 退款金额, 0)` over 付款日 cohort。
- **T1 `settled_total`** = cohort 订单在 bill-details 中截至 `as_of_ts` 已匹配到账金额合计；bill-details 按 `订单号` 先聚合，`打款时间 <= as_of_ts`，跨收/付渠道全量，子订单多行 SUM。
- **T1 `normal_in_transit_amount`** = Σ`net_receivable` WHERE cohort 订单未匹配到账，且 `as_of_ts - 订单付款时间 <= N天`。
- **T1 `stuck_amount` / 待核查金额** = Σ`net_receivable` WHERE cohort 订单未匹配到账，且 `as_of_ts - 订单付款时间 > N天`（钱卡住/疑似漏结信号）。
- **T1 `other_unexplained_amount`** = 无法归类残差，仅用于财务明细：`net_receivable_total - settled_total - normal_in_transit_amount - stuck_amount - net_deduction_total`；老板摘要不直接展示该技术字段。
- **T2 `platform_net_deduction`** = 在 matched（order_no 两侧都有）行上 Σ`max(买家实付 − 退款, 0) − 订单实际金额到账`（差额倒算，非读费用行）。
- **T2 `net_deduction_rate`** = `platform_net_deduction / matched_net_receivable_total`。（环比 = 本期率 vs 上期 rollup，**本期暂缓**：日环比受 as_of 到账成熟度影响，周/月环比待粒度/性能方案，见 §11。）
- **T3 `unsettled_amount_aged`** = `stuck_amount` + 对应订单数/最长挂账天数（**疑似卡单/少打款信号，非确诊**）。

**底稿（财务）**
- **F2 `payback_days_avg`** = `payback_days_sum / payback_days_count`，其中单订单回款周期 = `(bill-details·打款时间) − (sold-orders·订单付款时间)`（**matched 行**，引擎内算 daydiff，§6.4），GROUP BY plan_code 求均值/分位
- **F3 `in_transit_ratio`** = `(normal_in_transit_amount + stuck_amount) / net_receivable_total`（按 plan_code）。
- **F3 `refund_ratio`** = `refund_total / receivable_total`（按 plan_code）。
- **F3 健康度红黄绿** = `in_transit_ratio + refund_ratio + 最长挂账天数` 三指标加权阈值（**阈值为产品定义非数据事实**，须标口径）。（环比依赖 `recon_shop_baseline`（表名沿用，维度已改为 plan_code），**本期暂缓**，见 §11。）
- `residual_gap_ratio` = `other_unexplained_amount / net_receivable_total` → 无法归类差额信号（财务明细使用，不直接对老板称“少打款”）
- `refund_count`　→ 退款突增
- `stale_diff_days`(差异连续未平天数)　→ 长期挂账

阈值三型：绝对值 / 比率 / 基线σ（均值+kσ）。**所有金额型 metric 取自 `recon_period_rollup`，绝不从 `execution_run_exceptions` SUM。**

### 9.2 基线与冷启动

`recon_shop_baseline`：每资金计划×指标，滚动窗口（近14/30天）存 mean+stddev+sample_count，每日 run 后更新。冷启动 `sample_count < 阈值(如7天)` → **不触发基线型预警**，只用绝对/比率阈值，标"基线建立中"。

### 9.3 预警生命周期

`recon_alert.status`：`open → ack(钉钉卡片点确认) → resolved`。`first_seen_biz_date` 跨天去重更新 → 长期挂账 = open 预警变老；超 N 天升级 severity。

### 9.4 诚实边界

现三份下预警是**"信号级(疑似)"非确诊**——`severity/confidence` 与文案用"疑似"；提现到账超范围。从疑似到确诊需补千牛费用明细/结算单（增值解锁点）。

## 10. 汇总 + 叙事 + 钉钉投递

- **fan-in + 完整性硬闸门**：调度到点不是投递点，而是发送窗口打开点。系统按 `company_id + biz_date + subscription.scope` 解析本次应参与日报的 `expected_run_plans`（通用任务集合，不写死资金/订单对账类型）。老板/财务日报默认 `scope=company_all`，即当前公司在该 `biz_date` 的所有启用对账任务均纳入闸门；未来如需部门/业务线子报表，可显式缩小 scope。闸门检查：
  1. 所有 `expected_run_plans` 均存在对应 `execution_run`；
  2. 所有 run 状态均为 `success`；
  3. 每个 run 的 normalize / attribution / alerts / rollup 后处理均已完成；
  4. 无数据采集中、对账中、后处理中任务；
  5. 汇总所需 `structured` 可确定性生成。
  
  只有全部满足，才生成 `recon_digest` 并投递老板/财务正式日报。任一条件不满足则进入发送窗口内重试，**不向老板/财务发送不完整日报**；超过截止时间仍不完整，只通知 `failure_recipients`（内部数据责任人/运维），日报标记为 `blocked/incomplete`。
- **汇总（确定性，写 `structured`）**：金额一律取自 `recon_period_rollup`（§6.2），计数取 summary 四类 count，**绝不复用 `execution_run_exceptions`（采样截断）**。第一版老板摘要只聚合订阅 scope 内 `recon_type=fund` 的资金对账计划；财务明细把资金对账与订单对账分区展示，不强行做跨计划主体映射。`structured` 字段：
  - **T1 漏斗**：`receivable_total / refund_total / net_receivable_total / settled_total / normal_in_transit / stuck_amount / other_unexplained_amount`（每项带「货款口径」标签；老板摘要不直接展示 `other_unexplained_amount`）
  - **T2 抽成**：`net_deduction / net_deduction_rate`（**本期不出环比**：日环比受 as_of 到账成熟度不一致影响会偏差；周/月环比待对账日期粒度调整 + 性能优化后再做，见 §11）
  - **T3 钱卡住**：`stuck_alerts[]`（plan_code, plan_name_snapshot, order_no, 净应收, 挂账天数, severity=疑似）
  - **F1**：差异清单（带归因 reason_code/is_true_diff，从 `canonical_recon_line` 全量取，不从 exceptions）+ `sampling_truncated`(N/M，读 `artifacts.runtime_summary.sampling_metadata`)
  - **F2**：`payback_days_avg` + per-plan 分布
  - **F3**：`plan_health[]`（plan_code, plan_name_snapshot, in_transit_ratio, refund_ratio, 挂账天数, 红黄绿）——**本期不含环比**
  - ~~周/月报加趋势（环比、长期挂账变化）~~ **本期暂缓**：周/月报需先调整对账日期粒度并优化大数据量对账任务性能，见 §11。
- **叙事（DeepSeek，写 `narrative`）**：`structured` 纯数字 + 口径说明 → `get_llm()` 生成正文，数字只传不算；按 `view` 出老板摘要 / 财务明细两版。**老板摘要 view 头部固定护栏文案：「本报告反映对账与资金健康，非经营损益（不含成本/毛利/利润）」**；所有金额带口径标签（「货款口径」「综合扣减·非精确佣金」）。
- **投递（dws + 安徽纳迈通道）**：完整性硬闸门通过后，钉钉 ActionCard 推给订阅 `recipients`（多选，单聊逐人或群）；明细按钮 → finance-web 日报详情页。硬闸门未通过时不推送 `recipients`，只在截止后通知 `failure_recipients`。
- **回写交互**：卡片按钮经钉钉机器人回调（`robot_code=dingmm03p1to5dq1jq1q`）→ 更新 `recon_alert.status` / `execution_run_exceptions`。**依赖一个机器人回调端点（子组件）。**
- **幂等**：一订阅×一周期一条 `recon_digest`；重跑重生成、已投递不重发。

### 卡片样例

**老板摘要 view（三件套）**

```
📊 福游 · 6/5 对账日报(T-1)   34店✓ 数据完整
ℹ️ 本报告反映对账与资金健康，非经营损益（不含成本/毛利/利润）

💰 资金到账总览(货款口径)
  买家实付 ¥182,400 → 退款 ¥6,200 → 已到账 ¥128,500
  正常在途 ¥41,300 ｜ 待核查 ¥3,100

📉 平台综合扣减 ¥3,800 (率5.1%)
  含手续费/营销，非精确佣金

⚠️ 钱卡住预警(疑似)
  • 单枪旗舰店 12笔付款超9天未到账，净应收¥3,100，建议核查
[查看完整明细]
```

**财务明细 view（底稿）**

```
📋 福游 · 6/5 对账明细(T-1)   34店✓
资金对账：平账3,218笔 · 金额差异18笔 · 超期未到账12笔
资金归因：正常在途¥41,300 | 综合扣减¥7,800 | 退款¥6,200 | 待核查¥3,100 | 未归类¥1,240
回款周期：计划均3.2天(P90 6天)
重点计划：🔴单枪旗舰店资金对账 超期未到账¥3,100；🟡dadada旗舰店资金对账 退款率11%

订单对账：店铺订单缺失6笔 · 中台订单缺失3笔 · 金额不一致4笔
[查看差异清单]  [导出底稿]  [标记已处理]
```

## 11. 触发与调度

- normalize / attribution / alerts：每个对账 run 完成后的后置步（data-agent 内）；基线每日更新。每个 run 完成后事件触发一次订阅完整性检查。
- 日报：每天 T-1 批次后进入发送窗口（如 09:00-10:30）+ 完整性硬闸门。窗口内每 `retry_interval_minutes`（默认 5 分钟）定时兜底检查；硬闸门通过后立即发送；超过窗口仍不完整则不发老板/财务正式日报，仅通知内部数据责任人/运维。**本期只做日报**。
- **周报/月报：本期暂缓**。原因：(1) 周/月聚合需调整对账任务的日期粒度（当前按日 cohort，跨周/月聚合的口径与 as_of 成熟度需重新定义）；(2) 跨周/月对账数据量过大，需先优化对账任务性能。架构上 digest 已按 `period(daily|weekly|monthly)` + `biz_date` 区间预留接缝（§2 决策表、§6.1 `digest_subscription.period`），周/月报为后续增量，不重写。
- 调度读 `digest_subscription.schedule + anchor`；一家公司可多条订阅（如日报给财务、日报给老板）。

## 12. Web 管理界面（finance-web/src，复用现有组件/API）

1. **字段映射确认页**：平台×dataset_kind，DeepSeek 提案 + 真实样本并排，低置信高亮，确认/改 → 存版本化。
2. **规则库编辑页**：按 domain/scope 列归因+预警规则，表单编 `when/then`、`metric/condition`、优先级、启停；DeepSeek 提案收件箱（review/改/晋升）。
3. **订阅 & 接收人多选页**：建订阅（period/scope/view/schedule/anchor），接收人走通讯录搜索多选（复用 dws contact search）。
4. **对账日报详情页**：老板详情页 / 财务详情页两个独立免登录公开页，配置驱动、响应式。**完整内容契约见 §17**。

## 13. 错误处理（失败安全、不阻断、可重跑）

- 无字段映射 / rollup 缺失 / 后处理未完成 → 完整性硬闸门不通过，不发老板/财务正式日报；无规则命中 → `未归因`（非错误）；基线冷启动 → 跳过基线型预警。
- **LLM(DeepSeek) 失败/超时 → 退回模板文案**，但前提是完整性硬闸门已通过且数字在；数字缺失时不得投递。
- 投递失败 → 重试+记录；部分接收人失败 → 报告哪几个失败。
- 所有确定性步骤按 `biz_date` 幂等可重跑。

## 14. 测试策略

- **单元（重点）**：规则求值算子、metric 公式、normalize 映射(value_map/类型)、基线数学、完整性硬闸门（expected_run_plans 全成功 + 后处理完成）—— 纯函数、表驱动。
- **Golden fixture**：喂已知 canonical 行 → 断言归因+预警（确定性，金标准测试最适合）。
- **LLM 部分**：不断言文案，断言"叙事拿到的数字正确" + "LLM 失败模板兜底"；映射/规则提案用 mock LLM 测提案→确认管线。
- **集成**：fixture 公司端到端（seed canonical → digest → 断言 structured + 投递 payload）；另测缺 run / run failed / rollup 缺失 / 后处理未完成时不投递老板财务、只通知内部失败接收人。复用 data-agent/tests、finance-mcp/tests。
- **迁移**：039+ 用迁移运行器 `status/apply` 验证。

## 15. 范围外（本期不做）+ 解锁路径（灰显占位，不假装）

- 其他对账域（银行/往来/存货）的具体域包——仅留接缝。
- 佣金/营销/技术服务费的费用科目细分、少打款确诊、提现到账——依赖补采费用明细/结算单/银行流水。
- 支付宝资金账单接入对账。

### 15.1 成本/利润：中台毛利可验证，净利润灰显占位

财务中台 `ods_yxst_trd_order_di_o` 有 `tax_sale_amount`（含税销售）与 `tax_cost_amount`（含税成本），可作为**中台口径含税毛利**候选指标。

**数据实查结论（2026-06-08，ods 落地处 `dataset_collection_records` dataset_id=`8a1b2991…`，2,932,152 行）**：`tax_cost_amount` **零空值/零空串、100% 数值型**，`tax_cost` 与 `tax_sale` 同时为数值的行 = 100%。**但"有值"≠"可直接算毛利"**——其中 **cost=0 占 29.1%（853,536 行），且这些 100% 是 `order_type='供货'`（供货订单，sale>0）**，直接全量算毛利会虚高到 100%。cost>0 的 70.5% 才是真实销售（充值卡/虚拟商品分销，毛利 2%~4% 的薄利，合理）。另有 0.41% 负成本 + `form_type='逆向交易'` 14,206 行（退货/冲销）。

**因此中台毛利 metric 的硬性口径规则（必须实现）**：

```
作用域：order_type='销售'类 且 form_type='正向交易' 且 tax_cost_amount > 0
       （排除 order_type='供货' 的 cost=0 行、form_type='逆向交易' 的退货冲销、cost<0）
中台口径含税毛利 = Σ(tax_sale_amount - tax_cost_amount)  over 作用域
中台口径毛利率   = 含税毛利 / Σ tax_sale_amount         over 作用域
扣减后贡献       = 含税毛利 - 平台综合净扣减
```

> ⚠️ **不切 `order_type`/`form_type` 直接全量算毛利 = 已知错误**：85 万供货订单(cost=0,sale>0)会把毛利率拉爆。golden fixture 须含"供货/逆向/负成本"行断言它们被排除。

但这仍不是完整净利润（缺平台费用、营销/人工/银行费用、银行流水）。实现前仍需验证订单粒度、重复行聚合、与 sold-orders 的稳定映射；本期老板摘要仍以资金健康为主，不承诺净利润。产品上将净利润/费用拆分**灰显占位**（不留白、不假装有数），并标注「如何解锁」：

| 灰显占位项 | 现状缺口 | 如何解锁 |
|---|---|---|
| 中台口径含税毛利 | 字段已满值无空值；须按 `order_type/form_type` 切口径（排除供货+逆向），并验证粒度/重复行/映射 | 按上述口径规则做 beta 指标校验，通过后解锁展示 |
| 净利润 | 无完整费用科目、银行流水、人工/营销等费用 | 补费用明细 + 银行流水 + 经营费用台账 |
| 平台费用拆分（佣金/营销/技术服务费） | bill-details 只采货款收入一类，无费用明细行 | 补千牛**全业务大类**费用明细（扩 bill-details 采集范围） |
| 真实净到账 / 提现是否到账 | 无银行流水、无平台结算单 | 补银行流水 + 平台结算单 |

解锁后：T1 漏斗升级为真实净资金、T2 由「综合净扣减」细分为佣金/营销/手续费、T3 由「疑似卡单」升级为确诊（规则包已为这些 reason_code 预留接缝，§8.2）。

> **诚实口径再申明**：本期 T1=货款口径净到账 + 正常在途 + 超期待核查，T2=综合净扣减率（非精确佣金），T3=信号级疑似（非确诊）；文案一律保留「货款口径 / 综合扣减 / 疑似」措辞，不得写成真实净资金 / 精确佣金 / 确诊。

## 16. 实现顺序建议（供写计划参考）

1. 迁移 039+ 建表（含 **`recon_period_rollup` 全量聚合表**）+ 配置读写 API（finance-mcp）。
2. **付款日 cohort + 截至 as_of 到账回查（§3.3.2/§6.4）**：资金三件套先取 sold-orders 付款日 cohort，再按订单号查 bill-details 截至 `as_of_ts` 的到账记录，写入 `recon_period_rollup`。**这是 T1/T2/F2/F3 一切金额的前置依赖，须最先打通。**
3. 对账域 + canonical 模型 + normalize + 字段映射（含 DeepSeek 提案 + 确认页）。
4. 归因引擎 + 规则库 v1 + 回填 exceptions（含规则提案/编辑页）。
5. 预警引擎 + 基线 + 生命周期。
6. 汇总（三件套+底稿 structured，金额取 rollup）+ DeepSeek 叙事 + recon_digest。
7. dws 投递（卡片多选）+ 机器人回调回写。
8. 订阅&接收人页 + 日报详情页。
9. 调度（日报发送窗口 + 完整性硬闸门 + 重试；周/月只预留）。
10. 端到端集成测试 + fixture。

## 17. 对账日报详情页内容契约（老板 / 财务 · 配置驱动 · 响应式）

> 本节细化 §12.4，是钉钉卡片「查看详细」按钮落地页的完整内容契约。设计于 2026-06-09 brainstorming 确认。**核心铁律与 §6.4 / rollup-foundation 一致：页面通用，行业知识全进配置。** 页面代码不得出现「买家实付 / 退款 / 钱卡住 / 资金对账 / 订单对账」等任何电商/淘系词——这些只能出现在 `view_layout` 配置与 fixture 中。换行业 = 加配置，页面不改。

### 17.1 页面架构

- **两个独立免登录公开页**：`老板详情页`、`财务详情页`。各由对应钉钉卡片的带 token 链接打开；`view`（老板|财务）**编码在链接里，不靠身份识别**（公开页无登录态）。token 限定到 `公司 + biz_date + view`，**沿用现有 `PublicReconRunExceptionsPage` 的 token / 有效期策略**（不另造一套）。
- **两视图取数逻辑与展示维度不同，故做成两页**（非同页切 tab）；但二者共用同一套渲染器与数据源。
- **配置驱动的通用渲染器**：详情页是一个「报表渲染器」，输入 = `view_layout` 配置（按 `域 × 视图`）+ 通用 digest 结构化数据，输出 = 页面。渲染器只认 §17.2 的 **8 类通用 section 类型**。
- **数据源全通用，零行业专有表**：`recon_period_rollup`（全量金额）、`canonical_recon_line`（差异行）、`recon_alert`（预警）、`recon_digest.narrative`（叙事）。**金额一律取自 rollup，绝不从 `execution_run_exceptions` SUM**（§6.2/§10 同律）。

### 17.2 通用 section 类型目录（渲染器内置，共 8 类）

| section 类型 | 职责 | 数据源 | 手机端降级 |
|---|---|---|---|
| `funnel` | 有序阶段漏斗，每段绑一个 metric | rollup | 横向条 → 竖向堆叠，每段一行 |
| `ranking_table` | 按实体（plan）列若干 metric，可排序 | rollup | 多列表格 → 每实体一卡（关键 2-3 指标 + 展开） |
| `metric_kpi` | 单个/几个关键数 + 口径标签；**可带 `group_by` 出分组计数** | rollup | 一排卡 → 2 列网格自动换行 |
| `alert_list` | 预警项，可下钻到明细行 | alert + canonical | 表格 → 卡片，点开下钻 |
| `diff_list` | 差异行 + 归因 + 左右原值，可筛选/导出/标记；**带 `group_by` 动态分 Tab** | canonical + 归因 | 表格(ResponsiveTable) → 每行卡片(复用 `PublicReconRunExceptionMobileCard`) |
| `distribution` | 均值/分位 | rollup | 均值+分位一行 → 纵向 |
| `locked_placeholder` | 未解锁指标 + 「如何解锁」 | 配置 | 灰显块（同） |
| `narrative` | DeepSeek 正文（数字只传不算） | digest | 正文段（react-markdown，同） |

**响应式总则**：断点沿用 Tailwind 默认 `md`(768px)；电脑表格 ↔ 手机卡片；导出在手机端走「生成后给下载链接」。

### 17.3 `view_layout` 配置格式（按 `域 × 视图`，渲染器据此渲染）

```json
{ "domain": "ecom", "view": "boss",
  "sections": [
    {"type":"funnel", "title":"资金到账总览（货款口径）",
     "stages":[
       {"metric":"receivable_total","label":"买家实付"},
       {"metric":"refund_total","label":"退款"},
       {"metric":"settled_total","label":"已到账"},
       {"metric":"normal_in_transit_amount","label":"正常在途"},
       {"metric":"stuck_amount","label":"待核查"}],
     "caption":"货款口径"},
    {"type":"ranking_table","title":"按店铺拆解","entity":"plan_code",
     "columns":["net_receivable_total","settled_total","normal_in_transit_amount","stuck_amount"],
     "sort":"stuck_amount desc"},
    {"type":"metric_kpi","title":"平台综合扣减",
     "metrics":["net_deduction_total","net_deduction_rate"],"caption":"含手续费/营销，非精确佣金"},
    {"type":"alert_list","title":"钱卡住预警（疑似）","alert_code":"unsettled_amount_aged",
     "drilldown":{"source":"canonical","filter":"match_status=left_only & aging>N",
                  "columns":["order_no","net_receivable","aging_days"]}},
    {"type":"locked_placeholder","items":[
       {"metric":"midplatform_gross_profit","state":"beta","unlock":"按 order_type/form_type 切口径并 beta 校验后解锁"},
       {"metric":"net_profit","state":"locked","unlock":"补费用明细+银行流水+经营费用台账"}]}
  ]}
```

> `group_label_map` / `group_by` 用于财务视图分组（见 §17.5）。所有 `metric` / `label` / `stages` / `columns` 均来自配置；渲染器不内置任何具体指标名。

### 17.4 电商·老板视图（首批配置实例）

护栏：头部固定「本报告反映对账与资金健康，非经营损益（不含成本/毛利/利润）」，所有金额带口径标签。`sections` 顺序：

1. `funnel`：买家实付 → 退款 → 已到账 → 正常在途 → 待核查（货款口径）。
2. `ranking_table`：按店铺(plan)列 应收净额 / 已到账 / 在途 / 待核查。**【确认要】**
3. `metric_kpi` + `ranking_table`：平台综合扣减额 / 率 + 按店铺扣减率排名。**【确认要，数据已具备】**——`recon_period_rollup` 已按 `plan_code` 落 `net_deduction_total` / `net_deduction_rate`（§6.2），排名 = 对 rollup 按率排序，零额外取数；口径「综合净扣减·非精确佣金」。
4. `alert_list`：钱卡住，下钻到订单明细（订单号 / 净应收 / 挂账天数）。**【确认要，数据已具备】**——`left_only` 单边缺失行落 `canonical_recon_line`（§6.2），可逐笔列出；差异行 >1000 被采样时标「已采样 N/M」。
5. `locked_placeholder`：**中台口径含税毛利（beta 校验中）** + **净利润（灰显）** + 如何解锁。**【确认要】**——见 §17.6 数据裁决。

### 17.5 电商·财务视图（首批配置实例）

`sections` 顺序：

1. `metric_kpi`（计数，带 `group_by`）：按对账类型分组出四类计数。
2. `diff_list`（带 `group_by` 动态分 Tab）：差异行 + 归因（`reason_code` / `is_true_diff`）+ 左右原值，**扩展现有 `PublicReconRunExceptionsPage`**；采样时标「已采样 N/M，导出取全量」。
3. `distribution`：回款周期 均值 + P90（按 plan）。
4. `ranking_table`：健康度红黄绿排名。
5. `narrative`：DeepSeek 叙事段。**【确认要】**

**导出底稿** **【确认】**：全 canonical 字段 + 归因 + 左右原值；格式 Excel(.xlsx，前端无导出库则退 CSV)；范围 = 当前筛选；文件名 `{公司}_{biz_date}_{分组标签}对账底稿`。手机端走「生成后给下载链接」。

**标记处理** **【确认】**：粒度 = **逐差异行**，复用现有 处理状态 / 修复状态 / 责任人 / 反馈。钉钉卡片与 Web 页**写同一后端**（`recon_alert.status` / `execution_run_exceptions`）：卡片做粗粒度 ack、Web 做逐行；两条回写路径统一到同一更新入口（§10 机器人回调）。

> **通用性关键：分组维度不得硬编码「资金对账 / 订单对账」。** `diff_list` 与计数 `metric_kpi` 带一个**可配置 `group_by`**（默认 `recon_type`，它是 rollup/canonical 上的通用列）+ **`group_label_map`**（配置）。渲染器只认「按 `group_by` 分组、每组一 Tab、标签取 `group_label_map`」：
> - **电商配置**：`group_by=recon_type`，`group_label_map={"fund":"资金对账","order":"订单对账"}` → 渲两个 Tab。
> - **其他行业**（如银行/往来/存货对账）：同样 `group_by=recon_type`，换自己的 `group_label_map` → 渲它自己的 N 个 Tab。
> - **退化规则**：scope 内只有 1 个分组值 → 不出 Tab 栏，直接单清单；0 个 → 空态。Tab 数量由数据 + 配置决定，页面代码不变。
>
> 「资金对账 / 订单对账」只是**电商 view_layout 配置的示例值，非渲染器内置**。

### 17.6 数据可得性裁决（写入作为实现依据）

| 项 | 结论 | 依据 |
|---|---|---|
| 平台扣减 + 店铺扣减率排名（B） | **能，数据已就位** | `recon_period_rollup` 按 `plan_code` 已落 `net_deduction_total`/`net_deduction_rate`（§6.2）；排名=排序 |
| 钱卡住下钻订单明细（C） | **能** | `left_only` 落 `canonical_recon_line`（§6.2），带订单号/净应收/付款时间→挂账天数；注意采样标注 |
| 中台口径含税毛利（D） | **数据有，需切口径 + beta 校验后解锁** | `ods_yxst_trd_order_di_o` 有 `tax_sale_amount`/`tax_cost_amount`；必须按 `order_type='销售' + form_type='正向交易' + tax_cost_amount>0` 切口径（排除供货 cost=0 / 逆向 / 负成本，§15.1）；解锁前以 `locked_placeholder` state=beta 呈现 |
| 净利润（D） | **数据没有，永久灰显占位** | 缺平台费用明细 / 银行流水 / 人工营销费用（§15.1）；`locked_placeholder` state=locked + 如何解锁 |

### 17.7 数据模型增量（迁移 039+ 接缝，供写计划细化）

- **`view_layout` 配置表**：`layout_code, domain, view(boss|finance), sections(jsonb), version, status` —— Web 管理界面读写，与 §6.1 配置表同构。
- 详情页读取 = `view_layout`(按 domain×view) + `recon_digest.structured` + 按需查 `recon_period_rollup` / `canonical_recon_line` / `recon_alert`。
- 详情页公开链接 token 解析复用现有 `PublicReconRunExceptions` 路由机制，扩 `view` 维度。

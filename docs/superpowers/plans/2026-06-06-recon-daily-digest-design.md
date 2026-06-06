# 对账日报/周报/月报 + 归因引擎 + 资金安全预警 — 设计文档

- 日期：2026-06-06
- 状态：已确认设计，待写实现计划
- 目标版本：v2（产品已上线，本功能随下一版发布，不追赶单周临时版）

## 1. 背景与价值

Tally 已上线，首个验证客户为**武汉福游网络科技有限公司**（淘系 34 个对账任务，订单对账 + 资金对账）。当前能力是"每天 T-1 跑对账、产出差异"，但差异是一堆原始数据，客户仍需人工判断"为什么差、要不要紧"。

本功能把对账从**差异检测**升级为**给财务负责人/老板一份「今天发现了哪些问题、归因是什么、预警了哪些资金安全」的钉钉日报/周报/月报**，放大自动对账的价值，支撑付费验证。

### 核心原则（贯穿全文）

- **数字确定性、措辞 LLM 化**：运行时的 normalize / 归因 / 预警**全部确定性规则**，金额与结论一律由确定性层计算；LLM（DeepSeek）只出现在①离线字段映射提案 ②离线归因规则提案 ③运行时日报叙事生成（数字只传不算）。这是财务 AI 的防幻觉主心骨。
- **引擎通用、知识分包**：引擎与 canonical 核心通用；字段映射 / 归因规则 / 预警指标按**对账域**分包配置，是产品的可积累 IP。
- **失败安全**：每步幂等可重跑；LLM 失败退回模板；缺数据标注而非中断。

## 2. 关键决策（brainstorming 确认）

| # | 决策 | 取值 |
|---|---|---|
| 1 | spec 范围 | 完整产品（含 Web 管理界面），一份大 spec，v2 发布 |
| 2 | LLM 角色 | DeepSeek v4（`LLM_PROVIDER=deepseek`）；仅离线提案（映射/规则）+ 运行时叙事；运行时归因/预警全确定性 |
| 3 | 配置面 | 全套 Web 管理界面 |
| 4 | 触发与取数 | 由「订阅(subscription)」定义 scope；日/周/月按 `biz_date` 区间 |
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
| 调度 | 日/周/月触发 + 完整性闸门 | finance-cron/run_scheduler |
| Web 管理 | 字段映射 / 规则库 / 订阅&接收人 / 日报详情 | finance-web/src |

### 4.2 数据流（日报）

```
T-1 对账批次(现有) → 配对结果
  → normalize  →  canonical_recon_line          (按 field_mapping)
  → attribution → recon_attribution + 回填 execution_run_exceptions
  → alerts     →  recon_alert                   (含 per-shop 基线)
  ── 调度到点 + 完整性闸门(scope内计划是否都出 run) ──
  → digest 聚合(scope×biz_date) → DeepSeek 叙事 → recon_digest
  → delivery: 钉钉 ActionCard → 订阅接收人(多选) + 详情页链接
  → 接收人点[标记已核销/转人工] → 回写 recon_alert / execution_run_exceptions
```

normalize / attribution / alerts 作为**每个对账 run 完成后的后置步**执行（data-agent 内），基线每日更新。周报/月报同链路，digest 聚合换成 `biz_date` 区间（自然周/自然月）。

## 5. 对账域（recon_domain）抽象

一个对账域 = `{canonical 语义别名 + 字段映射模板 + 归因规则包 + 预警指标包}`。

- 引擎与 canonical **核心字段**（`left_amount/right_amount/diff_amount/order_no/biz_date/各时间/match_status`）通用。
- `receivable_amount / settled_amount / refund_amount` 等是**电商域语义别名**，靠 field_mapping 落上去。
- `field_mapping / attribution_rule / alert_rule / canonical_recon_line / metric_definition` 均带 `domain` 维度。
- **本期只产出一个域：`电商对账`（含 order / fund 两类）**；不构建其他域，但接缝（domain 维度 + metric 可配置）就位，传统企业接入 = 加域包不重写。

## 6. 数据模型（新表，迁移 039+；表名加前缀避免冲突）

> 规模约束：订单行约 300 万，**`canonical_recon_line` 只落差异行**（mismatch / 单边缺失），平账只在 run 级汇总计数。差异行与 `execution_run_exceptions` 一一对应。

### 6.1 配置表（Web 管理界面读写，JSONB 驱动）

- **`field_mapping`**：`mapping_code, domain, scope{platform,dataset_kind}, fields(jsonb), version, status, created_at`
- **`attribution_rule`**：`rule_code, domain, scope{platform,recon_type}, priority, when(jsonb), then(jsonb), enabled, version`
- **`metric_definition`**：`metric_code, domain, formula(jsonb 作用于 canonical 字段), description`
- **`alert_rule`**：`rule_code, domain, scope, metric_code→metric_definition, condition(jsonb), severity, alert_template, enabled`
- **`digest_subscription`**：`id, company_id, period(daily|weekly|monthly), scope(jsonb), recipients(jsonb 钉钉userId数组), view(老板摘要|财务明细), schedule, anchor(jsonb), enabled`

### 6.2 运行结果表（引擎确定性写入）

- **`canonical_recon_line`**（仅差异行）：`id, company_id, domain, execution_run_id, exception_id→execution_run_exceptions, plan_code, shop_id, recon_type, biz_date, order_no, channel, receivable_amount, settled_amount, refund_amount, left_amount, right_amount, diff_amount, pay_time, settle_time, finish_time, match_status, order_status`
  - 索引：`(company_id,biz_date)`、`(plan_code,biz_date)`、`(shop_id,biz_date)`
- **`recon_attribution`**：`id, line_id→canonical_recon_line, rule_code, reason_code, is_true_diff, confidence, explain_text, created_at`
- **`recon_shop_baseline`**：`company_id, shop_id, metric_code, window, value, stddev, sample_count, updated_at`
- **`recon_alert`**：`id, company_id, domain, biz_date, shop_id, alert_code, severity, amount, evidence(jsonb), status(open|ack|resolved), first_seen_biz_date, last_seen_biz_date, created_at`
- **`recon_digest`**：`id, subscription_id, company_id, period, period_start, period_end, structured(jsonb), narrative(text), completeness(jsonb), status, delivered_at`
  - 唯一约束：`(subscription_id, period_start, period_end)` —— 一订阅×一周期幂等一条

### 6.3 与现有表关系

`canonical_recon_line.exception_id → execution_run_exceptions.id`；归因的 `reason_code/is_true_diff` 回填到 `execution_run_exceptions`，现有异常闭环 UI 直接显示归因。平账总量走 `execution_run` 汇总，不落明细。

## 7. 规范化模型 + 字段映射

### 7.1 canonical 字段集

| 概念字段 | 含义 | 淘宝来源示例 |
|---|---|---|
| `order_no` | 关联键 | 订单编号 / 订单号 / customer_order_no |
| `shop_id`,`biz_date`,`recon_type`,`channel` | 维度 | — / 账期 / order\|fund / 收·付渠道 |
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
  "alert":"{shop}货款缺口{gap}元(应收{receivable}的{pct}),超历史均值,疑似少打款" }
```

初始 metric（`metric_definition`，公式作用于 canonical 字段）：
- `residual_gap_ratio` =(应收 − 实收 − 已归因正常扣减 − 退款)/ 应收　→ 少打款信号
- `refund_ratio` / `refund_count`　→ 退款突增
- `unsettled_amount_aged`(超N天未到账)　→ 疑漏结
- `stale_diff_days`(差异连续未平天数)　→ 长期挂账

阈值三型：绝对值 / 比率 / 基线σ（均值+kσ）。

### 9.2 基线与冷启动

`recon_shop_baseline`：每店×指标，滚动窗口（近14/30天）存 mean+stddev+sample_count，每日 run 后更新。冷启动 `sample_count < 阈值(如7天)` → **不触发基线型预警**，只用绝对/比率阈值，标"基线建立中"。

### 9.3 预警生命周期

`recon_alert.status`：`open → ack(钉钉卡片点确认) → resolved`。`first_seen_biz_date` 跨天去重更新 → 长期挂账 = open 预警变老；超 N 天升级 severity。

### 9.4 诚实边界

现三份下预警是**"信号级(疑似)"非确诊**——`severity/confidence` 与文案用"疑似"；提现到账超范围。从疑似到确诊需补千牛费用明细/结算单（增值解锁点）。

## 10. 汇总 + 叙事 + 钉钉投递

- **fan-in + 完整性闸门**：调度到点 → 按订阅 `scope` 圈定计划集 → 查 `biz_date`(日)/区间(周·月) 的 `execution_run`；缺的标进 `completeness`，照发但头部红字提示"X 店缺失，结果不完整"。
- **汇总（确定性，写 `structured`）**：店数/平账/差异数/总差额、按 reason_code 分组（真异常 vs 已归因正常）、预警清单（含挂账天数）、完整性；周/月报加趋势（环比、长期挂账变化）。
- **叙事（DeepSeek，写 `narrative`）**：`structured` 纯数字 + 口径说明 → `get_llm()` 生成正文，数字只传不算；按 `view` 出老板摘要 / 财务明细两版。
- **投递（dws + 安徽纳迈通道）**：钉钉 ActionCard 推给订阅 `recipients`（多选，单聊逐人或群）；明细按钮 → finance-web 日报详情页。
- **回写交互**：卡片按钮经钉钉机器人回调（`robot_code=dingmm03p1to5dq1jq1q`）→ 更新 `recon_alert.status` / `execution_run_exceptions`。**依赖一个机器人回调端点（子组件）。**
- **幂等**：一订阅×一周期一条 `recon_digest`；重跑重生成、已投递不重发。

### 卡片样例

```
📊 福游 · 6/5 对账日报(T-1)   34店✓ 数据完整
平账28 · 差异6 · 总差额¥1,240
已归因¥980(跨期/退款·正常) | 待关注¥260
⚠️腾讯游戏旗舰 货款缺口¥210 疑似少打款
• dadada 退款挂账¥50 (已挂3天)
[查看完整明细]  [标记已核销]  [转人工]
```

## 11. 触发与调度

- normalize / attribution / alerts：每个对账 run 完成后的后置步（data-agent 内）；基线每日更新。
- 日报：每天 T-1 批次后固定时刻（如 09:00）+ 完整性闸门。
- 周报：每周固定日（如周一 09:30），聚合上一自然周。
- 月报：每月固定日（如 1 号），聚合上一自然月。
- 调度读 `digest_subscription.schedule + anchor`；一家公司可多条订阅（如日报给财务、月报给老板）。

## 12. Web 管理界面（finance-web/src，复用现有组件/API）

1. **字段映射确认页**：平台×dataset_kind，DeepSeek 提案 + 真实样本并排，低置信高亮，确认/改 → 存版本化。
2. **规则库编辑页**：按 domain/scope 列归因+预警规则，表单编 `when/then`、`metric/condition`、优先级、启停；DeepSeek 提案收件箱（review/改/晋升）。
3. **订阅 & 接收人多选页**：建订阅（period/scope/view/schedule/anchor），接收人走通讯录搜索多选（复用 dws contact search）。
4. **对账日报详情页**：structured 表 + 叙事 + 差异清单(带归因) + 预警(带挂账天数) + `标记已核销/转人工`。

## 13. 错误处理（失败安全、不阻断、可重跑）

- 无字段映射 → normalize 跳过并标完整性缺口；无规则命中 → `未归因`（非错误）；基线冷启动 → 跳过基线型预警。
- **LLM(DeepSeek) 失败/超时 → 退回模板文案**，日报照发（数字在）。
- 投递失败 → 重试+记录；部分接收人失败 → 报告哪几个失败。
- 所有确定性步骤按 `biz_date` 幂等可重跑。

## 14. 测试策略

- **单元（重点）**：规则求值算子、metric 公式、normalize 映射(value_map/类型)、基线数学、完整性闸门 —— 纯函数、表驱动。
- **Golden fixture**：喂已知 canonical 行 → 断言归因+预警（确定性，金标准测试最适合）。
- **LLM 部分**：不断言文案，断言"叙事拿到的数字正确" + "LLM 失败模板兜底"；映射/规则提案用 mock LLM 测提案→确认管线。
- **集成**：fixture 公司端到端（seed canonical → digest → 断言 structured + 投递 payload）。复用 data-agent/tests、finance-mcp/tests。
- **迁移**：039+ 用迁移运行器 `status/apply` 验证。

## 15. 范围外（本期不做）

- 其他对账域（银行/往来/存货）的具体域包——仅留接缝。
- 佣金/营销/技术服务费的费用科目细分、少打款确诊、提现到账——依赖补采费用明细/结算单/银行流水。
- 支付宝资金账单接入对账。

## 16. 实现顺序建议（供写计划参考）

1. 迁移 039+ 建表 + 配置读写 API（finance-mcp）。
2. 对账域 + canonical 模型 + normalize + 字段映射（含 DeepSeek 提案 + 确认页）。
3. 归因引擎 + 规则库 v1 + 回填 exceptions（含规则提案/编辑页）。
4. 预警引擎 + 基线 + 生命周期。
5. 汇总 + DeepSeek 叙事 + recon_digest。
6. dws 投递（卡片多选）+ 机器人回调回写。
7. 订阅&接收人页 + 日报详情页。
8. 调度（日/周/月 + 完整性闸门）。
9. 端到端集成测试 + fixture。

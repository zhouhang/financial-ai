# 老板经营分析 Agent 设计

日期: 2026-06-30

## 背景

Tally 已经把财务对账工作做成闭环: 数据获取、数据整理、数据对账、差异催办、处理验证。下一步需要让企业老板和财务人员通过自然语言直接获取经营数据和分析结论。

目标不是做一个简单的 NL2SQL, 也不是把 Codex、Claude Code 这类通用 agent 直接接到生产库。第一版需要有足够灵活的老板体验: 能问总览、问原因、自动拆解、下钻明细、导出结果, 同时保证数据来自 Tally 可控的数据契约和审计链路。

本设计采用混合分析 Agent:

- 普通问数走受控查询路径, 速度快、口径稳、可审计。
- 深度分析走本地隔离 runner 沙箱路径, 在受控数据包上做临时 DuckDB/Pandas 分析。
- 入口复用现有 Tally 聊天窗口。
- 不为福游等单一客户写定制逻辑, 以所有企业客户可配置为原则。

## 目标

1. 老板能在当前 Tally 聊天中自然询问经营数据。
2. 第一版支持灵活问题, 不限于单次汇总查询:
   - 总览
   - 同比/环比或指定期间对比
   - 贡献度拆解
   - 多维下钻
   - TopN 明细
   - 对账差异处理进度
   - 导出
   - 深度归因和异常扫描
3. 复用现有 `recon_period_rollup`、`semantic_profile`、对账差异台账和数据源目录。
4. 新增轻量分析契约层, 支撑不同企业配置自己的指标、事实源、维度和数据完整性说明。
5. 第一版不做角色/部门/字段级权限, 但必须强制 company 级隔离。
6. 指标、维度或数据缺失时, 不只提示“不存在”, 还要说明需要财务补充什么数据或字段映射。
7. 新客户接入数据后, 系统自动跑一次数据体检, 自动生成“老板可问能力”, 让老板先用起来, 再通过缺口提示逐步补齐数据。

## 非目标

- 不做通用 agent 直接访问生产库。
- 不做任意自由 SQL。
- 不新建独立“老板问数”入口。
- 不做角色、部门、字段、明细级细权限。
- 不做跨公司集团视角。
- 不做完整企业级容器沙箱平台。第一版实现本地隔离 runner, 不允许退回普通 subprocess 执行不可信脚本。
- 不把 `view_layout` 扩展成业务指标契约。
- 不重做已有 rollup、digest、semantic_profile 能力。
- 不做重配置式上线向导。第一版不要求新客户先完整配置 6 层数据后才能问数。

## 核心原则

### 公司级隔离是第一版硬约束

第一版不做细权限, 但所有分析只能访问当前登录用户所属 `company_id` 的数据。

约束:

- `company_id` 从登录态或 token 推导, 不由 LLM 生成。
- Query IR 不接受用户或 LLM 自行指定跨公司范围。
- finance-mcp analysis tools 必须自动注入 `company_id` 过滤。
- Data Pack Builder 只能打包该 `company_id` 的数据。
- 审计记录 `company_id`、`user_id`、`conversation_id`、`message_id`。
- 用户询问其他公司或全部公司时, 第一版返回“不支持跨公司分析”。

### 受控查询不会消失

受控查询不是固定报表模板。它是数据访问网关:

- 校验指标和维度
- 注入 company 级隔离
- 编译 Query IR 到参数化 SQL
- 控制行数、超时和导出
- 记录审计
- 为沙箱构造安全数据包

第一版中受控查询直接回答大部分问题。后续沙箱能力增强后, 受控查询演进为数据包构造和审计层。

### V1 必须支持经营指标, 不只支持对账指标

第一版不能只接 `recon_period_rollup`。对账 rollup 只能回答到账、在途、差异、处理进度, 不能回答老板最关心的收入、退款、费用、成本、利润。

V1 受控查询必须至少支持三类事实源:

- `rollup_metric`: 来源于 `recon_period_rollup`, 用于对账和资金健康问题。
- `dataset_metric`: 来源于数据库数据源和浏览器采集写入的数据集, 用于收入、退款、费用、成本、平台费等经营明细。
- `derived_metric`: 来源于其他 metric 的公式组合, V1 至少支持 `subtract_many` 类型的利润/经营利润和 `ratio` 类型的占比/率指标。

因此, V1 的 data pack 也必须能包含 dataset_metric 的受控查询结果。否则沙箱只能分析对账汇总, 无法做利润下降、费用增长、退款影响等深度归因。

利润类问题在数据不完整时不能硬算完整净利润, 但必须能给出“已接入口径利润”:

```text
已接入口径利润 = 收入 - 退款 - 平台费 - 已接入费用 - 已接入成本
```

缺失人工、分摊、税费等数据时, 回答中标注 `partial`, 并说明需要财务补充哪些数据。

### 时间解析必须确定性完成

老板自然语言常用“这个月”“上个月”“最近三天”“最近三个月”。LLM 可以在 Query IR 中输出相对时间, 但受控查询执行前必须由后端确定性解析成绝对日期范围。

规则:

- 解析基于后端注入的业务日期锚点, 默认使用 Tally 服务时区的当天日期。
- Query IR 中的 `relative` period 不直接进入 SQL 编译。
- 支持 V1 常用值: `today`, `yesterday`, `this_month`, `last_month`, `last_7_days`, `last_30_days`, `recent_3_months`。
- 无法解析的相对时间返回澄清问题, 不执行查询。

### 聚合口径必须执行契约

编译器不能一律 `SUM(metric_field)`。它必须执行 `analysis_metric_contract` 中的 `default_aggregation`、`additivity` 和 `formula_ir`:

- `sum`: 可加指标按范围求和。
- `count`: 计数。
- `avg`: 平均值。
- `ratio`: 分子、分母分别聚合后相除, 不对比率本身求和。
- `semi_additive`: 跨时间范围默认取期末快照或按契约指定的快照策略, 不跨天简单求和。
- `non_additive`: 无明确公式或聚合策略时拒绝查询并提示口径不支持。

derived metric 必须先编译依赖指标, 再按公式组合结果。公式不完整时返回缺口, 不编造指标。

### SQL 标识符必须白名单化

SQL 值参数必须参数化; 表名、列名、别名等 SQL 标识符也不能裸拼 LLM 输出。

规则:

- `source_ref` 必须来自后端允许的事实源配置。
- `metric_field`、`time_field`、`dimension_mappings` 必须存在于该事实源的 `allowed_columns` 或 schema summary 白名单中。
- 维度别名来自已确认的 `analysis_dimension_contract.dimension_code`, 不直接使用 LLM 原文。
- 编译器使用安全 identifier quoting 或等价的白名单校验和转义; 校验失败时拒绝查询。

### 沙箱只分析受控数据包

沙箱不连接生产库。它只接收受控查询构造的数据包:

- 输入: 数据表、指标定义、字段字典、数据完整性说明。
- 执行: DuckDB/Pandas 临时分析代码。
- 输出: 结构化结果、表格、图表文件、审计日志。
- 校验: 关键总数必须与受控查询一致。

### V1 沙箱选型

第一版沙箱采用本地隔离 runner, 首选 Linux `nsjail`:

- macOS 本地开发: 通过 Docker Desktop 提供 Linux VM, 在 VM 内运行 `analysis-runner`, runner 再用 `nsjail` 即用即销执行分析脚本。
- ECS Ubuntu 部署: 直接在 Ubuntu 主机部署 `analysis-runner + nsjail`, runner 只监听内网或 `127.0.0.1`。
- 不使用普通 subprocess 作为 fallback。`subprocess` 只能作为 runner 内部启动 `nsjail` 的控制动作, 不作为安全边界。
- 如果 `analysis-runner` 不可用, 深度分析失败关闭, 只能退回受控查询结果回答。
- 沙箱无数据库凭证、无 API key、无公网网络, 只挂载本次 data pack 只读输入和 output 可写目录。

后续可升级到 gVisor / Firecracker / 云沙箱, 但第一版不为了未来形态牺牲本地开发和 ECS 部署的简单性。

## 现有能力复用

### recon_period_rollup

`recon_period_rollup` 是对账/到账类指标的可信聚合事实源, 已包含:

- `receivable_amount_total`
- `settled_amount_total`
- `normal_in_transit_amount_total`
- `diff_amount_total`
- `matched_with_diff_count`
- `source_only_count`
- `target_only_count`

第一版把它注册为分析事实源, 用于对账、到账、在途、差异类问题。

### recon_rollup

`finance-mcp/recon/mcp_server/recon_rollup.py` 已经提供 canonical 投影和确定性聚合模式。新设计复用这个模式, 但不把它扩展为全量经营利润引擎。

### data_source_datasets.meta.semantic_profile

已有语义数据集是企业明细字段识别和映射的重要来源。分析契约中的 `dataset_metric` 不直接写死表字段, 而是引用 semantic profile 中的业务字段。

### view_layout

`view_layout` 继续作为展示配置, 不承载指标公式、权限、事实源、维度、血缘等查询语义。

## 新客户数据接入体验

第一版补齐的是“可问数据能力层”, 不是要求客户一次性配置完整数据仓库。新客户的数据接入体验分成两个产品位置:

1. **数据接入页 / 数据源详情页**
   - 第一版老板取数的数据源主要是数据库数据源和浏览器采集数据源。
   - 当数据库数据源首次同步成功、浏览器采集任务成功写入数据集、或对账方案产出 rollup 后, 后台自动触发一次“经营分析数据体检”。
   - 数据源详情页展示体检状态: 正在识别、可用于分析、部分可用、需要补充字段、无法识别。
   - 财务/管理员看到字段识别结果、候选指标、候选维度、低置信度映射和需要确认的缺口。
   - 这里承接“数据接入后自动体检”, 不是让老板配置。

2. **老板取数聊天入口**
   - 聊天首页或空状态区域展示“当前可问能力”。
   - 老板看到的是可直接点击或直接追问的问题建议, 例如收入趋势、费用结构、退款影响、对账差异进度。
   - 如果能力不完整, 老板看到的是“可问”和“暂不可问”的自然语言说明, 不是后台配置表。
   - 这里承接“系统自动生成老板可问能力”。

因此产品上不是新增一个独立问数应用, 而是在两个已有动作里体现:

```text
接入数据 / 同步成功
  -> 数据源详情页出现自动体检结果
  -> 后台生成 analysis capability map
  -> 老板聊天入口展示可问建议
  -> 问到缺失指标/维度时, 回答中说明缺什么和怎么补
```

### 自动数据体检

自动体检由程序触发, 不由老板触发。触发时机:

- 数据库数据源对应的 `data_source_datasets` 新增或同步成功。
- `schema_summary` 或 `semantic_profile` 更新。
- 浏览器采集任务成功写入数据集。
- 对账方案成功运行并写入 `recon_period_rollup`。
- 财务确认字段映射或指标口径。

一次性上传文件不自动进入老板取数长期数据层。除非未来产品提供“保存为企业经营数据集”的明确动作, 否则上传附件只属于当次整理/对账任务上下文。

体检做四类事:

- 读取数据源目录、schema summary、semantic profile 和 rollup 元数据。
- 识别候选事实: 收入、退款、费用、成本、平台费、到账、在途、差异等。
- 识别候选维度: 日期、客户、供应商、项目、产品、渠道、部门、业务线、成本中心、来源系统等。
- 生成或更新 `analysis_metric_contract`、`analysis_fact_source`、`analysis_dimension_contract` 的候选项和状态。

体检结果不是简单成功/失败, 而是能力地图:

- `ready`: 可直接回答。
- `partial`: 可以回答, 但口径不完整。
- `needs_confirmation`: 系统有候选映射, 需要财务确认。
- `missing_data`: 缺数据源。
- `missing_mapping`: 有数据但缺字段或维度映射。
- `unsupported`: 第一版暂不支持。

### 老板可问能力

“老板可问能力”是面向老板的 capability map 摘要, 不暴露内部表名和字段名。

示例:

```json
{
  "ready_questions": [
    "最近 3 个月收入趋势怎么样?",
    "上个月费用最高的类型是什么?",
    "对账差异还有多少没处理?"
  ],
  "partial_questions": [
    {
      "question": "这个月利润为什么下降?",
      "note": "可以按已接入收入、退款、平台费和费用分析, 但未包含人工和分摊成本。"
    }
  ],
  "blocked_questions": [
    {
      "question": "按部门看利润",
      "missing": "缺少部门维度映射",
      "finance_should_add": "请在收入和费用数据中补充或确认部门字段。"
    }
  ]
}
```

聊天入口展示原则:

- 优先展示 `ready` 和 `partial` 问题, 让老板直接开始问。
- 不展示长配置清单。
- `blocked` 能力只在老板问到相关问题时解释, 或在“暂不可问”折叠区展示。
- 所有建议问题来自 capability map, 不由前端硬编码客户或行业。

### 轻量补齐路径

当系统识别到缺口时, 不要求客户回到重配置向导。第一版只需要轻量补齐:

- 字段确认: “这列是否代表收入金额/费用金额/发生日期/项目?”
- 指标确认: “利润是否按 收入 - 退款 - 平台费 - 费用 - 成本 计算?”
- 维度确认: “项目/部门/渠道字段是否来自这几列?”
- 数据缺失: “要回答净利润, 需要接入人工成本、分摊成本或费用流水。”

财务确认后重新触发体检并更新 capability map。老板侧下一次提问自动使用新能力。

### 指标物化与定时补偿

老板问数不能依赖日报生成时顺带产出的 rollup。第一版采用“事件触发为主, 定时补偿兜底”的指标物化机制:

```text
数据库数据源同步成功 / 浏览器采集成功 / recon rollup 写入 / 映射确认
  -> 投递 analysis materialize job
  -> 生成或更新 metric rollup version
  -> 更新 capability snapshot

定时补偿
  -> 扫描漏投递、失败、卡住、过期的任务
  -> 幂等重跑
  -> 成功后发布新版本
  -> 失败时保留旧版本
```

推荐频率:

- 轻量扫描: 每 5 分钟, 处理 `pending`、`failed`、`building_timeout`。
- 小窗口重算: 每小时, 补偿最近 1 到 3 天的数据水位落后。
- 深夜校准: 每天凌晨 2 点到 4 点, 校验最近 7 到 30 天的一致性并必要重算。

第一版最小实现:

- 每 5 分钟扫描 pending / failed / building timeout。
- 每小时扫描最近 3 天 source watermark 落后项。
- 每天凌晨校准最近 30 天。

物化必须版本化, 不能失败覆盖旧结果:

```text
metric_rollup_version
  status: building / ready / failed / stale
  source_watermark
  completeness_status
  error_reason
  active_version
```

发布规则:

- 新版本成功: 切换 active version。
- 新版本失败且有旧版本: 保留旧版本, 标记 stale 或 partial。
- 新版本失败且无旧版本: capability 标记 blocked / missing_data / missing_mapping。

补偿任务必须幂等。建议幂等键:

```text
company_id + source_group + metric_code + period_grain + period_start + source_watermark
```

失败重试策略:

- 第 1 次失败: 5 分钟后重试。
- 第 2 次失败: 15 分钟后重试。
- 第 3 次失败: 1 小时后重试。
- 第 4 次以后: 标记 failed, 等待人工处理或下一次源数据变化。

若失败原因是数据库连接超时、任务中断等临时错误, 自动重试。若失败原因是字段缺失、schema 变化、口径冲突, 转成 `needs_confirmation` / `missing_mapping`, 由财务/管理员确认。

老板侧只看到自然语言状态:

- `ready`: 当前可用。
- `stale`: 可用但不是最新, 回答必须提示数据截至时间。
- `building`: 正在准备。
- `failed`: 准备失败, 有旧版本则降级回答。
- `blocked`: 缺数据或缺映射, 暂不能回答。

## 数据契约

新增轻量分析契约层, 不替换现有表。

### analysis_metric_contract

定义企业可分析的指标。

建议字段:

- `id`
- `company_id`
- `metric_code`
- `metric_name`
- `category`: `revenue` / `refund` / `cost` / `expense` / `fee` / `profit` / `recon`
- `description`
- `formula_ir`
- `source_refs`
- `default_aggregation`: `sum` / `avg` / `count` / `ratio`
- `additivity`: `additive` / `semi_additive` / `non_additive`
- `supported_ops`: `compare` / `contribution` / `drilldown` / `topn` / `trend` / `export` / `sandbox`
- `completeness_note`
- `status`: `draft` / `active` / `disabled`
- `created_at`
- `updated_at`

利润类指标是企业可配置公式, 不做客户硬编码:

```json
{
  "metric_code": "profit",
  "formula_ir": {
    "op": "subtract_many",
    "base": "revenue",
    "subtract": ["refund", "fee", "expense", "cost"]
  },
  "completeness_note": "按当前已接入数据计算, 未接入项不计入"
}
```

### analysis_fact_source

定义指标事实来源。

建议字段:

- `id`
- `company_id`
- `source_code`
- `source_type`: `rollup_metric` / `dataset_metric` / `derived_metric`
- `source_ref`
- `metric_field`
- `amount_field`
- `time_field`
- `dimension_mappings`
- `drilldown_config`
- `status`
- `created_at`
- `updated_at`

第一版支持三类:

1. `rollup_metric`
   - 来源: `recon_period_rollup`
   - 用于: 对账、到账、在途、差异金额、差异计数
2. `dataset_metric`
   - 来源: `data_source_datasets` 和对应存储表
   - 用于: 订单收入、退款、费用流水、平台费、企业自有明细
3. `derived_metric`
   - 来源: 其他 metric 的公式组合
   - 用于: 利润、费用率、退款率、毛利率

### analysis_dimension_contract

定义可下钻维度。

通用维度:

- `date`
- `company`
- `department`
- `customer`
- `supplier`
- `project`
- `product`
- `channel`
- `business_line`
- `cost_center`
- `source_system`
- `dataset`

每个企业映射了多少就支持多少。没有映射时, 返回数据缺口引导。

## 数据缺口引导

每次指标、维度或数据不可用时, 系统必须返回:

1. 缺什么。
2. 当前能算什么。
3. 需要财务补充什么。
4. 补充后能支持什么问题。

状态分类:

- `configured`: 已配置可用
- `missing_source`: 缺数据源
- `missing_mapping`: 有数据但缺字段映射
- `incomplete`: 可计算但口径不完整
- `disabled`: 已禁用

示例:

- 净利润缺人工成本、分摊成本、税费时, 改为提供“已接入口径利润”, 并提示需要补充这些成本数据。
- 用户要求按项目拆, 但没有项目维度时, 提示当前可按客户、渠道、日期分析, 并说明需要补充项目字段或项目映射。
- 用户要求物流费占比, 但企业没有物流费数据时, 提示未接入物流费流水或费用类型映射。

## 执行流程

第一版 Analysis Agent 是有限多步流程, 最多 3 到 5 步。

```text
parse_intent
  -> plan_analysis
  -> validate_plan
  -> execute_fast_queries
  -> decide_deep_analysis
  -> optional_sandbox_analysis
  -> verify_result
  -> compose_answer
```

### parse_intent

识别是否为经营分析问题, 抽取:

- 时间范围
- 比较期间
- 指标
- 维度
- 是否下钻
- 是否导出
- 是否开放归因

### plan_analysis

LLM 生成 Query IR, 不生成 SQL。

示例:

```json
{
  "intent": "analysis",
  "question_type": "metric_change_reason",
  "metric": "profit",
  "period": "this_month",
  "compare_to": "previous_month",
  "ops": ["period_compare", "contribution", "dimension_scan"],
  "candidate_dimensions": ["date", "customer", "project", "product", "channel", "department"],
  "need_sandbox": "auto"
}
```

### validate_plan

后端确定性校验:

- metric 是否存在
- fact source 是否绑定
- dimension 是否可用
- time field 是否明确
- company_id 是否来自登录态
- 查询范围是否可控
- 是否需要澄清

### execute_fast_queries

先跑受控查询:

- 本期/上期总览
- 指标贡献度
- TopN 变化项
- 可用维度扫描
- 明细样本

### decide_deep_analysis

默认不进入沙箱。触发条件:

- 用户明确要求找原因、找模式、找异常
- 单维拆解解释力不足
- 需要多维组合扫描
- 需要临时派生字段
- 需要模拟测算
- 需要生成老板分析报告

### optional_sandbox_analysis

Data Pack Builder 构造数据包:

- `*.parquet` 或 DuckDB 文件
- `metric_definitions.json`
- `data_dictionary.json`
- `source_refs.json`
- `completeness.json`

沙箱限制:

- 只读数据包
- 禁止联网
- 限制执行时间
- 限制数据行数和大小
- 最多 3 轮代码修正
- 只允许输出结构化结果、表格、图表文件

### verify_result

沙箱结果必须通过校验:

- 关键总数与受控查询一致
- 指标公式来自 contract
- 引用字段存在
- 未使用未提供数据
- 有 `query_result_id` 或 `data_pack_id` 证据

不通过时降级为受控查询回答。

### compose_answer

最终回答包含:

- 结论
- 关键数字
- 贡献度或拆解
- 证据表格
- 口径说明
- 数据完整性说明
- 可追问建议
- 导出入口

## 后端模块

### data-agent

新增独立模块:

```text
finance-agents/data-agent/graphs/analysis/
  api.py
  state.py
  router.py
  planner.py
  executor.py
  sandbox.py
  verifier.py
  answer.py
```

职责:

- 识别 analysis intent
- 调 LLM 生成 Query IR
- 调 finance-mcp analysis tools
- 管理有限多步分析
- 管理隔离分析 runner
- 组织最终回答

### finance-mcp

新增独立模块:

```text
finance-mcp/analysis/
  contracts.py
  repository.py
  query_ir.py
  query_compiler.py
  query_executor.py
  data_pack.py
  audit.py
  tools.py
```

职责:

- 契约读取和校验
- Query IR Pydantic 模型
- Query IR 到参数化 SQL 的编译
- 受控查询执行
- 数据包构造
- 审计落库
- MCP tools 暴露

## MCP Tools

第一版新增:

- `analysis_list_capabilities`
  - 返回当前 company 可问指标、维度、时间范围、数据完整性。
- `analysis_plan_validate`
  - 校验 Query IR, 返回可执行计划或澄清/缺口提示。
- `analysis_query`
  - 执行受控查询, 返回结构化结果。
- `analysis_build_data_pack`
  - 构造沙箱数据包。
- `analysis_record_result`
  - 记录沙箱产物、审计和导出信息。
- `analysis_export`
  - 导出表格或报告。

data-agent 只能通过这些 tools 获取分析数据, 不直接连业务表。

## 前端体验

入口复用当前 Tally 聊天窗口。主 router 增加 `analysis` 分支:

```text
proc
recon
analysis
general
```

第一版前端支持 4 类分析展示:

- `analysis_summary`: 结论摘要和口径说明
- `analysis_metrics`: 指标卡, 包含本期、上期、变化额、变化率
- `analysis_table`: 表格, 包含贡献度、TopN、明细
- `analysis_trace`: 数据来源、口径、查询时间、是否使用沙箱

图表不是第一版硬要求。若实现, 仅支持简单趋势折线和柱状图。

多轮追问需要保留上一轮分析上下文:

- metric
- period
- company_id
- query_result_id
- data_pack_id
- drilldown path

用户可以继续问:

- 再按客户拆。
- 只看费用流水。
- 把最高的几条明细列出来。
- 导出刚才那张表。
- 这个费用项来自哪里。

历史标题可优化为:

- `经营分析 · 利润下降原因`
- `经营分析 · 费用明细 TopN`
- `经营分析 · 对账差异进度`

## 错误处理和幻觉防护

### 计划校验门

LLM 只能生成 Query IR。后端校验失败则不执行查询。

### 结果一致性门

普通查询结果带:

- `query_plan_id`
- `query_result_id`
- `metric_contract_version`
- `source_refs`
- `row_count`
- `generated_sql_hash`

沙箱结果额外带:

- `data_pack_id`
- `input_query_result_ids`
- `sandbox_run_id`
- `executed_code_hash`
- `validation_status`

### 回答生成门

LLM 最终回答只能引用结构化结果中存在的指标、维度和明细。必须展示 `completeness_note` 和数据缺口。

## 审计

新增审计记录至少包含:

- `company_id`
- `user_id`
- `conversation_id`
- `message_id`
- `question`
- `query_ir`
- `compiled_queries`
- `returned_row_count`
- `data_pack_id`
- `model_name`
- `status`
- `error`
- `created_at`

审计表不承担权限控制, 但为后续权限、复盘、调试和客户信任提供基础。

## 测试验收

### 后端单测

- Query IR 校验
- metric contract 解析
- fact source 绑定
- rollup 指标查询
- dataset 指标查询
- company_id 强制注入
- 数据缺口引导
- 沙箱一致性校验

### 集成测试

- 自然语言到 Query IR 到受控查询到回答。
- 自然语言到数据包到沙箱到校验到回答。
- 多轮追问复用上一轮上下文。
- 跨 company 请求无法访问。
- 沙箱失败降级为受控查询结果。

### 产品验收问题集

- 这个月经营情况怎么样?
- 这个月利润为什么下降?
- 收入、退款、费用分别是多少?
- 按客户/项目/渠道/日期拆一下。
- 费用最高的 20 条明细是什么?
- 对账差异还有多少没处理?
- 为什么不能算净利润?
- 按不存在的维度拆。
- 导出刚才的结果。

每个问题验收三点:

1. 数字正确。
2. 口径清楚。
3. 缺数据时能说清楚要补什么。

## 分阶段落地

### 第一阶段: V1.5 老板经营分析 Agent

- 复用当前聊天入口。
- 新增 analysis intent。
- 新增分析契约表和 MCP tools。
- 接入 `recon_period_rollup`、semantic profile 和已配置 dataset fact source。
- 实现受控查询路径。
- 实现本地隔离 runner 沙箱路径, 仅深度分析触发。
- 实现数据缺口引导。
- 实现公司级隔离和审计。

### 第二阶段: 扩展数据域

- 接入人工成本、分摊成本、税费、预算、应收应付、现金流等事实源。
- 扩展维度映射和数据完整性评估。
- 支持更多图表和报告模板。

### 第三阶段: 沙箱增强

- 独立 sandbox worker 或容器化 sandbox。
- 更严格资源隔离。
- 多用户并发调度。
- 通用 coding agent 可作为高级 sandbox runtime, 但仍只能访问受控数据包。

### 第三阶段: Agent 级沙箱与记忆

如果第二版把完整分析 agent 放进沙箱, 不要求沙箱进程长期不关。推荐做法是“agent 运行时即用即销, 记忆外部持久化”:

- 会话记忆: 存在 Tally 自己的 `analysis_ctx` / checkpointer / 审计表 / result artifact 中, 下次启动沙箱时按 `company_id + user_id + conversation_id + thread_id` 重新注入。
- 工作区记忆: 如确实需要保留临时文件、Notebook、分析中间产物, 存成受控 workspace snapshot 或 object storage, 下次以只读或受控可写 volume 挂载进新沙箱。
- 长期偏好记忆: 第一版不做; 第二版如做, 必须是 Tally 自己的租户隔离 memory store, 不依赖通用 agent 进程里的隐藏记忆。
- Provider/CLI 记忆: 尽量禁用。若通用 agent 不支持禁用, 必须为每个公司/用户/会话提供独立 HOME、配置目录、workdir 和 token, 禁止不同用户复用同一 agent profile。

因此, agent 沙箱可以是即用即销的。销毁的是进程和未持久化临时状态, 不是业务记忆。需要保留的记忆必须在沙箱外以结构化、可审计、可按公司隔离的方式保存。

可选优化是 warm sandbox pool: 为同一会话保留短 TTL 的热沙箱提升速度, 例如 5 到 15 分钟空闲后销毁。但这只是性能优化, 不能作为记忆唯一来源。

### 第四阶段: 主动洞察

- 定时生成老板日报/周报。
- 自动发现异常。
- 自动推送差异和利润变化原因。
- 与催办和处理验证闭环联动。

## 风险

1. 指标契约配置不足, 回答覆盖面不够。
   - 通过企业默认指标包和数据缺口引导缓解。
2. LLM 计划不稳定。
   - 通过 Query IR schema、validate_plan、few-shot 和失败追问缓解。
3. 沙箱输出不一致。
   - 通过一致性校验和降级路径缓解。
4. 第一版不做细权限, 后续权限补充需要谨慎。
   - 第一版保留 `company_id`、`user_id`、`conversation_id`、审计和 source refs, 避免重写链路。

## 设计结论

第一版应实现“老板经营分析 Agent”, 不是普通自然语言 SQL。

推荐方案:

```text
Tally Chat
  -> Analysis Agent
  -> Metric Contract
  -> Controlled Query
  -> Optional Sandbox
  -> Verified Answer
```

这条路径复用现有 rollup 和语义数据集能力, 避免为单一客户定制, 同时保留第一版需要的灵活体验。

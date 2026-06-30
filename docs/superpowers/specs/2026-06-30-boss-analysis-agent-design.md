# 老板经营分析 Agent 设计

日期: 2026-06-30

## 背景

Tally 已经把财务对账工作做成闭环: 数据获取、数据整理、数据对账、差异催办、处理验证。下一步需要让企业老板和财务人员通过自然语言直接获取经营数据和分析结论。

目标不是做一个简单的 NL2SQL, 也不是把 Codex、Claude Code 这类通用 agent 直接接到生产库。第一版需要有足够灵活的老板体验: 能问总览、问原因、自动拆解、下钻明细、导出结果, 同时保证数据来自 Tally 可控的数据契约和审计链路。

本设计采用混合分析 Agent:

- 普通问数走受控查询路径, 速度快、口径稳、可审计。
- 深度分析走轻量沙箱路径, 在受控数据包上做临时 DuckDB/Pandas 分析。
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

## 非目标

- 不做通用 agent 直接访问生产库。
- 不做任意自由 SQL。
- 不新建独立“老板问数”入口。
- 不做角色、部门、字段、明细级细权限。
- 不做跨公司集团视角。
- 不做完整企业级容器沙箱平台。第一版仅实现轻量沙箱。
- 不把 `view_layout` 扩展成业务指标契约。
- 不重做已有 rollup、digest、semantic_profile 能力。

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

### 沙箱只分析受控数据包

沙箱不连接生产库。它只接收受控查询构造的数据包:

- 输入: 数据表、指标定义、字段字典、数据完整性说明。
- 执行: DuckDB/Pandas 临时分析代码。
- 输出: 结构化结果、表格、图表文件、审计日志。
- 校验: 关键总数必须与受控查询一致。

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
- 管理轻量沙箱
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
- 实现轻量沙箱路径, 仅深度分析触发。
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

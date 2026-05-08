# 平台授权语义数据集展示设计

## 背景

数据连接里的数据库数据集已经支持刷新语义数据集：系统基于表结构和样本生成
`semantic_profile`，再由人工审核确认发布。语义信息存放在
`data_source_datasets.meta.semantic_profile`，raw 明细表只保存采集数据。

淘宝/天猫和支付宝授权接入后，也会生成固定数据集供对账绑定：

- 淘宝/天猫：一个店铺生成一个订单明细数据集。
- 支付宝：一个商户生成资金账单和交易账单两个数据集。

这些平台数据集同样需要面向财务人员展示中文语义结构和真实样例。否则用户在授权成功后只能看到
`tid`、`oid`、`payment`、`source_row_key`、`raw` 等技术字段，无法判断数据是否已经可用于对账。

## 已确认决策

- 授权成功后自动创建数据集目录、排队初始化采集，并在有真实样本后生成语义数据集。
- 后台任务运行中只展示进度，不允许用户重复触发初始化。
- 只有任务未启动、失败，或用户明确重跑时才展示手工动作。
- 只有已有真实样本后才允许刷新语义。
- 只有完成字段语义确认并发布的数据集，才可以进入对账方案选择。
- 自动对账和重新对账触发的数据采集只负责采集真实业务数据，不负责生成或发布语义数据集。
- 采集任务最多重试 3 次；3 次仍失败则本次授权初始化或对账运行失败。
- 店铺详情里必须能看到真实语义数据结构和 20 条真实数据。
- 支付宝数据集元数据使用新口径：
  - `storage = "platform_alipay_bill_lines"`
  - `source = "alipay_bill_lines"`
  - `resource_key = "alipay_bill:<bill_type>:<shop_connection_id>"`

## 目标

1. 淘宝/天猫、支付宝授权成功后，在店铺详情展示每个固定数据集的初始化状态、语义状态、字段结构和 20 条真实数据。
2. 语义生成从真实采集样本出发，淘宝读取 `platform_order_lines`，支付宝读取 `platform_alipay_bill_lines`。
3. 支付宝展示标准化字段、原始账单字段和系统字段的来源差异，避免财务人员误用系统字段。
4. 现有发布/管理发布流程继续可用，语义信息仍写入 `data_source_datasets.meta.semantic_profile`。
5. 失败状态提供明确重试入口，运行中状态不制造重复任务。
6. 明确区分平台采集时间字段和对账运行计划的业务日期字段。

## 非目标

- 不新增独立的数据资产管理页面。
- 不改变 `semantic_profile` 的持久化位置。
- 不把语义字段写入 raw 明细表。
- 不在首版实现所有未来平台的抽象 UI。
- 不要求授权回调同步等待初始化采集和语义生成完成。
- 不让自动对账或重新对账反向触发语义生成。
- 不把对账运行计划选择的时间字段当作平台 API 的采集窗口字段。

## 数据模型

### 发布数据集目录

平台数据集目录仍存放在 `data_source_datasets`。

淘宝/天猫订单明细：

- `extract_config.storage = "platform_order_lines"`
- `schema_summary.storage = "platform_order_lines"`
- `schema_summary.source = "taobao_order_lines"`
- `resource_key = "taobao_order_lines:<shop_connection_id>"`

支付宝资金账单和交易账单：

- `extract_config.storage = "platform_alipay_bill_lines"`
- `schema_summary.storage = "platform_alipay_bill_lines"`
- `schema_summary.source = "alipay_bill_lines"`
- `resource_key = "alipay_bill:<bill_type>:<shop_connection_id>"`

其中 `bill_type` 保持：

- `signcustomer`：资金账单
- `trade`：交易账单

### 语义数据

语义数据继续写入：

```text
data_source_datasets.meta.semantic_profile
```

字段结构建议包含：

- `business_name`
- `business_description`
- `key_fields`
- `field_label_map`
- `fields`
- `low_confidence_fields`
- `status`
- `generated_from`
- `semantic_generator`

字段项需要扩展来源标记：

| 来源 | field_source | 示例 | 展示策略 |
| --- | --- | --- | --- |
| 标准字段 | `normalized` | `tid`, `oid`, `alipay_trade_no` | 默认展示，可作为对账字段 |
| 原始账单字段 | `raw_bill` | `raw.支付宝交易号`, `raw.收入` | 默认展示，可作为对账字段 |
| 系统字段 | `system` | `source_row_key`, `source_file_name` | 默认折叠，不推荐用于业务对账 |

## 授权初始化与对账采集边界

平台授权场景和对账运行场景共享底层采集能力，但用户体验和职责不同。

授权初始化负责：

1. 授权成功后创建平台数据源和固定数据集目录。
2. 排队初始化采集，抓取首批真实样本。
3. 基于真实样本生成语义建议。
4. 经字段语义确认并发布后，数据集进入对账方案选择。

自动对账和重新对账负责：

1. 基于已发布的数据集触发当次业务数据采集。
2. 采集成功后执行 proc/recon。
3. 采集失败时按任务策略重试，最多 3 次。
4. 3 次仍失败则本次运行失败，并在运行详情中展示采集失败原因。

自动对账和重新对账不负责生成语义数据集，也不改变“数据集是否可选”的发布状态。店铺详情可以展示这些采集任务的最近记录，但主错误应出现在对账运行详情中。

## 状态机

每个店铺数据集独立维护两个状态：采集初始化状态和语义状态。

### 初始化状态

| 状态 | 含义 | 用户可操作 |
| --- | --- | --- |
| `not_started` | 数据集存在但没有初始化任务 | 显示“立即初始化” |
| `queued` | 初始化任务已排队 | 显示“等待初始化”，可查看任务 |
| `running` | 初始化任务正在采集 | 显示“初始化中”，禁止重复触发 |
| `succeeded` | 已采集真实样本 | 显示样本统计和 20 条真实数据 |
| `failed` | 初始化失败 | 显示失败原因和“重新初始化” |

### 语义状态

| 状态 | 含义 | 用户可操作 |
| --- | --- | --- |
| `waiting_for_samples` | 尚无真实样本 | 不允许刷新语义 |
| `preset` | 只有平台内置字段字典，没有真实样本 | 可查看预置结构，不允许标记为真实样本语义 |
| `queued` | 语义生成已排队 | 显示“等待语义生成” |
| `running` | 正在生成语义 | 显示“语义生成中”，禁止重复触发 |
| `succeeded` | 已生成语义结构 | 显示字段结构，可刷新语义 |
| `failed` | 语义生成失败 | 显示失败原因和“重新生成语义” |

前端即使状态滞后，也不能导致重复任务。后端需要对初始化任务按
`dataset_id + resource_key + biz_date/initial window` 幂等；对语义生成任务按
`dataset_id + schema_hash + sample_hash` 幂等。重复触发时返回已有任务，前端提示“任务已在执行中”。

初始化采集失败时，系统最多重试 3 次。仍失败时，该数据集不能完成字段语义确认发布，也不能进入对账方案选择。若字段语义确认和发布已经完成，后续自动对账采集失败只影响本次对账运行，不反向取消发布。

## 时间字段口径

需要区分两个概念：

- 平台采集时间字段：系统向平台拉取数据时使用的 API 窗口或账单日期。
- 对账业务日期字段：新建运行计划时选择的 T-N 取数口径，用于确定本次对账核对哪一天的数据。

| 平台 | 采集时间字段/参数 | 对账业务日期字段建议 | 说明 |
| --- | --- | --- | --- |
| 淘宝/天猫初始化 | `created`，API 参数为 `start_created/end_created` | `biz_date` | 初始化按订单创建时间抓 T-1 样本。 |
| 淘宝/天猫增量 | `modified`，API 参数为 `start_modified/end_modified` | `biz_date` | 每 2 小时抓订单变更；财务对账仍按业务日期过滤。 |
| 支付宝 | `bill_date` | `bill_date` | 下载某天账单文件，采集日期和对账日期基本一致。 |

淘宝/天猫的 `biz_date` 当前由订单行推导，优先使用 `pay_time`，其次 `created`，再其次 `modified`。运行计划选择的是“对账日期口径”，不是淘宝 TOP API 的拉取字段。

## 语义生成逻辑

### 淘宝/天猫

淘宝订单 API 返回字段多为英文缩写。首版应以平台内置字典为主，LLM 只补充未知字段。

推荐内置字段：

| raw_name | display_name | field_source | semantic_type | business_role |
| --- | --- | --- | --- | --- |
| `tid` | 主订单号 | `normalized` | `identifier` | `identifier` |
| `oid` | 子订单号 | `normalized` | `identifier` | `identifier` |
| `biz_date` | 业务日期 | `normalized` | `date` | `time` |
| `pay_time` | 付款时间 | `normalized` | `datetime` | `time` |
| `modified` | 更新时间 | `normalized` | `datetime` | `time` |
| `trade_status` | 主订单状态 | `normalized` | `status` | `status` |
| `order_status` | 子订单状态 | `normalized` | `status` | `status` |
| `refund_status` | 退款状态 | `normalized` | `status` | `status` |
| `payment` | 主订单实付金额 | `normalized` | `amount` | `amount` |
| `order_payment` | 子订单实付金额 | `normalized` | `amount` | `amount` |
| `total_fee` | 主订单商品总额 | `normalized` | `amount` | `amount` |
| `order_total_fee` | 子订单商品总额 | `normalized` | `amount` | `amount` |
| `alipay_no` | 支付宝交易号 | `normalized` | `identifier` | `identifier` |
| `title` | 商品标题 | `normalized` | `text` | `name` |
| `quantity` | 购买数量 | `normalized` | `number` | `quantity` |

默认唯一标识建议：

- `tid + oid`

业务名称建议：

- `淘宝/天猫订单明细 - {店铺名}`

### 支付宝

支付宝账单文件本身包含中文表头。首版语义生成必须从 `platform_alipay_bill_lines.payload`
中提取两类字段：

1. 标准化顶层字段，例如 `alipay_trade_no`、`merchant_order_no`、`business_order_no`、
   `amount`、`income_amount`、`expense_amount`、`trade_time`、`bill_date`。
2. 原始账单字段，即 payload 内的 `raw` 对象字段，展示为 `raw.<中文列名>`。

展示时字段分组：

| 分组 | 示例 | 默认状态 |
| --- | --- | --- |
| 标准字段 | `alipay_trade_no`, `merchant_order_no`, `income_amount` | 展开 |
| 原始账单字段 | `raw.支付宝交易号`, `raw.收入`, `raw.支出`, `raw.入账时间` | 展开 |
| 系统字段 | `source_row_key`, `source_file_name`, `source_row_number` | 折叠 |

默认唯一标识建议：

- `source_row_key`

对账推荐字段：

- 订单匹配：`alipay_trade_no`、`merchant_order_no`、`business_order_no`
- 金额核对：`amount`、`income_amount`、`expense_amount`，以及原始账单里的收入/支出/发生金额字段
- 时间口径：`trade_time`、`bill_date`，以及原始账单里的入账时间/发生时间字段

业务名称建议：

- `支付宝资金账单 - {商户名}`
- `支付宝交易账单 - {商户名}`

## 后端接口

推荐增加店铺详情聚合接口，避免前端在店铺列表里自行拼多个数据源接口。

```http
GET /api/platform-connections/{platform_code}/shops/{shop_connection_id}/datasets
```

返回：

```json
{
  "shop": {},
  "datasets": [
    {
      "dataset": {},
      "collection_status": {
        "status": "running",
        "message": "初始化中",
        "latest_job": {},
        "stats": {}
      },
      "semantic_status": {
        "status": "waiting_for_samples",
        "message": "等待真实样本"
      },
      "semantic_profile": {},
      "fields": [],
      "sample_rows": [],
      "sample_limit": 20
    }
  ]
}
```

动作接口可复用现有数据源工具，前端通过聚合接口刷新状态：

- 初始化或重试：`data_source_trigger_dataset_collection`
- 刷新语义：`data_source_refresh_dataset_semantic_profile`
- 管理发布：现有 `data_source_update_dataset_semantic_profile` 和发布接口

后端需要补齐语义采样来源：

- `platform_order_lines`：从 `auth_db.list_platform_order_lines(..., limit=20)` 取 payload。
- `platform_alipay_bill_lines`：从 `auth_db.list_platform_alipay_bill_lines(..., limit=20)` 取 payload。
- 通用数据源：保持 `dataset_collection_records`。

## 前端交互

### 平台详情页

店铺表格增加“查看数据”动作，打开店铺数据详情抽屉或在行下方展开。

布局：

```text
店铺详情
  授权状态 / Token 到期 / 最近同步

  数据集卡片
    名称：淘宝/天猫订单明细
    初始化：初始化中 / 已采集 / 失败
    语义：等待样本 / 语义生成中 / 已生成 / 失败
    操作：查看任务 / 重新初始化 / 重新生成语义 / 管理发布

    字段结构
      标准字段
      原始账单字段
      系统字段

    真实数据预览
      20 条
```

### 操作可见性

| 场景 | 主显示 | 操作 |
| --- | --- | --- |
| 初始化排队或运行中 | “初始化中” | 只显示“查看任务” |
| 初始化失败 | “初始化失败：原因” | 显示“重新初始化” |
| 仅有预置结构 | “预置结构，等待真实样本” | 可查看字段，不允许刷新语义 |
| 初始化成功但语义未生成 | “等待语义生成” | 自动排队；如果未排队，显示“生成语义” |
| 语义运行中 | “语义生成中” | 禁用“刷新语义” |
| 语义失败 | “语义生成失败：原因” | 显示“重新生成语义” |
| 语义成功 | 字段结构可见 | 显示“刷新语义”和“管理发布” |

### 数据预览

真实数据预览最多展示 20 条：

- 列名优先使用语义中文名。
- 鼠标悬停或副标题显示技术字段名。
- 支付宝 `raw.*` 字段在表头显示原中文名，技术名显示为 `raw.原字段名`。
- 系统字段默认不进入预览主表，可在“系统字段”分组里查看。

## 错误处理

- 初始化失败必须展示平台、数据集、业务日期、失败原因。
- 支付宝账单未生成应展示为可理解状态，例如“支付宝 2026-05-07 trade 账单未生成”，并允许稍后重试。
- 语义生成失败不影响已采集数据查看，但阻止“已生成语义”标记。
- 如果已有预置语义但没有真实样本，标记为“预置结构”，不要冒充真实样本语义。

## 验收标准

1. 淘宝/天猫授权成功后，店铺详情能看到订单明细数据集的初始化状态。
2. 淘宝/天猫 T-1 初始化完成后，店铺详情能看到语义字段结构和 20 条真实订单明细。
3. 支付宝授权成功后，店铺详情能看到资金账单和交易账单两个数据集。
4. 支付宝账单初始化完成后，两个数据集都从 `platform_alipay_bill_lines` 展示语义字段结构和 20 条真实账单行。
5. 后台初始化或语义生成运行中，前端不允许重复触发同一任务。
6. 初始化失败时展示“重新初始化”；语义失败时展示“重新生成语义”。
7. `semantic_profile` 仍写入 `data_source_datasets.meta`，raw 明细表不保存语义字段。
8. 管理发布弹窗仍可编辑并保存语义字段。

## 测试建议

- 后端单测：支付宝数据集 payload 使用 `platform_alipay_bill_lines/alipay_bill_lines` 元数据。
- 后端单测：语义刷新对 `platform_order_lines` 采样成功。
- 后端单测：语义刷新对 `platform_alipay_bill_lines` 采样成功，并展开 `raw` 中文账单字段。
- 后端单测：初始化任务运行中重复触发返回已有任务。
- 前端组件测试：店铺详情运行中状态不显示可用的“立即初始化”。
- 前端组件测试：失败状态显示重试动作。
- 前端组件测试：成功状态展示字段结构和 20 条样例入口。
- E2E：淘宝授权 mock 成功后展示订单明细真实样例。
- E2E：支付宝授权 mock 成功后展示资金账单、交易账单真实样例。

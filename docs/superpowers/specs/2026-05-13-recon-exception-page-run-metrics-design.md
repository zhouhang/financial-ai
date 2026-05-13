# 对账差异页面运行指标设计

## 背景

公开对账差异页面目前主要展示某次对账运行的异常明细。财务用户在查看明细前，还需要先看到本次运行的关键概览：

- 有多少记录完全匹配成功；
- 当前有多少差异；
- 本次对账实际读取了哪些源数据集，各自多少行。

第一版保持现有差异总数口径，不按匹配字段去重，不改钉钉汇总消息、责任人消息，也不改运行记录异常看板。

## 目标

- 在现有“差异总数”左侧增加“匹配成功”。
- 增加“本次读取数据”，按真实中文数据集名称展示每个源数据集的行数。
- 保持异常列表、筛选、详情弹窗现有行为不变。
- 不做数据库迁移，不改变对账执行流程。

## 非目标

- 不做全局差异计数口径调整。
- 不按匹配字段对差异数去重。
- 不修改钉钉消息文案。
- 不修改运行记录异常看板。
- 不增加导出或新的详情页。

## 页面展示

在 `PublicReconRunExceptionsPage` 顶部概览区域展示：

```text
匹配成功：X 条    差异总数：Y 条

本次读取数据：
交易订单明细表：100 条
支付宝资金账单 - 武汉泰斯网络科技有限公司-婉美de承诺：160 条
```

如果能拿到新增/更新信息，则作为弱化辅助信息展示，例如小字或 tooltip：

```text
新增 30 / 更新 130
```

主数字始终表示本次对账读取或进入对账的数据行数，不用 upsert 合计替代主数字。

## 指标口径

### 匹配成功

固定读取：

```text
run.raw.recon_result_summary_json.matched_exact
```

含义：匹配字段命中，且对比字段无差异。

### 差异总数

继续使用当前页面已有口径：

- 优先使用接口返回的 `total`；
- 如果没有 `total`，使用已加载异常列表数量；
- 如果必须从对账汇总推导，则使用 `source_only + target_only + matched_with_diff`。

`matched_exact` 不计入差异总数。

### 本次读取数据

展示每个源数据集本次实际读取或进入对账的数据行数。优先读取：

```text
run.raw.source_snapshot_json.collections[].collection_records.record_count
```

字段兜底顺序：

- `collection_records.record_count`
- `collection_records.count`
- `collection_records.row_count`
- collection 顶层 `record_count`
- collection 顶层 `count`
- collection 顶层 `row_count`

数据集名称沿用差异页已有的财务友好名称逻辑：

- `dataset_name`
- `business_name`
- `display_name`
- `name`
- 非技术化的 `resource_key` / `table_name` 只作为最后兜底。

### 新增 / 更新辅助信息

如果运行快照中存在采集任务或采集摘要字段，可以展示辅助信息：

- `inserted_count`
- `updated_count`
- `upserted_count`

如果字段不存在，则不展示辅助信息，不报错，不把缺失字段当作 0。

## 数据流

1. 差异页继续通过现有公开 bundle 加载 run、scheme、task、exceptions、分页信息。
2. 前端从 `bundle.run.raw` 中读取运行级指标。
3. 前端生成一个页面视图模型：
   - `matchedSuccessCount`
   - `differenceTotal`
   - `sourceReadCounts[]`
4. 顶部概览区渲染这些指标，异常列表继续使用原来的数据。

第一版不新增后端接口。如果确认现有公开 bundle 没有返回 `source_snapshot_json` 或 `recon_result_summary_json`，实现时只补充 bundle 序列化字段，不新增表结构。

## 兼容策略

历史运行可能缺少完整快照字段，页面应当：

- 缺少 `matched_exact` 时，“匹配成功”显示 `--`；
- “差异总数”保持当前页面逻辑；
- 缺少可用源数据条数时，隐藏“本次读取数据”或显示“不详”；
- 异常列表必须正常渲染。

## 测试要求

增加或更新前端测试，覆盖指标提取逻辑：

- `matched_exact` 正确展示为“匹配成功”。
- `total` 继续作为差异总数。
- `record_count` 能按中文数据集名称展示。
- 指标缺失时页面不崩溃。
- 只有存在新增/更新字段时才展示新增/更新辅助信息。

手工验证使用现有“泰斯支付宝对账”差异页面，确认顶部新增指标出现，且异常列表内容不变。

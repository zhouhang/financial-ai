# 自动对账平台授权采集适配设计

## 背景

自动对账和重新对账的新运行计划链路已经围绕数据集绑定执行：

- 运行计划读取 `dataset_bindings` 或 `input_bindings_json`。
- 执行前触发 `data_source_trigger_dataset_collection`。
- 采集完成后通过数据集读取层构造 `dataset_ref`，再进入 proc/recon。

当前采集适配主要覆盖数据库通用采集和淘宝/天猫订单明细专用采集。接下来需要让自动对账对不同平台授权渠道采用各自的采集方式，同时保持对账执行层只消费结构化数据集。

## 目标

1. 自动对账和重新对账根据对账方案绑定的数据集触发采集，不直接假设数据来自数据库。
2. 数据库、淘宝/天猫、支付宝都通过统一数据集采集入口接入。
3. 支付宝继续归类为电商平台授权来源，不因为内部存在下载文件步骤而归为普通文件来源。
4. 对账执行层只消费采集后的结构化数据，不直接读取支付宝 raw file。
5. 重新对账默认重新触发采集，并保留原运行快照作为审计与排查依据。

## 非目标

本设计不实现以下内容：

- 普通 API 数据源采集扩展。
- 普通文件上传或文件下载型数据源扩展。
- 网页抓取或浏览器辅助采集。
- 支付宝 raw file 保存和解析入库的内部实现。

支付宝内部采集方案由并行开发工作负责。本设计只要求支付宝采集能力完成后，可以被统一数据集采集入口调用，并能返回可供自动对账读取的结构化数据集。

## 分类模型

使用两层分类，避免把业务来源和执行方式混在一起。

### 业务来源

`source_kind` 和 `provider_code` 表达数据来源的业务身份：

| 来源 | source_kind | provider_code |
| --- | --- | --- |
| 数据库连接 | database | 按连接类型 |
| 淘宝/天猫授权 | platform_oauth | taobao / tmall |
| 支付宝授权 | platform_oauth | alipay |

### 采集实现

`collection_driver` 表达数据集的采集实现方式：

| driver | 用途 |
| --- | --- |
| db_query | 数据库查询采集 |
| taobao_order_api | 淘宝/天猫订单 API 采集 |
| alipay_bill_download_import | 支付宝授权后获取下载链接，下载账单文件，解析并入库 |

`collection_driver` 应来自数据集元数据，例如 `dataset.extract_config.collection_driver` 或 catalog profile 的 `collection_config.collection_driver`。如果缺省，则保留现有兼容推断：

- `storage=platform_order_lines` 推断为淘宝/天猫订单采集。
- `source_kind=database` 推断为 `db_query`。
- `source_kind=platform_oauth + provider_code=alipay` 推断为 `alipay_bill_download_import`，前提是支付宝采集器已注册。

## 读取层约定

采集实现可以不同，但自动对账读取层只接受结构化数据集。

| 来源 | 采集后读取方式 |
| --- | --- |
| 数据库 | `dataset_collection_records` |
| 淘宝/天猫 | 兼容现有 `platform_order_lines` |
| 支付宝 | 支付宝采集器解析入库后的 PostgreSQL 结构化表，读取层通过统一 dataset loader 暴露 |

支付宝 raw file 保存路径形如：

```text
finance-mcp/uploads/platform/alipay/{merchant_id}/{bill_date}/...
```

raw file 只作为审计资产和问题排查依据，不作为 recon/proc 的直接输入。

## 自动对账流程

1. `auto_scheme_run` 读取运行计划和执行方案。
2. `resolve_plan_inputs_node` 解析运行计划或方案的数据集绑定。
3. 对每个基础数据集 binding 调用 `data_source_trigger_dataset_collection`。
4. 统一采集入口根据数据源与数据集元数据选择 `collection_driver`。
5. 采集入口创建或复用 `sync_jobs`，执行具体采集器。
6. 自动对账节点等待采集任务结束。
7. 采集成功后读取数据集记录，确认必需数据就绪。
8. `bind_ready_collection_node` 构造 `dataset_ref`。
9. 进入 proc/recon 执行。

## 重新对账流程

`/recon/runs/rerun` 会以 `trigger_mode=rerun` 入队。运行图会将其归一为 `retry`，并复用自动对账的数据集采集流程。

重新对账的默认行为：

- 根据原运行恢复 `run_plan_code` 和 `biz_date`。
- 重新触发当前绑定数据集的采集。
- 使用最新采集成功的数据执行对账验证。
- 原运行的 `source_snapshot_json` 保留，用于审计和问题定位。

## 采集适配边界

统一采集入口负责：

- 解析 `source_kind`、`provider_code`、`collection_driver`。
- 创建和更新 `sync_jobs`、`sync_job_attempts`。
- 标准化采集结果、错误、指标和 checkpoint。
- 对外返回一致的 job 状态。

各渠道 driver 负责：

- 数据库：执行查询，返回 rows。
- 淘宝/天猫：调用已有平台订单 API 采集能力，写入现有存储。
- 支付宝：调用并行开发的支付宝采集能力，完成 raw file 保存、解析和 PostgreSQL 入库。

自动对账执行层不应该直接写渠道分支。它只触发数据集采集、等待 job、读取结构化数据集。

## 错误处理

采集失败时：

- 当前数据集 binding 标记为 missing。
- 必需数据集缺失时，运行停在 `validate_dataset` 或等价采集失败状态。
- 错误信息包含数据集名称、业务日期、采集 driver、底层错误摘要。
- `source_snapshot_json.collection_attempts` 保留每个 binding 的采集尝试记录。

可选数据集缺失时：

- 记录 warning。
- 不阻塞对账执行。

## 测试建议

1. 数据库数据集自动对账仍能触发采集并执行成功。
2. 淘宝/天猫 `platform_order_lines` 数据集仍走现有采集与读取兼容路径。
3. 支付宝数据集在采集器已注册时，自动对账能触发其 driver 并消费结构化结果。
4. 支付宝 raw file 路径不出现在 recon/proc 输入中。
5. 重新对账以 `rerun` 入队后会重新触发采集。
6. 必需数据集采集失败时，运行进入数据未就绪/采集失败状态并写入可读错误。


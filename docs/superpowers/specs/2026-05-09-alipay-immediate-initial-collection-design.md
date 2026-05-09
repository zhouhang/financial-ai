# 支付宝授权后即时初始化采集设计

## 背景

支付宝授权接入已经完成商户授权、数据集创建、账单下载解析、专表存储和 recon loader。

当前缺口是授权回调后的初始化采集行为偏离了已确认方案：

- 淘宝/天猫授权成功后会 `asyncio.create_task()` 后台立即执行 T-1 初始化采集。
- 支付宝授权成功后当前只调用 `_schedule_alipay_initial_collection_jobs()` 创建 `sync_jobs` 记录，并写入 `deferred_until = "alipay_bill_collector"`。
- 目前没有消费该 deferred 标记的 worker，因此授权后不会立刻下载 T-1 账单。

这导致授权页/数据集详情页无法在授权后展示 20 条真实支付宝账单样例。

## 决策锁

以下为已确认决策，后续实现不得擅自改变。如实现阶段发现更优或更安全的替代方案，必须先暂停并获得用户明确确认。

- **MUST**：支付宝授权成功后立即后台触发 T-1 初始化采集。
- **MUST**：回调接口不能被账单下载长时间阻塞；初始化采集应后台异步执行。
- **MUST**：初始化采集仍走统一采集入口 `trigger_dataset_collection_for_company()`，复用 job、attempt、event、health、checkpoint 和幂等逻辑。
- **MUST**：支付宝初始化实际落表仍是 `platform_alipay_bill_lines`。
- **MUST NOT**：把支付宝初始化实现成只创建 deferred sync job 记录。
- **MUST NOT**：把支付宝账单写回 `dataset_collection_records`。
- **MUST NOT**：初始化采 T 日或 90 天历史数据；首版只采 T-1。
- **MUST NOT**：改变每天 `10:30` 的后续 T-1 定时采集策略。

## 目标

修正支付宝授权回调后的初始化行为：

1. 授权成功后创建支付宝数据源。
2. 创建两个数据集：
   - `支付宝资金账单 - {商户名}`，`bill_type = signcustomer`
   - `支付宝交易账单 - {商户名}`，`bill_type = trade`
3. 构建两个 T-1 初始化采集任务 payload。
4. 立即后台串行执行这两个初始化采集任务。
5. 每个任务通过统一采集入口触发真实下载、解析并写入 `platform_alipay_bill_lines`。
6. 授权页面和数据集预览继续从 `platform_alipay_bill_lines` 读取真实样例数据。

## 非目标

- 不新增独立 deferred job worker。
- 不改变淘宝/天猫初始化采集逻辑。
- 不改变支付宝每日定时采集逻辑。
- 不改变支付宝专表结构。
- 不新增前端页面流程；首版复用现有采集状态和预览读取能力。

## 设计

### 初始化任务构建

保留 `_build_alipay_initial_collection_jobs()`，继续负责构建 T-1 初始化任务 payload：

- `trigger_mode = "initial"`
- `idempotency_key = "alipay-initial:{dataset_id}:{bill_type}:{bill_date}"`
- `params.bill_date = T-1`
- `params.biz_date = T-1`
- `params.force_mode = "initial"`

该函数只生成 payload，不直接执行。

### 初始化任务执行

新增 `_run_alipay_initial_collection_jobs()`，对齐现有 `_run_taobao_initial_collection_jobs()`。

执行方式：

```text
for job_payload in jobs:
    await data_sources.trigger_dataset_collection_for_company(
        company_id=company_id,
        source_id=job_payload.source_id,
        dataset_id=job_payload.dataset_id,
        resource_key=job_payload.resource_key,
        trigger_mode="initial",
        idempotency_key=job_payload.idempotency_key,
        background=False,
        params=job_payload.params,
    )
```

这里调用统一采集入口不是为了写通用表，而是为了复用采集任务编排。实际落表由支付宝数据集 metadata 和 collection driver 决定：

```text
trigger_dataset_collection_for_company
  -> _execute_sync_job
  -> alipay_bill_download_import
  -> _run_alipay_bill_collection
  -> auth_db.upsert_platform_alipay_bill_lines
  -> platform_alipay_bill_lines
```

### 授权回调

支付宝授权回调中，创建数据源和两个数据集后：

- 不再调用 `_schedule_alipay_initial_collection_jobs()`。
- 改为：

```python
asyncio.create_task(
    _run_alipay_initial_collection_jobs(
        company_id=company_id,
        jobs=alipay_jobs,
    )
)
```

回调仍立即返回授权成功，后台采集任务独立执行。

### 旧 deferred 函数

`_schedule_alipay_initial_collection_jobs()` 当前行为会制造不会被消费的 pending/deferred 记录。实现时应移除它，或至少确保授权回调不再调用它。首选移除，避免后续误用。

## 用户可见行为

授权成功后：

- 页面可立即看到支付宝商户连接和两个数据集。
- 初始化采集会在后台开始。
- 采集完成前，预览可能暂时为空或显示采集中状态。
- 采集成功后，预览从 `platform_alipay_bill_lines` 展示最多 20 条真实账单行。
- 若支付宝账单未生成或接口失败，sync job/attempt/event/health 中应可见失败原因。

## 测试要求

必须新增或更新行为级测试，防止再次偏离：

- 支付宝授权回调成功后调用 `_run_alipay_initial_collection_jobs()`，而不是 `_schedule_alipay_initial_collection_jobs()`。
- `_run_alipay_initial_collection_jobs()` 对每个 T-1 payload 调用 `trigger_dataset_collection_for_company()`。
- 调用参数必须包含：
  - `trigger_mode = "initial"`
  - `background = False`
  - `params.bill_date = T-1`
  - `params.biz_date = T-1`
  - `idempotency_key` 包含 `alipay-initial`
- 授权回调测试必须断言不再创建只含 `deferred_until = "alipay_bill_collector"` 的初始化 job。
- 现有支付宝专表采集测试继续保证不会调用 `upsert_dataset_collection_records`。

## 偏离协议

实现阶段如果需要改变以下任一行为，必须先停下来请求用户确认：

- 初始化是否立即执行。
- 初始化是否后台异步执行。
- 是否使用 `trigger_dataset_collection_for_company()`。
- 初始化采集日期范围。
- 支付宝账单物理落表。
- 是否保留/引入 deferred job worker。

请求确认时必须说明：原确认方案、拟改变方案、改变原因、风险、替代方案。

## 验收标准

- 支付宝授权成功后会立即后台触发两个 T-1 初始化采集任务。
- 初始化任务真实执行账单下载链路，而不是只创建 sync job 记录。
- 初始化采集写入 `platform_alipay_bill_lines`。
- 授权后数据集详情/预览可在采集完成后展示真实账单样例。
- 每日 `10:30` T-1 定时采集保持不变。
- 后端相关测试通过。


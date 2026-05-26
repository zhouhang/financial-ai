# 浏览器采集按账期复用设计

日期：2026-05-26

## 背景

浏览器采集目前主要面对千牛这类风控强的网站。自动对账触发采集时，如果短时间内重复打开浏览器、登录、下载同一账期文件，会增加风控概率，但对数据新鲜度没有明显收益：浏览器 playbook 下载的是某个 `biz_date` 的账单文件，同一数据集同一账期成功下载后，重复下载通常不会产生不同数据。

当前采集复用机制使用全局 TTL：

- 默认 `DATASET_COLLECTION_REUSE_TTL_SECONDS=600`。
- 单次请求可传 `collection_reuse_ttl_seconds` 或 `reuse_ttl_seconds`。
- TTL 上限为 3600 秒。

这套规则适合数据库/API/平台授权的短时间去重，但不适合浏览器采集的风控约束。浏览器需要的是“同一账期成功一次即复用”，不是“成功后一段时间内复用”。

## 目标

1. 自动对账只有在任务实际使用浏览器数据集时才触发浏览器采集。现有链路已满足，本文不改变。
2. 自动链路触发浏览器采集时，同一 `dataset_id + resource_key + biz_date` 已有成功采集结果，直接复用，不再打开浏览器重复下载。
3. 同一浏览器采集任务已在 `pending/running/waiting_human_verification/resuming` 中时，继续复用运行中任务，避免并发打开多个 Chrome。
4. 浏览器任务列表点击“重试”是人工显式维护/测试动作，必须可以绕过“同账期成功复用”，重新下发凭证 + playbook 到采集机采集。
5. 数据库、API、平台授权暂时保留现有 TTL 行为，不引入按类型配置 UI。

## 非目标

- 不开放浏览器 TTL 配置给普通用户。
- 不把全局 TTL 改成 24 小时。
- 不改变 `browser_collection_records` 的行级 upsert 幂等模型。
- 不新增每日预采集计划。
- 不改变风控 handoff、截图/远程输入等能力。

## 设计决策

### 决策一：浏览器自动链路按账期复用，不按时间 TTL 复用

浏览器采集驱动为 `browser_playbook_remote` 时，自动对账、手动对账、重新对账等自动链路触发采集，后端先查找同一：

- `company_id`
- `data_source_id`
- `dataset_id`
- `resource_key`
- `biz_date`

是否已有 `job_status='success'` 的采集任务。只要存在，就返回复用结果，`reuse_reason` 使用新的语义，例如 `browser_biz_date_success`。

这条规则不看 `completed_at`，所以不是 24 小时 TTL，而是按账期复用。

### 决策二：运行中任务仍优先复用

无论是否强制重采，只要同一浏览器采集任务已经处于：

- `pending`
- `running`
- `waiting_human_verification`
- `resuming`

后端都应复用该任务，不创建并发任务。这样避免同一店铺同一账期同时打开多个 Chrome 或多个风控验证。

### 决策三：浏览器任务列表“重试”绕过成功结果复用

数据连接里的浏览器任务列表“重试”按钮用于人工测试、修复和重新下发 playbook。该入口应向后端传递明确语义，例如：

- `force_collection=true`
- 或 `skip_recent_success_reuse=true`
- 或专用 trigger mode，如 `verification_retry`

后端收到该语义后：

1. 仍先复用同一任务的运行中 job。
2. 不复用历史成功 job。
3. 创建新的 browser sync job，下发到采集机。

这保证自动链路控风险，人工入口仍可验证最新 playbook 和采集环境。

### 决策四：非浏览器数据源维持现状

数据库、API、平台授权继续使用现有全局 TTL 和单次参数覆盖能力。本文不新增来源类型级 TTL 配置，也不调整 TTL 上限。

## 数据流

### 自动对账触发

1. recon run 解析 input bindings。
2. binding 指向 browser dataset 时，调用 `data_source_trigger_dataset_collection`。
3. finance-mcp 解析 collection driver 为 `browser_playbook_remote`。
4. 后端先查找同一任务是否有运行中 job。
5. 如果有，返回 `reused=true`、`queued=true`。
6. 如果没有运行中 job，再查找同一 `dataset_id + resource_key + biz_date` 是否已有成功 browser job。
7. 如果有，返回 `reused=true`、`queued=false`，自动对账直接读取已采集的 `browser_collection_records`。
8. 如果没有，创建新的 browser sync job。

### 浏览器任务列表重试

1. 用户点击“重试”。
2. finance-web 调用现有 browser retry API。
3. data-agent/MCP 请求携带强制采集语义。
4. 后端先检查运行中 job；如有则复用。
5. 没有运行中 job 时，即使同一 `biz_date` 已有成功 job，也创建新的 browser sync job。

## 错误处理

- 找到历史成功 job 但 `browser_collection_records` 为空：不复用，创建新采集任务，避免成功状态与数据落库不一致导致对账空跑。
- 找到历史成功 job 但数据集已删除、禁用或数据源未激活：不复用，返回现有的数据源/数据集不可用错误。
- 浏览器任务列表重试遇到运行中 job：返回复用提示，提示“已有同一浏览器任务正在执行或等待人工验证”。
- 风控等待中的任务按运行中处理，避免新开 Chrome。

## 测试策略

后端测试：

- 自动链路 browser driver 遇到同一 `dataset_id + resource_key + biz_date` 历史成功 job 时复用，不创建新 attempt。
- 复用历史成功 job 时要求能查到对应 `browser_collection_records`。
- browser retry/verification retry 传强制采集语义时，不复用历史成功 job。
- browser retry 遇到运行中 job 时仍复用运行中 job。
- 非 browser driver 仍使用现有 TTL 行为。

前端/API 测试：

- 浏览器任务列表“重试”请求携带强制采集语义。
- 重试复用运行中任务时展示现有提示。
- 自动对账入口不携带强制采集语义。

## 迁移与兼容

不需要数据库迁移。历史 `sync_jobs` 已包含 `request_payload.dataset_id`、`request_payload.biz_date` 和 `resource_key`，可直接用于查找历史成功任务。

如果存量成功 job 缺少 `dataset_id` 或 `biz_date`，不参与复用，走新采集。

## 验收标准

1. 同一浏览器数据集同一 `biz_date` 自动对账首次触发会采集，第二次自动对账直接复用，不打开新的 Chrome。
2. 同一浏览器任务正在运行或等待人工验证时，再次触发自动对账或点击重试都不会并发创建第二个 Chrome 任务。
3. 浏览器任务列表点击重试，在没有运行中任务时会创建新的 sync job，即使当天账期已有成功采集。
4. 数据库、API、平台授权采集行为不变。

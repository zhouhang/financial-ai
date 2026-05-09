# 支付宝商家授权认领流程设计

## 背景

支付宝开放平台的第三方应用商家授权与当前 Tally 的 OAuth 会话模型不完全一致。

当前 Tally 实现以 `appToAppAuth + state` 为主：

- Tally 创建 `auth_sessions`。
- 授权链接携带 `state`。
- 回调后用 `state` 找到企业、操作人和授权上下文。
- 再用 `app_auth_code` 换 `app_auth_token`，创建商户连接和支付宝账单数据集。

实际联调发现，支付宝开放平台“商家授权”中勾选“商家账单数据查询及下载接口”后生成的二维码/链接可以回调到 Tally，但真实回调只包含：

```text
app_auth_code=...
app_id=2021006152656574
source=alipay_app_auth
```

没有 `state`。因此当前代码会报“授权会话不存在或已失效”，无法把授权自动绑定到某个 Tally 企业。

## 决策锁

以下决策已确认，实施阶段不得擅自改变：

- **MUST**：支付宝账单采集授权主流程以开放平台“商家授权”二维码/PC 链接为准。
- **MUST**：Tally 授权页支持展示固定二维码和 PC 授权链接。
- **MUST**：保留后续动态生成支付宝商家授权链接的扩展点，但首版不依赖动态生成。
- **MUST**：支付宝无 `state` 回调后进入“待认领授权”流程。
- **MUST**：回调收到 `app_auth_code` 后立即换取 `app_auth_token`，避免授权码过期。
- **MUST**：待认领授权由 Tally 管理员通过认领码绑定到当前企业。
- **MUST**：认领成功后复用现有商户连接、商户授权、`trade/signcustomer` 数据集创建和初始化采集能力。
- **MUST NOT**：把无 `state` 的支付宝回调直接绑定到任意企业。
- **MUST NOT**：要求商户创建支付宝第三方应用。
- **MUST NOT**：把支付宝 `app_auth_token` 暴露给前端。

## 目标

1. 让支付宝开放平台商家授权二维码/PC 链接可以作为 Tally 支付宝授权入口。
2. 支持无 `state` 回调，避免真实商家授权被当前会话模型拒绝。
3. 在授权码有效期内换取并安全保存商户 `app_auth_token`。
4. 通过管理员认领，将待认领支付宝授权绑定到正确的 Tally 企业。
5. 认领成功后自动创建支付宝商户连接、授权记录、`trade` 交易账单数据集和 `signcustomer` 资金账单数据集。
6. 保持现有支付宝账单下载、raw file 保存、解析入库和 recon loader 逻辑不变。

## 非目标

- 不重新设计淘宝/天猫授权流程。
- 不移除现有 `state` 授权处理；它作为兼容路径保留。
- 不在首版实现动态生成支付宝商家授权二维码。
- 不新增支付宝账单类型；仍只采集 `trade` 和 `signcustomer`。
- 不改变自动对账和重新对账的采集入口。

## 方案

### 支付宝应用配置

支付宝应用配置增加商家授权入口字段：

- `merchant_auth_pc_url`：支付宝开放平台生成的商家授权 PC 链接。
- `merchant_auth_qr_url` 或 `merchant_auth_qr_asset`：二维码图片地址或上传后的资源引用。
- `merchant_auth_mode`：首版固定为 `static_invite`，后续可扩展为 `dynamic_invite`。

这些字段保存在现有 `platform_apps.extra` 中，避免新增应用配置表。配置接口仍由服务商管理员操作。

### 待认领授权模型

新增 PostgreSQL 表 `platform_pending_authorizations`，用于保存无 `state` 的支付宝商家授权回调。

核心字段：

- `id`
- `platform_code`，首版为 `alipay`
- `platform_app_id`
- `app_id`
- `source`
- `claim_code`
- `status`：`pending_claim`、`claimed`、`expired`、`failed`、`discarded`
- `access_token`
- `refresh_token`
- `token_expires_at`
- `refresh_expires_at`
- `raw_auth_payload`
- `callback_payload`
- `external_shop_id`
- `external_seller_id`
- `claimed_company_id`
- `claimed_by_user_id`
- `claimed_shop_connection_id`
- `claimed_at`
- `expires_at`
- `last_error`
- `created_at`
- `updated_at`

`access_token` 存放支付宝 `app_auth_token`，沿用现有 `shop_authorizations.access_token` 的语义和脱敏展示规则。前端接口不得返回 token 明文。

约束：

- `claim_code` 在未过期待认领记录中唯一。
- 同一个支付宝授权主体被重复授权时，认领阶段按 `external_shop_id + platform_code` 做幂等更新。
- 过期记录不可认领。

### 回调处理

`platform_handle_auth_callback` 增加分支：

1. 如果有 `state`，沿用当前 `auth_sessions` 流程。
2. 如果 `platform_code == alipay`、没有 `state`、有 `app_auth_code`，进入商家授权回调流程。
3. 商家授权回调流程加载服务商支付宝应用配置。
4. 调用 `alipay.open.auth.token.app` 换取 `app_auth_token`。
5. 从 token 响应中提取 `user_id` 作为 `external_shop_id`，`auth_app_id` 作为 `external_seller_id`。
6. 创建或更新待认领授权，生成认领码，默认 24 小时过期。
7. 回调页重定向到 Tally，展示“授权已收到”和认领码。

如果换 token 失败，记录失败状态和脱敏错误信息，回调页提示重新扫码授权。

### 管理员认领

新增平台连接工具和 API：

- `platform_list_pending_authorizations`
- `platform_claim_pending_authorization`
- `GET /platform-connections/alipay/pending-authorizations`
- `POST /platform-connections/alipay/pending-authorizations/{id}/claim`

认领请求参数：

- `claim_code`
- `merchant_display_name`

认领规则：

1. 必须是已登录用户。
2. 待认领记录必须是 `pending_claim` 且未过期。
3. `claim_code` 必须匹配。
4. 认领绑定到当前登录用户的 `company_id`。
5. 使用待认领 token 创建或更新 `shop_connections` 和 `shop_authorizations`。
6. 调用现有 `_upsert_alipay_bill_datasets()` 创建 `trade/signcustomer` 数据集。
7. 调用现有支付宝初始化采集逻辑触发 T-1 采集。
8. 将待认领记录置为 `claimed`，写入认领人、企业、商户连接和时间。

如果同一个支付宝 `external_shop_id` 已在当前企业存在，认领应更新该商户授权，而不是创建重复商户。若已被其他企业绑定，首版阻止自动认领并提示联系服务商管理员处理。

### 前端体验

支付宝授权页分为三个区域：

1. **商家授权入口**
   - 展示支付宝开放平台生成的二维码。
   - 提供 PC 授权链接按钮。
   - 说明商户授权完成后回到 Tally 输入认领码。

2. **待认领授权**
   - 展示当前可认领记录列表，隐藏 token。
   - 支持输入认领码刷新查询。
   - 展示回调时间、过期时间、支付宝主体 ID 后四位或脱敏信息、状态。

3. **绑定表单**
   - 输入商户显示名称。
   - 输入或选择认领码。
   - 点击绑定后刷新支付宝商户列表和数据集列表。

回调落地页在无 `state` 流程下显示：

```text
支付宝授权已收到。请复制认领码，在 Tally 支付宝授权页完成绑定。
```

如果当前浏览器已经登录 Tally，也可以提供“前往支付宝授权页”按钮，但认领动作仍要求管理员确认。

## 数据流

```text
服务商管理员配置支付宝商家授权二维码/PC 链接
  -> Tally 支付宝授权页展示二维码/链接
  -> 商户扫码或打开链接完成授权
  -> 支付宝回调 /api/platform-auth/callback/alipay?app_auth_code=...&app_id=...
  -> Tally 立即换 app_auth_token
  -> 创建 pending_claim 待认领授权和 claim_code
  -> 回调页展示认领码
  -> Tally 管理员登录并输入认领码
  -> 绑定到当前企业
  -> 创建 shop_connection 和 shop_authorization
  -> 创建 trade/signcustomer 数据集
  -> 触发 T-1 初始化采集
  -> 后续自动对账和重新对账读取 platform_alipay_bill_lines
```

## 安全和审计

- 待认领 token 不返回前端。
- 待认领记录默认 24 小时过期。
- 认领动作记录 `claimed_by_user_id`、`claimed_company_id`、`claimed_at`。
- 失败回调记录脱敏错误，不记录完整下载链接或 token。
- 无 `state` 回调不做企业自动匹配，避免财务数据误绑定。
- 重复认领、过期认领、跨企业已有绑定都应返回明确错误。

## 错误处理

- 缺少 `app_auth_code`：回调失败，提示重新授权。
- 支付宝 token 交换失败：创建失败记录或记录错误事件，提示重新扫码。
- 认领码不存在：提示检查认领码。
- 认领码过期：提示重新扫码授权。
- 商户已绑定其他企业：阻止绑定，提示联系服务商管理员。
- 数据集创建失败：商户授权仍保留，待认领记录标记为 `claimed`，授权会话记录 warning，页面提示稍后重试数据集初始化。

## 测试要求

后端：

- 无 `state` 支付宝回调创建 `pending_claim` 待认领授权。
- 无 `state` 回调会立即调用 token 交换。
- 回调响应不再提示“授权会话不存在或已失效”。
- 认领成功创建或更新 `shop_connections`。
- 认领成功创建 `shop_authorizations`。
- 认领成功创建 `trade` 和 `signcustomer` 数据集。
- 过期待认领记录不可认领。
- 认领码不匹配不可认领。
- 已绑定其他企业的支付宝主体不可自动认领。

前端：

- 支付宝授权页展示固定二维码和 PC 授权链接。
- 管理员可查看待认领授权列表。
- 管理员可输入认领码和商户显示名称完成绑定。
- 绑定成功后刷新支付宝商户列表。
- 回调无 `state` 时展示认领码和下一步操作。

集成：

- 使用真实形态回调参数 `app_auth_code/app_id/source` 能进入待认领流程。
- 认领后能触发支付宝 T-1 初始化采集。

## 验收标准

- 使用支付宝开放平台下载的商家授权二维码，商户扫码后能回调 Tally。
- 无 `state` 回调不会再失败为“授权会话不存在或已失效”。
- Tally 生成认领码，并能由管理员绑定到当前企业。
- 绑定后支付宝商户出现在电商平台授权列表。
- 绑定后自动创建 `trade` 和 `signcustomer` 数据集。
- 后续支付宝账单采集仍写入 `platform_alipay_bill_lines`。
- 现有 `state` 授权测试保持通过。

## 后续扩展

首版完成固定二维码/PC 链接闭环后，再评估动态生成支付宝商家授权链接。如果支付宝允许稳定构造 `b.alipay.com/page/message/tasksDetail` 链接并携带可回传上下文，可将 `merchant_auth_mode` 扩展为 `dynamic_invite`，但不得移除待认领兜底流程。

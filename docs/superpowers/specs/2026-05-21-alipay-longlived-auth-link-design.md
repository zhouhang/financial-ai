# 支付宝长效专属授权链接设计

## 背景

`数据连接 → 电商平台授权 → 支付宝` 现有的"生成专属授权链接"功能(`POST /api/platform-connections/alipay/auth-sessions` → `platform_create_auth_session`)会:

1. 创建一条 `auth_sessions`,`expires_at = now + 30min`。
2. 返回 `auth_url = openauth.alipay.com/oauth2/appToAppAuth.htm?app_id=..&redirect_uri=..&state=<state_token>`(直连支付宝)。

问题:这个 `auth_url` 背后的 session 30 分钟过期。运营人把链接复制发给商户/财务,对方稍后(几小时/几天)点开时,session 已失效,回调报"授权会话不存在或已失效"。这使得"生成链接 → 发出去 → 对方择时点击授权"这个真实使用方式不成立。

支付宝回调带 `state` 已实测会回传(动态 `appToAppAuth` + 自有 `redirect_uri` 流程),因此命中 session 绑定到正确企业的链路是通的;**唯一卡点就是 30 分钟时效**。

## 目标

1. 让"生成专属授权链接"产出**长效**链接(默认 30 天),发出去后对方任意时刻点开都能完成授权。
2. 长效链接被点开时,**当场**创建一条新的 30 分钟 `auth_session` 再跳转支付宝——把"30 分钟"从"链接寿命"变成"单次点击后的授权窗口"。
3. 链接点开**不需要 Tally 登录态**(商户/财务没有 Tally 账号)。
4. 复用现有支付宝回调、连接创建、`trade`/`signcustomer` 数据集创建逻辑,不改回调。
5. 每条链接互不影响(各自独立 token + 点击时各自独立 session)。

## 非目标

- ❌ 不做 Excel 批量生成 20 条链接 —— 这是独立的后续一次性任务,等本功能本地验证通过后,复用本设计的 token 签名函数离线生成。**不在本 spec 范围。**
- 不做 token 状态看板(无状态签名,授权进度直接看现有支付宝连接列表)。
- 不改支付宝回调 / 待认领(claim)流程。
- 不改淘宝/天猫授权。
- 不自动新建 `data_source` —— 复用绑定时既有的连接/数据集创建能力。

## 决策锁

- **MUST**:专属链接形态从"30min 直连 alipay"改为"长效 Tally 落地链接 `/p/alipay-auth?t=<jwt>`"。
- **MUST**:落地链接点开免登录;`company_id` / `operator_user_id` 来自验签后的 token,而非 Bearer 用户。
- **MUST**:30min `auth_session` 在落地页"继续"动作时**当场**创建。
- **MUST**:token 用现有 `JWT_SECRET` 签 HS256,不落库;`exp` 默认 30 天。
- **MUST**:回调逻辑不改,靠 `state` 命中既有 session。
- **MUST NOT**:把长效 token 直接当作可换 `app_auth_token` 的凭据(它只能发起一次新的授权会话)。
- **MUST NOT**:在落地链接里明文带支付宝密码/凭证。

## 方案

### Token(JWT HS256,无状态)

载荷:

```json
{
  "purpose": "alipay_auth_invite",
  "company_id": "<运营人企业>",
  "operator_user_id": "<运营人>",
  "merchant_display_name": "<弹窗填写的店铺显示名>",
  "expected_alipay_account": "<可选,落地页提示用;正常 UI 流程可空>",
  "external_shop_id": "<可选,店铺编码>",
  "iat": 0,
  "exp": 0,
  "jti": "<uuid>"
}
```

- 用 `auth.jwt_utils` 现有 `JWT_SECRET` + HS256 签发与校验。
- `exp = iat + 30 天`(常量,后续可配)。
- 不落库:链接是无状态 bearer 凭据,可离线生成(供后续 Excel 批量用)。

### 签 token 的复用函数

新增一个纯函数(不依赖请求上下文),供两处调用:

- `build_alipay_auth_invite_token(*, company_id, operator_user_id, merchant_display_name, expected_alipay_account="", external_shop_id="", ttl_days=30) -> str`
- `verify_alipay_auth_invite_token(token) -> dict | None`(校验 sig + exp + `purpose`,失败返回 None)

放在 finance-mcp 侧(凭证/JWT 工具同层),既给 MCP 工具用,也给后续离线 Excel 脚本 import。

### 生成入口(改现有,不新增 UI)

`platform_create_auth_session`(`platform_code='alipay'`)行为变更:

- 仍要求 `merchant_display_name`。
- **不再**返回 30min 直连 alipay 链接;改为 `build_alipay_auth_invite_token(...)` 用当前登录用户的 `company_id` + `user_id` + 入参 `merchant_display_name`,返回:
  - `auth_url = <TALLY_PUBLIC_BASE_URL>/p/alipay-auth?t=<jwt>`
- 返回结构其余字段(`session_id`/`state`)在本入口不再有意义(此时尚未建 session);保留 `auth_url` 即可,前端只用它。

> 兼容:其它平台(淘宝/天猫)`platform_create_auth_session` 路径不变。仅 alipay 分支改为长效链接。

### 落地端点(data-agent FastAPI,公开免 Bearer)

与现有支付宝回调 redirect 路由同一层(都是公开路由)。**确认页用 data-agent 服务端直接渲染极简 HTML**(不走 finance-web SPA、不需要前端登录态/路由),确认页里是一个 `POST /p/alipay-auth/continue` 的 HTML form(隐藏字段带 token),提交后服务端 302 跳支付宝。这样整个落地流程零前端依赖、零登录。

- `GET /p/alipay-auth?t=<jwt>`
  1. `verify_alipay_auth_invite_token` 验签;失败 → 渲染"链接已失效/无效"页。
  2. 幂等检查:查 `company_id` 下是否已有匹配该店(`external_shop_name == merchant_display_name`,或 `external_shop_id`)的有效支付宝连接;有 → 渲染"该店铺已完成支付宝授权,无需重复"。
  3. 否则渲染确认页:店铺显示名 +(若 token 带)应登录支付宝账号 + 醒目提示"务必用该账号登录,登错会绑错主体" + `[继续去支付宝授权]`(POST 到 continue,带 token)。
- `POST /p/alipay-auth/continue`(body 含 token)
  1. 再次验签。
  2. 用 token 的 `company_id` + `operator_user_id` + `merchant_display_name`,**服务端**创建一条 30min `auth_session`(复用 `auth_db.create_auth_session` + `session_extra={merchant_display_name, connection_label, subject_type:'alipay_merchant'}`),不依赖 Bearer。
  3. `connector.build_auth_url(state=<新 session state>)` → 302 跳支付宝。

> 这一步需要一个"免登录建 session"的服务端函数:把现有 `_create_auth_session` 里"从 Bearer user 取 company_id/user_id"的部分,改成可由调用方显式传入 `company_id` / `operator_user_id`,共用其余建库 + build_auth_url 逻辑。

### 回调(不改)

支付宝带 `state` 回调 → 现有 `platform_handle_auth_callback`/`get_auth_session_by_state` → 命中 session → 换 token、建连接、建 `trade`/`signcustomer` 数据集。`session.extra.merchant_display_name` 作为连接显示名。

### 配置

- `TALLY_PUBLIC_BASE_URL`:落地链接的对外可达域名(env)。本地测试可用 `http://127.0.0.1:<port>` 或隧道域名。
- `ALIPAY_AUTH_INVITE_TTL_DAYS`:默认 30。

## 错误处理

| 场景 | 处理 |
|---|---|
| token 验签失败 / 过期 / 篡改 | 落地页渲染"链接已失效或无效,请联系对接人重新生成";不泄露内部细节 |
| 该店已有有效支付宝连接 | "已完成授权,无需重复"页,不再建 session |
| 财务登错支付宝账号 | 技术上无法阻止(绑定的是实际登录账号);确认页强提示 `expected_alipay_account`;事后可在连接列表核对/解绑重来 |
| 支付宝授权失败回调 | 复用现有失败页 |
| `TALLY_PUBLIC_BASE_URL` 未配 | 生成入口返回明确错误,不产出半成品链接 |

## 安全

- 长效 token 是 bearer 能力:持链接者可发起"把某支付宝账号绑到该 `company_id`"。缓解:① HMAC(HS256)签名,无法伪造/篡改 `company_id`;② `exp` 30 天;③ `purpose` 限定,该 token 不能用于其它接口;④ 它只能发起新授权会话,换不到 `app_auth_token`。最坏后果 = 预期动作(给该企业绑一个支付宝账号),可接受。
- token 不带任何支付宝凭证;明文不入日志。

## 测试

- token:有效签发可被验签;过期 / 篡改 sig / `purpose` 不符 → 验签返回 None。
- 生成入口:alipay 分支返回 `auth_url` 形如 `<base>/p/alipay-auth?t=<jwt>`;`merchant_display_name` 进 token。
- `GET /p/alipay-auth`:有效 token 渲染确认页含店铺名(+应登账号);失效 token 渲染错误页;已存在连接 → 已授权页。
- `POST /p/alipay-auth/continue`:免 Bearer 下用 token 的 company 建 session 并返回 alipay url;state 写入 session。
- 回调:带 state 命中 session → 绑定(沿用现有测试)。
- mock alipay 端到端:生成长效链接 → 落地 → continue → mock 回调 → 连接 + 数据集创建。

## 后续(本 spec 之外)

- Excel 20 条批量:离线脚本 import `build_alipay_auth_invite_token`,按锁定筛选(福游云非空非"无" + 支付宝账号非空非"无" + 非退店 = 20)逐行签 token、拼 URL,写入 `现店铺负责人` 后一列 `支付宝授权专属链接`,存 Excel 副本。等本功能本地验证通过后再做。

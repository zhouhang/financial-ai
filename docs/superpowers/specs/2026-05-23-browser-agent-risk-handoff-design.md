# 浏览器采集风控兜底设计

日期：2026-05-23

## 背景

浏览器采集必须是云端 Tally 自动对账的数据获取能力。采集机部署 `browser-agent`，
负责根据云端下发的 playbook 和凭证，在本机打开浏览器、完成登录态检查、下载源数据，
并把采集结果回传到 Tally。

千牛 / 淘宝登录可能触发滑块、短信验证码、手机确认或其他安全校验。这个风险不能
100% 杜绝，也不能通过破解验证码的方式绕过。因此设计目标不是“完全不触发验证码”，
而是：

1. 尽可能降低触发风控的概率。
2. 触发风控后，不让采集任务直接失败。
3. 保持同一个浏览器会话不关闭。
4. 通过钉钉给负责人发送一次性链接。
5. 负责人远程接管当前浏览器页面，完成验证码或安全确认。
6. 验证完成后，browser-agent 检测登录态恢复，并继续执行原 playbook。

生产采集机会运行在 Windows 或 macOS。采集机可能在客户内网、NAT 或安全策略后面，
所以不应要求云端 Tally 直接访问采集机端口。

## 总体决策

采用“云端 Tally 中转 + browser-agent 主动出站连接 + 同会话人工接管”的架构。

- browser-agent 仍然拥有本机 Chrome、采集 profile、下载目录和 Playwright 执行权。
- browser-agent 主动连接云端 Tally，用于任务领取、心跳、状态上报，以及后续远程接管通道。
- 云端 Tally 负责创建人工验证会话，生成一次性钉钉链接，并把操作页面提供给负责人。
- 负责人打开的是云端 Tally 页面，不是采集机本地地址。
- 云端通过 browser-agent 的出站通道，把画面帧和输入事件转发到正在运行的浏览器会话。
- 第一版远程接管使用 Playwright 截图流 + 鼠标/键盘事件转发。
- 如果千牛滑块对 Playwright 级输入事件仍然敏感，再把同一套 handoff session 后端升级为
  Windows/macOS 的 OS 级远程桌面接管。

这套设计明确拒绝“采集机直连 URL”作为生产方案，因为它要求采集机暴露公网或内网可访问端口，
不适合云端 Tally 调用分布式采集机的部署形态。

## 第一层：降低触发风控概率

当前 runner 使用：

```python
playwright.chromium.launch_persistent_context(channel="chrome")
```

这确实打开的是本机 Google Chrome，不是 Playwright 自带 Chromium。但它仍然是 Playwright
直接 launch 出来的 Chrome，会带自动化控制通道和一组与普通用户手动启动不同的运行特征。

第一层改造目标是让浏览器运行方式更接近普通浏览器，同时保留自动采集能力：

1. browser-agent 自己启动本机 Google Chrome。
2. 使用采集专属 persistent profile。
3. Chrome 只监听本机 `127.0.0.1` 调试端口。
4. Playwright 通过 CDP attach 到这个 Chrome。
5. 保留 headed 模式，不使用 headless。
6. 保留每个采集 profile 独立的下载目录。
7. 每次采集先检查 `auth_check.logged_in_selector`。
8. 如果 profile 已有登录态，直接跳过 `login_if_needed`。
9. 如果没有登录态，再使用 UI 保存的凭证自动登录。
10. 登录输入继续使用慢速逐字输入。
11. 步骤之间和点击之前继续保留 1 到 3 秒左右的随机等待。

这不会消除所有自动化特征，也不能保证千牛永不触发滑块。但它能减少不必要的差异：

- 不再由 Playwright 直接创建完整浏览器进程。
- Chrome 以普通本机程序形式启动。
- profile 是长期持久化的采集 profile，能积累设备信任信息。
- CDP 只绑定本机，不暴露给公网。
- 采集流程仍然由 Playwright 控制，不影响 playbook 执行。

## 第二层：验证码兜底闭环

当千牛仍然触发滑块、短信验证码或安全验证时，新增“人工验证会话”。

触发条件：

- 页面出现滑块 / 拖动滑块 / 安全校验 / 手机验证 / 验证码等强风控标记。
- 登录后仍停留在登录域名或安全验证页。
- playbook 无法继续，但浏览器页面仍然可被人工处理。

处理流程：

1. browser-agent 检测到滑块、验证码或手机验证。
2. browser-agent 不关闭 Chrome，不销毁 Playwright context，不立即把 sync job 标记为失败。
3. browser-agent 创建或请求云端创建 `verification handoff session`。
4. sync job 进入 `waiting_human_verification` 状态。
5. 云端 Tally 通过现有钉钉通知能力给周行发送消息。
6. 钉钉消息包含一个短期有效、一次性使用的云端 Tally 链接。
7. 周行打开链接后，看到当前浏览器页面画面。
8. 周行可以点击、拖拽、输入，完成滑块或其他验证码。
9. browser-agent 持续检测登录态 selector 和风控标记。
10. 登录态恢复后，sync job 进入 `resuming` 状态。
11. browser-agent 从被阻塞的步骤继续执行原 playbook。
12. playbook 完成后，正常上传 records 和 capture files，并标记 sync job 成功。
13. 如果链接过期、无人处理、采集机离线或登录态没有恢复，最终标记为 `RISK_VERIFICATION` 失败。

关键约束：

- 人工处理的是同一个 Chrome 页面，不是重新打开一个浏览器。
- 人工验证完成后，原 playbook 继续跑，不重新领取任务。
- 验证期间凭证不暴露给钉钉链接或接管页面。
- 这个人工环节只处理验证码，不改变自动采集主路径。

## 远程接管实现

第一版使用 Playwright screenshot + 鼠标键盘事件转发。

原因：

- 不要求采集机额外部署 VNC/noVNC。
- 不要求采集机暴露公网端口。
- browser-agent 只需要主动连接云端。
- Windows 和 macOS 都能支持。
- 与现有 Playwright runner 集成成本最低。

第一版能力：

1. browser-agent 对当前 page 周期性截图。
2. 截图通过 browser-agent 的出站连接发送到云端。
3. 云端 Tally handoff 页面展示当前画面。
4. 用户在页面上的鼠标移动、点击、拖拽、键盘输入被发送回云端。
5. 云端把事件转发给对应 browser-agent。
6. browser-agent 在当前 Playwright page 上执行对应鼠标/键盘事件。
7. browser-agent 同时轮询登录态，发现验证通过后结束 handoff。

风险：

- 某些滑块可能识别 Playwright 级鼠标事件，导致人工拖动仍然失败。
- 截图流会有延迟，拖拽手感可能不如真实远程桌面。

升级路径：

如果 Playwright 级事件无法稳定通过千牛滑块，则保持云端 handoff session、钉钉链接、
状态机和审计模型不变，只替换 browser-agent 本地控制后端：

- Windows 采集机使用 OS 级远程桌面或原生输入注入。
- macOS 采集机使用系统辅助功能权限或远程桌面后端。
- 云端仍然只看到“画面帧 + 输入事件”的抽象接口。
- browser-agent 仍然通过出站连接和云端通信。

## 状态模型

为浏览器采集增加人工验证等待状态，避免把可人工恢复的风控直接当成终态失败。

状态：

- `running`：browser-agent 正在执行 playbook。
- `waiting_human_verification`：检测到风控，等待人工验证。
- `resuming`：人工验证完成，正在确认登录态并准备继续执行。
- `success`：playbook 完成并上传数据。
- `failed`：任务无法继续，或人工验证过期/取消/失败。

失败码：

- `RISK_VERIFICATION`：验证码无人处理、处理超时或登录态未恢复。
- `AUTH_EXPIRED`：登录凭证失效、登录页无法完成、或登录后仍未获得有效登录态。
- `PAGE_CHANGED`：页面结构变化导致 playbook 无法继续。
- `DATA_MISMATCH`：下载数据通过不了质量校验。
- `AGENT_OFFLINE`：采集机离线或失联。

## Handoff Session 数据

新增人工验证会话，绑定一个 sync job 和一个 browser-agent 运行中的浏览器会话。

字段：

- `handoff_session_id`
- `sync_job_id`
- `company_id`
- `data_source_id`
- `agent_id`
- `profile_key`
- `status`
- `reason`
- `created_at`
- `expires_at`
- `claimed_by_user_id`
- `claimed_at`
- `completed_at`
- `audit_events`

一次性链接只包含签名后的不透明 token，不包含：

- 商户登录账号或密码。
- 本机 profile 路径。
- Chrome CDP 端口。
- playbook JSON。
- 下载文件路径。

## 正常自动采集流程

1. 云端创建 browser sync job。
2. browser-agent 领取任务。
3. browser-agent 打开采集 profile 对应的 Chrome。
4. runner 检查 profile 是否已有登录态。
5. 有登录态则跳过登录步骤。
6. 无登录态则注入凭证并自动登录。
7. 登录成功后继续执行 playbook。
8. 下载并解析数据。
9. 通过质量校验后上传 records 和 capture files。
10. sync job 标记成功。

## 风控人工兜底流程

1. runner 检测到强风控标记。
2. runner 暂停当前步骤 deadline，并保持 Chrome 打开。
3. browser-agent 上报 `waiting_human_verification`。
4. 云端创建 handoff session。
5. 云端发送钉钉消息给周行。
6. 周行打开一次性链接并领取 session。
7. 云端页面展示当前浏览器截图流。
8. 周行操作页面，输入事件经云端转发给 browser-agent。
9. browser-agent 在同一个页面执行输入事件。
10. browser-agent 检测到登录态恢复。
11. runner 继续执行原 playbook。
12. 成功则正常完成；超时则 `RISK_VERIFICATION` 失败。

## 安全要求

- handoff 链接必须短期有效。
- handoff 链接必须一次性使用。
- handoff 页面必须要求 Tally 登录态，或至少完成钉钉身份校验。
- 一个 session 同一时间只能被一个用户控制。
- 所有领取、开始控制、结束控制、超时、取消、失败都要审计。
- 截图画面按敏感财务数据处理。
- 第一版禁用剪贴板能力。
- 第一版不允许通过 handoff 页面下载文件。
- 下载文件仍然通过现有 capture file 上传链路进入系统。
- 云端不通过 handoff 通道接收商户明文密码。
- Chrome CDP 端口只监听 `127.0.0.1`。
- 采集机不暴露公网端口。

## 组件边界

### browser-agent

负责：

- 启动本机 Chrome。
- 管理采集 profile 和下载目录。
- 通过 CDP attach Chrome。
- 执行 playbook。
- 检测登录态和风控标记。
- 风控时保持页面不关闭。
- 生成截图帧。
- 接收并执行远程输入事件。
- 登录态恢复后继续 playbook。
- 超时或失败时上报明确失败码。

### 云端 Tally / finance-mcp

负责：

- 持久化 handoff session。
- 生成和校验一次性 token。
- 维护 sync job 的 `waiting_human_verification` / `resuming` 状态。
- 通过现有钉钉通知适配器发送消息。
- 代理 handoff 页面和 browser-agent 之间的事件通道。
- 把 handoff 状态暴露给浏览器采集列表和 sync job 详情。

### finance-web

负责：

- 提供 handoff 页面。
- 展示 session 状态、剩余时间、错误信息。
- 展示 browser-agent 传来的截图流。
- 捕获鼠标、拖拽、键盘输入。
- 把输入事件发送给云端。
- 显示验证完成、过期、失败或采集机离线状态。

## 错误处理

- browser-agent 在 handoff 期间离线：session 标记 `agent_offline`，sync job 保持等待，
  最终由 runner timeout 决定失败。
- 一次性链接过期：session 标记 `expired`，sync job 失败为 `RISK_VERIFICATION`。
- 用户完成操作但登录态未恢复：继续等待直到超时，最终 `RISK_VERIFICATION`。
- 登录态恢复后页面结构变化：按原 playbook 映射为 `PAGE_CHANGED`。
- 登录后仍回到登录页：`AUTH_EXPIRED`。
- 数据下载后校验不一致：`DATA_MISMATCH`。
- 截图可用但事件转发不可用：handoff 页面显示“无法控制”，任务继续等待直到取消或超时。

## 测试计划

单元测试：

- Chrome 启动配置只绑定 `127.0.0.1`。
- runner 检测到风控时返回等待 handoff，而不是立即终态失败。
- handoff token payload 不包含凭证、profile 路径或 CDP 端口。
- handoff 过期会映射为 `RISK_VERIFICATION`。
- 同一个 handoff session 不能被两个用户同时控制。
- 登录态恢复后 runner 能继续执行下一步。

集成测试：

- 模拟风险页面后创建 handoff session，并只发送一次钉钉消息。
- 模拟用户完成验证后，runner 继续执行 playbook。
- browser-agent 断连时，云端能看到 session 离线状态。
- 重复打开一次性链接时，第二个打开者不能获得控制权。
- sync job 状态能从 `running` 到 `waiting_human_verification` 到 `resuming` 到 `success`。

人工验证：

- macOS 采集机上，千牛风险页面能通过 Tally handoff 页面看到。
- Windows 采集机上，千牛风险页面能通过 Tally handoff 页面看到。
- Playwright 截图 + 事件转发能否完成真实千牛滑块。
- 如果不能完成，切换 OS 级远程桌面后端前，云端 session 模型不需要重做。

## 分阶段落地

### 阶段 1：降低风控概率

- browser-agent 改为自己启动本机 Chrome。
- Chrome 使用采集专属 persistent profile。
- Chrome CDP 只监听 `127.0.0.1`。
- Playwright 通过 CDP attach。
- 保留慢速输入、随机等待和登录态优先检查。
- 保留现有下载、解析和质量校验逻辑。

### 阶段 2：人工验证状态

- 增加 `waiting_human_verification` / `resuming` 状态。
- 检测到风控时不立即终态失败。
- browser-agent 保持 Chrome 页面打开。
- 超时后仍然按 `RISK_VERIFICATION` 失败。

### 阶段 3：云端 handoff session

- 新增 handoff session 持久化。
- 新增一次性 token。
- 新增钉钉消息内容和链接。
- 新增云端到 browser-agent 的出站事件通道。
- sync job 详情显示 handoff 状态。

### 阶段 4：handoff 页面

- finance-web 新增 handoff 页面。
- 页面显示当前浏览器截图流。
- 页面捕获点击、拖拽、键盘输入。
- 云端转发输入事件给 browser-agent。
- browser-agent 执行事件并继续检测登录态。

### 阶段 5：生产验证

- macOS 采集机验证。
- Windows 采集机验证。
- 真实千牛账号验证自动登录、风控等待、人工兜底和继续 playbook。
- 验证登录态已存在时不重复登录。
- 验证无人处理时产生可行动的 `RISK_VERIFICATION` 告警。

## 重要约束

第一版远程接管先做 Playwright screenshot + 鼠标键盘事件转发，因为它不要求采集机额外部署
VNC/noVNC，也不要求采集机暴露公网端口。

如果真实千牛滑块仍然因为 Playwright 级输入事件而失败，则不推翻云端中转、钉钉链接、
handoff session、状态机和审计设计，只替换 browser-agent 本地控制后端为 Windows/macOS
的 OS 级远程桌面接管。

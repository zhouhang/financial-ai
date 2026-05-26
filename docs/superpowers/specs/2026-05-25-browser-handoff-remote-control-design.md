# 浏览器采集 Handoff 远程接管设计

日期：2026-05-25

## 背景

现有阶段 3a 已完成 handoff session 的基本创建、token、`risk_waiting` 上报、按对账任务责任人定向通知，以及一个后端 HTML 提示页。剩余缺口是：

- 3a 的 session 状态、过期、审计、控制者语义不完整。
- 3b 的云端到 browser-agent 截图/输入双工通道未实现。
- 4 的 finance-web 远程接管页未实现。

本设计补齐 3a，并实现 3b/4 的第一版 Playwright 远控。若 Playwright 级输入对千牛滑块效果不好，后续优先切 Windows OS 级控制后端，云端协议和页面不重做。

## 用户确认的关键决策

- 第一版做完整 Playwright 远控：截图流 + 点击 + 拖拽 + 键盘输入。
- Handoff 页面只靠 token，不要求 Tally 登录或钉钉/飞书二次确认。
- token 有效期内可重复打开，最新打开页面成为当前控制者。
- 用户点击“我已完成验证”后触发 agent 立即复检；没点也可继续自动检测。
- 截图帧率自适应：默认约 1 FPS，拖拽/交互时临时升到约 5 FPS。
- 完整页面放在 finance-web `/handoff?t=...`。
- 删除 `/p/handoff` 轻量提示页；通知直接发 `/handoff?t=...`。
- 审计只记录元数据事件，不保存截图帧、验证码内容或键盘输入内容。
- runner、session、token 默认等待时长统一为 15 分钟。
- frame/input 不落库，只在 data-agent 内存中转。
- agent 离线时页面显示等待，session 继续等到 15 分钟超时。
- 如果 OS 级后端要做，优先 Windows，macOS 不进近期范围。

## 范围

### 本次实现范围

1. 补齐 handoff session 状态闭环、短有效期 capability token 语义、过期和元数据审计。
2. 新增 data-agent handoff WebSocket，连接 finance-web 与 browser-agent。
3. 新增 browser-agent 远程控制后端接口和 Playwright 实现。
4. 新增 finance-web 移动端优先的 `/handoff?t=...` 远程接管页。
5. 通知链接改为 `/handoff?t=...`，移除 `/p/handoff`。
6. 为 Windows OS 级后端保留接口和切换点，先不实现 Windows OS 后端。

### 非本次范围

- 不实现钉钉/企微/飞书身份校验。
- 不保存截图帧或输入事件用于回放。
- 不实现剪贴板、文件下载、上传、复制凭证。
- 不实现 macOS OS 级远控后端。
- 不承诺 Playwright 后端一定通过所有滑块；只做真机验证并保留 Windows OS 升级路径。

## 3a 补齐设计：状态、过期、审计

### Token 语义

现有 token 改为“15 分钟短有效期 capability token”，不再称为一次性消费 token。原因是当前产品决策允许 token 有效期内重复打开，且最新打开页面接管控制权。

token 只编码：

- `handoff_session_id`
- `company_id`
- `iat`
- `exp`
- `jti`

token 不编码商户凭证、profile 路径、CDP 端口、playbook、下载目录。

### Session 状态

Handoff session 使用以下状态：

- `pending`：session 已创建，等待责任人打开页面。
- `active`：已有 web 控制者连接，agent 可控。
- `waiting_agent`：页面已打开，但 browser-agent 不在线或暂不可控。
- `resuming`：用户点“我已完成验证”，agent 正在复检登录态/风控状态。
- `completed`：agent 复检通过，原 playbook 继续执行。
- `expired`：15 分钟超时，未完成验证。
- `failed`：agent 明确报告无法继续。

`waiting_human_verification` 和 `resuming` 仍是 sync job 状态；handoff session 自己使用上面的页面/控制状态。

### 控制者规则

- finance-web 打开 `/handoff?t=...` 后连接 data-agent `/handoff/ws?t=...`。
- data-agent 校验 token 未过期，创建新的 `controller_id`。
- 最新连接的 `controller_id` 成为当前控制者。
- 旧控制者收到 `controller_revoked`，页面进入只读提示。
- token-only 页面不提供取消任务、删除数据、下载文件等高权限操作。

### 审计事件

只记录元数据事件到 `browser_handoff_sessions.audit_events`，不记录截图和输入内容。

事件类型：

- `session_created`
- `page_opened`
- `controller_changed`
- `agent_connected`
- `agent_offline`
- `stream_started`
- `stream_stopped`
- `resume_requested`
- `resuming`
- `completed`
- `expired`
- `failed`

每条事件至少包含：

- `event_type`
- `ts`
- `handoff_session_id`
- `controller_id`（如有）
- `agent_id`（如有）
- `reason`（如有）

### 过期策略

- create session 时写 `expires_at = now + 15min`。
- token `exp` 与 session `expires_at` 对齐。
- browser-agent 风控等待默认调成 15 分钟。
- data-agent 在 web/agent 事件处理前检查过期，并调用 finance-mcp 的过期工具更新持久状态。
- finance-mcp 负责持久化 `expired` 和最终 sync job 失败结果；data-agent 负责在 WS/agent 事件入口触发该处理。

## 3b 双工通道设计

### 连接关系

- browser-agent 保持现有 `/browser-agent` WebSocket 出站连接。
- finance-web 新增连接 data-agent `/handoff/ws?t=...`。
- data-agent 维护两个内存注册表：
  - `agent_id -> BrowserAgentConnection`
  - `handoff_session_id -> HandoffControllerConnection`

data-agent 是唯一中转方。finance-web 不直连 browser-agent，browser-agent 不暴露本地端口。

### 启动流程

1. browser-agent 检测风控并上报 `risk_waiting`。
2. data-agent 创建 handoff session，通知责任人。
3. 责任人打开 `/handoff?t=...`。
4. finance-web 连接 `/handoff/ws?t=...`。
5. data-agent 校验 token，加载 session，生成 `controller_id`。
6. 最新 controller 接管，旧 controller 被 revoke。
7. data-agent 根据 session 的 `agent_id` 查找 browser-agent 连接。
8. agent 在线时，data-agent 下发 `handoff_start`。
9. browser-agent 开始对当前阻塞 page 截图并上报 frame。
10. data-agent 把 frame 转给当前 controller。

### Browser-Agent 下行事件

data-agent 发给 browser-agent：

```json
{
  "type": "event",
  "event": "handoff_start",
  "handoff_session_id": "...",
  "controller_id": "...",
  "sync_job_id": "...",
  "frame_profile": {"idle_fps": 1, "interactive_fps": 5}
}
```

其他事件：

- `handoff_stop`
- `handoff_input`
- `handoff_frame_rate`
- `handoff_resume_check`

### 截图帧协议

browser-agent 上行：

```json
{
  "type": "handoff_frame",
  "handoff_session_id": "...",
  "controller_id": "...",
  "frame_id": 42,
  "mime": "image/jpeg",
  "width": 1440,
  "height": 900,
  "data": "<base64>",
  "ts": 123456789
}
```

数据策略：

- 不落库。
- data-agent 可在内存保存每个 session 最新一帧，用于页面重连快速显示。
- 页面断开后 agent 停止截图流。

### 输入事件协议

finance-web 发给 data-agent，再转发 browser-agent：

```json
{
  "type": "handoff_input",
  "handoff_session_id": "...",
  "controller_id": "...",
  "event": {
    "kind": "mouse_down",
    "x": 0.42,
    "y": 0.58,
    "button": "left"
  }
}
```

支持事件：

- `mouse_down`
- `mouse_move`
- `mouse_up`
- `click`
- `wheel`
- `key_down`
- `key_up`
- `text`

坐标使用 `0..1` 归一化比例，browser-agent 映射到当前截图/viewport。这样前端缩放、手机横竖屏切换不会改变协议。

### 自适应帧率

- 默认 1 FPS。
- `mouse_down`、拖拽、连续输入时提升到 5 FPS。
- `mouse_up` 或交互停止 2 秒后降回 1 FPS。
- 页面隐藏或断开时发送 `handoff_stop`。

### 验证完成与恢复

页面提供“我已完成验证”按钮：

1. web 发 `resume_requested`。
2. data-agent 写审计并把 `handoff_resume_check` 转给 agent。
3. browser-agent 立即复检：
   - 风控标记消失；
   - 登录态 selector 成立，或 playbook 可继续。
4. 通过：agent 上报 `handoff_completed`，runner 进入 `resuming` 并继续原 playbook。
5. 未通过：agent 上报 `handoff_still_blocked`，页面继续保持可操作。

## Browser-Agent 远控后端设计

### 统一接口

browser-agent 内部定义：

```python
class RemoteControlBackend:
    def start_stream(self, session): ...
    def stop_stream(self, session): ...
    def capture_frame(self): ...
    def apply_input_event(self, event): ...
    def check_resume_ready(self): ...
```

### PlaywrightControlBackend

第一版实现：

- `page.screenshot()` 生成 JPEG/WebP frame。
- `page.mouse` 执行点击、拖拽、滚轮。
- `page.keyboard` 执行输入、按键。
- 复用现有风控/登录态检测判断 `check_resume_ready`。

### Windows OS 后端预案

如果 Playwright 拖滑块效果不好，下一阶段实现 `WindowsOsControlBackend`：

- 定位对应 Chrome 窗口句柄。
- 截图 Chrome 窗口或屏幕区域。
- 使用 Windows `SendInput` 注入鼠标、键盘、拖拽、滚轮。
- 处理 DPI 缩放、窗口坐标、浏览器内容区偏移。
- 启动自检：是否 Windows、能否定位 Chrome、能否截图、能否注入输入。
- 环境变量切换：
  - `HANDOFF_CONTROL_BACKEND=playwright`
  - `HANDOFF_CONTROL_BACKEND=windows_os`

macOS OS 后端不进近期实现范围。

## 阶段4：Finance-Web 页面设计

### 入口

finance-web 新增 `/handoff?t=...` React 页面。通知直接发：

```text
https://<finance-web>/handoff?t=<token>
```

删除 data-agent `/p/handoff` HTML 页面和相关测试。data-agent 只提供 API/WS。

### 移动端优先

主要场景是责任人从钉钉、企微、飞书手机内置浏览器打开链接，因此页面 mobile-first：

- 竖屏默认可用。
- 顶部显示店铺、剩余时间、连接状态。
- 主体远程浏览器画面尽量占满屏幕宽度。
- 底部或浮层放核心操作：
  - “我已完成验证”
  - “重连画面”
  - 当前状态提示。
- 横屏时切换为更适合拖拽的布局：画面更大，按钮靠侧边。
- PC 页面只是响应式 fallback。

### 页面状态

- `connecting`：正在连接远程浏览器。
- `active`：可操作。
- `waiting_agent`：采集机离线或未连接，等待重连。
- `revoked`：此页面已被新的打开页面接管。
- `resuming`：已点完成验证，agent 正在复检。
- `still_blocked`：复检未通过，请继续操作。
- `completed`：验证通过，采集继续。
- `expired`：链接过期，不能再操作。

### 输入捕获

远程画面区域捕获：

- tap/click
- touch drag / mouse drag
- wheel/scroll
- keyboard text input
- Enter、Backspace 等常用按键

页面要避免浏览器默认手势干扰：

- 远程画面区域禁用文本选择。
- 拖拽时阻止页面滚动。
- 需要输入文字时提供明确的输入模式，转成 `text` 事件发送给 agent。

## 错误处理

- token 无效或过期：页面显示失效，不连接控制 WS。
- agent 离线：页面显示 `waiting_agent`，session 继续等到 15 分钟超时。
- 控制权被新页面接管：旧页面显示 `revoked`，停止发送输入。
- frame 中断：页面显示重连状态，允许重新连接。
- input 转发失败：页面显示短错误提示，不结束 session。
- resume 检查未通过：显示 `still_blocked`，继续远控。
- session 过期：停止截图和输入，sync job 最终 `RISK_VERIFICATION`。

## 测试与验收

### 单元与集成测试

- token 有效时 `/handoff/ws?t=...` 可连接 session。
- token 无效/过期时拒绝连接。
- 最新连接者接管，旧连接收到 `controller_revoked`。
- agent 在线时收到 `handoff_start`。
- agent 离线时页面收到 `waiting_agent`。
- browser-agent 上报 frame，web controller 能收到。
- web 发送 click/text/drag，browser-agent backend 被调用。
- “我已完成验证”触发 resume check。
- completed/still_blocked 状态可返回到 web。
- expired 后 session 不再可控。
- audit 只记录元数据，不包含截图 base64 或输入 text。

### 人工真机验收

- 手机钉钉打开 `/handoff?t=...` 可看到页面。
- 手机企微打开 `/handoff?t=...` 可看到页面。
- 手机飞书打开 `/handoff?t=...` 可看到页面。
- 短信验证码输入可完成。
- 图片验证码点击/输入可完成。
- 普通安全确认按钮可完成。
- 千牛滑块用 Playwright 拖拽实测。
- 如果滑块失败，下一阶段切 Windows OS 后端，不改云端协议和 finance-web 页面。

## 实施切片

1. **3a 状态闭环补齐**
   - session 状态、审计、过期、token 语义、通知链接改 `/handoff`、删除 `/p/handoff`。
2. **3b data-agent/browser-agent 双工通道**
   - agent 连接注册、web handoff WS、frame/input/resume 协议、Playwright backend。
3. **4 finance-web 移动端远控页**
   - `/handoff?t=...` 页面、移动端画面、输入捕获、状态展示。
4. **真机验证与 Windows OS 预案**
   - 手机内置浏览器验证、千牛滑块验证、记录是否需要 `WindowsOsControlBackend`。

## 风险

- Playwright 级拖拽可能无法通过部分滑块。缓解：保留 Windows OS 后端切换接口。
- 手机内置浏览器对横屏、键盘、touch 事件行为不同。缓解：移动端优先测试钉钉/企微/飞书。
- token-only 链接泄露会暴露当前 handoff 控制能力。缓解：15 分钟短有效期、不显示凭证/文件、不提供取消/下载能力、记录元数据审计。
- 截图流可能含敏感页面。缓解：不落库、不回放、断开即停止。

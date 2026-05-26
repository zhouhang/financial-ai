# 飞书 / 企微 CLI 能力探测结论(Task 1 GATE)

日期:2026-05-22 · 机器:macOS Darwin x86_64 · Node v23.11 / npm 10.9 / Python 3.12 · **无 Go、无 Rust/cargo**

## 结论 / GATE

| CLI | 结论 | 说明 |
|---|---|---|
| **飞书 `lark-cli`** | ✅ **可用** | npm 预编译二进制(不需 Go);非交互配置;文件级加密凭证存 `$HOME` 下(**可按公司隔离**);`--as bot` 应用身份**无头**发送(无 device flow)。Task 5 可做。 |
| **企微 `wecom-pro`** | ❌ **被安装阻塞,需用户决策** | npm 平台二进制包 `@liangdi/wecom-pro-darwin-x64` **未发布(registry 404)**,装出来是空壳;crates.io 有(0.1.7)但需先装 Rust 工具链(本机无)。未能运行,发送命令/隔离/是否为推送均未实测。 |

---

## 飞书 lark-cli(实测)

- **安装**:`npm install -g @larksuite/cli` → `/usr/local/bin/lark-cli` v1.0.38。postinstall(`scripts/install.js`)下载预编译二进制,**不需要 Go**。`os: darwin/linux/win32, cpu: x64/arm64`。
- **非交互配置**(关键):
  ```bash
  echo "<app_secret>" | env HOME=<company_dir> lark-cli config init \
      --app-id <app_id> --app-secret-stdin --brand feishu
  ```
  secret 走 stdin(不进进程列表);exit 0,**不弹浏览器**。输出里 secret 自动掩码为 `"appSecret": "****"`(利于脱敏)。
- **凭证存储与隔离**(关键,推翻了文档"只存系统钥匙串"的说法):
  - `config.json` → `$HOME/.lark-cli/config.json`
  - 加密 secret + 主密钥 → `$HOME/Library/Application Support/lark-cli/appsecret_<appid>.enc` + `master.key.file`
  - **是文件级加密存储,不是系统钥匙串** → 设 `HOME=<per-company dir>` 即可**按公司隔离**。实测在 `/tmp/larktestA` 下 init,全部文件落在该目录内。
- **无头应用身份发送**:`--as bot` 用 tenant_access_token。实测假凭证发送时直接走 TAT 接口报 `[10003] invalid param`(说明**没有**弹 device flow 授权),证明无头可行。
- **发送命令(推荐用 `api` 通用命令,JSON 信封确定)**:
  ```bash
  env HOME=<company_dir> lark-cli api POST /open-apis/im/v1/messages \
      --params '{"receive_id_type":"chat_id"}' \
      --data '{"receive_id":"<oc_xxx>","msg_type":"text","content":"{\"text\":\"<内容>\"}"}' \
      --as bot --format json
  ```
  - **成功判定字段:`payload["ok"] === true`**(lark-cli 自有信封,**不是** feishu 的 `code`)。失败时 `payload["error"]["message"]` 有错误文案。
  - `--format json` 在 `api` 命令上有效;**在 `im +messages-send` 子命令上非法**(`Error: unknown flag: --format`)。所以**适配器走 `api POST` 而非 `+messages-send`**(spec 基线写的 `+messages-send --format json` 需改)。
  - 备选:`lark-cli im +messages-send --chat-id <oc> --text <内容> --as bot`(参数 `--chat-id`/`--user-id` 互斥、`--text`/`--markdown`/`--content`、`--idempotency-key`),但输出格式未确定,不如 `api POST` 稳。
- **每公司 provision 流程**:对每个公司用其 `app_id`/`app_secret` 在 `HOME=<state>/feishu/<company_id>` 下跑一次 `config init`,之后发送复用该目录。

### 对 Task 5(飞书适配器)的修正项
1. `_run` 改走 `api POST /open-apis/im/v1/messages`(带 `--params`/`--data`/`--as bot`/`--format json`),**不用** `+messages-send`。
2. 成功判定:`result.payload.get("ok") is True`(不是 `code==0`)。
3. 错误信息:`result.payload["error"]["message"]`。
4. 隔离 helper 的 `HOME` 注入对 lark-cli 有效(已实测)。
5. 凭证:适配器需先确保该公司已 `config init`(惰性 provision),secret 走 stdin。

---

## 企微 wecom-pro(被阻塞,未实测)

- **npm 路径坏了**:`npm install -g @liangdi/wecom-pro` 只装了启动器 `bin/wecom.js`,它 `require.resolve` 平台包 `@liangdi/wecom-pro-darwin-x64`,而该包**在 npm registry 上 404**(四个平台包 `*-darwin-arm64/-darwin-x64/-linux-x64/-win32-x64` 均为 optionalDependencies,作者未发布)。运行报 `Error: cannot find @liangdi/wecom-pro binary`。
- **crates.io 有**:`wecom-pro` 0.1.7,可 `cargo install wecom-pro`,但**本机无 Rust/cargo**。
- 因此**未能运行**,以下均**未实测**(据 README):`msg send_message '{json}'`、`init --method manual --bot-id .. --secret ..`、`-o json`、`contact get_userlist`。
- 额外存疑:README 的 `msg send_message`(`chat_type`/`chatid`)看着更像**会话存档(消息记录)**接口族(同组还有 `get_message`/`get_msg_chat_list`/`get_msg_media`),**是否真能"主动推送"消息未确认**。

### 需用户决策(企微路线)
- **(a) 装 Rust 工具链** → `cargo install wecom-pro`,我再实测 + 做 Task 4。代价:本机装 rustup/cargo(较重的环境改动)。
- **(b) 企微改走 HTTP API**(群机器人 webhook `cgi-bin/webhook/send?key=`,或应用消息 `gettoken`+`message/send`)。无需任何工具链,天然多租户(每公司 key/secret),且明确是"主动推送"。**推荐**。
- **(c) 等作者发布 npm 平台二进制**(不可控,不建议等)。

> 飞书侧(lark-cli)已验证可用,Task 5 不受企微决策影响,可先行。

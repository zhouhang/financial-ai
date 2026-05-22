# 飞书 / 企微 CLI 消息推送渠道接入 — 设计文档

> 状态:已确认设计,待写实现 plan。
> 日期:2026-05-22

## Goal

让运行计划(`execution_run_plan`)的消息推送除钉钉外,新增**飞书**与**企业微信**两个渠道,二者均通过各自的 CLI(飞书 `larksuite/cli`,企微 `Liangdi/wecom-pro`)发送,沿用现有 `NotificationAdapter` 抽象与"运行计划关联 `channel_config_id`"的既有管道。凭证按公司隔离。

## 背景与现状(大半管道已就位)

系统本就是按多 provider 设计的,本次只补两个适配器与配套:

- `NotificationProvider` 枚举已含 `dingtalk_dws` / `feishu` / `wechat_work`(`services/notifications/models.py`)。
- `company_channel_configs` 表 + `repository.py` 的 CRUD(`load_company_channel_config`、`load_company_channel_config_by_id`、`list/save/delete`)均 **provider 无关**,字段:`provider`、`channel_code`、`name`、`client_id`、`client_secret`、`robot_code`、`is_default`、`is_enabled`、`extra`。
- 运行计划已存 `channel_config_id`;recon 自动运行(`graphs/recon/auto_run_service.py`、`auto_scheme_run/nodes.py`)按 `channel_config.provider` **动态**建适配器:`get_notification_adapter(provider=channel_config.provider, channel_config=channel_config)`,再调 `send_reminder` / `send_bot_message`。
- 前端运行计划渠道选择器已存在且 provider 无关(`finance-web/src/components/recon/ReconAutoTaskConfigs.tsx`:拉 `/api/collaboration-channels`、提交 `channel_config_id`);"协作通道"设置卡三家齐全(`collaborationChannelConfig.ts`)。
- 钉钉适配器 `DingTalkDwsAdapter`(`dingtalk_dws.py`)是范式:shell 调 `dws` CLI,凭证 **per-call 通过子进程 env 注入**(`DWS_CLIENT_ID` / `DWS_CLIENT_SECRET`),`robot_code` 走 `--robot-code` flag。

**唯一缺口**:`get_notification_adapter` 遇 `feishu` / `wechat_work` 直接 `raise ValueError`(无适配器实现)。

> 注:存在两套适配器解析路径——`__init__.get_notification_adapter`(recon 实际使用)与 `service.py` 的 `NotificationAdapterRegistry`(另一套门面,未被 recon 使用)。本次顺手统一,避免并存。

## Scope

**In scope**
- 新增 `FeishuLarkCliAdapter`、`WecomProCliAdapter` 两个适配器(仅消息推送能力)。
- 工厂注册两个 provider;统一 `service.py` 与 `__init__` 两套解析路径。
- config.py 新增 CLI 相关配置项。
- 按公司隔离的 CLI 配置目录机制。
- 单元测试(mock CLI executor)。
- 实现首步:CLI 能力探测(见"风险与待验证")。

**Out of scope**
- 真机发送验收(用户后续提供真实凭证与目标群自测)。
- 待办(todo)能力:企微无原生待办,飞书 Tasks API 本次不做。
- 飞书/企微的查人(按姓名/手机号搜索)定向催办:本次 `resolve_user` 仅直传 user_id。
- 前端新增字段/页面:渠道选择器与三家设置卡已存在,预期零或极少改动(仅验证飞书/企微渠道可保存并被选中)。
- Excel 批量、其它通知场景。

## 架构

### 1. 核心隔离原语:per-company 配置目录 + 子进程 env 注入

钉钉靠 per-call env 注入凭证实现多租户。两个新 CLI 是**文件型配置**(各自把凭证落盘),因此隔离改为"**每公司独立配置目录**":

- 新增配置 `NOTIFY_CLI_STATE_DIR`(默认 `~/.local/state/tally-notify`)。
- 适配器每次调用 CLI 前,计算 `company_dir = <NOTIFY_CLI_STATE_DIR>/<provider>/<company_id>`,通过子进程 env 注入(`HOME` 和/或 `XDG_CONFIG_HOME` 指向该目录),令每家公司的 CLI 凭证/配置落在各自目录,互不串扰。
- 首次惰性用 DB 凭证为该公司在其目录内 provision(如 `wecom-pro init --method manual --bot-id <id> --secret <secret>`);已存在则跳过。
- 该机制集中在一个 helper(如 `_company_env(company_id, channel_config)`),两个适配器复用。

> ⚠️ lark-cli 凭证存系统钥匙串(macOS Keychain / Linux Secret Service),`HOME`/`XDG` 未必能隔离钥匙串。该机制对 wecom-pro 成立;对 lark-cli 是否成立**取决于能力探测结果**(见风险段)。

### 2. 两个适配器(仅消息推送)

均位于 `finance-agents/data-agent/services/notifications/`,继承 `NotificationAdapter`,复用 `SubprocessCLIExecutor`,解析 CLI 的 JSON 输出。

实现的方法:
- `send_bot_message(content, to_user_id, content_type, title, ...)` —— 核心。目标为 channel_config 配置的群 chat_id(或 `to_user_id` 直传)。
- `send_reminder(...)` —— 降级为"纯发消息"(不创建 todo),返回 `ReminderResult`(`bot_result` 有值,`todo_result` 标记不支持)。
- `resolve_user(user_id=...)` —— 直传 user_id(仿 dws 的 direct_user_id 分支);传 mobile/keyword 时返回"该 provider 暂不支持查人"。

返回"不支持"而非崩溃的方法:`create_todo` / `get_todo` / `list_todos` / `update_todo` / `complete_todo` / `sync_todo_status` —— 统一返回 `success=False, code="unsupported", message="<provider> 暂不支持该能力"`。

**CLI 命令(以探测结果为准,以下为文档基线)**
- 飞书 `lark-cli`:
  - 发消息:`lark-cli im +messages-send --chat-id <chat_id> --text <content> --as bot --format json`
  - 或通用:`lark-cli api POST /open-apis/im/v1/messages --params '{"receive_id_type":"chat_id"}' --data '{"receive_id":"<chat>","msg_type":"text","content":"{\"text\":\"...\"}"}' --format json`
- 企微 `wecom-pro`:
  - 发消息:`wecom-pro msg --bot-id <id> send_message '{"chat_type":1,"chatid":"<chat>","msgtype":"text","text":{"content":"<content>"}}' -o json`
  - provision:`wecom-pro init --method manual --bot-id <id> --secret <secret> -o json`

### 3. 工厂注册与统一

- `__init__.get_notification_adapter`:新增
  - `provider == NotificationProvider.FEISHU.value` → `FeishuLarkCliAdapter(...)`
  - `provider == NotificationProvider.WECHAT_WORK.value` → `WecomProCliAdapter(...)`
  - 两者从 `resolved_channel_config` 取 per-company 凭证与目标 chat。
- `service.py` 的 `create_default_registry()` 同步注册三家,使两套解析路径一致(消除"recon 用 __init__、门面用 registry"的分裂)。

### 4. 配置(config.py,仿钉钉)

```
FEISHU_LARK_ENABLED   (默认 True)
FEISHU_LARK_BIN       (默认 "lark-cli")
WECOM_PRO_ENABLED     (默认 True)
WECOM_PRO_BIN         (默认 "wecom-pro")
NOTIFY_CLI_STATE_DIR  (默认 "~/.local/state/tally-notify")
NOTIFICATION_CLI_TIMEOUT_SECONDS  (已存在,复用)
```
`company_channel_configs` 字段映射:
- 飞书:`client_id`=App ID,`client_secret`=App Secret,`robot_code`=目标 chat_id(oc_xxx),`extra` 备用。
- 企微:`client_id`=Corp ID/Agent ID,`client_secret`=Secret,`robot_code`=bot-id/目标 chatid,`extra` 备用。

### 5. 数据流

运行计划创建(`ReconAutoTaskConfigs.tsx` 选渠道 → `channel_config_id`)→ 存入 `execution_run_plan` → recon 自动运行 `auto_run_service.py` 用 `channel_config_id` `load_company_channel_config_by_id` → `get_notification_adapter(provider, channel_config)` → 新适配器 → 注入 per-company env → shell 调 CLI → 解析 JSON → 映射为 `BotMessageResult`/`ReminderResult`。

### 6. 错误处理(照搬 dws 适配器范式)

- CLI 未安装:`SubprocessCLIExecutor` 返回 exit_code=127 → 适配器映射为 `code="missing_cli"`,message "未安装/未配置 飞书(企微)CLI"。
- 未配置(provider disabled / 缺凭证 / 缺目标 chat):`_ensure_ready()` 前置校验,返回 `code="invalid_input"` / `code="missing_*"`。
- 超时:exit_code=124,`timed_out=True`。
- 非零退出:`_build_cli_error_message(prefix, result)` 拼接 stderr/payload。
- JSON 解析失败:`_parse_payload` 兜底为 `{}`,据 exit code 判定成功/失败。

## Testing

- `tests/.../test_feishu_lark_adapter.py`、`test_wecom_pro_adapter.py`:
  - mock `SubprocessCLIExecutor`,断言**拼出的 CLI 参数列表**正确(含 per-company env、目标 chat、JSON payload 结构)。
  - 断言 JSON 输出 → `BotMessageResult`/`ReminderResult` 映射(成功路径)。
  - 失败路径:exit 127(未装)、非零退出(CLI 报错)、超时、JSON 不可解析。
  - 不支持的方法返回 `code="unsupported"`。
- `test_get_notification_adapter` 增加 feishu/wechat_work 分支断言(返回对应适配器类型;disabled 时的行为)。
- 不连真实 CLI / 网络(真机验收后续)。

## 安全

- `client_secret` 等凭证沿用现有 `company_channel_configs` 的密文存储(KMS),明文绝不进日志、transcript、LLM 上下文。
- per-company 配置目录写入的凭证文件,权限收紧(0700 目录)。
- CLI stderr/stdout 入库或日志前需脱敏(避免回显 secret)。

## 风险与待验证(写进实现首步)

1. **CLI 能力探测(实现 Task 1,先于写适配器)**:两个 CLI 文档对以下点都不完整,**必须装上实测 `--help` 与 dry-run 确认真实行为后再写适配器**,而非照文档猜:
   - 非交互 / 无头 provision 与发送(尤其飞书应用身份 `--as bot` 是否真能不弹授权)。
   - 通过 env(`HOME`/`XDG_CONFIG_HOME`)或参数覆盖凭证存储位置,实现按公司隔离。
   - 发送命令确切参数、JSON 输出确切结构(字段名),用于结果映射。
2. **lark-cli 隔离风险(明示)**:若实测确认 lark-cli 凭证仅落系统钥匙串、`HOME`/`XDG` 无法隔离,则飞书多公司隔离在无头 Linux 上不可达。届时的退路(择一,实现时回报用户决策):(a) 飞书改走 HTTP API(per-company app_id/secret 换 tenant_access_token,天然多租户);(b) 接受飞书单租户。**该退路不阻塞企微**。
3. CLI 为外部工具、版本可能漂移输出格式 → 固定/记录所用版本;适配器对未知字段容错。
4. lark-cli 依赖 Node + Go1.23 + Python3,wecom-pro 为 Rust/npm;部署文档需列明安装步骤。

## 验收标准(本轮代码层面)

- `get_notification_adapter("feishu"/"wechat_work", channel_config=...)` 返回对应适配器,不再 ValueError。
- 两个适配器单测全绿(成功/失败/未装/不支持路径)。
- 配置项就位;per-company env 隔离 helper 有单测。
- CLI 能力探测结论记录在案;lark-cli 隔离风险有明确结论与(必要时)退路建议。
- 真机发送、前端联调留待后续。

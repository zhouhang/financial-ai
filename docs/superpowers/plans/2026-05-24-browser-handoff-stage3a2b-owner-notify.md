# 阶段3a-2b:handoff 通知按对账任务责任人(owner) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 3a-2 的 handoff 通知从"发公司默认通道(群播)"改为**按对账任务责任人(owner)定向通知**;**无对账任务的自动采集(无 owner)→ 不发通知**(仅建 session + 等待 + 超时,符合用户确认的策略)。

**Architecture:** 对账任务触发浏览器采集时,把任务的 `channel_config_id` + `owner`(`run_plan.owner_mapping_json.default_owner` 的 name/identifier)塞进采集 `params` → 落到 sync_job 的 `request_payload`。finance-mcp `browser_handoff_session_create` 读 sync_job 的 request_payload 取出 channel_config_id + owner,存到 handoff session 并回传给 data-agent。data-agent 的 `risk_waiting` 处理:**有 owner → 用该任务通道 + resolve_user(owner) 定向发给责任人;无 owner → 跳过通知并记日志**。

**Tech Stack:** Python 3.12;复用 3a-1 工具 / 3a-2 gateway / 已建通知适配器(含 `resolve_user`、`load_company_channel_config_by_id`)。

---

## 策略(用户确认)
- 数据采集分两类:① **自动采集**(未绑对账任务,无 owner)② **对账任务伴随的采集**(有 owner)。
- ① → handoff session 照建、Chrome 保持等待、超时 RISK_VERIFICATION;**不发通知**(没有具体责任人)。
- ② → 经该对账任务配置的通道,**定向通知责任人(owner)**。

## 现状依赖
- 3a-1:`browser_handoff_session_create`(返回 session+token);auth.db handoff CRUD。
- 3a-2:agent 上报 `risk_waiting`(已上线);gateway `_handle_risk_waiting`(当前用公司默认通道群播——本计划改它);`/p/handoff` 落地页。
- recon owner/channel 范式(`auto_run_service.py:1508-1545`):`channel_config_id` 来自 feedback/run_plan;owner 来自 `run_plan.owner_mapping_json.default_owner`(name/identifier);通知用 `load_company_channel_config_by_id` + `get_notification_adapter` + 适配器 `resolve_user`/`send_bot_message`。
- recon 触发采集处(不传 params):`auto_scheme_run/nodes.py:_trigger_collection`、`auto_run_service.py`(~809 采集循环)。`data_source_trigger_dataset_collection(..., params=...)` 的 params 会落入 sync_job request_payload(参见 3a-1 的 verification_payload 形态)。

---

## Task 1: recon 触发采集时把 channel_config_id + owner 塞进 params

**Files:**
- Modify: `finance-agents/data-agent/graphs/recon/auto_scheme_run/nodes.py`(`_trigger_collection` + 其调用方,把任务的 channel_config_id + default_owner 传入)
- Modify: `finance-agents/data-agent/graphs/recon/auto_run_service.py`(采集触发循环,同样传入)
- Test: `finance-agents/data-agent/tests/test_recon_collection_owner_params.py`

- [ ] **Step 1**:实现前先定位 owner/channel 在这两处触发上下文的取值来源(任务/run_plan 已加载在 scope):
  - `channel_config_id`:任务/run_plan 的 `channel_config_id`。
  - `owner`:`run_plan.owner_mapping_json.default_owner`(`{name, identifier}`);取不到则视为无 owner(不阻断采集)。
- [ ] **Step 2**:给 `_trigger_collection`(nodes.py)增加可选入参 `handoff_channel_config_id: str=""`、`handoff_owner: dict|None=None`,并在调用 `data_source_trigger_dataset_collection` 时合并进 `params`:
```python
    params = {}
    if handoff_channel_config_id:
        params["handoff_channel_config_id"] = handoff_channel_config_id
    if handoff_owner:
        params["handoff_owner"] = handoff_owner  # {"name":..., "identifier":...}
    return await data_source_trigger_dataset_collection(
        auth_token, source_id, dataset_id=dataset_id, resource_key=resource_key,
        biz_date=biz_date, trigger_mode=trigger_mode, background=True, mode="real",
        params=params,
    )
```
  调用方(scheme run / auto_run_service 采集循环)把任务的 channel_config_id + default_owner 传进来(从已加载的 run_plan/task 取;auto_run_service 的采集循环若此处还没解析 run_plan,则在循环前解析一次 channel_config_id + default_owner 复用)。
- [ ] **Step 3**:测试——构造一个带 channel_config_id + default_owner 的 run_plan/task,断言触发时 `data_source_trigger_dataset_collection` 收到的 `params` 含 `handoff_channel_config_id` + `handoff_owner`(mock 该函数捕获 params)。
- [ ] **Step 4**:运行通过;**Step 5**:Commit `feat(handoff): recon collection trigger carries channel+owner into sync_job params`。

> 注:`data_source_trigger_dataset_collection` 的 params 是否原样进 sync_job.request_payload,需在实现时确认(读 3a-1 看到的 trigger→insert 路径);若 params 嵌在 request_payload.params,Task 2 按该路径读取。

## Task 2: finance-mcp create 从 sync_job 读 channel+owner 并回传

**Files:**
- Modify: `finance-mcp/auth/db.py`(加 `get_sync_job(sync_job_id)` 读 request_payload,若无现成读取函数)
- Modify: `finance-mcp/tools/data_sources.py`(`_handle_browser_handoff_session_create` 读 sync_job 的 request_payload 取 `handoff_channel_config_id` + `handoff_owner`,存 channel_config_id 到 session,返回里带 `channel_config_id` + `owner`)
- Test: `finance-mcp/tests/test_handoff_session_tools.py`(追加)

- [ ] **Step 1**:测试——先插一条 sync_jobs(request_payload.params 含 handoff_channel_config_id + handoff_owner),create 后断言返回含 `channel_config_id` + `owner`;另一条无这俩的 → 返回 owner 为空。
- [ ] **Step 2**:实现:create 里 `job = auth_db.get_sync_job(sync_job_id)`;`params = (job.get("request_payload") or {}).get("params") or {}`;`channel_config_id = arguments.get("channel_config_id") or params.get("handoff_channel_config_id")`;`owner = params.get("handoff_owner") or {}`;`insert_handoff_session(..., channel_config_id=channel_config_id)`;返回追加 `"channel_config_id": channel_config_id, "owner": owner`。
- [ ] **Step 3**:运行通过;**Step 4**:Commit `feat(handoff): create resolves channel+owner from sync_job request_payload`。

## Task 3: data-agent risk_waiting 定向通知 owner(无 owner 则跳过)

**Files:**
- Modify: `finance-agents/data-agent/services/browser_agent_gateway.py`(`_handle_risk_waiting` 改:用 create 回传的 channel_config_id + owner;有 owner→定向发,无→跳过)
- Test: `finance-agents/data-agent/tests/test_gateway_risk_waiting.py`(改写用例)

- [ ] **Step 1**:改写测试:
  - create 回传 `{success, handoff_session_id, handoff_token, channel_config_id:"chan1", owner:{"identifier":"u1","name":"周行"}}` → 断言 `load_company_channel_config_by_id(chan1)` + 适配器 `send_bot_message(to_user_id="u1", ...)`(或 resolve_user→send)被调,内容含 `/p/handoff?t=`。
  - create 回传 `owner:{}`(无 owner)→ 断言**不发任何通知**(adapter 未被调),但仍返回 ok(session 已建)。
- [ ] **Step 2**:实现:`_handle_risk_waiting` 去掉"公司默认通道群播";改为读 `created.get("channel_config_id")` + `created.get("owner")`;
```python
    owner = created.get("owner") or {}
    channel_id = created.get("channel_config_id")
    recipient = str(owner.get("identifier") or owner.get("user_id") or "").strip()
    if channel_id and recipient:
        channel = load_company_channel_config_by_id(channel_id=channel_id)
        if channel is not None:
            adapter = get_notification_adapter(provider=getattr(channel,"provider",""), channel_config=channel)
            resolved = adapter.resolve_user(user_id=recipient, keyword=str(owner.get("name") or ""))
            target = resolved.resolved_user.user_id if (resolved.success and resolved.resolved_user) else recipient
            adapter.send_bot_message(content=f"...{link}", to_user_id=target)
    else:
        logger.info("handoff 无对账任务责任人,跳过通知 sync_job_id=%s", sync_job_id)
```
  (`load_company_channel_config_by_id` 从 `services.notifications.repository` 导入。)
- [ ] **Step 3**:运行通过(含"无 owner 不发"用例);**Step 4**:Commit `feat(handoff): notify the recon-task owner; skip when no task/owner`。

## Task 4: 联调
- [ ] 重启 finance-mcp + data-agent + browser-agent。
- [ ] **对账任务触发**一次会进风控的采集 → 责任人(owner)在配置通道收到含 `/p/handoff?t=` 的消息;打开链接渲染正常。
- [ ] **自动采集(无任务)**触发一次进风控 → 确认**不发通知**,但 handoff session 已建、sync_job=waiting_human_verification、超时 RISK_VERIFICATION。

## 收尾
- 至此 handoff 通知按"对账任务责任人"定向,自动采集不打扰。
- 远程实时接管(责任人在链接里看画面+操作)仍是阶段3b/4(滑块输入分叉待真机)。
- owner 身份解析(identifier vs 平台 user_id)以各通知适配器 `resolve_user` 为准;真机以钉钉为先验证。

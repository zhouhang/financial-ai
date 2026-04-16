Finance Cron
============

`finance-cron` 负责对账任务的定时调度，不再由 `data-agent` 进程内置轮询。

职责边界
--------
- 读取已配置的 `execution_run_plans`
- 用 APScheduler 为启用计划注册调度任务
- 到点后通过 `data-agent` internal API 触发执行
- 通过 `schedule_slot` 做幂等去重

关键文件
--------
- `run_scheduler.py`：启动定时服务
- `scheduler_service.py`：APScheduler 调度逻辑
- `mcp_client.py`：最小 finance-mcp 客户端，只调用调度器所需工具
- `data_agent_client.py`：调用 data-agent `/recon/run-plans/{run_plan_code}/run`
- `run_reconciliation.py`：手工触发单个运行计划

启动方式
--------
```bash
cd /Users/kevin/workspace/financial-ai
source .venv/bin/activate
python finance-cron/run_scheduler.py --config finance-cron/config/cron_config.yaml
```

手工触发单个计划
---------------
```bash
python finance-cron/run_reconciliation.py \
  --run-plan-code your_plan_code \
  --company-id your_company_id
```

依赖
----
- APScheduler
- httpx
- PyJWT
- PyYAML
- python-dotenv

环境变量
--------
- `JWT_SECRET`
- `FINANCE_MCP_BASE_URL`，默认 `http://localhost:3335`
- `DATA_AGENT_BASE_URL`，默认 `http://localhost:8100`
- `RECON_SCHEDULER_TIMEZONE`，可覆盖配置文件

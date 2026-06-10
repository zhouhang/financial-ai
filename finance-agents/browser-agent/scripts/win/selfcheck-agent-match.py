"""采集任务可达性自检:本机 BROWSER_AGENT_ID 是否与 tally 的采集绑定/注册匹配。

为什么需要:采集机 WS 连得上、心跳正常,但如果本机 agent_id 与 tally 的
shop_runtime_bindings.agent_id 不一致,tally 永远不会把采集任务下发到本机
(任务按 agent_id 路由)—— 这是"连着却收不到活"的隐性故障。

做法:用一个临时 throwaway agent_id 连 data-agent WS(不打扰正在运行的采集机
在网关里的注册),问服务端"真实 agent_id 能否收到下发任务"。只读、无副作用。

退出码:0=匹配(能收任务) 1=不匹配/未注册 2=连不上/出错。
"""
from __future__ import annotations
import asyncio
import dataclasses
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../browser-agent
sys.path.insert(0, str(ROOT))


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


async def _run() -> int:
    _load_env_file(ROOT / ".env")
    from finance_browser_agent.tally_client import BrowserAgentConfig, BrowserAgentTallyClient

    cfg = BrowserAgentConfig.from_env()
    real_agent = cfg.agent_id
    company_id = (cfg.company_id or "").strip()
    print(f"  local BROWSER_AGENT_ID : {real_agent}")
    print(f"  company_id             : {company_id or '(missing!)'}")
    print(f"  data-agent WS          : {cfg.data_agent_ws_url}")
    if not company_id:
        print("TASK-MATCH : UNKNOWN  (BROWSER_AGENT_COMPANY_ID 未设置,无法自检)")
        return 2

    # throwaway connection id so we don't disturb the live agent's gateway registration
    probe_cfg = dataclasses.replace(cfg, agent_id=f"{real_agent}-selfcheck-{os.getpid()}")
    client = BrowserAgentTallyClient(config=probe_cfg)
    try:
        res = await asyncio.wait_for(
            client.self_check(agent_id=real_agent, company_id=company_id), timeout=20
        )
    except Exception as exc:  # noqa: BLE001
        print(f"TASK-MATCH : ERROR  (self_check 调用失败: {exc})")
        return 2

    if not isinstance(res, dict) or not res.get("success"):
        print(f"TASK-MATCH : ERROR  (服务端返回: {res})")
        return 2

    registered = res.get("registered")
    bound = int(res.get("bound_bindings") or 0)
    total = int(res.get("total_company_bindings") or 0)
    others = [a for a in (res.get("binding_agent_ids") or []) if a != real_agent]
    if res.get("can_receive_tasks"):
        print(
            f"TASK-MATCH : OK     (已注册, {bound}/{total} 个采集绑定指向本机 agent_id, "
            f"online={res.get('online')})"
        )
        return 0

    print("TASK-MATCH : FAIL   (本机收不到 tally 下发的采集任务)")
    if not registered:
        print(f"  原因: agent_id '{real_agent}' 未在 tally 注册(agents 表无此记录)")
    if bound == 0:
        print(f"  原因: 没有任何采集绑定指向 '{real_agent}'(共 {total} 个绑定)")
        if others:
            print(f"  tally 实际把绑定分配给了: {', '.join(others)}")
            print(f"  → 把本机 .env 的 BROWSER_AGENT_ID 改成上面的值,或在运维侧把绑定迁移到 '{real_agent}'")
    return 1


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 2


if __name__ == "__main__":
    sys.exit(main())

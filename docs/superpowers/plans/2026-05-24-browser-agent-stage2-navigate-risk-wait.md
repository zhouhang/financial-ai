# 阶段2:人工验证状态(navigate 风控等待补齐) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `navigate` 动作检测到风控(RISK_VERIFICATION)时,也像 login 路径那样保持 Chrome 不关、有界等待人工清除(上限 `risk_manual_timeout_ms`)后继续 playbook,超时再失败——补齐 阶段2 在 navigate 路径上的唯一缺口。

**Architecture:** 复用现有 `_wait_for_risk_to_clear` 与 `_login_candidates`,在 `_execute_action` 的 `navigate` 分支抽一个 `_await_navigate_risk_clearance` 包一层等待;清除返回 None(继续),超时返回 "RISK_VERIFICATION"(由原处抛出)。不动 login/post-login(已实现+已测),不动 finance-mcp / 云端。

**Tech Stack:** Python 3.12;Playwright 同步 API;测试 `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/<file> -v`(`tests/` 被 gitignore,提交用 `git add -f`)。

---

## 现状:阶段2 大部分已完成(不要重复做)

当前 `finance_browser_agent/playwright_runner.py` 已实现并已测的 阶段2 行为:
- **检测到风控不立即失败 + 保持 Chrome 不关 + 有界等待 + 超时 RISK_VERIFICATION**:
  - login 表单路径:line 445-469(设 `risk_deadline` ← `risk_manual_timeout_ms`、`_wait_for_risk_to_clear`、清除则 `continue` 续登、超时抛 RISK_VERIFICATION)。
  - post-login 路径:line 634-664(同模式)。
  - 轮询器:`_wait_for_risk_to_clear(contexts, *, timeout_ms, poll_interval_ms=1000)`(line 519)。
- **已测**:`tests/test_playwright_profile_login_state.py` 覆盖 login 等待、风控复现继续等待、超时→RISK_VERIFICATION、monkeypatch `_wait_for_risk_to_clear`;`risk_manual_timeout_ms` 配置测试在 contract 测试里。

**唯一缺口**:`_execute_action` 的 `navigate` 分支(line 244-251)检测到风控**立即抛** `BrowserActionError(detected)`(line 250),没有走等待循环。即:playbook 在 `navigate` 落到风控页(滑块/验证码)时直接失败,不给人工窗口——与 login 路径不一致。本计划只补这一处。

> 说明:`waiting_human_verification`/`resuming` 的**云端 sync_job 状态**与 handoff session 绑定,属阶段3(需改 finance-mcp + 云端中转),不在本轮。本轮只补 runner 本地等待行为的 navigate 缺口。

## 当前要改的代码(line 244-251,精确锚点)

```python
    if name == "navigate":
        page.goto(str(action.get("url") or ""), wait_until="load", timeout=timeout_ms)
        detected = _detect_auth_or_risk(page)
        if detected == "AUTH_EXPIRED" and allow_auth_redirect:
            return {"auth_required": True}
        if detected:
            raise BrowserActionError(detected, f"navigate detected {detected}")
        return {}
```

## 文件结构

- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py` — 新增 `_await_navigate_risk_clearance` helper + 改 navigate 分支。
- Test `finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py`(新)。

---

## Task 1: navigate 风控等待

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Test: `finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py`

> 实现前先确认 `_execute_action` 的签名与调用形态:`grep -nE "def _execute_action" playwright_runner.py`,并看调用点(约 line 853)如何传参(`page, action, *, params, extracted, capture_files, download_dir, allow_auth_redirect, run_config`)。测试按真实签名构造调用。

- [ ] **Step 1: 写失败测试** `tests/test_playwright_navigate_risk_wait.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import finance_browser_agent.playwright_runner as runner
from finance_browser_agent.playwright_runner import (
    BrowserActionError,
    PlaywrightRunConfig,
    _execute_action,
)


class FakeNavPage:
    """navigate 用的最小假页面:goto 无副作用;frames 为空。"""
    def __init__(self):
        self.url = "https://example.com/bill"
        self.frames = []
    def goto(self, *a, **k):
        return None


def _config(timeout_ms: int) -> PlaywrightRunConfig:
    return PlaywrightRunConfig(
        profile_root="/tmp/p", download_root="/tmp/d", headless=True,
        timezone_id="Asia/Shanghai", browser_channel="chrome",
        risk_manual_timeout_ms=timeout_ms,
    )


def _navigate(page, config, **over):
    action = {"action": "navigate", "url": "https://example.com/bill", "id": "nav1"}
    kwargs = dict(params={}, extracted={}, capture_files=[], download_dir=Path("/tmp/d"),
                  allow_auth_redirect=False, run_config=config)
    kwargs.update(over)
    return _execute_action(page, action, **kwargs)


def test_navigate_risk_waits_then_resumes(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "RISK_VERIFICATION")
    calls = {"n": 0}
    def fake_wait(contexts, *, timeout_ms, poll_interval_ms=1000):
        calls["n"] += 1
        return True  # 人工已清除
    monkeypatch.setattr(runner, "_wait_for_risk_to_clear", fake_wait)
    result = _navigate(FakeNavPage(), _config(3000))
    assert result == {}           # 清除后继续(不抛)
    assert calls["n"] == 1        # 确实等待过


def test_navigate_risk_timeout_raises(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "RISK_VERIFICATION")
    monkeypatch.setattr(runner, "_wait_for_risk_to_clear", lambda *a, **k: False)
    with pytest.raises(BrowserActionError) as exc:
        _navigate(FakeNavPage(), _config(3000))
    assert exc.value.fail_reason == "RISK_VERIFICATION"


def test_navigate_risk_no_wait_when_timeout_zero(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "RISK_VERIFICATION")
    def boom(*a, **k):
        raise AssertionError("timeout=0 不应等待")
    monkeypatch.setattr(runner, "_wait_for_risk_to_clear", boom)
    with pytest.raises(BrowserActionError) as exc:
        _navigate(FakeNavPage(), _config(0))
    assert exc.value.fail_reason == "RISK_VERIFICATION"


def test_navigate_auth_expired_redirect_unaffected(monkeypatch):
    monkeypatch.setattr(runner, "_detect_auth_or_risk", lambda p: "AUTH_EXPIRED")
    result = _navigate(FakeNavPage(), _config(3000), allow_auth_redirect=True)
    assert result == {"auth_required": True}   # 原 AUTH_EXPIRED 行为不变
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_playwright_navigate_risk_wait.py -v`
Expected: `test_navigate_risk_waits_then_resumes` / `..._timeout_raises` 失败(当前 navigate 不等待,RISK_VERIFICATION 会被立即抛出,`_wait_for_risk_to_clear` 不被调用 → `calls["n"]==0` 断言失败 / 第一个用例抛错而非返回 {})。

- [ ] **Step 3: 实现**

(a) 在 `_wait_for_risk_to_clear`(约 line 519)附近、`_login_candidates`(line 482)之后,新增 helper:
```python
def _await_navigate_risk_clearance(page: Any, *, run_config: "PlaywrightRunConfig | None") -> str | None:
    """navigate 落到风控页时,不立即失败:保持页面打开,轮询等待人工清除,
    上限 risk_manual_timeout_ms。清除返回 None(继续 playbook);超时或未配置超时返回
    'RISK_VERIFICATION'(由调用方抛出)。"""
    manual_timeout_ms = int(run_config.risk_manual_timeout_ms if run_config else 0)
    if manual_timeout_ms <= 0:
        return "RISK_VERIFICATION"
    logger.warning(
        "browser navigate risk verification waiting for manual completion: timeout_ms=%s",
        manual_timeout_ms,
    )
    cleared = _wait_for_risk_to_clear(
        _login_candidates(page),
        timeout_ms=manual_timeout_ms,
        poll_interval_ms=1000,
    )
    return None if cleared else "RISK_VERIFICATION"
```

(b) 改 navigate 分支(line 244-251)为:
```python
    if name == "navigate":
        page.goto(str(action.get("url") or ""), wait_until="load", timeout=timeout_ms)
        detected = _detect_auth_or_risk(page)
        if detected == "AUTH_EXPIRED" and allow_auth_redirect:
            return {"auth_required": True}
        if detected == "RISK_VERIFICATION":
            detected = _await_navigate_risk_clearance(page, run_config=run_config)
        if detected:
            raise BrowserActionError(detected, f"navigate detected {detected}")
        return {}
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_playwright_navigate_risk_wait.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 回归(确认 login/post-login 路径无回归)**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q`
Expected: 全绿(原有风控等待测试不受影响)。

- [ ] **Step 6: Commit**
```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py
git add -f finance-agents/browser-agent/tests/test_playwright_navigate_risk_wait.py
git commit -m "feat(browser-agent): navigate also waits for manual risk clearance (stage2 gap)"
```

## Rules
- 只动 `playwright_runner.py` 的 navigate 分支 + 新 helper + 新测试。**不要**改 login/post-login 的等待逻辑(已实现+已测),不要碰 `_wait_for_risk_to_clear`/`_login_candidates` 的实现,不碰 finance-mcp / dispatcher_loop / tally_client / data_agent_ws / chrome_launcher。
- 若 `_execute_action` 实际签名与测试里的参数名不符,以真实签名为准调整测试调用(grep 确认)。

---

## 收尾(完成后)
- 阶段2 至此完整:login / post-login / navigate 三处风控均"保持会话 + 有界等待 + 超时 RISK_VERIFICATION"。
- 阶段3(云端 handoff session:`waiting_human_verification`/`resuming` 状态持久化、一次性 token、钉钉、云端→agent 截图/输入双工)需真机千牛验证 gate 后再写;它会复用阶段0 的 data-agent WS 双工通道。
- 真机验证(阶段5)项不变:本地等待循环在真实千牛风控页上能否被人工清除并续跑。

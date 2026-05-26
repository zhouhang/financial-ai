# 阶段1:browser-agent 自启 Chrome + CDP attach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 browser-agent 的浏览器获取方式从 “Playwright `launch_persistent_context` 直接 launch Chrome” 改为 “browser-agent 自己以本机程序方式启动 Google Chrome(持久化 user-data-dir + `--remote-debugging-port` 仅绑 127.0.0.1)+ Playwright `connect_over_cdp` attach”,让浏览器进程特征更接近普通用户启动、CDP 不对外暴露,同时保留现有 playbook 执行/下载/解析/质量校验。

**Architecture:** 新增 `chrome_launcher.py`(定位 Chrome、选空闲端口、拼参数、起进程、等 CDP 就绪、可终止的句柄)。`playwright_runner.py` 的浏览器获取段从 `launch_persistent_context(...)` 改为 `launch_chrome(...)` + `connect_over_cdp(...)`,并在 finally 里终止自启的 Chrome 进程。其余逻辑不动。

**Tech Stack:** Python 3.12;`subprocess` 起 Chrome;`httpx` 轮询 CDP `/json/version`;Playwright `connect_over_cdp`。测试:`cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/<file> -v`(用 `@pytest.mark.asyncio` 仅限异步;本计划多为同步)。

---

## 基线现状(已实现,不要重复做)

当前 `finance_browser_agent/playwright_runner.py`(947 行)**已实现**第一层的大部分:
- 持久化采集 profile:`build_user_data_dir` / `sanitize_profile_key`。
- 登录态优先检查:`auth_check.logged_in_selector` + `_profile_is_authenticated`(line ~187)。
- 已登录跳过 `login`/`login_if_needed`:`should_skip_login_action`(line ~828)。
- 慢速逐字输入:`locator.type(value, delay=type_delay_ms)`(line ~611)。
- 步骤/点击前随机等待:`_random_delay_ms` + `_pause_before_step`(line ~533-575)。
- 独立下载目录:`download_dir = download_root/shop_id/job_id`(line ~791)。
- `PlaywrightRunConfig`(含 `headless`/`timezone_id`/`browser_channel`/各 delay)+ `from_env`。

**唯一缺口(第一层 1/3/4)**:浏览器由 Playwright 直接 launch(line 815 `launch_persistent_context`),而非 browser-agent 自启 Chrome + CDP attach。本计划只补这一点。

## 当前要改的代码(line 813-866,精确锚点)

```python
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=config.headless,
                channel=config.browser_channel,
                accept_downloads=True,
                timezone_id=config.timezone_id,
                downloads_path=str(download_dir),
            )
            page = context.pages[0] if context.pages else context.new_page()
            try:
                for index, step_dict in enumerate(steps):
                    ...                      # 步骤循环,保持不变
            finally:
                context.close()
```

## 文件结构

- Create `finance-agents/browser-agent/finance_browser_agent/chrome_launcher.py` — 自启 Chrome + CDP 就绪 + 可终止句柄。
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py` — 浏览器获取段改为 launch_chrome + connect_over_cdp;`PlaywrightRunConfig` 增 `cdp_ready_timeout_ms`(可选)。
- Tests: `tests/test_chrome_launcher.py`(新);`tests/test_playwright_runner_cdp.py`(新,契约测试:rewire 后调用 connect_over_cdp + 终止 Chrome)。

---

## Task 1: chrome_launcher 模块

**Files:**
- Create: `finance-agents/browser-agent/finance_browser_agent/chrome_launcher.py`
- Test: `finance-agents/browser-agent/tests/test_chrome_launcher.py`

- [ ] **Step 1: 写失败测试** `tests/test_chrome_launcher.py`:
```python
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent import chrome_launcher as cl


def test_resolve_binary_env_override(monkeypatch):
    monkeypatch.setenv("BROWSER_AGENT_CHROME_BINARY", "/custom/chrome")
    assert cl.resolve_chrome_binary("chrome") == "/custom/chrome"


def test_resolve_binary_macos(monkeypatch):
    monkeypatch.delenv("BROWSER_AGENT_CHROME_BINARY", raising=False)
    monkeypatch.setattr(cl.platform, "system", lambda: "Darwin")
    assert "Google Chrome.app" in cl.resolve_chrome_binary("chrome")


def test_pick_free_port_returns_usable_int():
    port = cl.pick_free_port()
    assert isinstance(port, int) and 1024 <= port <= 65535


def test_build_chrome_args_headed_binds_localhost():
    args = cl.build_chrome_args(binary="/c", user_data_dir="/u", port=9333, headless=False)
    assert args[0] == "/c"
    assert "--user-data-dir=/u" in args
    assert "--remote-debugging-port=9333" in args
    assert "--remote-debugging-address=127.0.0.1" in args
    assert "--no-first-run" in args
    assert not any(a.startswith("--headless") for a in args)


def test_build_chrome_args_headless_adds_flag():
    args = cl.build_chrome_args(binary="/c", user_data_dir="/u", port=1, headless=True)
    assert "--headless=new" in args


def test_wait_for_cdp_returns_true_when_version_ok(monkeypatch):
    class _Resp:
        status_code = 200
    monkeypatch.setattr(cl.httpx, "get", lambda *a, **k: _Resp())
    assert cl.wait_for_cdp(9333, timeout_seconds=1.0) is True


def test_wait_for_cdp_times_out(monkeypatch):
    def _boom(*a, **k):
        raise cl.httpx.HTTPError("nope")
    monkeypatch.setattr(cl.httpx, "get", _boom)
    monkeypatch.setattr(cl.time, "sleep", lambda *_: None)
    assert cl.wait_for_cdp(9333, timeout_seconds=0.2) is False
```

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_chrome_launcher.py -v`
Expected: FAIL（`ModuleNotFoundError: finance_browser_agent.chrome_launcher`）

- [ ] **Step 3: 实现** `finance_browser_agent/chrome_launcher.py`:
```python
"""自启本机 Chrome 并暴露仅绑 127.0.0.1 的 CDP 端口,供 Playwright connect_over_cdp 接管。

阶段1:不再由 Playwright 直接 launch Chrome,而是 browser-agent 以普通本机程序方式启动
Google Chrome(持久化 user-data-dir + --remote-debugging-port 仅绑 127.0.0.1),再让
Playwright attach。这样浏览器进程特征更接近普通用户启动,且 CDP 不对外暴露。
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
_WIN_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]
_LINUX_CHROME_CANDIDATES = ["google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser"]


def resolve_chrome_binary(channel: str = "chrome") -> str:
    """定位本机 Chrome 可执行文件;env BROWSER_AGENT_CHROME_BINARY 优先。"""
    override = os.getenv("BROWSER_AGENT_CHROME_BINARY", "").strip()
    if override:
        return override
    system = platform.system()
    if system == "Darwin":
        return _MAC_CHROME
    if system == "Windows":
        for path in _WIN_CHROME_CANDIDATES:
            if os.path.exists(path):
                return path
        return _WIN_CHROME_CANDIDATES[0]
    for name in _LINUX_CHROME_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return "google-chrome"


def pick_free_port() -> int:
    """取一个本机空闲端口(绑 127.0.0.1:0 后释放)。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def build_chrome_args(*, binary: str, user_data_dir: str, port: int, headless: bool) -> list[str]:
    """拼启动参数:仅绑 127.0.0.1 的 CDP 端口 + 持久化 profile + 默认 headed。"""
    args = [
        binary,
        f"--user-data-dir={user_data_dir}",
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
    ]
    if headless:
        args.append("--headless=new")
    return args


@dataclass
class ChromeProcess:
    process: subprocess.Popen
    port: int
    user_data_dir: str

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def terminate(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


def wait_for_cdp(port: int, *, timeout_seconds: float = 20.0) -> bool:
    """轮询 /json/version 直到 CDP 就绪。"""
    deadline = time.time() + timeout_seconds
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            resp = httpx.get(url, timeout=2.0)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.3)
    return False


def launch_chrome(
    *,
    user_data_dir: str,
    headless: bool,
    channel: str = "chrome",
    timezone_id: str = "",
    cdp_ready_timeout_seconds: float = 20.0,
) -> ChromeProcess:
    """启动本机 Chrome 并等待 CDP 就绪,返回句柄。就绪失败则终止并抛错。"""
    binary = resolve_chrome_binary(channel)
    port = pick_free_port()
    args = build_chrome_args(binary=binary, user_data_dir=user_data_dir, port=port, headless=headless)
    proc_env = dict(os.environ)
    if timezone_id:
        proc_env["TZ"] = timezone_id
    logger.info("launching chrome: binary=%s port=%s user_data_dir=%s headless=%s", binary, port, user_data_dir, headless)
    process = subprocess.Popen(args, env=proc_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    handle = ChromeProcess(process=process, port=port, user_data_dir=user_data_dir)
    if not wait_for_cdp(port, timeout_seconds=cdp_ready_timeout_seconds):
        handle.terminate()
        raise RuntimeError(f"Chrome CDP 未在超时内就绪 (port={port})")
    return handle
```

- [ ] **Step 4: 运行,确认通过**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_chrome_launcher.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**(测试目录被 gitignore,用 `-f`)
```bash
git add finance-agents/browser-agent/finance_browser_agent/chrome_launcher.py
git add -f finance-agents/browser-agent/tests/test_chrome_launcher.py
git commit -m "feat(browser-agent): chrome_launcher (self-launch Chrome + 127.0.0.1 CDP)"
```

---

## Task 2: runner 改用 launch_chrome + connect_over_cdp

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`(浏览器获取段 line 813-866;import 段;`PlaywrightRunConfig`)
- Test: `finance-agents/browser-agent/tests/test_playwright_runner_cdp.py`(新)

> ⚠️ **下载行为(本任务必查)**:原 `launch_persistent_context` 通过 `downloads_path` 设置下载目录。改用 `connect_over_cdp` attach 已存在的默认 context 后,不能在 context 创建时设 `downloads_path`。先读 `_execute_action` 里的下载动作(grep `expect_download`/`save_as`/`download`):
> - 若它用 `page.expect_download()` + `download.save_as(download_dir/...)`(把文件另存到 download_dir),则 attach 后仍然有效,无需改下载逻辑。
> - 若它依赖 context 的 `downloads_path`(不显式 save_as),则需要改为显式 `expect_download` + `save_as`。
> 真机下载在 CDP attach 下能否落盘,留待阶段5 真机验证;本任务只保证“代码路径不依赖 launch 时的 downloads_path”。

- [ ] **Step 1: 写失败契约测试** `tests/test_playwright_runner_cdp.py`(用假 playwright/假 launcher,断言:用 cdp_url attach、取 contexts[0]、finally 里终止 Chrome):
```python
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import finance_browser_agent.playwright_runner as runner


class FakePage:
    def __init__(self):
        self.url = "https://example.com"
    def wait_for_selector(self, *a, **k):
        return object()


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]
    def new_page(self):
        p = FakePage(); self.pages.append(p); return p
    def close(self):
        pass


class FakeBrowser:
    def __init__(self):
        self.contexts = [FakeContext()]
        self.closed = False
    def new_context(self, **k):
        c = FakeContext(); self.contexts.append(c); return c
    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, browser):
        self._browser = browser
        self.cdp_url = None
    def connect_over_cdp(self, url, **k):
        self.cdp_url = url
        return self._browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class FakeChrome:
    def __init__(self):
        self.port = 9999
        self.terminated = False
    @property
    def cdp_url(self):
        return f"http://127.0.0.1:{self.port}"
    def terminate(self):
        self.terminated = True


def test_runner_attaches_over_cdp_and_terminates_chrome(monkeypatch, tmp_path):
    """rewire 契约:跑一个空 steps 的 playbook,应 connect_over_cdp(chrome.cdp_url) 且 finally 终止 Chrome。"""
    fake_chrome = FakeChrome()
    fake_browser = FakeBrowser()
    fake_pw = FakePlaywright(fake_browser)

    monkeypatch.setattr(runner, "launch_chrome", lambda **k: fake_chrome)
    monkeypatch.setattr(runner, "sync_playwright", lambda: fake_pw)

    config = runner.PlaywrightRunConfig(
        profile_root=str(tmp_path / "p"), download_root=str(tmp_path / "d"),
        headless=False, timezone_id="Asia/Shanghai", browser_channel="chrome",
    )
    message = {
        "job_id": "j1", "shop_id": "s1", "runtime_profile_ref": "s1",
        "playbook_body": {"steps": [], "auth_check": {}},
        "params": {},
    }
    result = runner.run_playbook_with_playwright(message, config=config)

    assert fake_pw.chromium.cdp_url == fake_chrome.cdp_url
    assert fake_chrome.terminated is True
    assert isinstance(result, dict)
```
> 入口已确认:`run_playbook_with_playwright(message, *, config=None)`(line 769,正是含浏览器获取段的函数;dispatcher 经 `run_message` 调它)。它读 `message["playbook_body"]/["params"]/["shop_id"]/["runtime_profile_ref"]/["job_id"]`,与上面 message 字段一致。`launch_chrome`/`sync_playwright` 必须是模块级名字(Step 3 (a) 保证),测试才能 monkeypatch。空 steps 下走完整获取/teardown 路径即可验证 attach + 终止契约;真机行为见阶段5。

- [ ] **Step 2: 运行,确认失败**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_playwright_runner_cdp.py -v`
Expected: FAIL（`runner` 还在用 `launch_persistent_context`,没有模块级 `launch_chrome`/`sync_playwright`,或未调用 connect_over_cdp)

- [ ] **Step 3: 改 playwright_runner.py**

(a) 模块级 import(顶部):把 `from playwright.sync_api import sync_playwright`(原本在函数内 line 794-795 延迟导入)提到模块顶部,并新增 launcher 导入:
```python
from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from finance_browser_agent.chrome_launcher import launch_chrome
```
（删掉函数体里 line 794-795 的重复延迟导入。提到模块级是为了让测试能 monkeypatch `runner.sync_playwright` / `runner.launch_chrome`。）

(b) 浏览器获取段:把 line 813-822 + finally(865-866)替换为:
```python
    try:
        chrome = launch_chrome(
            user_data_dir=user_data_dir,
            headless=config.headless,
            channel=config.browser_channel,
            timezone_id=config.timezone_id,
        )
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(chrome.cdp_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    for index, step_dict in enumerate(steps):
                        ...                      # 步骤循环原样不动
                finally:
                    try:
                        browser.close()           # 断开 CDP(不杀 Chrome 进程)
                    except Exception:
                        pass
        finally:
            chrome.terminate()                    # 关闭我们自启的 Chrome
    except BrowserActionError as exc:
        ...                                       # 原异常处理保持不变
```
（保持 `for index, step_dict in enumerate(steps):` 整段逻辑、`_pause_before_step`、`_execute_action(..., download_dir=download_dir, ...)` 调用不变。）

(c) 下载行为核查:`grep -nE "expect_download|save_as|download" finance_browser_agent/playwright_runner.py`。按本任务顶部 ⚠️ 处理:若下载未显式 `save_as` 到 `download_dir`,改为显式 `expect_download()` + `download.save_as(download_dir / <name>)`;若已显式,则不动。

- [ ] **Step 4: 运行契约测试 + 全量回归**

Run:
```bash
cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_playwright_runner_cdp.py tests/test_playwright_runner_contract.py tests/test_playwright_profile_login_state.py -v
```
Expected: 契约测试 PASS;现有 runner 测试无回归(它们测 config/user_data_dir,不受影响)。

- [ ] **Step 5: Commit**
```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py
git add -f finance-agents/browser-agent/tests/test_playwright_runner_cdp.py
git commit -m "feat(browser-agent): attach via connect_over_cdp to self-launched Chrome"
```

---

## Task 3: 回归 + 配置/部署说明

**Files:**
- Modify(可选): `.env.example`(若有 browser-agent 段)
- Test: 全量回归

- [ ] **Step 1: 全量 browser-agent 测试**

Run: `cd finance-agents/browser-agent && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q`
Expected: 全绿(原 67 passed + 新增 chrome_launcher/cdp 测试)。

- [ ] **Step 2: 确认未触碰 finance-mcp / dispatcher_loop / tally_client / data_agent_ws**

Run: `git --no-pager diff --stat <阶段1首个提交>^..HEAD -- finance-mcp finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/finance_browser_agent/tally_client.py finance-agents/browser-agent/finance_browser_agent/data_agent_ws.py`
Expected: 无输出（阶段1 只动 chrome_launcher.py + playwright_runner.py + 各自测试)。

- [ ] **Step 3: 配置说明**

`BROWSER_AGENT_CHROME_BINARY`(可选,覆盖 Chrome 路径,Win/非标准安装用)。若 `.env.example` 有 browser-agent 段则补一行注释;无则跳过。CDP 端口自动选空闲端口,无需配置。

- [ ] **Step 4: Commit**(若 Step 3 改了文件)
```bash
git add .env.example
git commit -m "docs(browser-agent): note BROWSER_AGENT_CHROME_BINARY for stage1"
```

---

## 收尾(全部任务完成后)

- **阶段5 真机验证项**(本计划不做,记录待办):真实 Win/mac 上 ① Chrome 能被自启且 CDP 就绪;② Playwright attach 后 playbook 正常跑;③ **下载在 CDP attach 下能落到 download_dir**(本计划最大的经验性未知);④ 自启 Chrome 进程在任务结束/异常后确实被终止(无僵尸进程)。
- 不在本轮:阶段2(人工验证状态机)及之后。
- 并发:`max_concurrency>1` 时每个 run 取独立空闲端口 + 独立 user-data-dir(已分别由 pick_free_port 与 build_user_data_dir 保证),互不冲突。

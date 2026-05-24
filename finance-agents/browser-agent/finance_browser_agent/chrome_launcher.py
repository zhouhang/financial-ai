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

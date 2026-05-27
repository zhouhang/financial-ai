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


def test_find_profile_chrome_processes_matches_only_agent_profile(monkeypatch):
    class _Result:
        stdout = "\n".join(
            [
                "101 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "102 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/tmp/profile-a --remote-debugging-port=9333",
                "103 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/tmp/profile-b --remote-debugging-port=9444",
                "104 /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --user-data-dir=/tmp/profile-a",
            ]
        )
        stderr = ""
        returncode = 0

    monkeypatch.setattr(cl.subprocess, "run", lambda *a, **k: _Result())
    monkeypatch.setattr(cl.os, "getpid", lambda: 999)

    assert cl.find_profile_chrome_processes("/tmp/profile-a") == [102]


def test_launch_chrome_cleans_existing_profile_process_before_start(monkeypatch):
    calls: list[object] = []

    class _Proc:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminate")

        def wait(self, timeout=None):
            calls.append(("wait", timeout))

        def kill(self):
            calls.append("kill")

    monkeypatch.setattr(cl, "resolve_chrome_binary", lambda channel: "/chrome")
    monkeypatch.setattr(cl, "pick_free_port", lambda: 9333)
    monkeypatch.setattr(cl, "wait_for_cdp", lambda port, timeout_seconds: True)
    monkeypatch.setattr(cl, "terminate_existing_profile_chrome", lambda user_data_dir: calls.append(("cleanup", user_data_dir)) or [123])
    monkeypatch.setattr(cl.subprocess, "Popen", lambda *a, **k: calls.append(("popen", a[0])) or _Proc())

    chrome = cl.launch_chrome(user_data_dir="/tmp/profile-a", headless=False)

    assert chrome.port == 9333
    assert calls[0] == ("cleanup", "/tmp/profile-a")
    assert calls[1][0] == "popen"

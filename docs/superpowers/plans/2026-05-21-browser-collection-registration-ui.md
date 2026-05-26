# Browser Collection Registration UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the browser collection registration flow with a user-facing list + modal UI that creates the underlying browser source, semantic dataset, playbook, credentials, and verification job automatically.

**Architecture:** Add a source-less browser registration path in finance-mcp, expose it through the data-agent REST API, and rewrite `BrowserPlaybookPanel` into a compact list/modal component. Keep the legacy `/{source_id}/browser-playbook/register` API for compatibility, but the UI must call the new source-less route. Runtime login behavior should be profile-login-state first: open the persistent profile, detect whether login is already valid, and only use saved credentials if the profile is unauthenticated or expired.

**Tech Stack:** Python FastAPI + MCP tool wrappers, PostgreSQL-backed auth DB helpers, React + TypeScript + Vite, Vitest/Testing Library, pytest.

---

## File Structure

- Modify `finance-mcp/tools/data_sources.py`
  - Add a new MCP tool handler for source-less browser registration.
  - Create a browser source and same-title semantic dataset before delegating into existing registration logic.
  - Make `playbook_id`, `version`, and `verification_biz_date` internal defaults.
- Modify `finance-agents/data-agent/tools/mcp_client.py`
  - Add a wrapper for the new source-less MCP tool.
- Modify `finance-agents/data-agent/graphs/data_source/api.py`
  - Add request/response models and `POST /data-sources/browser-playbook/registrations`.
  - Keep existing source-bound endpoint unchanged for backward compatibility.
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
  - Clarify and implement profile-login-state first behavior.
  - Prefer `runtime_profile_ref` as the profile key; fall back to current `shop_id` field for compatibility.
- Modify `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
  - Ensure `runtime_profile_ref` is propagated and profile locks use the same profile key the runner uses.
- Modify `finance-web/src/dataSourceConfig.ts`
  - Remove file and desktop/CLI cards.
  - Rename API card to `API（待开发）`.
- Replace most of `finance-web/src/components/BrowserPlaybookPanel.tsx`
  - List registrations.
  - New modal.
  - Detail modal.
  - Poll verification status after save.
- Add tests:
  - `finance-mcp/tests/test_browser_playbook_source_less_registration.py`
  - `finance-agents/data-agent/tests/test_browser_playbook_registration_api.py`
  - `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`
  - `finance-web/tests/components/browser-playbook-panel.test.tsx`
  - Extend `finance-web/tests/components/data-connections-panel.test.tsx` or create a small source-card config test.

---

### Task 1: Add Source-Less Registration MCP Tool

**Files:**
- Modify: `finance-mcp/tools/data_sources.py`
- Test: `finance-mcp/tests/test_browser_playbook_source_less_registration.py`

- [ ] **Step 1: Write failing MCP tool tests**

Create `finance-mcp/tests/test_browser_playbook_source_less_registration.py`:

```python
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

FINANCE_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(FINANCE_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(FINANCE_MCP_ROOT))

from tools import data_sources


def test_slug_from_browser_registration_title_handles_chinese_and_collisions() -> None:
    assert data_sources._browser_registration_slug("千牛每日资金账单") == "browser-collection"
    assert data_sources._browser_registration_slug("Daily Fund Bill") == "daily-fund-bill"


def test_default_browser_verification_biz_date_is_t_minus_one(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDate(data_sources.date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 21)

    monkeypatch.setattr(data_sources, "date", FakeDate)

    assert data_sources._default_browser_verification_biz_date() == "2026-05-20"


def test_register_browser_collection_creates_source_dataset_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    monkeypatch.setattr(
        data_sources,
        "_require_user",
        lambda token: {"company_id": "company-1", "id": "user-1"},
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source",
        lambda **kwargs: calls.append(("source", kwargs)) or {
            "id": "source-1",
            "company_id": kwargs["company_id"],
            "code": kwargs["code"],
            "name": kwargs["name"],
            "source_kind": kwargs["source_kind"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_unified_data_source_dataset",
        lambda **kwargs: calls.append(("dataset", kwargs)) or {
            "id": "dataset-1",
            "dataset_code": kwargs["dataset_code"],
            "dataset_name": kwargs["dataset_name"],
            "resource_key": kwargs["resource_key"],
            "source_type": "browser_collection_records",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "get_unified_data_source_by_id",
        lambda **kwargs: {
            "id": "source-1",
            "company_id": "company-1",
            "code": "browser-collection",
            "name": "千牛每日资金账单",
            "source_kind": "browser_playbook",
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "list_unified_data_source_datasets",
        lambda **kwargs: [
            {
                "id": "dataset-1",
                "dataset_code": "browser-collection",
                "dataset_name": "千牛每日资金账单",
                "source_type": "browser_collection_records",
                "publish_status": "published",
                "meta": {"source_type": "browser_collection_records"},
            }
        ],
    )
    monkeypatch.setattr(data_sources.auth_db, "_seal_json_payload", lambda payload: "sealed-secret")
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_playbook",
        lambda **kwargs: calls.append(("playbook", kwargs)) or {
            "playbook_id": kwargs["playbook_id"],
            "version": kwargs["version"],
            "title": kwargs["title"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "upsert_shop_runtime_binding",
        lambda **kwargs: calls.append(("binding", kwargs)) or {
            "data_source_id": kwargs["data_source_id"],
            "credential_ref": kwargs["credential_ref"],
        },
    )
    monkeypatch.setattr(
        data_sources.auth_db,
        "insert_browser_verification_sync_job",
        lambda **kwargs: calls.append(("sync_job", kwargs)) or {"id": "sync-1"},
    )
    monkeypatch.setattr(data_sources, "_default_browser_verification_biz_date", lambda: "2026-05-20")

    result = asyncio.run(
        data_sources._handle_data_source_register_browser_collection(
            {
                "auth_token": "token",
                "title": "千牛每日资金账单",
                "credential_username": "finance_ops@example.com",
                "credential_password": "secret",
                "playbook_body": {"schema_version": "1.0", "steps": []},
            }
        )
    )

    assert result["success"] is True
    assert result["source"]["id"] == "source-1"
    assert result["dataset"]["id"] == "dataset-1"
    assert result["verification_sync_job_id"] == "sync-1"
    assert result["verification_biz_date"] == "2026-05-20"

    source_call = next(payload for name, payload in calls if name == "source")
    assert source_call["source_kind"] == "browser_playbook"
    assert source_call["name"] == "千牛每日资金账单"
    assert source_call["is_enabled"] is True

    dataset_call = next(payload for name, payload in calls if name == "dataset")
    assert dataset_call["dataset_name"] == "千牛每日资金账单"
    assert dataset_call["publish_status"] == "published"
    assert dataset_call["meta"]["source_type"] == "browser_collection_records"

    playbook_call = next(payload for name, payload in calls if name == "playbook")
    assert playbook_call["playbook_id"] == "browser-collection"
    assert playbook_call["version"] == "1"

    sync_call = next(payload for name, payload in calls if name == "sync_job")
    assert sync_call["request_payload"]["dataset_id"] == "dataset-1"
    assert sync_call["request_payload"]["params"]["biz_date"] == "2026-05-20"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_source_less_registration.py -v
```

Expected: FAIL because `_handle_data_source_register_browser_collection`, `_browser_registration_slug`, and `_default_browser_verification_biz_date` do not exist.

- [ ] **Step 3: Add helper imports and helper functions**

In `finance-mcp/tools/data_sources.py`, update imports near the top if `date` and `timedelta` are not already imported:

```python
from datetime import date, timedelta
```

Add helpers near the existing browser playbook constants/helpers:

```python
def _browser_registration_slug(title: Any) -> str:
    raw = str(title or "").strip().lower()
    slug_chars: list[str] = []
    previous_dash = False
    for ch in raw:
        if ch.isascii() and ch.isalnum():
            slug_chars.append(ch)
            previous_dash = False
        elif ch in {" ", "-", "_", ".", "/"} and not previous_dash:
            slug_chars.append("-")
            previous_dash = True
    slug = "".join(slug_chars).strip("-")
    return slug or "browser-collection"


def _default_browser_verification_biz_date() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def _browser_registration_code(*, title: str, company_id: str) -> str:
    base = _browser_registration_slug(title)
    suffix = hashlib.sha1(f"{company_id}:{title}".encode("utf-8")).hexdigest()[:8]
    return f"{base}-{suffix}"
```

If `hashlib` is not imported in `data_sources.py`, add:

```python
import hashlib
```

- [ ] **Step 4: Add source-less handler**

Add this handler above `_handle_data_source_register_browser_playbook`:

```python
async def _handle_data_source_register_browser_collection(arguments: dict[str, Any]) -> dict[str, Any]:
    user = _require_user(arguments.get("auth_token", ""))
    company_id = str(user["company_id"])
    title = str(arguments.get("title") or "").strip()
    credential_username = str(arguments.get("credential_username") or "").strip()
    credential_password = str(arguments.get("credential_password") or "")
    playbook_body = dict(arguments.get("playbook_body") or {})

    if not title:
        return {"success": False, "error": "标题不能为空"}
    if not credential_username or not credential_password:
        return {"success": False, "error": "登录账号和密码不能为空"}
    if not playbook_body:
        return {"success": False, "error": "Playbook JSON 不能为空"}

    source_code = _browser_registration_code(title=title, company_id=company_id)
    playbook_id = _browser_registration_slug(title)
    version = "1"

    source_row = auth_db.upsert_unified_data_source(
        company_id=company_id,
        code=source_code,
        name=title,
        source_kind="browser_playbook",
        domain_type="ecommerce",
        provider_code="browser_playbook",
        execution_mode="deterministic",
        description=f"{title} 浏览器采集",
        status="active",
        is_enabled=True,
        meta={"registration_title": title, "managed_by": "browser_collection_registration"},
    )
    if not source_row:
        return {"success": False, "error": "创建浏览器采集数据源失败"}

    source_id = str(source_row.get("id") or "")
    dataset_code = playbook_id
    dataset_row = auth_db.upsert_unified_data_source_dataset(
        company_id=company_id,
        data_source_id=source_id,
        dataset_code=dataset_code,
        dataset_name=title,
        resource_key=f"{playbook_id}@{version}",
        dataset_kind="table",
        origin_type="browser_playbook",
        extract_config={
            "source_type": "browser_collection_records",
            "storage": "browser_collection_records",
        },
        schema_summary={
            "source_type": "browser_collection_records",
            "storage": "browser_collection_records",
        },
        sync_strategy={"mode": "browser_playbook"},
        status="active",
        is_enabled=True,
        health_status="unknown",
        publish_status="published",
        business_domain="browser_collection",
        business_object_type="browser_collection_records",
        grain="row",
        meta={"source_type": "browser_collection_records", "managed_by": "browser_collection_registration"},
    )
    if not dataset_row:
        return {"success": False, "error": "创建浏览器采集语义数据集失败", "source": source_row}

    result = await _handle_data_source_register_browser_playbook(
        {
            **arguments,
            "source_id": source_id,
            "playbook_id": playbook_id,
            "version": version,
            "title": title,
            "dataset_id": str(dataset_row.get("id") or ""),
            "verification_biz_date": _default_browser_verification_biz_date(),
            "egress_group": "",
        }
    )
    if result.get("success"):
        result["source"] = _build_data_source_view(source_row)
        result["dataset"] = _build_dataset_view(dataset_row)
    return result
```

- [ ] **Step 5: Register the MCP tool**

In the tool list where `data_source_register_browser_playbook` is declared, add:

```python
Tool(
    name="data_source_register_browser_collection",
    description="用户入口：新增浏览器采集。自动创建 browser_playbook 数据源、同名 browser_collection_records 语义数据集、playbook、凭证绑定和首次验证 sync_job。",
    inputSchema={
        "type": "object",
        "properties": {
            "auth_token": {"type": "string"},
            "title": {"type": "string"},
            "credential_username": {"type": "string"},
            "credential_password": {"type": "string"},
            "playbook_body": {"type": "object"},
        },
        "required": ["auth_token", "title", "credential_username", "credential_password", "playbook_body"],
    },
)
```

In the tool dispatch block, before the source-bound registration branch, add:

```python
if name == "data_source_register_browser_collection":
    return await _handle_data_source_register_browser_collection(arguments)
```

- [ ] **Step 6: Run MCP tests**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_source_less_registration.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-mcp/tools/data_sources.py finance-mcp/tests/test_browser_playbook_source_less_registration.py
git commit -m "feat: add source-less browser collection registration"
```

---

### Task 2: Expose Source-Less Registration Through Data-Agent REST

**Files:**
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
- Modify: `finance-agents/data-agent/graphs/data_source/api.py`
- Test: `finance-agents/data-agent/tests/test_browser_playbook_registration_api.py`

- [ ] **Step 1: Write failing API test**

Create `finance-agents/data-agent/tests/test_browser_playbook_registration_api.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

DATA_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(DATA_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_AGENT_ROOT))

from graphs.data_source import api


def test_source_less_browser_registration_route(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_register(auth_token: str, *, title: str, credential_username: str, credential_password: str, playbook_body: dict):
        calls.append(
            {
                "auth_token": auth_token,
                "title": title,
                "credential_username": credential_username,
                "credential_password": credential_password,
                "playbook_body": playbook_body,
            }
        )
        return {
            "success": True,
            "status": "verification_pending",
            "source_id": "source-1",
            "verification_sync_job_id": "sync-1",
            "verification_biz_date": "2026-05-20",
            "source": {"id": "source-1", "name": title},
            "dataset": {"id": "dataset-1", "dataset_name": title},
            "playbook": {"playbook_id": "browser-collection", "version": "1"},
            "binding": {"credential_ref": "sealed"},
            "message": "ok",
        }

    monkeypatch.setattr(api, "data_source_register_browser_collection", fake_register)

    app = api.FastAPI()
    app.include_router(api.router)
    client = TestClient(app)

    response = client.post(
        "/data-sources/browser-playbook/registrations",
        headers={"Authorization": "Bearer token-1"},
        json={
            "title": "千牛每日资金账单",
            "credential_username": "finance_ops@example.com",
            "credential_password": "secret",
            "playbook_body": {"schema_version": "1.0", "steps": []},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["source_id"] == "source-1"
    assert body["verification_sync_job_id"] == "sync-1"
    assert body["dataset"]["id"] == "dataset-1"
    assert calls == [
        {
            "auth_token": "token-1",
            "title": "千牛每日资金账单",
            "credential_username": "finance_ops@example.com",
            "credential_password": "secret",
            "playbook_body": {"schema_version": "1.0", "steps": []},
        }
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest finance-agents/data-agent/tests/test_browser_playbook_registration_api.py -v
```

Expected: FAIL because the wrapper and route do not exist.

- [ ] **Step 3: Add MCP client wrapper**

In `finance-agents/data-agent/tools/mcp_client.py`, after `data_source_register_browser_playbook`, add:

```python
async def data_source_register_browser_collection(
    auth_token: str,
    *,
    title: str,
    credential_username: str,
    credential_password: str,
    playbook_body: dict[str, Any],
) -> dict[str, Any]:
    if not auth_token:
        return {"success": False, "error": "未提供认证 token，请先登录"}
    if not title.strip():
        return {"success": False, "error": "标题不能为空"}
    return await call_mcp_tool(
        "data_source_register_browser_collection",
        {
            "auth_token": auth_token,
            "title": title,
            "credential_username": credential_username,
            "credential_password": credential_password,
            "playbook_body": playbook_body,
        },
    )
```

- [ ] **Step 4: Add API model and route**

In `finance-agents/data-agent/graphs/data_source/api.py`, import the new wrapper:

```python
from tools.mcp_client import data_source_register_browser_collection
```

Add models near the existing browser playbook models:

```python
class BrowserCollectionRegistrationRequest(BaseModel):
    title: str
    credential_username: str
    credential_password: str
    playbook_body: dict[str, Any]


class BrowserCollectionRegistrationResponse(BaseModel):
    success: bool
    status: str = "verification_pending"
    source_id: str = ""
    verification_sync_job_id: str = ""
    verification_biz_date: str = ""
    source: dict[str, Any] | None = None
    dataset: dict[str, Any] | None = None
    playbook: dict[str, Any] | None = None
    binding: dict[str, Any] | None = None
    message: str = ""
```

Add the route before the source-bound `register_browser_playbook` route so it is not confused with `{source_id}`:

```python
@router.post(
    "/data-sources/browser-playbook/registrations",
    response_model=BrowserCollectionRegistrationResponse,
)
async def register_browser_collection(
    body: BrowserCollectionRegistrationRequest,
    authorization: Optional[str] = Header(None),
):
    auth_token = _extract_auth_token(authorization)
    if not auth_token:
        raise HTTPException(status_code=401, detail="未提供认证 token，请先登录")

    result = await data_source_register_browser_collection(
        auth_token,
        title=body.title,
        credential_username=body.credential_username,
        credential_password=body.credential_password,
        playbook_body=body.playbook_body,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "浏览器采集注册失败"))
    return BrowserCollectionRegistrationResponse(
        success=True,
        status=str(result.get("status") or "verification_pending"),
        source_id=str(result.get("source_id") or result.get("source", {}).get("id") or ""),
        verification_sync_job_id=str(result.get("verification_sync_job_id") or ""),
        verification_biz_date=str(result.get("verification_biz_date") or ""),
        source=result.get("source"),
        dataset=result.get("dataset"),
        playbook=result.get("playbook"),
        binding=result.get("binding"),
        message=str(result.get("message") or ""),
    )
```

- [ ] **Step 5: Run API tests**

Run:

```bash
pytest finance-agents/data-agent/tests/test_browser_playbook_registration_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add finance-agents/data-agent/tools/mcp_client.py finance-agents/data-agent/graphs/data_source/api.py finance-agents/data-agent/tests/test_browser_playbook_registration_api.py
git commit -m "feat: expose browser collection registration api"
```

---

### Task 3: Update Browser-Agent Profile Login-State Semantics

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Modify: `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`
- Test: `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`

- [ ] **Step 1: Write failing unit tests for profile key and login action skipping**

Create `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

BROWSER_AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(BROWSER_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(BROWSER_AGENT_ROOT))

from finance_browser_agent.playwright_runner import (
    PlaywrightRunConfig,
    build_user_data_dir,
    should_skip_login_action,
)


def test_build_user_data_dir_prefers_runtime_profile_ref() -> None:
    config = PlaywrightRunConfig(
        profile_root="/profiles",
        download_root="/downloads",
        headless=False,
        timezone_id="Asia/Shanghai",
        browser_channel="chrome",
    )

    assert build_user_data_dir(config=config, shop_id="shop-a", runtime_profile_ref="bank/profile-01").endswith(
        "/profiles/bankprofile-01"
    )


def test_should_skip_login_action_when_profile_already_authenticated() -> None:
    login_action = {"action": "login", "username_selector": "#u", "password_selector": "#p"}
    normal_action = {"action": "click", "selector": "#download"}

    assert should_skip_login_action(login_action, authenticated=True) is True
    assert should_skip_login_action(login_action, authenticated=False) is False
    assert should_skip_login_action(normal_action, authenticated=True) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py -v
```

Expected: FAIL because `runtime_profile_ref` and `should_skip_login_action` are not implemented.

- [ ] **Step 3: Implement profile key helper**

Change `build_user_data_dir` in `playwright_runner.py` to accept `runtime_profile_ref`:

```python
def build_user_data_dir(
    *,
    config: PlaywrightRunConfig,
    shop_id: str,
    runtime_profile_ref: str = "",
) -> str:
    """Compose the persistent Chrome user-data-dir.

    The historical field name is shop_id, but the runtime rule is profile-login-state first.
    Prefer runtime_profile_ref when provided so browser collection is not tied to a shop-only
    business model. Sanitize the profile key to prevent path traversal.
    """
    raw_key = str(runtime_profile_ref or shop_id or "unknown")
    safe = "".join(ch for ch in raw_key if ch.isalnum() or ch in {"-", "_"})
    return str(Path(config.profile_root) / (safe or "unknown"))
```

- [ ] **Step 4: Add login action skip helper**

Add:

```python
def should_skip_login_action(action: dict[str, Any], *, authenticated: bool) -> bool:
    return authenticated and str(action.get("action") or "").strip() in {"login", "login_if_needed"}
```

Add a login-state check helper:

```python
def _profile_is_authenticated(page: Any, playbook: dict[str, Any]) -> bool:
    auth_check = dict(playbook.get("auth_check") or {})
    selector = str(auth_check.get("logged_in_selector") or "").strip()
    if selector:
        try:
            page.locator(selector).first.wait_for(timeout=int(auth_check.get("timeout_ms") or 5000))
            return True
        except Exception:
            return False
    detected = _detect_auth_or_risk(page)
    return detected is None
```

In `run_playbook_with_playwright`, after opening the page and before looping steps, compute:

```python
runtime_profile_ref = str(message.get("runtime_profile_ref") or "")
user_data_dir = build_user_data_dir(
    config=config,
    shop_id=shop_id,
    runtime_profile_ref=runtime_profile_ref,
)
```

Inside the context block, before `for step in playbook.get("steps") or []`, add:

```python
authenticated = _profile_is_authenticated(page, playbook)
```

Inside the loop:

```python
step_dict = dict(step)
if should_skip_login_action(step_dict, authenticated=authenticated):
    continue
result = _execute_action(
    page,
    step_dict,
    params=params,
    extracted=extracted,
    capture_files=capture_files,
    download_dir=download_dir,
)
```

This supports future playbooks that include explicit `login` or `login_if_needed` actions without forcing repeated login when the persistent profile is already authenticated. Existing playbooks that rely on `navigate` detecting login pages remain compatible.

- [ ] **Step 5: Align dispatcher lock key with runtime profile key**

In `finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py`, locate the worker logic that locks by shop. Change the key construction to prefer `runtime_profile_ref`:

```python
profile_key = str(job.get("runtime_profile_ref") or job.get("shop_id") or "unknown")
async with self.profile_locks.lock_for_shop(profile_key):
    result = await asyncio.to_thread(self.runner, self._build_run_message(job))
    await self.client.report_result(result)
```

Do not rename `lock_for_shop` in this task; keep API churn small.

- [ ] **Step 6: Run browser-agent tests**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py finance-agents/browser-agent/finance_browser_agent/dispatcher_loop.py finance-agents/browser-agent/tests/test_playwright_profile_login_state.py
git commit -m "fix: use profile login state for browser collection"
```

---

### Task 4: Simplify Data Source Cards

**Files:**
- Modify: `finance-web/src/dataSourceConfig.ts`
- Test: `finance-web/tests/components/data-source-config.test.ts`

- [ ] **Step 1: Write failing config test**

Create `finance-web/tests/components/data-source-config.test.ts`:

```typescript
import { describe, expect, it } from 'vitest';

import { SOURCE_TYPE_CARDS, sourceKindLabel } from '../../src/dataSourceConfig';

describe('data source type cards', () => {
  it('only exposes the supported user-facing source cards', () => {
    expect(SOURCE_TYPE_CARDS.map((card) => card.source_kind)).toEqual([
      'platform_oauth',
      'database',
      'api',
      'browser_playbook',
    ]);
    expect(SOURCE_TYPE_CARDS.find((card) => card.source_kind === 'api')?.title).toBe('API（待开发）');
    expect(sourceKindLabel('api')).toBe('API（待开发）');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd finance-web
npm run test -- tests/components/data-source-config.test.ts
```

Expected: FAIL because file and desktop/CLI cards still exist and API label is still `API`.

- [ ] **Step 3: Update data source config**

In `finance-web/src/dataSourceConfig.ts`, remove the `file` and `desktop_cli` entries from `SOURCE_TYPE_CARDS`.

Change the API card to:

```typescript
{
  source_kind: 'api',
  title: 'API（待开发）',
  description: 'API 数据接入能力预留，后续开放配置和数据集生成',
  execution_mode: 'deterministic',
  provider_code: 'rest_api',
  behavior: 'reserved',
  accent: 'text-violet-700 bg-violet-50',
},
```

Change `sourceKindLabel`:

```typescript
if (kind === 'api') return 'API（待开发）';
```

Keep the `file`, `browser`, and `desktop_cli` label branches only if TypeScript requires exhaustive compatibility for existing data rows; they should no longer appear in the source-type navigation.

- [ ] **Step 4: Run config test**

Run:

```bash
cd finance-web
npm run test -- tests/components/data-source-config.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add finance-web/src/dataSourceConfig.ts finance-web/tests/components/data-source-config.test.ts
git commit -m "fix: simplify data connection source cards"
```

---

### Task 5: Rewrite BrowserPlaybookPanel As List + Modals

**Files:**
- Modify: `finance-web/src/components/BrowserPlaybookPanel.tsx`
- Test: `finance-web/tests/components/browser-playbook-panel.test.tsx`

- [ ] **Step 1: Write failing component tests**

Create `finance-web/tests/components/browser-playbook-panel.test.tsx`:

```typescript
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BrowserPlaybookPanel } from '../../src/components/BrowserPlaybookPanel';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('BrowserPlaybookPanel', () => {
  const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('renders list and opens the create modal with final fields only', async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/data-sources?source_kind=browser_playbook') {
        return jsonResponse({
          sources: [
            {
              id: 'source-1',
              name: '千牛每日资金账单',
              source_kind: 'browser_playbook',
              status: 'active',
              latest_sync_at: '2026-05-21T00:00:00Z',
              meta: { registration_title: '千牛每日资金账单' },
            },
          ],
        });
      }
      return jsonResponse({});
    });

    render(<BrowserPlaybookPanel authToken="token" />);

    expect(await screen.findByText('千牛每日资金账单')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '新增' }));

    expect(await screen.findByText('新增浏览器采集')).toBeInTheDocument();
    expect(screen.getByLabelText('标题')).toBeInTheDocument();
    expect(screen.getByLabelText('登录账号')).toBeInTheDocument();
    expect(screen.getByLabelText('密码')).toBeInTheDocument();
    expect(screen.getByLabelText('Playbook JSON')).toBeInTheDocument();
    expect(screen.queryByText('playbook_id')).not.toBeInTheDocument();
    expect(screen.queryByText('version')).not.toBeInTheDocument();
    expect(screen.queryByText(/egress_group/)).not.toBeInTheDocument();
    expect(screen.queryByText(/验证日期/)).not.toBeInTheDocument();
    expect(screen.queryByText(/落地数据集/)).not.toBeInTheDocument();
  });

  it('submits source-less registration endpoint and clears password', async () => {
    const requests: Array<{ url: string; body: Record<string, unknown> }> = [];

    fetchMock.mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/data-sources?source_kind=browser_playbook') {
        return jsonResponse({ sources: [] });
      }
      if (url === '/api/data-sources/browser-playbook/registrations') {
        requests.push({ url, body: JSON.parse(String(init?.body || '{}')) });
        return jsonResponse({
          success: true,
          status: 'verification_pending',
          source_id: 'source-1',
          verification_sync_job_id: 'sync-1',
          verification_biz_date: '2026-05-20',
          source: { id: 'source-1', name: '千牛每日资金账单' },
          dataset: { id: 'dataset-1', dataset_name: '千牛每日资金账单' },
        });
      }
      if (url === '/api/sync-jobs/sync-1') {
        return jsonResponse({ job: { id: 'sync-1', job_status: 'success' } });
      }
      return jsonResponse({});
    });

    render(<BrowserPlaybookPanel authToken="token" />);
    fireEvent.click(screen.getByRole('button', { name: '新增' }));
    fireEvent.change(await screen.findByLabelText('标题'), { target: { value: '千牛每日资金账单' } });
    fireEvent.change(screen.getByLabelText('登录账号'), { target: { value: 'finance_ops@example.com' } });
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'secret' } });
    fireEvent.change(screen.getByLabelText('Playbook JSON'), {
      target: { value: '{"schema_version":"1.0","steps":[]}' },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存并验证' }));

    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0]).toMatchObject({
      url: '/api/data-sources/browser-playbook/registrations',
      body: {
        title: '千牛每日资金账单',
        credential_username: 'finance_ops@example.com',
        credential_password: 'secret',
        playbook_body: { schema_version: '1.0', steps: [] },
      },
    });
    expect(screen.getByLabelText('密码')).toHaveValue('');
  });
});
```

- [ ] **Step 2: Run component test to verify it fails**

Run:

```bash
cd finance-web
npm run test -- tests/components/browser-playbook-panel.test.tsx
```

Expected: FAIL because the existing panel still renders the old form.

- [ ] **Step 3: Replace panel state model**

In `finance-web/src/components/BrowserPlaybookPanel.tsx`, keep imports minimal:

```typescript
import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Loader2, MonitorSmartphone, Plus, RefreshCw, X } from 'lucide-react';
```

Define types:

```typescript
interface BrowserRegistrationRow {
  id: string;
  name?: string;
  status?: string;
  latest_sync_at?: string;
  last_sync_at?: string;
  meta?: Record<string, unknown>;
}

interface BrowserRegistrationForm {
  title: string;
  credentialUsername: string;
  credentialPassword: string;
  playbookBodyText: string;
}
```

Use these states:

```typescript
const [rows, setRows] = useState<BrowserRegistrationRow[]>([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState('');
const [createOpen, setCreateOpen] = useState(false);
const [detailRow, setDetailRow] = useState<BrowserRegistrationRow | null>(null);
const [form, setForm] = useState<BrowserRegistrationForm>({
  title: '',
  credentialUsername: '',
  credentialPassword: '',
  playbookBodyText: '',
});
const [submitting, setSubmitting] = useState(false);
const [registerResult, setRegisterResult] = useState<RegisterResponse | null>(null);
```

- [ ] **Step 4: Implement list fetch**

Implement:

```typescript
const refreshRows = useCallback(async () => {
  if (!authToken) return;
  setLoading(true);
  setError('');
  try {
    const response = await fetch('/api/data-sources?source_kind=browser_playbook', { headers: authHeaders });
    if (!response.ok) throw new Error(`浏览器采集列表请求失败: ${response.status}`);
    const body = await response.json();
    setRows(((body?.sources ?? body?.data_sources ?? []) as BrowserRegistrationRow[]));
  } catch (e) {
    setError(String((e as Error)?.message || e));
  } finally {
    setLoading(false);
  }
}, [authHeaders, authToken]);
```

Call it from `useEffect`.

- [ ] **Step 5: Implement source-less submit**

Implement:

```typescript
const handleCreate = useCallback(async () => {
  if (!authToken) {
    setError('未登录');
    return;
  }
  let parsedBody: unknown;
  try {
    parsedBody = JSON.parse(form.playbookBodyText || '{}');
  } catch (e) {
    setError(`Playbook JSON 解析失败: ${(e as Error).message}`);
    return;
  }
  if (!form.title.trim() || !form.credentialUsername.trim() || !form.credentialPassword || !parsedBody || typeof parsedBody !== 'object') {
    setError('请填写标题、登录账号、密码和有效的 Playbook JSON');
    return;
  }

  setSubmitting(true);
  setError('');
  try {
    const response = await fetch('/api/data-sources/browser-playbook/registrations', {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify({
        title: form.title.trim(),
        credential_username: form.credentialUsername.trim(),
        credential_password: form.credentialPassword,
        playbook_body: parsedBody,
      }),
    });
    const body = await response.json();
    if (!response.ok || !body?.success) {
      setError(String(body?.detail || body?.error || '注册失败'));
      return;
    }
    setRegisterResult(body as RegisterResponse);
    setForm((current) => ({ ...current, credentialPassword: '' }));
    await refreshRows();
  } catch (e) {
    setError(String((e as Error)?.message || e));
  } finally {
    setSubmitting(false);
  }
}, [authHeaders, authToken, form, refreshRows]);
```

- [ ] **Step 6: Render final UI**

Render:

- Header title `浏览器`
- Header buttons `刷新` and `新增`
- Table/list columns: `标题`, `登录账号`, `状态`, `最近采集`
- New modal labels exactly: `标题`, `登录账号`, `密码`, `Playbook JSON`
- Detail modal with same user-facing fields and no plaintext password

Use accessible labels like this exact pattern:

```tsx
<label>
  <span>标题</span>
  <input
    aria-label="标题"
    value={form.title}
    onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
  />
</label>
```

Make row buttons open `setDetailRow(row)`.

- [ ] **Step 7: Run component test**

Run:

```bash
cd finance-web
npm run test -- tests/components/browser-playbook-panel.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add finance-web/src/components/BrowserPlaybookPanel.tsx finance-web/tests/components/browser-playbook-panel.test.tsx
git commit -m "feat: simplify browser collection registration ui"
```

---

### Task 6: Integration Verification And Service Restart

**Files:**
- No source changes unless tests expose issues.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest finance-mcp/tests/test_browser_playbook_source_less_registration.py finance-agents/data-agent/tests/test_browser_playbook_registration_api.py -v
```

Expected: PASS.

- [ ] **Step 2: Run focused browser-agent test**

Run:

```bash
pytest finance-agents/browser-agent/tests/test_playwright_profile_login_state.py -v
```

Expected: PASS.

- [ ] **Step 3: Run focused frontend tests**

Run:

```bash
cd finance-web
npm run test -- tests/components/data-source-config.test.ts tests/components/browser-playbook-panel.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Type-check frontend**

Run:

```bash
cd finance-web
npx tsc --noEmit
```

Expected: PASS.

- [ ] **Step 5: Restart services**

Because this changes data-agent, finance-mcp, and finance-web behavior, run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web, data-agent, finance-mcp, and browser-agent start without errors.

- [ ] **Step 6: Smoke check endpoints**

Run:

```bash
curl -s http://127.0.0.1:3335/health
curl -s http://127.0.0.1:8100/health
curl -I http://127.0.0.1:5173
```

Expected: MCP/data-agent health responses are successful and finance-web returns HTTP 200.

- [ ] **Step 7: Commit any verification fixes**

If verification required fixes, commit only those fixes. Example for a frontend-only type fix:

```bash
git add finance-web/src/components/BrowserPlaybookPanel.tsx
git commit -m "fix: complete browser collection registration integration"
```

---

## Self-Review

Spec coverage:

- UI list + new/detail modals: Task 5.
- Removed cards and API label: Task 4.
- Source-less backend registration with automatic source/dataset/playbook/version/T-1: Task 1 and Task 2.
- No user-facing source_id/playbook_id/version/egress_group/date/dataset: Task 5 tests and Task 1/2 API design.
- Profile-login-state first runtime rule: Task 3.
- Verification: Task 6.

Placeholder scan: no TBD/TODO placeholders are intentionally left in this plan.

Type consistency:

- Backend request uses `title`, `credential_username`, `credential_password`, `playbook_body`.
- Frontend form fields map to that request exactly.
- Response uses `source`, `dataset`, `verification_sync_job_id`, `verification_biz_date`, matching backend/data-agent tests.

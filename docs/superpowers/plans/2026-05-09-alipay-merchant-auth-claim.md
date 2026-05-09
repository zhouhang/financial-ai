# Alipay Merchant Auth Claim Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持支付宝开放平台“商家授权”无 `state` 回调，先保存待认领授权，再由 Tally 管理员用认领码绑定到当前企业并复用现有支付宝账单采集能力。

**Architecture:** 后端新增 `platform_pending_authorizations` 作为无 `state` 支付宝回调的安全缓冲区，回调时立即换取 `app_auth_token` 并保存密文 token。认领接口负责把待认领授权绑定为现有 `shop_connections`、`shop_authorizations`、`trade/signcustomer` 数据集，并触发 T-1 初始化采集；data-agent 仅转发 MCP 工具，前端展示固定二维码/PC 链接和认领表单。

**Tech Stack:** Python FastAPI/MCP、PostgreSQL migrations、React + TypeScript、Vitest/pytest。

---

### File Structure

- Create: `finance-mcp/auth/migrations/026_platform_pending_authorizations.sql`
  - 新建待认领支付宝授权表、状态约束、索引和更新时间触发器。
- Modify: `finance-mcp/auth/db.py`
  - 增加 schema ensure、待认领 CRUD、token 密封/解密 helper、跨企业绑定检查。
- Modify: `finance-mcp/tools/platform_connections.py`
  - 增加工具定义和 handler；支持支付宝应用配置中的固定商家授权入口；实现无 `state` 支付宝回调和管理员认领。
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
  - 增加 pending list / claim MCP client wrapper。
- Modify: `finance-agents/data-agent/graphs/platform/api.py`
  - 增加 REST API；回调重定向携带认领码和 pending id。
- Modify: `finance-web/src/components/DataConnectionsPanel.tsx`
  - 在支付宝授权页展示固定授权入口、待认领列表和认领表单；回调页显示认领码。
- Test: `finance-mcp/tests/test_platform_connections_alipay.py`
  - 覆盖无 `state` 回调、待认领脱敏、认领成功和错误分支。
- Test: `finance-agents/data-agent/tests/recon/test_platform_auth_real_mode.py`
  - 覆盖 data-agent 新 API 转发和回调 query 参数。
- Test: `finance-web/tests/components/data-connections-platform-auth.spec.tsx`
  - 覆盖支付宝授权入口展示、待认领列表、认领提交和无 `state` 回调显示。

### Task 1: Database Pending Authorization Model

**Files:**
- Create: `finance-mcp/auth/migrations/026_platform_pending_authorizations.sql`
- Modify: `finance-mcp/auth/db.py`
- Test: `finance-mcp/tests/test_platform_connections_alipay.py`

- [ ] **Step 1: Write failing DB helper tests**

Add tests that monkeypatch `auth_db` helpers at the tool layer first:

```python
@pytest.mark.anyio
async def test_alipay_no_state_callback_creates_pending_claim(monkeypatch) -> None:
    created: dict[str, Any] = {}
    token = PlatformTokenBundle(
        access_token="app-auth-token",
        refresh_token="app-refresh-token",
        expires_in=3600,
        refresh_expires_in=7200,
        raw_payload={"user_id": "2088000000000001", "auth_app_id": "2021000000000000"},
    )

    class FakeConnector:
        def exchange_code_for_token(self, **kwargs: Any) -> PlatformTokenBundle:
            assert kwargs["code"] == "P01-auth-code"
            return token

        def fetch_shop_profile(self, **kwargs: Any) -> PlatformShopProfile:
            return PlatformShopProfile(
                external_shop_id="2088000000000001",
                external_shop_name="2088000000000001",
                external_seller_id="2021000000000000",
                auth_subject_name="2088000000000001",
                shop_type="merchant",
                metadata={"platform": "alipay"},
            )

    monkeypatch.setattr(platform_connections.auth_db, "get_auth_session_by_state", lambda state: None)
    monkeypatch.setattr(platform_connections, "_load_app_config", lambda *args, **kwargs: PlatformAppConfig(
        platform_code="alipay",
        app_key="2021006152656574",
        app_secret="PRIVATE",
        redirect_uri="https://dev.tallyai.cn/api/platform-auth/callback/alipay",
        auth_mode="real",
        id="app-1",
    ))
    monkeypatch.setattr(platform_connections, "build_connector", lambda app_config: FakeConnector())
    monkeypatch.setattr(platform_connections.auth_db, "create_platform_pending_authorization", lambda **kwargs: created.update(kwargs) or {
        "id": "pending-1",
        "claim_code": "ALIPAY-123456",
        "status": "pending_claim",
        **kwargs,
    })

    result = await platform_connections._handle_auth_callback({
        "platform_code": "alipay",
        "state": "",
        "callback_payload": {
            "app_auth_code": "P01-auth-code",
            "app_id": "2021006152656574",
            "source": "alipay_app_auth",
        },
    })

    assert result["success"] is True
    assert result["pending_authorization"]["claim_code"] == "ALIPAY-123456"
    assert created["access_token"] == "app-auth-token"
    assert created["external_shop_id"] == "2088000000000001"
```

- [ ] **Step 2: Run RED**

Run: `source .venv/bin/activate && pytest finance-mcp/tests/test_platform_connections_alipay.py::test_alipay_no_state_callback_creates_pending_claim -v`
Expected: FAIL because `create_platform_pending_authorization` and no-state callback branch do not exist.

- [ ] **Step 3: Add migration**

Create `026_platform_pending_authorizations.sql` with:

```sql
CREATE TABLE IF NOT EXISTS public.platform_pending_authorizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    platform_code varchar(64) NOT NULL,
    platform_app_id uuid NULL REFERENCES public.platform_apps(id) ON DELETE SET NULL,
    app_id varchar(128) NOT NULL DEFAULT '',
    source varchar(128) NOT NULL DEFAULT '',
    claim_code varchar(64) NOT NULL,
    status varchar(32) NOT NULL DEFAULT 'pending_claim',
    access_token text NOT NULL DEFAULT '',
    refresh_token text NOT NULL DEFAULT '',
    token_expires_at timestamptz NULL,
    refresh_expires_at timestamptz NULL,
    raw_auth_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    callback_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    external_shop_id varchar(255) NOT NULL DEFAULT '',
    external_seller_id varchar(255) NOT NULL DEFAULT '',
    merchant_display_name varchar(255) NOT NULL DEFAULT '',
    claimed_company_id uuid NULL REFERENCES public.company(id) ON DELETE SET NULL,
    claimed_by_user_id uuid NULL REFERENCES public.users(id) ON DELETE SET NULL,
    claimed_shop_connection_id uuid NULL REFERENCES public.shop_connections(id) ON DELETE SET NULL,
    claimed_at timestamptz NULL,
    expires_at timestamptz NOT NULL,
    last_error text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT platform_pending_authorizations_status_check
        CHECK (status IN ('pending_claim', 'claimed', 'expired', 'failed', 'discarded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_pending_authorizations_claim_code_active
    ON public.platform_pending_authorizations (claim_code)
    WHERE status = 'pending_claim';

CREATE INDEX IF NOT EXISTS idx_platform_pending_authorizations_platform_status
    ON public.platform_pending_authorizations (platform_code, status, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_platform_pending_authorizations_external_shop
    ON public.platform_pending_authorizations (platform_code, external_shop_id);

CREATE OR REPLACE FUNCTION public.update_platform_pending_authorizations_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_platform_pending_authorizations_updated_at
    ON public.platform_pending_authorizations;
CREATE TRIGGER update_platform_pending_authorizations_updated_at
    BEFORE UPDATE ON public.platform_pending_authorizations
    FOR EACH ROW
    EXECUTE FUNCTION public.update_platform_pending_authorizations_updated_at();
```

- [ ] **Step 4: Add DB helpers**

In `finance-mcp/auth/db.py`:

```python
_PLATFORM_PENDING_AUTHORIZATIONS_SCHEMA_READY = False
```

Add `ensure_platform_pending_authorizations_schema()` mirroring `ensure_auth_sessions_extra_schema()`, then call it at the start of every new helper.

Add helpers:

```python
def create_platform_pending_authorization(...) -> dict | None:
    # seal access_token/refresh_token, insert pending_claim, return without token plaintext

def list_platform_pending_authorizations(*, platform_code: str, status: str = "pending_claim", limit: int = 50) -> list[dict]:
    # return records with access_token/refresh_token removed

def get_platform_pending_authorization_by_id(pending_authorization_id: str, *, include_secrets: bool = False) -> dict | None:
    # decrypt token only when include_secrets=True

def get_platform_pending_authorization_by_claim_code(claim_code: str, *, include_secrets: bool = False) -> dict | None:
    # decrypt token only when include_secrets=True

def mark_platform_pending_authorization_claimed(...) -> dict | None:
    # set status claimed and audit fields

def mark_platform_pending_authorization_failed(...) -> dict | None:
    # set failed/expired/discarded and last_error

def find_shop_connection_by_platform_external_shop(platform_code: str, external_shop_id: str) -> dict | None:
    # no company filter; used to block cross-company binding
```

- [ ] **Step 5: Run GREEN for DB helper-adjacent tests**

Run: `source .venv/bin/activate && pytest finance-mcp/tests/test_platform_connections_alipay.py::test_alipay_no_state_callback_creates_pending_claim -v`
Expected: PASS after Task 2 callback code is implemented.

### Task 2: MCP No-State Callback And Claim Tools

**Files:**
- Modify: `finance-mcp/tools/platform_connections.py`
- Test: `finance-mcp/tests/test_platform_connections_alipay.py`

- [ ] **Step 1: Write failing claim tests**

Add tests:

```python
@pytest.mark.anyio
async def test_claim_pending_alipay_authorization_creates_connection_authorization_datasets_and_jobs(monkeypatch) -> None:
    calls: dict[str, Any] = {"sync_sources": [], "jobs": []}
    pending = {
        "id": "pending-1",
        "platform_code": "alipay",
        "platform_app_id": "app-1",
        "claim_code": "ALIPAY-123456",
        "status": "pending_claim",
        "access_token": "app-auth-token",
        "refresh_token": "app-refresh-token",
        "external_shop_id": "2088000000000001",
        "external_seller_id": "2021000000000000",
        "raw_auth_payload": {"user_id": "2088000000000001"},
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }

    monkeypatch.setattr(platform_connections, "_require_user", lambda token: {
        "company_id": "company-1",
        "user_id": "user-1",
        "role": "admin",
    })
    monkeypatch.setattr(platform_connections.auth_db, "get_platform_pending_authorization_by_id", lambda pending_authorization_id, include_secrets=False: pending)
    monkeypatch.setattr(platform_connections.auth_db, "find_shop_connection_by_platform_external_shop", lambda platform_code, external_shop_id: None)
    monkeypatch.setattr(platform_connections.auth_db, "upsert_shop_connection", lambda **kwargs: {"id": "shop-1", **kwargs})
    monkeypatch.setattr(platform_connections.auth_db, "create_shop_authorization", lambda **kwargs: {"id": "auth-1", **kwargs})
    monkeypatch.setattr(platform_connections.auth_db, "upsert_sync_source", lambda **kwargs: calls["sync_sources"].append(kwargs) or {"id": f"source-{kwargs['source_type']}"})
    monkeypatch.setattr(platform_connections, "_upsert_alipay_bill_datasets", lambda **kwargs: (
        {"id": "source-1"},
        {"id": "fund-dataset", "resource_key": "alipay_bill:signcustomer:shop-1"},
        {"id": "trade-dataset", "resource_key": "alipay_bill:trade:shop-1"},
    ))
    monkeypatch.setattr(platform_connections, "_build_alipay_initial_collection_jobs", lambda **kwargs: [{"dataset_id": kwargs["dataset_id"], "bill_type": kwargs["bill_type"]}])
    monkeypatch.setattr(platform_connections.auth_db, "mark_platform_pending_authorization_claimed", lambda **kwargs: {"id": "pending-1", "status": "claimed", **kwargs})

    async def fake_run_jobs(**kwargs: Any) -> None:
        calls["jobs"].extend(kwargs["jobs"])

    monkeypatch.setattr(platform_connections, "_run_alipay_initial_collection_jobs", fake_run_jobs)

    result = await platform_connections._handle_claim_pending_authorization({
        "auth_token": "token",
        "pending_authorization_id": "pending-1",
        "claim_code": "ALIPAY-123456",
        "merchant_display_name": "福游网络",
    })

    assert result["success"] is True
    assert result["shop"]["id"] == "shop-1"
    assert {item["source_type"] for item in calls["sync_sources"]} == {"orders", "refunds", "settlements", "bills"}
    assert {job["bill_type"] for job in calls["jobs"]} == {"signcustomer", "trade"}
```

Add negative tests for wrong claim code, expired pending record, and existing other-company binding.

- [ ] **Step 2: Run RED**

Run: `source .venv/bin/activate && pytest finance-mcp/tests/test_platform_connections_alipay.py::test_claim_pending_alipay_authorization_creates_connection_authorization_datasets_and_jobs -v`
Expected: FAIL because claim handler does not exist.

- [ ] **Step 3: Extend MCP tool registry**

In `create_tools()` add:

```python
Tool(name="platform_list_pending_authorizations", ...)
Tool(name="platform_claim_pending_authorization", ...)
```

In `handle_tool_call()` route to `_handle_list_pending_authorizations()` and `_handle_claim_pending_authorization()`.

- [ ] **Step 4: Add app config fields**

Extend upsert/get public config for Alipay:

```python
merchant_auth_mode = "static_invite"
merchant_auth_pc_url = str(arguments.get("merchant_auth_pc_url") or existing_extra.get("merchant_auth_pc_url") or "")
merchant_auth_qr_url = str(arguments.get("merchant_auth_qr_url") or existing_extra.get("merchant_auth_qr_url") or "")
```

Return these fields in `_public_app_config()` only, not secrets.

- [ ] **Step 5: Implement no-state callback branch**

At the top of `_handle_auth_callback()`:

```python
if not state and platform_code == "alipay" and (callback_payload.get("app_auth_code") or code):
    return await _handle_alipay_merchant_auth_callback(arguments)
```

`_handle_alipay_merchant_auth_callback()` loads service provider app config, exchanges token immediately, fetches shop profile, generates `claim_code`, creates pending auth, and returns:

```python
{
    "success": True,
    "platform_code": "alipay",
    "pending_authorization": _public_pending_authorization(pending),
    "claim_code": pending["claim_code"],
    "message": "支付宝授权已收到，请在 Tally 输入认领码完成绑定",
    "return_path": "/data-connections?mode=platform&platform=alipay",
}
```

- [ ] **Step 6: Implement claim handler**

`_handle_claim_pending_authorization()` must:

1. Require logged-in user.
2. Load pending record by id or claim code with secrets.
3. Validate status `pending_claim`, expires_at not expired, claim code matches.
4. Block if `find_shop_connection_by_platform_external_shop()` returns a different company.
5. Upsert shop connection and shop authorization.
6. Upsert sync sources and Alipay datasets.
7. Trigger initial collection jobs.
8. Mark pending claimed.
9. Return shop, pending, dataset ids, and warning if dataset init fails.

- [ ] **Step 7: Run GREEN**

Run: `source .venv/bin/activate && pytest finance-mcp/tests/test_platform_connections_alipay.py -v`
Expected: PASS.

### Task 3: Data-Agent API Layer

**Files:**
- Modify: `finance-agents/data-agent/tools/mcp_client.py`
- Modify: `finance-agents/data-agent/graphs/platform/api.py`
- Test: `finance-agents/data-agent/tests/recon/test_platform_auth_real_mode.py`

- [ ] **Step 1: Add failing API tests**

Add tests that patch MCP wrappers and assert:

```python
GET /platform-connections/alipay/pending-authorizations
POST /platform-connections/alipay/pending-authorizations/{id}/claim
```

Also assert callback redirect includes `pending_authorization_id` and `claim_code` when MCP result contains them.

- [ ] **Step 2: Run RED**

Run: `source .venv/bin/activate && pytest finance-agents/data-agent/tests/recon/test_platform_auth_real_mode.py -v`
Expected: FAIL for missing endpoints / query params.

- [ ] **Step 3: Add MCP wrappers**

In `mcp_client.py`:

```python
async def platform_list_pending_authorizations(auth_token: str, platform_code: str, *, status: str = "pending_claim", mode: str = "") -> dict[str, Any]:
    return await call_mcp_tool("platform_list_pending_authorizations", {...})

async def platform_claim_pending_authorization(auth_token: str, platform_code: str, pending_authorization_id: str, *, claim_code: str, merchant_display_name: str, mode: str = "") -> dict[str, Any]:
    return await call_mcp_tool("platform_claim_pending_authorization", {...})
```

- [ ] **Step 4: Add FastAPI models and routes**

In `api.py`, add Pydantic response/request models, import wrappers, and routes:

```python
@router.get("/platform-connections/{platform_code}/pending-authorizations")
async def list_pending_authorizations(...)

@router.post("/platform-connections/{platform_code}/pending-authorizations/{pending_authorization_id}/claim")
async def claim_pending_authorization(...)
```

Reject non-Alipay pending endpoints with 400 for now.

- [ ] **Step 5: Extend callback redirect**

Add optional params to `_build_callback_redirect_url()`:

```python
pending_authorization_id: str = "",
claim_code: str = "",
```

Include them in query pairs when present.

- [ ] **Step 6: Run GREEN**

Run: `source .venv/bin/activate && pytest finance-agents/data-agent/tests/recon/test_platform_auth_real_mode.py -v`
Expected: PASS.

### Task 4: Frontend Alipay Claim UX

**Files:**
- Modify: `finance-web/src/components/DataConnectionsPanel.tsx`
- Test: `finance-web/tests/components/data-connections-platform-auth.spec.tsx`

- [ ] **Step 1: Write failing UI tests**

Add tests:

```typescript
it('支付宝授权页展示固定二维码和 PC 授权链接', async () => {
  // app-config returns merchant_auth_pc_url and merchant_auth_qr_url
  // click 支付宝 查看店铺
  // expect image alt 支付宝商家授权二维码 and link/button 打开支付宝商家授权
});

it('管理员可输入认领码绑定支付宝待认领授权', async () => {
  // pending endpoint returns one pending record
  // fill claim code + merchant name
  // POST /api/platform-connections/alipay/pending-authorizations/pending-1/claim
  // assert shops refreshed
});

it('无 state 支付宝回调页展示认领码', async () => {
  render with initialCallback containing claim_code and pending_authorization_id
  expect claim code visible
});
```

- [ ] **Step 2: Run RED**

Run: `cd finance-web && npm run test -- data-connections-platform-auth.spec.tsx`
Expected: FAIL because UI and APIs are missing.

- [ ] **Step 3: Extend types and config form state**

Add fields to `PlatformAppConfigFormState`:

```typescript
merchantAuthMode: string;
merchantAuthPcUrl: string;
merchantAuthQrUrl: string;
```

Add pending authorization type and state:

```typescript
interface PlatformPendingAuthorization { id: string; claim_code?: string; ... }
const [alipayPendingAuthorizations, setAlipayPendingAuthorizations] = useState<PlatformPendingAuthorization[]>([]);
const [alipayClaimForm, setAlipayClaimForm] = useState({ pendingAuthorizationId: '', claimCode: '', merchantDisplayName: '' });
```

- [ ] **Step 4: Load and save static auth entry fields**

Include merchant auth fields in app-config GET/PUT for Alipay:

```typescript
merchant_auth_mode: form.merchantAuthMode || 'static_invite',
merchant_auth_pc_url: form.merchantAuthPcUrl.trim(),
merchant_auth_qr_url: form.merchantAuthQrUrl.trim(),
```

- [ ] **Step 5: Add pending fetch and claim functions**

Use:

```typescript
GET /api/platform-connections/alipay/pending-authorizations?status=pending_claim&mode=real
POST /api/platform-connections/alipay/pending-authorizations/${id}/claim
```

Payload:

```typescript
{ claim_code: claimCode.trim(), merchant_display_name: merchantDisplayName.trim(), mode: 'real' }
```

After success, refresh pending list, shops, platforms, and remote sources.

- [ ] **Step 6: Render Alipay merchant auth section**

When selected platform is Alipay, render:

- Static QR image when configured.
- PC link button when configured.
- Pending list.
- Claim form with claim code and merchant display name.
- Do not expose tokens.

- [ ] **Step 7: Render callback claim code**

In callback mode, if `callbackPayload.claim_code` exists, show claim code and “前往支付宝授权页” action.

- [ ] **Step 8: Run GREEN**

Run: `cd finance-web && npm run test -- data-connections-platform-auth.spec.tsx`
Expected: PASS.

### Task 5: Verification, Service Restart, Commit

**Files:**
- All modified files.

- [ ] **Step 1: Run backend targeted tests**

Run:

```bash
source .venv/bin/activate
pytest finance-mcp/tests/test_platform_connections_alipay.py -v
pytest finance-agents/data-agent/tests/recon/test_platform_auth_real_mode.py -v
```

Expected: PASS.

- [ ] **Step 2: Run frontend targeted tests**

Run:

```bash
cd finance-web
npm run test -- data-connections-platform-auth.spec.tsx
```

Expected: PASS.

- [ ] **Step 3: Restart services**

Run:

```bash
cd /Users/kevin/workspace/financial-ai
./START_ALL_SERVICES.sh
```

Expected: finance-web、data-agent、finance-mcp restart without immediate startup failure.

- [ ] **Step 4: Check git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: only planned files plus pre-existing unrelated `finance-web/src/App.tsx`, `finance-web/vite.config.ts`, recon output files, and untracked chat test remain.

- [ ] **Step 5: Commit planned changes**

Run:

```bash
git add -f docs/superpowers/plans/2026-05-09-alipay-merchant-auth-claim.md
git add finance-mcp/auth/migrations/026_platform_pending_authorizations.sql finance-mcp/auth/db.py finance-mcp/tools/platform_connections.py finance-mcp/tests/test_platform_connections_alipay.py finance-agents/data-agent/tools/mcp_client.py finance-agents/data-agent/graphs/platform/api.py finance-agents/data-agent/tests/recon/test_platform_auth_real_mode.py finance-web/src/components/DataConnectionsPanel.tsx finance-web/tests/components/data-connections-platform-auth.spec.tsx
git commit -m "feat: support alipay merchant auth claim flow"
```

Expected: commit succeeds and does not include unrelated worktree files.

### Self-Review

- Spec coverage: covers fixed Alipay merchant auth entry, no-state callback, immediate token exchange, pending claim, admin binding, dataset creation, initial collection trigger, API routes, UI, and callback page.
- Placeholder scan: no TBD/TODO/later placeholders.
- Type consistency: pending authorization id is `pending_authorization_id` in MCP/API payloads and `pendingAuthorizationId` only in React local state.

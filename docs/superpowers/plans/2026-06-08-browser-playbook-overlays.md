# Browser Playbook Overlays Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace site-specific hardcoded popup dismissal in the browser runner with a generic top-level `playbook_body.overlays` contract, then migrate QianNiu order and bill-detail playbooks to use it.

**Architecture:** `finance-mcp` validates top-level overlay definitions, and `finance-agents/browser-agent` treats them as generic runtime configuration. The Playwright runner receives parsed overlays for each run and calls a generic dismiss helper before interaction actions; all QianNiu-specific popup selectors move to playbook JSON stored in local PostgreSQL and ECS/RDS.

**Tech Stack:** Python 3.12, Pydantic, Playwright sync API, pytest, PostgreSQL JSONB, SSH to ECS container.

---

## File Structure

- Modify `finance-mcp/browser_playbook/models.py` for `PlaybookOverlay` and `PlaybookBody.overlays`.
- Modify `finance-mcp/tests/test_browser_playbook_schema.py` for schema acceptance and validation tests.
- Modify `finance-agents/browser-agent/finance_browser_agent/playbook_interpreter.py` only if action validation needs awareness of top-level playbook fields; otherwise leave unchanged.
- Replace most of `finance-agents/browser-agent/tests/test_playwright_runner_overlays.py` with tests for configured overlays, not hardcoded QianNiu overlays.
- Modify `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py` to remove `_KNOWN_OVERLAY_*` constants and route interactions through configured overlays.
- Add or update test helpers in `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py` for `download_history_file` overlay invocation.
- Modify `AGENTS.md` to record the browser collection playbook-first development preference.
- Update local PostgreSQL and ECS/RDS `playbooks.playbook_body` JSONB data. Do not encode this migration in application startup code.

## Shared Overlay Definitions For Migration

Use these playbook overlay objects for active QianNiu playbooks.

For both store-order and bill-detail playbooks:

```json
[
  {
    "id": "qianniu_warning_notice",
    "markers": [
      "text=预警通知",
      ".normal_headTitle__iJ44s:has-text('预警通知')"
    ],
    "close_selectors": [
      ".notify_headRight__XdjnE .next-icon-close_blod",
      "[class*='notify_headRight'] .next-icon-close_blod",
      "[class*='notify_headRight'] [class*='next-icon-close']",
      ".normal_container__13Xbj button:has-text('知道了')",
      ".normal_container__13Xbj button:has-text('确定')",
      ".normal_container__13Xbj button:has-text('关闭')",
      ".normal_container__13Xbj button:has-text('我知道了')",
      ".normal_container__13Xbj [role='button']:has-text('知道了')",
      ".normal_container__13Xbj [role='button']:has-text('确定')",
      ".normal_container__13Xbj .next-dialog-close",
      ".normal_container__13Xbj .next-icon-close",
      ".container--SMNuCb74 button:has-text('知道了')",
      ".container--SMNuCb74 button:has-text('确定')",
      ".container--SMNuCb74 button:has-text('关闭')",
      ".container--SMNuCb74 [role='button']:has-text('知道了')",
      ".container--SMNuCb74 [role='button']:has-text('确定')",
      ".container--SMNuCb74 .next-dialog-close",
      ".container--SMNuCb74 .next-icon-close"
    ]
  },
  {
    "id": "qianniu_guidance",
    "markers": [
      "text=新手引导",
      "text=操作指引",
      "text=功能介绍",
      "text=下次再说",
      ".driver-popover",
      ".driver-overlay"
    ],
    "close_selectors": [
      "button.driver-popover-close-btn",
      ".driver-popover button.driver-popover-close-btn",
      ".driver-popover .driver-popover-close-btn",
      ".driver-popover button:has-text('跳过')",
      ".driver-popover button:has-text('关闭')",
      ".driver-popover button:has-text('知道了')",
      ".driver-popover button:has-text('我知道了')",
      "button.driver-popover-next-btn:has-text('完成')",
      ".driver-popover button.driver-popover-next-btn:has-text('完成')",
      ".driver-popover .driver-popover-next-btn:has-text('完成')",
      "button.driver-popover-next-btn:has-text('下一步')",
      ".driver-popover button.driver-popover-next-btn:has-text('下一步')",
      ".driver-popover .driver-popover-next-btn:has-text('下一步')",
      ".next-dialog button:has-text('完成')",
      ".next-dialog button:has-text('跳过')",
      ".next-dialog button:has-text('关闭')",
      ".next-dialog button:has-text('知道了')",
      ".next-dialog .next-dialog-close",
      ".next-balloon button:has-text('完成')",
      ".next-balloon button:has-text('跳过')",
      ".next-balloon button:has-text('关闭')",
      ".next-balloon .next-balloon-close",
      "[class*='guide'] button:has-text('完成')",
      "[class*='guide'] button:has-text('跳过')",
      "[class*='guide'] button:has-text('关闭')",
      "[class*='Guide'] button:has-text('完成')",
      "[class*='Guide'] button:has-text('跳过')",
      "[class*='Guide'] button:has-text('关闭')"
    ]
  }
]
```

Add this extra overlay only to bill-detail playbooks:

```json
{
  "id": "qianniu_finance_survey",
  "markers": [
    ".aes-survey-hanging",
    "[class*='aes-survey-hanging']",
    "text=财务管理工具"
  ],
  "close_selectors": [
    ".aes-survey-hanging--close",
    "[class*='aes-survey-hanging--close']"
  ]
}
```

## Task 1: Add Playbook Overlay Schema

**Files:**
- Modify: `finance-mcp/browser_playbook/models.py`
- Test: `finance-mcp/tests/test_browser_playbook_schema.py`

- [ ] **Step 1: Write schema acceptance test**

Add this test after `test_playbook_accepts_download_history_file_action` in `finance-mcp/tests/test_browser_playbook_schema.py`:

```python
def test_playbook_accepts_top_level_overlays() -> None:
    playbook = _valid_playbook_body()
    playbook["overlays"] = [
        {
            "id": "finance_survey",
            "markers": [".aes-survey-hanging", "text=财务管理工具"],
            "close_selectors": [".aes-survey-hanging--close"],
        }
    ]

    msg = RunPlaybookMessage.model_validate(
        {
            "job_id": "job-001",
            "shop_id": "shop-001",
            "playbook_id": "qianniu-daily-bill-export",
            "playbook_version": "1.0.0",
            "playbook_body": playbook,
            "params": {"biz_date": "2026-05-18"},
            "runtime_profile_ref": "profiles/shop-001",
        }
    )

    assert msg.playbook_body.overlays[0].id == "finance_survey"
    assert msg.playbook_body.overlays[0].markers == [
        ".aes-survey-hanging",
        "text=财务管理工具",
    ]
    assert msg.playbook_body.overlays[0].close_selectors == [".aes-survey-hanging--close"]
```

- [ ] **Step 2: Write schema validation test**

Add this test in the same file:

```python
def test_playbook_rejects_overlay_without_markers_or_close_selectors() -> None:
    playbook = _valid_playbook_body()
    playbook["overlays"] = [
        {
            "id": "finance_survey",
            "markers": [],
            "close_selectors": [],
        }
    ]

    with pytest.raises(ValidationError) as exc_info:
        RunPlaybookMessage.model_validate(
            {
                "job_id": "job-001",
                "shop_id": "shop-001",
                "playbook_id": "qianniu-daily-bill-export",
                "playbook_version": "1.0.0",
                "playbook_body": playbook,
                "params": {"biz_date": "2026-05-18"},
                "runtime_profile_ref": "profiles/shop-001",
            }
        )

    assert "overlays.markers cannot be empty" in str(exc_info.value)
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -m pytest \
  finance-mcp/tests/test_browser_playbook_schema.py::test_playbook_accepts_top_level_overlays \
  finance-mcp/tests/test_browser_playbook_schema.py::test_playbook_rejects_overlay_without_markers_or_close_selectors \
  -q
```

Expected: the first test fails because `PlaybookBody` has no `overlays` field, or the second fails because there is no overlay validation.

- [ ] **Step 4: Implement schema model**

In `finance-mcp/browser_playbook/models.py`, add this class before `PlaybookBody`:

```python
class PlaybookOverlay(BaseModel):
    id: str
    markers: list[str]
    close_selectors: list[str]

    @model_validator(mode="after")
    def validate_overlay(self) -> "PlaybookOverlay":
        if not self.id.strip():
            raise ValueError("overlays.id cannot be empty")
        self.markers = [selector.strip() for selector in self.markers if selector.strip()]
        self.close_selectors = [
            selector.strip()
            for selector in self.close_selectors
            if selector.strip()
        ]
        if not self.markers:
            raise ValueError("overlays.markers cannot be empty")
        if not self.close_selectors:
            raise ValueError("overlays.close_selectors cannot be empty")
        return self
```

Then add this field to `PlaybookBody`:

```python
    overlays: list[PlaybookOverlay] = Field(default_factory=list)
```

- [ ] **Step 5: Run schema tests to verify pass**

Run the same pytest command from Step 3.

Expected: both tests pass.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add finance-mcp/browser_playbook/models.py finance-mcp/tests/test_browser_playbook_schema.py
git commit -m "feat: validate browser playbook overlays"
```

## Task 2: Replace Hardcoded Overlay Dismissal With Configured Overlay Helper

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Modify: `finance-agents/browser-agent/tests/test_playwright_runner_overlays.py`

- [ ] **Step 1: Replace overlay tests with configured behavior tests**

Rewrite `finance-agents/browser-agent/tests/test_playwright_runner_overlays.py` so it imports `_dismiss_configured_overlays` and uses this focused content:

```python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance_browser_agent.playwright_runner import _dismiss_configured_overlays


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str, *, visible: bool = False) -> None:
        self.page = page
        self.selector = selector
        self._visible = visible
        self.first = self

    def is_visible(self, timeout: int = 0) -> bool:
        self.page.visibility_checks.append((self.selector, timeout))
        return self._visible

    def click(self, timeout: int = 0) -> None:
        self.page.click_attempts.append((self.selector, timeout))
        if self.selector in self.page.failing_click_selectors:
            raise RuntimeError("not clickable")
        if self.selector not in self.page.visible_selectors:
            raise RuntimeError("not found")
        self.page.clicks.append((self.selector, timeout))


class FakePage:
    def __init__(
        self,
        visible_selectors: set[str],
        *,
        failing_click_selectors: set[str] | None = None,
    ) -> None:
        self.visible_selectors = visible_selectors
        self.failing_click_selectors = failing_click_selectors or set()
        self.visibility_checks: list[tuple[str, int]] = []
        self.click_attempts: list[tuple[str, int]] = []
        self.clicks: list[tuple[str, int]] = []
        self.waits: list[int] = []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector, visible=selector in self.visible_selectors)

    def wait_for_timeout(self, delay_ms: int) -> None:
        self.waits.append(delay_ms)


def test_dismiss_configured_overlays_skips_when_marker_is_missing() -> None:
    page = FakePage({".close"})
    overlays = [
        {
            "id": "finance_survey",
            "markers": [".survey"],
            "close_selectors": [".close"],
        }
    ]

    dismissed = _dismiss_configured_overlays(page, overlays)

    assert dismissed is False
    assert page.click_attempts == []


def test_dismiss_configured_overlays_clicks_first_available_close_selector() -> None:
    page = FakePage({".survey", ".close"})
    overlays = [
        {
            "id": "finance_survey",
            "markers": [".survey"],
            "close_selectors": [".missing", ".close"],
        }
    ]

    dismissed = _dismiss_configured_overlays(page, overlays)

    assert dismissed is True
    assert page.click_attempts == [(".missing", 1000), (".close", 1000)]
    assert page.clicks == [(".close", 1000)]
    assert page.waits == [300]


def test_dismiss_configured_overlays_continues_when_close_clicks_fail() -> None:
    page = FakePage(
        {".survey", ".close-a", ".close-b"},
        failing_click_selectors={".close-a", ".close-b"},
    )
    overlays = [
        {
            "id": "finance_survey",
            "markers": [".survey"],
            "close_selectors": [".close-a", ".close-b"],
        }
    ]

    dismissed = _dismiss_configured_overlays(page, overlays)

    assert dismissed is False
    assert page.click_attempts == [(".close-a", 1000), (".close-b", 1000)]
    assert page.clicks == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -m pytest \
  finance-agents/browser-agent/tests/test_playwright_runner_overlays.py -q
```

Expected: import fails because `_dismiss_configured_overlays` does not exist.

- [ ] **Step 3: Implement generic helper and remove hardcoded constants**

In `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`:

1. Delete QianNiu/site-specific overlay constants and helper code:
   - `_KNOWN_OVERLAY_MARKERS`
   - `_KNOWN_OVERLAY_PANEL_TITLE_SELECTORS`
   - `_KNOWN_OVERLAY_CONTAINER_SELECTORS`
   - `_KNOWN_DRIVER_POPOVER_CLOSE_SELECTORS`
   - `_KNOWN_OVERLAY_CLOSE_SELECTORS`
   - `_KNOWN_OVERLAY_CLOSE_POINT_SCRIPT`
   - `_locator_bounding_box`
   - `_box_is_reasonable_overlay_card`
   - `_click_dom_detected_overlay_close`
   - `_click_overlay_panel_header_close`
   - `_click_overlay_top_right_close`
   - `_dismiss_known_overlays`

2. Add these generic helpers near `_locator_visible`:

```python
def _normalize_overlay_configs(raw_overlays: Any) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    if not isinstance(raw_overlays, list):
        return overlays
    for index, raw_overlay in enumerate(raw_overlays):
        if not isinstance(raw_overlay, dict):
            continue
        overlay_id = str(raw_overlay.get("id") or f"overlay_{index + 1}").strip()
        markers = [
            str(selector or "").strip()
            for selector in list(raw_overlay.get("markers") or [])
            if str(selector or "").strip()
        ]
        close_selectors = [
            str(selector or "").strip()
            for selector in list(raw_overlay.get("close_selectors") or [])
            if str(selector or "").strip()
        ]
        if overlay_id and markers and close_selectors:
            overlays.append(
                {
                    "id": overlay_id,
                    "markers": markers,
                    "close_selectors": close_selectors,
                }
            )
    return overlays
```

```python
def _dismiss_configured_overlays(context: Any, overlays: list[dict[str, Any]] | None) -> bool:
    dismissed_any = False
    for overlay in overlays or []:
        overlay_id = str(overlay.get("id") or "overlay").strip()
        markers = list(overlay.get("markers") or [])
        close_selectors = list(overlay.get("close_selectors") or [])
        has_overlay = False
        for marker in markers:
            locator = _safe_first_locator(context, str(marker))
            if locator is not None and _locator_visible(locator, timeout_ms=300):
                has_overlay = True
                break
        if not has_overlay:
            continue
        clicked = False
        for selector in close_selectors:
            locator = _safe_first_locator(context, str(selector))
            if locator is None:
                continue
            try:
                locator.click(timeout=1000)
                _wait_for_timeout(context, 300)
                clicked = True
                dismissed_any = True
                logger.info(
                    "browser configured overlay dismissed: overlay_id=%s selector=%s",
                    overlay_id,
                    selector,
                )
                break
            except Exception as exc:
                logger.info(
                    "browser configured overlay close skipped: overlay_id=%s selector=%s error=%s",
                    overlay_id,
                    selector,
                    exc,
                )
        if not clicked:
            logger.info("browser configured overlay detected but not dismissed: overlay_id=%s", overlay_id)
    return dismissed_any
```

- [ ] **Step 4: Run tests to verify pass**

Run the pytest command from Step 2.

Expected: all overlay tests pass.

- [ ] **Step 5: Verify no hardcoded QianNiu overlay symbols remain**

Run:

```bash
grep -R -n "_KNOWN_OVERLAY\\|_KNOWN_DRIVER_POPOVER\\|aes-survey\\|notify_headRight\\|driver-popover\\|预警通知\\|新手引导" \
  finance-agents/browser-agent/finance_browser_agent/playwright_runner.py
```

Expected: no output.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py \
  finance-agents/browser-agent/tests/test_playwright_runner_overlays.py
git commit -m "feat: use configured browser overlays"
```

## Task 3: Route Configured Overlays Through Runner Actions

**Files:**
- Modify: `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`
- Test: `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py`

- [ ] **Step 1: Add click retry test**

Add this test to `finance-agents/browser-agent/tests/test_playwright_profile_login_state.py` near other `_execute_action` tests:

```python
class OverlayBlockingClickPage:
    def __init__(self) -> None:
        self.overlay_visible = True
        self.main_clicks = 0
        self.overlay_clicks = 0
        self.waits: list[int] = []

    def locator(self, selector: str):
        page = self

        class Locator:
            first = None

            def __init__(self) -> None:
                self.first = self

            def is_visible(self, timeout: int = 0) -> bool:
                return selector == ".overlay" and page.overlay_visible

            def click(self, timeout: int = 0) -> None:
                if selector == ".overlay-close" and page.overlay_visible:
                    page.overlay_visible = False
                    page.overlay_clicks += 1
                    return
                raise RuntimeError("not clickable")

        return Locator()

    def click(self, selector: str, timeout: int = 0) -> None:
        if selector == ".target" and self.overlay_visible:
            raise RuntimeError("overlay blocks click")
        if selector == ".target":
            self.main_clicks += 1
            return
        raise RuntimeError("unexpected selector")

    def wait_for_timeout(self, delay_ms: int) -> None:
        self.waits.append(delay_ms)


def test_click_action_dismisses_configured_overlay_before_retry(tmp_path) -> None:
    page = OverlayBlockingClickPage()

    _execute_action(
        page,
        {"id": "click_target", "action": "click", "selector": ".target", "timeout_ms": 1000},
        params={"biz_date": "2026-06-08"},
        extracted={},
        capture_files=[],
        download_dir=tmp_path,
        overlays=[
            {
                "id": "blocking_overlay",
                "markers": [".overlay"],
                "close_selectors": [".overlay-close"],
            }
        ],
    )

    assert page.overlay_clicks == 1
    assert page.main_clicks == 1
```

- [ ] **Step 2: Add `download_history_file` overlay test**

Add this fake and test near existing history download tests:

```python
class OverlayHistoryOpenPage(ClosedHistoryPage):
    def __init__(self, rows: list[FakeHistoryRow]) -> None:
        super().__init__(rows)
        self.overlay_visible = True
        self.overlay_clicks = 0

    def locator(self, selector: str):
        if selector == ".history-overlay":
            page = self

            class Marker:
                first = None

                def __init__(self) -> None:
                    self.first = self

                def is_visible(self, timeout: int = 0) -> bool:
                    return page.overlay_visible

            return Marker()
        if selector == ".history-overlay-close":
            page = self

            class Close:
                first = None

                def __init__(self) -> None:
                    self.first = self

                def click(self, timeout: int = 0) -> None:
                    page.overlay_visible = False
                    page.overlay_clicks += 1

            return Close()
        return super().locator(selector)


def test_download_history_file_dismisses_configured_overlay_before_opening_history(tmp_path) -> None:
    target_row = FakeHistoryRow("2026-06-08 ~ 2026-06-08 交易货款 已完成 下载")
    page = OverlayHistoryOpenPage([target_row])
    capture_files: list[dict[str, object]] = []

    result = _execute_action(
        page,
        {
            "id": "download_completed_file",
            "action": "download_history_file",
            "selector": ".history tr",
            "history_open_selector": ".next-dialog button:has-text('历史下载记录')",
            "value_from": "params.biz_date",
            "download_timeout_ms": 600000,
            "timeout_ms": 1000,
        },
        params={"biz_date": "2026-06-08"},
        extracted={},
        capture_files=capture_files,
        download_dir=tmp_path,
        overlays=[
            {
                "id": "history_overlay",
                "markers": [".history-overlay"],
                "close_selectors": [".history-overlay-close"],
            }
        ],
    )

    assert page.overlay_clicks == 1
    assert page.dialog_history_clicked == [(30000, True)]
    assert result["last_download"].endswith("交易货款_20260521_20260521.csv")
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -m pytest \
  finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_click_action_dismisses_configured_overlay_before_retry \
  finance-agents/browser-agent/tests/test_playwright_profile_login_state.py::test_download_history_file_dismisses_configured_overlay_before_opening_history \
  -q
```

Expected: `_execute_action()` does not accept `overlays`.

- [ ] **Step 4: Update action signatures and click paths**

In `finance-agents/browser-agent/finance_browser_agent/playwright_runner.py`:

1. Add `overlays: list[dict[str, Any]] | None = None` to `_execute_action`.
2. Change `_click_like_human` signature to accept `overlays`.
3. Replace `_dismiss_known_overlays(context)` calls in `_click_like_human` and `_set_date_value` with `_dismiss_configured_overlays(..., overlays)`.
4. Add `overlays` to `_set_date_value`, `_select_checkboxes`, `_download_history_file`, and `_download_qianniu_export_report` signatures.
5. Before root wait/click loops in `_select_checkboxes`, call `_dismiss_configured_overlays(page, overlays)`.
6. Before internal clicks in `_download_history_file`, call `_dismiss_configured_overlays(page, overlays)` in `_open_history`, `_refresh_history`, and before `row.locator(download_selector).click(...)`.
7. Before refresh clicks and final button clicks in `_download_qianniu_export_report`, call `_dismiss_configured_overlays(page, overlays)`.
8. In `_run_playbook_with_playwright_inner`, add:

```python
    overlays = _normalize_overlay_configs(playbook.get("overlays"))
```

Pass `overlays=overlays` into every `_execute_action(...)` call.

- [ ] **Step 5: Run targeted tests to verify pass**

Run the pytest command from Step 3.

Expected: both tests pass.

- [ ] **Step 6: Run runner test group**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -m pytest \
  finance-agents/browser-agent/tests/test_playwright_runner_overlays.py \
  finance-agents/browser-agent/tests/test_playwright_profile_login_state.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add finance-agents/browser-agent/finance_browser_agent/playwright_runner.py \
  finance-agents/browser-agent/tests/test_playwright_profile_login_state.py
git commit -m "feat: dismiss configured overlays during browser actions"
```

## Task 4: Add Browser Collection Development Preference

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Add browser collection guideline**

Add this section under `### General` in `AGENTS.md`:

```markdown
7. **Browser Collection Playbook First**:
   - For browser collection page changes, popup changes, selector drift, or new page collection,
     prefer modifying or adding browser playbooks.
   - Change Python runner code only when a reusable browser capability is missing.
   - Site-specific selectors, popup markers, and popup close selectors belong in playbooks, not in
     `finance_browser_agent.playwright_runner`.
```

- [ ] **Step 2: Verify the section is present**

Run:

```bash
grep -n "Browser Collection Playbook First" AGENTS.md
```

Expected: one matching line.

- [ ] **Step 3: Commit Task 4**

Run:

```bash
git add AGENTS.md
git commit -m "docs: prefer playbook-first browser collection changes"
```

## Task 5: Migrate Local PostgreSQL Playbooks

**Files:**
- No application files.
- Database: local PostgreSQL table `playbooks`.

- [ ] **Step 1: Inspect active order and bill-detail playbooks**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -c "exec('''import sys
sys.path.insert(0, \"finance-mcp\")
from db_config import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute(\"\"\"
    select playbook_id, title, status
    from playbooks
    where status in ('active', 'canary')
      and (
        title ilike %s
        or title ilike %s
        or playbook_id ilike %s
        or playbook_id ilike %s
      )
    order by title
\"\"\", (\"%收支明细%\", \"%收支账单%\", \"%bill-details%\", \"%sold-orders%\"))
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
''')"
```

Expected: output includes active sold-orders and bill-details playbooks.

- [ ] **Step 2: Update local playbook JSONB**

Run this local migration script:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -c "exec('''import json
import sys
sys.path.insert(0, \"finance-mcp\")
from db_config import get_db_connection

BASE_OVERLAYS = [
    {
        \"id\": \"qianniu_warning_notice\",
        \"markers\": [\"text=预警通知\", \".normal_headTitle__iJ44s:has-text('预警通知')\"],
        \"close_selectors\": [
            \".notify_headRight__XdjnE .next-icon-close_blod\",
            \"[class*='notify_headRight'] .next-icon-close_blod\",
            \"[class*='notify_headRight'] [class*='next-icon-close']\",
            \".normal_container__13Xbj button:has-text('知道了')\",
            \".normal_container__13Xbj button:has-text('确定')\",
            \".normal_container__13Xbj button:has-text('关闭')\",
            \".normal_container__13Xbj button:has-text('我知道了')\",
            \".normal_container__13Xbj [role='button']:has-text('知道了')\",
            \".normal_container__13Xbj [role='button']:has-text('确定')\",
            \".normal_container__13Xbj .next-dialog-close\",
            \".normal_container__13Xbj .next-icon-close\",
            \".container--SMNuCb74 button:has-text('知道了')\",
            \".container--SMNuCb74 button:has-text('确定')\",
            \".container--SMNuCb74 button:has-text('关闭')\",
            \".container--SMNuCb74 [role='button']:has-text('知道了')\",
            \".container--SMNuCb74 [role='button']:has-text('确定')\",
            \".container--SMNuCb74 .next-dialog-close\",
            \".container--SMNuCb74 .next-icon-close\",
        ],
    },
    {
        \"id\": \"qianniu_guidance\",
        \"markers\": [
            \"text=新手引导\", \"text=操作指引\", \"text=功能介绍\", \"text=下次再说\",
            \".driver-popover\", \".driver-overlay\",
        ],
        \"close_selectors\": [
            \"button.driver-popover-close-btn\",
            \".driver-popover button.driver-popover-close-btn\",
            \".driver-popover .driver-popover-close-btn\",
            \".driver-popover button:has-text('跳过')\",
            \".driver-popover button:has-text('关闭')\",
            \".driver-popover button:has-text('知道了')\",
            \".driver-popover button:has-text('我知道了')\",
            \"button.driver-popover-next-btn:has-text('完成')\",
            \".driver-popover button.driver-popover-next-btn:has-text('完成')\",
            \".driver-popover .driver-popover-next-btn:has-text('完成')\",
            \"button.driver-popover-next-btn:has-text('下一步')\",
            \".driver-popover button.driver-popover-next-btn:has-text('下一步')\",
            \".driver-popover .driver-popover-next-btn:has-text('下一步')\",
            \".next-dialog button:has-text('完成')\",
            \".next-dialog button:has-text('跳过')\",
            \".next-dialog button:has-text('关闭')\",
            \".next-dialog button:has-text('知道了')\",
            \".next-dialog .next-dialog-close\",
            \".next-balloon button:has-text('完成')\",
            \".next-balloon button:has-text('跳过')\",
            \".next-balloon button:has-text('关闭')\",
            \".next-balloon .next-balloon-close\",
            \"[class*='guide'] button:has-text('完成')\",
            \"[class*='guide'] button:has-text('跳过')\",
            \"[class*='guide'] button:has-text('关闭')\",
            \"[class*='Guide'] button:has-text('完成')\",
            \"[class*='Guide'] button:has-text('跳过')\",
            \"[class*='Guide'] button:has-text('关闭')\",
        ],
    },
]
FINANCE_SURVEY = {
    \"id\": \"qianniu_finance_survey\",
    \"markers\": [\".aes-survey-hanging\", \"[class*='aes-survey-hanging']\", \"text=财务管理工具\"],
    \"close_selectors\": [\".aes-survey-hanging--close\", \"[class*='aes-survey-hanging--close']\"],
}

def merge_overlays(body, include_finance):
    overlays_by_id = {overlay.get(\"id\"): overlay for overlay in body.get(\"overlays\", []) if isinstance(overlay, dict)}
    for overlay in BASE_OVERLAYS:
        overlays_by_id[overlay[\"id\"]] = overlay
    if include_finance:
        overlays_by_id[FINANCE_SURVEY[\"id\"]] = FINANCE_SURVEY
    body[\"overlays\"] = list(overlays_by_id.values())
    removed = 0
    for step in body.get(\"steps\", []):
        if \"overlay_close_selectors\" in step:
            removed += 1
            del step[\"overlay_close_selectors\"]
    return removed

conn = get_db_connection()
cur = conn.cursor()
cur.execute(\"\"\"
    select id, playbook_id, title, playbook_body
    from playbooks
    where status in ('active', 'canary')
      and (
        title ilike %s
        or title ilike %s
        or playbook_id ilike %s
        or playbook_id ilike %s
      )
\"\"\", (\"%收支明细%\", \"%收支账单%\", \"%bill-details%\", \"%sold-orders%\"))
rows = cur.fetchall()
updated = 0
removed = 0
for row_id, playbook_id, title, body in rows:
    if isinstance(body, str):
        body = json.loads(body)
    include_finance = \"bill-details\" in playbook_id or \"收支明细\" in title or \"收支账单\" in title
    removed += merge_overlays(body, include_finance)
    cur.execute(\"update playbooks set playbook_body=%s::jsonb, updated_at=now() where id=%s\", (json.dumps(body, ensure_ascii=False), row_id))
    updated += 1
conn.commit()
print({\"matched\": len(rows), \"updated\": updated, \"removed_overlay_close_selectors\": removed})
cur.close()
conn.close()
''')"
```

Expected: `matched` and `updated` include active order and bill-detail playbooks; `removed_overlay_close_selectors` may be `0` if already cleaned.

- [ ] **Step 3: Verify local migration**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -c "exec('''import sys
sys.path.insert(0, \"finance-mcp\")
from db_config import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute(\"\"\"
    select
      count(*) filter (where playbook_body ? 'overlays') as with_overlays,
      count(*) as total,
      count(*) filter (
        where (title ilike %s or title ilike %s or playbook_id ilike %s)
          and playbook_body::text like %s
      ) as bill_with_finance_survey
    from playbooks
    where status in ('active', 'canary')
      and (
        title ilike %s
        or title ilike %s
        or playbook_id ilike %s
        or playbook_id ilike %s
      )
\"\"\", (
    \"%收支明细%\", \"%收支账单%\", \"%bill-details%\", \"%qianniu_finance_survey%\",
    \"%收支明细%\", \"%收支账单%\", \"%bill-details%\", \"%sold-orders%\",
))
print(cur.fetchone())
cur.execute(\"\"\"
    select count(*)
    from playbooks p
    cross join lateral jsonb_array_elements(p.playbook_body->'steps') step
    where step ? 'overlay_close_selectors'
\"\"\")
print(\"remaining_overlay_close_selectors\", cur.fetchone()[0])
cur.close()
conn.close()
''')"
```

Expected: `with_overlays == total`; bill-detail count with finance survey is greater than `0`; remaining `overlay_close_selectors` is `0`.

## Task 6: Sync ECS/RDS Playbooks

**Files:**
- Create temporary script: `/private/tmp/migrate_browser_overlays_rds.py`
- Database: RDS PostgreSQL via `ssh aliyun-tally` and `tally-finance-mcp-1`.

- [ ] **Step 1: Confirm ECS container**

Run:

```bash
ssh aliyun-tally "docker ps --format '{{.Names}}'"
```

Expected: output includes `tally-finance-mcp-1`.

- [ ] **Step 2: Create the RDS migration script**

Create `/private/tmp/migrate_browser_overlays_rds.py` with this exact content:

```python
from __future__ import annotations

import json
import os

import psycopg2

BASE_OVERLAYS = [
    {
        "id": "qianniu_warning_notice",
        "markers": ["text=预警通知", ".normal_headTitle__iJ44s:has-text('预警通知')"],
        "close_selectors": [
            ".notify_headRight__XdjnE .next-icon-close_blod",
            "[class*='notify_headRight'] .next-icon-close_blod",
            "[class*='notify_headRight'] [class*='next-icon-close']",
            ".normal_container__13Xbj button:has-text('知道了')",
            ".normal_container__13Xbj button:has-text('确定')",
            ".normal_container__13Xbj button:has-text('关闭')",
            ".normal_container__13Xbj button:has-text('我知道了')",
            ".normal_container__13Xbj [role='button']:has-text('知道了')",
            ".normal_container__13Xbj [role='button']:has-text('确定')",
            ".normal_container__13Xbj .next-dialog-close",
            ".normal_container__13Xbj .next-icon-close",
            ".container--SMNuCb74 button:has-text('知道了')",
            ".container--SMNuCb74 button:has-text('确定')",
            ".container--SMNuCb74 button:has-text('关闭')",
            ".container--SMNuCb74 [role='button']:has-text('知道了')",
            ".container--SMNuCb74 [role='button']:has-text('确定')",
            ".container--SMNuCb74 .next-dialog-close",
            ".container--SMNuCb74 .next-icon-close",
        ],
    },
    {
        "id": "qianniu_guidance",
        "markers": [
            "text=新手引导",
            "text=操作指引",
            "text=功能介绍",
            "text=下次再说",
            ".driver-popover",
            ".driver-overlay",
        ],
        "close_selectors": [
            "button.driver-popover-close-btn",
            ".driver-popover button.driver-popover-close-btn",
            ".driver-popover .driver-popover-close-btn",
            ".driver-popover button:has-text('跳过')",
            ".driver-popover button:has-text('关闭')",
            ".driver-popover button:has-text('知道了')",
            ".driver-popover button:has-text('我知道了')",
            "button.driver-popover-next-btn:has-text('完成')",
            ".driver-popover button.driver-popover-next-btn:has-text('完成')",
            ".driver-popover .driver-popover-next-btn:has-text('完成')",
            "button.driver-popover-next-btn:has-text('下一步')",
            ".driver-popover button.driver-popover-next-btn:has-text('下一步')",
            ".driver-popover .driver-popover-next-btn:has-text('下一步')",
            ".next-dialog button:has-text('完成')",
            ".next-dialog button:has-text('跳过')",
            ".next-dialog button:has-text('关闭')",
            ".next-dialog button:has-text('知道了')",
            ".next-dialog .next-dialog-close",
            ".next-balloon button:has-text('完成')",
            ".next-balloon button:has-text('跳过')",
            ".next-balloon button:has-text('关闭')",
            ".next-balloon .next-balloon-close",
            "[class*='guide'] button:has-text('完成')",
            "[class*='guide'] button:has-text('跳过')",
            "[class*='guide'] button:has-text('关闭')",
            "[class*='Guide'] button:has-text('完成')",
            "[class*='Guide'] button:has-text('跳过')",
            "[class*='Guide'] button:has-text('关闭')",
        ],
    },
]
FINANCE_SURVEY = {
    "id": "qianniu_finance_survey",
    "markers": [".aes-survey-hanging", "[class*='aes-survey-hanging']", "text=财务管理工具"],
    "close_selectors": [".aes-survey-hanging--close", "[class*='aes-survey-hanging--close']"],
}


def merge_overlays(body: dict, include_finance: bool) -> int:
    overlays_by_id = {
        overlay.get("id"): overlay
        for overlay in body.get("overlays", [])
        if isinstance(overlay, dict) and overlay.get("id")
    }
    for overlay in BASE_OVERLAYS:
        overlays_by_id[overlay["id"]] = overlay
    if include_finance:
        overlays_by_id[FINANCE_SURVEY["id"]] = FINANCE_SURVEY
    body["overlays"] = list(overlays_by_id.values())
    removed = 0
    for step in body.get("steps", []):
        if "overlay_close_selectors" in step:
            removed += 1
            del step["overlay_close_selectors"]
    return removed


conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute(
    """
    select id, playbook_id, title, playbook_body
    from playbooks
    where status in ('active', 'canary')
      and (
        title ilike %s
        or title ilike %s
        or playbook_id ilike %s
        or playbook_id ilike %s
      )
    """,
    ("%收支明细%", "%收支账单%", "%bill-details%", "%sold-orders%"),
)
rows = cur.fetchall()
updated = 0
removed = 0
for row_id, playbook_id, title, body in rows:
    if isinstance(body, str):
        body = json.loads(body)
    include_finance = "bill-details" in playbook_id or "收支明细" in title or "收支账单" in title
    removed += merge_overlays(body, include_finance)
    cur.execute(
        "update playbooks set playbook_body=%s::jsonb, updated_at=now() where id=%s",
        (json.dumps(body, ensure_ascii=False), row_id),
    )
    updated += 1
conn.commit()
print({"matched": len(rows), "updated": updated, "removed_overlay_close_selectors": removed})
cur.close()
conn.close()
```

- [ ] **Step 3: Copy and run the RDS migration script**

Run:

```bash
scp /private/tmp/migrate_browser_overlays_rds.py aliyun-tally:/tmp/migrate_browser_overlays_rds.py
ssh aliyun-tally "docker cp /tmp/migrate_browser_overlays_rds.py tally-finance-mcp-1:/tmp/migrate_browser_overlays_rds.py"
ssh aliyun-tally "docker exec tally-finance-mcp-1 python /tmp/migrate_browser_overlays_rds.py"
ssh aliyun-tally "docker exec tally-finance-mcp-1 rm /tmp/migrate_browser_overlays_rds.py"
ssh aliyun-tally "rm /tmp/migrate_browser_overlays_rds.py"
```

Expected: printed `matched` and `updated` counts include RDS active order and bill-detail playbooks.

- [ ] **Step 4: Verify RDS migration**

Run:

```bash
ssh aliyun-tally "docker exec tally-finance-mcp-1 python -c \"exec('''import os
import psycopg2
conn = psycopg2.connect(os.environ[\\\"DATABASE_URL\\\"])
cur = conn.cursor()
cur.execute(\\\"\\\"\\\"
    select
      count(*) filter (where playbook_body ? 'overlays') as with_overlays,
      count(*) as total,
      count(*) filter (
        where (title ilike %s or title ilike %s or playbook_id ilike %s)
          and playbook_body::text like %s
      ) as bill_with_finance_survey
    from playbooks
    where status in ('active', 'canary')
      and (
        title ilike %s
        or title ilike %s
        or playbook_id ilike %s
        or playbook_id ilike %s
      )
\\\"\\\"\\\", (
    \\\"%收支明细%\\\", \\\"%收支账单%\\\", \\\"%bill-details%\\\", \\\"%qianniu_finance_survey%\\\",
    \\\"%收支明细%\\\", \\\"%收支账单%\\\", \\\"%bill-details%\\\", \\\"%sold-orders%\\\",
))
print(cur.fetchone())
cur.execute(\\\"\\\"\\\"
    select count(*)
    from playbooks p
    cross join lateral jsonb_array_elements(p.playbook_body->'steps') step
    where step ? 'overlay_close_selectors'
\\\"\\\"\\\")
print(\\\"remaining_overlay_close_selectors\\\", cur.fetchone()[0])
cur.close()
conn.close()
''')\""
```

Expected: `with_overlays == total`; bill-detail count with finance survey is greater than `0`; remaining `overlay_close_selectors` is `0`.

## Task 7: Run Automated Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
/Users/kevin/workspace/financial-ai/.venv/bin/python -m pytest \
  finance-mcp/tests/test_browser_playbook_schema.py \
  finance-agents/browser-agent/tests/test_playbook_interpreter_contract.py \
  finance-agents/browser-agent/tests/test_playwright_runner_overlays.py \
  finance-agents/browser-agent/tests/test_playwright_profile_login_state.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Verify no site-specific overlay selectors remain in runner**

Run:

```bash
grep -R -n "aes-survey\\|notify_headRight\\|driver-popover\\|预警通知\\|新手引导\\|操作指引\\|财务管理工具" \
  finance-agents/browser-agent/finance_browser_agent/playwright_runner.py
```

Expected: no output.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: only intended implementation files are modified, plus pre-existing unrelated dirty files that must not be reverted.

## Task 8: Operator-Approved Runtime Activation And Production Rerun

**Files:**
- No application files.

- [ ] **Step 1: Report readiness before restart/deploy**

Tell the operator:

```text
代码和本地/RDS playbook 已同步，自动化测试已通过。browser-agent 需要按你确认的方式重启或部署后，新 overlays 能力才会在线上任务生效。我不会自动重启。
```

- [ ] **Step 2: After operator activates runtime, rerun failed tasks**

Rerun only these two funding reconciliation tasks:

```text
abgame旗舰店资金对账
履冰旗舰店资金对账
```

Run:

```bash
cd /Users/kevin/workspace/financial-ai
/Users/kevin/workspace/financial-ai/.venv/bin/python finance-cron/run_reconciliation.py \
  --company-id 00000000-0000-0000-0000-000000000001 \
  --run-plan-code plan_9da2295257c7 \
  --biz-date 2026-06-07 \
  --trigger-mode rerun \
  --requested-by codex-browser-overlays

/Users/kevin/workspace/financial-ai/.venv/bin/python finance-cron/run_reconciliation.py \
  --company-id 00000000-0000-0000-0000-000000000001 \
  --run-plan-code plan_0d178b7b6477 \
  --biz-date 2026-06-07 \
  --trigger-mode rerun \
  --requested-by codex-browser-overlays
```

- [ ] **Step 3: Verify production outcome**

Confirm each rerun:

```text
任务名: abgame旗舰店资金对账
浏览器采集: 收支明细下载成功
对账任务: 不再因弹窗遮挡下载明细失败

任务名: 履冰旗舰店资金对账
浏览器采集: 收支明细下载成功
对账任务: 不再因弹窗遮挡下载明细失败
```

If either task fails, collect the browser-agent log window around the failed `sync_job_id` and identify whether the failure is overlay dismissal, authentication/risk verification, selector drift, or unrelated data quality.

## Self-Review

- Spec coverage: schema contract, runner behavior, hardcoding removal, playbook migration, project memory, tests, RDS sync, and two-task production verification are each covered by a task.
- Red-flag token scan: No deferred implementation notes remain.
- Type consistency: The plan uses `overlays`, `markers`, and `close_selectors` consistently across schema, tests, runner, and migration.

# Browser Agent Risk Handoff Design

Date: 2026-05-23

## Context

Browser collection must remain an automatic collection solution for cloud Tally. The collection
machine runs `browser-agent`; it receives playbook jobs, launches a local browser, uses saved
merchant credentials when needed, downloads source data, and reports records back to Tally.

QianNiu / Taobao login can still trigger slider, SMS, or other risk verification. This cannot be
fully eliminated and must not be bypassed. The product requirement is therefore:

1. Avoid triggering risk verification as much as practical.
2. When risk verification appears, pause the same browser session.
3. Notify the responsible operator in DingTalk with a one-time link.
4. Let the operator complete verification remotely.
5. Resume the original playbook in the same Chrome page after login state is restored.

Production collection machines will run on Windows or macOS. They may be inside customer or
operator networks and should not require inbound public ports.

## Decision

Use cloud-mediated handoff with browser-agent outbound connectivity:

- browser-agent owns Chrome, profiles, downloads, and Playwright execution locally.
- browser-agent establishes outbound communication with Tally Cloud for job claim, heartbeat,
  and future handoff streaming.
- Tally Cloud generates the DingTalk one-time handoff link.
- Operators open a Tally Cloud page. Cloud forwards screen frames and input events through the
  browser-agent outbound channel to the active browser session.
- The first implementation uses Playwright screenshot frames plus mouse/keyboard event forwarding.
- If slider verification proves sensitive to Playwright-level events, the same handoff session
  interface can be backed later by OS-level remote desktop for Windows/macOS.

Do not require Tally Cloud to connect directly to a browser-agent host or local browser port.

## Goals

1. Keep normal browser collection automatic: credentials + playbook should run without operator
   action when login state is valid or password login succeeds.
2. Reduce risk triggers by making Chrome startup and interaction closer to normal headed Chrome.
3. Convert risk verification from a terminal failure into a waiting state with operator handoff.
4. Preserve the original browser page, profile, download directory, and job context while waiting.
5. Support Windows and macOS collection machines.
6. Keep the handoff link short-lived, single-use, auditable, and scoped to one sync job.

## Non-Goals

- Do not crack, bypass, or automate CAPTCHA/risk verification.
- Do not expose browser-agent or Chrome debug ports to the public internet.
- Do not require customers to install a full remote desktop stack for the first implementation.
- Do not make ordinary collection dependent on manual login.
- Do not store merchant plaintext credentials in playbooks, logs, or handoff payloads.
- Do not build a general browser automation IDE in this change.

## Approach Options

### Option A: Cloud-mediated screenshot and input handoff

browser-agent captures screenshots from the active Playwright page and sends them to Tally Cloud.
The Tally handoff page renders frames and forwards operator mouse/keyboard events back to
browser-agent, which applies them to the same page.

Pros:

- No inbound port requirement.
- Works with the existing Playwright runner.
- Cross-platform for Windows/macOS.
- Smallest production path for the current architecture.

Cons:

- Some slider implementations may reject Playwright-generated pointer events.
- Video latency and drag fidelity need careful tuning.

This is the recommended first implementation.

### Option B: Cloud-mediated OS-level remote desktop

browser-agent starts or integrates with a local remote-control process and streams the desktop or
browser window through Tally Cloud.

Pros:

- Best chance to satisfy hard anti-automation slider checks because input is OS-level.
- Closer to a real human sitting at the collection machine.

Cons:

- Larger deployment surface on Windows/macOS.
- More security review, installer work, and permissions handling.
- Harder to ship quickly.

This is the fallback backend if Option A cannot clear QianNiu slider reliably.

### Option C: Direct browser-agent URL

browser-agent hosts a local web UI and sends that URL in DingTalk.

Pros:

- Fast to prototype on a trusted local network.

Cons:

- Requires reachable inbound network path.
- Hard to secure in customer NAT/firewall environments.
- Does not fit cloud Tally production deployment.

This is rejected for production.

## Browser Launch Hardening

Current runner uses `playwright.chromium.launch_persistent_context(channel="chrome")`, which does
start local Google Chrome, not bundled Chromium. The next hardening step is to make launch closer
to normal headed Chrome:

1. browser-agent starts local Google Chrome itself with a dedicated persistent profile.
2. Chrome listens only on `127.0.0.1` for a local CDP endpoint.
3. Playwright attaches via CDP to the existing Chrome process.
4. Browser windows use normal headed mode.
5. Profile and download directories remain per browser collection profile.
6. The runner still checks `auth_check.logged_in_selector` before any login step.
7. Login actions keep slow typing and randomized step/click delay.

This does not remove all automation signals. It reduces avoidable differences while preserving the
ability to run playbooks automatically.

## Handoff State Model

Add a waiting state distinct from terminal failure:

- `running`: browser-agent is executing the playbook.
- `waiting_human_verification`: risk verification is visible and the browser session is paused.
- `resuming`: operator finished verification and browser-agent is checking login state.
- `success`: playbook completed and records were uploaded.
- `failed`: playbook cannot continue or handoff expired.

`RISK_VERIFICATION` should not immediately finalize the sync job as failed while the handoff window
is active. It becomes terminal only after the handoff session expires, is cancelled, or login state
does not recover.

## Handoff Session Data

Create a handoff session associated with one sync job and one browser-agent runtime session.

Fields:

- `handoff_session_id`
- `sync_job_id`
- `company_id`
- `data_source_id`
- `agent_id`
- `profile_key`
- `status`
- `reason`
- `created_at`
- `expires_at`
- `claimed_by_user_id`
- `claimed_at`
- `completed_at`
- `audit_events`

The one-time DingTalk URL points to Tally Cloud and contains only a signed opaque token. It must
not contain credentials, profile paths, local debug ports, or playbook contents.

## Runtime Flow

Normal automatic flow:

1. Cloud creates a browser sync job.
2. browser-agent claims the job.
3. browser-agent opens Chrome with the target profile.
4. Runner checks whether the profile is authenticated.
5. If authenticated, `login_if_needed` is skipped.
6. If unauthenticated, runner uses sealed credentials injected into params and logs in.
7. Runner executes the playbook and uploads records/capture files.

Risk handoff flow:

1. Runner detects strong risk markers such as slider, SMS verification, or security verification.
2. Runner pauses the step deadline and keeps Chrome open.
3. browser-agent reports `waiting_human_verification` to Cloud with screenshot availability.
4. Cloud creates a handoff session and sends DingTalk message to the configured operator.
5. Operator opens the one-time link and claims the session.
6. Cloud streams screenshots from browser-agent to the page.
7. Operator sends mouse/keyboard events through Cloud to browser-agent.
8. browser-agent applies events to the same page.
9. Runner polls login-state selectors and risk markers.
10. When login state is restored, runner resumes the original playbook from the blocked step.
11. If handoff expires, runner marks the job failed with `RISK_VERIFICATION`.

## Security

- Handoff links are single-use and short-lived.
- Links must require an authenticated Tally user or a signed DingTalk identity check before control
  is granted.
- The session is scoped to one sync job and one browser page.
- Only one operator can control a session at a time.
- Every claim, input-control start, completion, timeout, and cancellation is audited.
- Screenshots should be treated as sensitive financial data.
- Clipboard access is disabled in the first implementation.
- File download access through the handoff UI is disabled; downloaded files continue through the
  existing capture-file upload path.
- Cloud never receives merchant plaintext credentials through the handoff channel.

## Error Handling

- If browser-agent disconnects during handoff, Cloud marks the session `agent_offline` and keeps
  the sync job waiting until the runner timeout decides final state.
- If the operator link expires, Cloud marks the session `expired`; browser-agent fails the job as
  `RISK_VERIFICATION`.
- If login state does not recover after operator action, browser-agent keeps waiting until timeout
  or fails as `RISK_VERIFICATION`.
- If the page changes after verification, normal playbook failure mapping applies (`PAGE_CHANGED`,
  `AUTH_EXPIRED`, or `DATA_MISMATCH`).
- If screenshot streaming works but event forwarding fails, the UI must show a clear "control
  unavailable" state and the job remains paused until timeout or cancellation.

## Data And API Boundaries

MCP / Cloud responsibilities:

- Persist handoff sessions.
- Issue and verify one-time tokens.
- Send DingTalk handoff messages through the existing notification adapter.
- Proxy operator WebSocket events to the correct browser-agent connection.
- Expose handoff status to the browser collection UI and sync job detail.

browser-agent responsibilities:

- Detect risk state.
- Hold the Chrome page open.
- Produce screenshot frames.
- Apply input events to the active page.
- Continue polling login state.
- Resume or fail the original playbook.

finance-web responsibilities:

- Render the handoff page.
- Show session metadata, expiry, frame stream, and control state.
- Send mouse/keyboard events.
- Show completion/timeout/failure result.

## Testing

Unit tests:

- Risk detection creates a waiting handoff result instead of immediate terminal failure.
- Handoff token payload excludes credentials and local paths.
- Expired handoff session maps to `RISK_VERIFICATION`.
- Only the owning sync job can resume from a handoff session.
- Browser launch config never binds CDP to a public interface.

Integration tests:

- Simulated risk page creates a handoff session and sends one DingTalk notification.
- Simulated operator completion lets the runner continue the next playbook step.
- Agent disconnect during handoff is reflected in handoff status.
- Duplicate link open cannot create a second controller.

Manual validation:

- macOS collection machine: QianNiu login risk page can be viewed through the Tally handoff page.
- Windows collection machine: same validation with Chrome Stable.
- If screenshot/event forwarding cannot clear QianNiu slider, run the same handoff flow with the
  OS-level remote desktop backend before production expansion.

## Rollout

Phase 1: Browser launch hardening and state plumbing.

- Start Chrome in local CDP attach mode.
- Add `waiting_human_verification` state and avoid terminal failure while waiting.
- Keep current local/manual window fallback for development validation.

Phase 2: Cloud handoff session.

- Persist handoff sessions.
- Add one-time token and DingTalk message.
- Add cloud-to-agent event channel.
- Add handoff status to sync job detail.

Phase 3: Handoff UI.

- Build the Tally handoff page.
- Stream screenshots and forward mouse/keyboard events.
- Audit control events.

Phase 4: Production validation.

- Validate macOS and Windows collection machines.
- Run QianNiu verification with real credentials.
- Confirm normal automatic collection still passes when login state is valid.
- Confirm expired or failed handoff produces actionable `RISK_VERIFICATION` alerts.

## Open Design Constraint

The first implementation intentionally starts with Playwright-level screenshot and event forwarding
because it is cross-platform and does not require inbound network access. If QianNiu slider
verification rejects those events, the architecture stays the same but the browser-agent-side
control backend changes to OS-level remote desktop for Windows/macOS.

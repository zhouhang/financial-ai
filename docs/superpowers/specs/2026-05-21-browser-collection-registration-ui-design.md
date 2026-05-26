# Browser Collection Registration UI Design

## Decision

The browser data-collection UI should present a single product action: create and manage
browser collection registrations. Users should not select or understand the underlying
`browser_playbook` data source, `source_id`, `playbook_id`, version, egress group, verification
date, or landing dataset.

Creating a browser collection registration creates the whole backend chain automatically:

1. a new `data_sources` row with `source_kind='browser_playbook'`
2. a same-title semantic dataset backed by `browser_collection_records`
3. an internal playbook id generated from the title
4. a system-maintained playbook version
5. encrypted credentials for login fallback
6. a first verification sync job using the latest T-1 business date

## UI Scope

The Data Connections source-type navigation keeps only:

- 电商平台授权
- 数据库连接
- API（待开发）
- 浏览器

Remove these user-facing cards:

- 文件链接
- 客户端/CLI 抓取
- 浏览器抓取 legacy card

The 浏览器 page shows a collection-registration list with a header action row:

- 刷新
- 新增

Clicking 新增 opens a modal. Clicking a list row opens a read-only modal with the saved
registration information and current status.

## New Registration Modal

The creation modal contains only:

- 标题
- 登录账号
- 密码
- Playbook JSON

The modal must not show:

- browser_playbook 数据源选择
- source_id
- playbook_id
- version
- egress_group
- 验证日期
- 落地数据集

The primary action is 保存并验证. It creates the backend objects and starts the first
verification run.

## Registration Detail Modal

The read-only detail modal shows the saved user-facing information:

- 标题
- 登录账号
- 密码状态, never plaintext
- Playbook JSON
- 注册/验证/激活状态
- 最近采集时间 when available
- failure reason when verification or collection failed

It may show the generated semantic dataset display name, but only as a business-facing
artifact. It must not expose raw `source_id`, internal playbook id, or version unless a future
operator-only debug mode explicitly adds them.

## Backend Contract

Add a user-facing registration path that does not require a `source_id` path parameter. The
route can wrap existing MCP operations internally, but the API shape must match the product
action:

```http
POST /api/data-sources/browser-playbook/registrations
```

Request body:

```json
{
  "title": "千牛每日资金账单",
  "credential_username": "finance_ops@example.com",
  "credential_password": "...",
  "playbook_body": {}
}
```

Backend behavior:

- Validate `title`, credentials, and `playbook_body`.
- Create a new `browser_playbook` data source for every new registration.
- Generate a stable internal code/id from the title, with collision handling.
- Create a same-title semantic dataset with `source_type='browser_collection_records'`.
- Register the playbook against the newly created source.
- Generate `playbook_id` from the title.
- Maintain version internally.
- Use latest T-1 as the first verification `biz_date`.
- Return the registration, generated dataset summary, and verification `sync_job` id.

The existing `POST /api/data-sources/{source_id}/browser-playbook/register` path can remain as
an internal/backward-compatible route, but the UI should use the new source-less path.

## Date Semantics

Verification date is not a user-facing registration field. The first verification run uses the
latest T-1 date by default.

Production and re-run dates are runtime inputs supplied by scheduling or manual collection
triggers. Playbooks should support `params.biz_date`; they should not hard-code "yesterday".
If an authored playbook is described as "download yesterday's data", the generated playbook
should translate that into a runtime `biz_date` parameter with T-1 as the default.

## Browser Login-State Constraint

Browser collection must not assume the business identity is always a shop. Some browser
collections may be shop-oriented, while others may target a bank or another external system.

For every browser collection run:

1. Open the configured persistent browser profile.
2. Check whether the profile already has a valid login state for the target system.
3. If logged in, run the playbook directly.
4. If not logged in or expired, use the saved login account and password, then run the playbook.
5. If risk verification blocks login, mark the binding/profile as blocked and avoid repeated
   automatic login attempts.

The key runtime rule is profile-login-state first, not business-entity matching. Multiple
registrations may reuse an existing profile state when the profile is already authenticated.

## Frontend Implementation Notes

`DataConnectionsPanel.tsx` is already large. Keep new behavior out of that file as much as
possible:

- Move browser-registration list, modal state, and API calls into `BrowserPlaybookPanel`.
- Extract child components if the panel grows beyond a compact list + modal structure.
- Keep source-type navigation changes in the existing config layer where possible.

List rows should be concise: title, login account, status, and recent collection/verification
time. The generated dataset can be shown in the detail modal but does not need to be a primary
list column.

## Test Plan

Frontend:

- Browser source tab shows the list and refresh/new actions.
- New modal contains only title, login account, password, and Playbook JSON.
- Row click opens the read-only detail modal.
- Removed source cards no longer render in Data Connections navigation.
- API card label is API（待开发）.

Backend:

- Source-less registration creates a new `browser_playbook` source.
- Registration creates a same-title `browser_collection_records` semantic dataset.
- The endpoint generates playbook id and version internally.
- First verification uses T-1 when no date is supplied.
- Plaintext password is not returned by registration/list/detail APIs.

Runtime:

- Runner skips login when the persistent profile is already authenticated.
- Runner logs in only when the profile is unauthenticated or expired.
- Risk-verification failures do not cause repeated automatic login attempts.

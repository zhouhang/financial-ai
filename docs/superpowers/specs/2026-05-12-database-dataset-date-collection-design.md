# Database Dataset Date Collection Design

## Context

Database-backed semantic datasets already support collection through the existing
`data_source_trigger_dataset_collection` flow. Published datasets store a collection
configuration that identifies the physical date field used for collection. For the
transaction order detail dataset, that field is `create_date`.

Users currently have an immediate collection action in the dataset collection detail
panel, but cannot manually collect one specific business date from the UI. This makes
backfills awkward when a user needs to collect historical days one by one.

## Goal

Add a single-day manual collection action next to the existing immediate collection
button in database connection collection detail views.

The new action lets a user choose one date and trigger collection for that date using
the dataset's existing configured collection date field.

## Non-Goals

- Do not add date range collection in this version.
- Do not let users override the dataset's configured date field from the collection
  modal.
- Do not change backend collection storage or idempotency rules.
- Do not special-case the transaction order detail table in code.

## User Experience

In the database connection dataset collection detail panel:

- Keep the existing `立即采集` button.
- Add `按日期采集` next to it.
- The button is enabled only when the dataset has a configured collection date field.
- If the dataset lacks a collection date field, show the action as disabled with a
  clear tooltip or inline disabled reason.

Clicking `按日期采集` opens a modal:

- Title: `按日期采集`
- Shows dataset name.
- Shows collection date field, for example `采集时间字段：create_date`.
- Contains one date input.
- Primary button: `采集`
- Cancel button closes the modal without triggering collection.

On submit:

- Send the selected date as `biz_date` in `YYYY-MM-DD` format.
- Use the existing dataset collection API.
- Close the modal after a successful request.
- Refresh collection detail so the new job appears in the recent job list.
- If the request fails, keep the modal open or show the error in the collection detail
  action area using the existing error style.

## Backend Contract

Reuse the existing `data_source_trigger_dataset_collection` tool/API behavior.

The frontend should pass:

- `source_id`
- `dataset_id`
- `dataset_code`
- `resource_key`
- `trigger_mode: "manual"`
- `params.biz_date: "YYYY-MM-DD"`

The backend already resolves:

- dataset collection config
- collection driver
- collection date field
- key fields
- query resource key

For database datasets, the connector uses `params.biz_date` with the configured
`date_field`. For the transaction order detail dataset, this means:

- selected date: `2026-04-01`
- date field: `create_date`
- query behavior: collect rows where `create_date` falls on `2026-04-01`

## Idempotency

The manual date collection request should use an idempotency key that includes:

- source id
- dataset id
- selected date
- action type

Recommended shape:

`manual-date-collection:<source_id>:<dataset_id>:<YYYY-MM-DD>`

This prevents repeated clicks from creating duplicate sync jobs for the same dataset
and date.

The data layer continues to rely on existing collection record keys. This design does
not change how records are upserted.

## Error Handling

Expected failure examples:

- source query timeout
- database permission or network failure
- no rows returned for the selected date
- dataset disabled
- missing collection date field

Display backend errors directly when available. For empty successful collections,
the recent job list should continue showing a successful job with `0` records.

## Testing

Frontend tests should cover:

- `按日期采集` appears next to `立即采集` in database collection detail.
- The modal shows dataset name and configured date field.
- Submitting a date calls the existing collection endpoint with `params.biz_date`.
- Success closes the modal and refreshes collection detail.
- Failure displays the backend error.
- The button is disabled or blocked when no collection date field exists.

Backend tests are optional for this change because the backend already supports
`biz_date`; add backend coverage only if implementation touches backend code.

## Open Decision

Range collection remains deliberately out of scope. If users need a full month, they
will trigger each day manually in this version.

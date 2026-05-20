# Browser First-Store Production Hardening Design

## Decision

First-store browser collection is not complete until a real shop can automatically create a browser collection job, have it consumed by a long-running collection-machine service, persist browser records and capture files, and resume or fail reconciliation without manual process calls.

The collection-machine process is `finance-agents/browser-agent/service.py`. It packages dispatcher and runner together. Tally Cloud remains the queue and data source of truth.

## Runtime Flow

1. `data_source_trigger_dataset_collection` creates `sync_jobs.pending` for a published browser dataset.
2. `finance-agents/browser-agent/service.py` claims pending browser jobs from finance-mcp.
3. The browser-agent enforces per-shop profile lock and local concurrency.
4. The browser-agent calls local `runner.run_message()`.
5. On success it uploads records and `capture_files`, then marks the sync job success.
6. On deterministic failure it marks the sync job failed and fails any waiting recon job immediately.
7. On transient failure it retries according to the browser retry policy.
8. `recon_execution_queue.waiting_data` jobs are restored to `queued` only when their non-empty `collection_job_ids` all point to successful sync jobs.

## Compatibility

Database, platform OAuth, and API collection remain unchanged. They may continue to execute inside finance-mcp because they are deterministic programmatic collectors. Browser collection uses browser-agent because it owns Chrome, profiles, downloads, and local concurrency.

## First-Store Dataset Publication

First-store v1 requires manual data-source dataset publication before collection. The browser-agent writes into the existing dataset id supplied by the queued sync job. Automatic dataset publication is deferred.

## Deferred

- Full WS runner protocol with HELLO/HEARTBEAT/ack lease.
- noVNC live browser UI.
- Browser-record soft delete for rows missing from a later recapture.
- Multi-machine fleet assignment UI.
- Canary version routing in browser job claim (currently `p.status = 'active'` only; `canary_shop_ids` not consulted).
- Automatic cleanup of stale pending browser sync_jobs whose binding turned unhealthy after creation.

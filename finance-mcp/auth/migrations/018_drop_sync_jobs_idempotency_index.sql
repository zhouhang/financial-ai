-- Collection jobs are audit records: every manual/scheduled/rerun trigger should
-- create a distinct sync_jobs row. Data-level idempotency lives in
-- dataset_collection_records via item_key, so the old task-level idempotency
-- unique index is intentionally removed.
DROP INDEX IF EXISTS public.idx_sync_jobs_idempotency;


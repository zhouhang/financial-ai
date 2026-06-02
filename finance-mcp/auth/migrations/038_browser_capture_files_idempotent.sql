-- 038: make browser_capture_files writes idempotent so completion retries don't duplicate audit rows.
-- A retried sync_job re-reports the same (sync_job_id, storage_path); upsert instead of insert.
CREATE UNIQUE INDEX IF NOT EXISTS idx_browser_capture_files_sync_job_storage_path
    ON public.browser_capture_files (sync_job_id, storage_path)
    WHERE sync_job_id IS NOT NULL;

---
phase: 07-browser-playbook-collection
reviewed: 2026-05-19T10:52:32Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - finance-mcp/auth/migrations/031_browser_playbook_collection.sql
  - finance-mcp/auth/db.py
  - finance-mcp/tests/test_browser_playbook_records.py
  - finance-mcp/tests/test_recon_execution_waiting_data.py
findings:
  critical: 0
  warning: 3
  info: 0
  total: 3
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-05-19T10:52:32Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the new browser playbook schema migration, the schema readiness helper, and the two companion tests. The main gaps are missing referential integrity/update hooks in the DDL and a readiness/test check that does not verify the new `waiting_data` queue semantics.

## Warnings

### WR-01: New browser playbook tables cannot enforce their references

**File:** `finance-mcp/auth/migrations/031_browser_playbook_collection.sql:1-165`
**Issue:** The new tables store company-scoped and cross-table identifiers (`company_id`, `data_source_id`, `dataset_id`, `sync_job_id`, `created_by`, `approved_by`, `first_seen_job_id`, `latest_seen_job_id`), but never add foreign-key constraints. More importantly, the playbook relation is only stored as `playbook_id` while `playbooks` is unique on `(company_id, playbook_id, version)`, so the child tables cannot even reference a single playbook version unambiguously.
**Fix:**
```sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'browser_collection_records_company_id_fkey') THEN
        ALTER TABLE ONLY public.browser_collection_records
            ADD CONSTRAINT browser_collection_records_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES public.company(id) ON DELETE CASCADE;
    END IF;
END $$;
```
Add the same style of FK blocks for the other referenced IDs (`data_sources`, `data_source_datasets`, `sync_jobs`, and `users`) where those IDs are meant to point to local tables, and either carry `playbook_version` or make `(company_id, playbook_id)` a stable unique key if version-less binding is intended.

### WR-02: `updated_at` never advances on updates for the new timestamped tables

**File:** `finance-mcp/auth/migrations/031_browser_playbook_collection.sql:1-73,75-148`
**Issue:** `playbooks`, `agents`, `shop_runtime_bindings`, and `browser_collection_records` all define `updated_at`, and `playbooks` even indexes it for recency, but the migration never adds `BEFORE UPDATE` triggers. Those timestamps will stay frozen at insert time, so recency ordering and any freshness logic built on `updated_at` will be wrong.
**Fix:**
```sql
DROP TRIGGER IF EXISTS update_playbooks_updated_at ON public.playbooks;
CREATE TRIGGER update_playbooks_updated_at
    BEFORE UPDATE ON public.playbooks
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
```
Repeat that for the other tables that expose `updated_at`.

### WR-03: Waiting-data schema check and test do not verify the new queue behavior

**File:** `finance-mcp/auth/db.py:484-542`
**File:** `finance-mcp/tests/test_recon_execution_waiting_data.py:13-22`
**Issue:** The readiness helper and the test only check that the new columns exist on `recon_execution_queue`, and the helper only looks for `draft`/`deprecated` in the playbooks status constraint. They never verify that `recon_execution_queue_status_check` now permits `waiting_data`, so a partially applied migration can be treated as ready even though waiting-data queue inserts would still fail at runtime.
**Fix:**
```python
constraint_def = auth_db._constraint_definition(
    "recon_execution_queue",
    "recon_execution_queue_status_check",
)
assert "waiting_data" in constraint_def
```
Mirror that check in `_browser_playbook_collection_schema_ready()` and extend the playbooks constraint check to cover all allowed statuses, not just `draft` and `deprecated`, so auto-migration cannot skip a half-applied upgrade.

---

_Reviewed: 2026-05-19T10:52:32Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

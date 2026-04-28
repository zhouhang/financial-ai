-- dataset_collection_records is the source-of-truth collection asset layer.
-- Migrate legacy published snapshots into collection records once, then drop the
-- raw/snapshot/checkpoint tables so runtime code no longer depends on them.
--
-- Important: keep this migration atomic. If migration from snapshots fails, the
-- legacy snapshot tables must remain available for retry.

BEGIN;

DO $$
BEGIN
    IF to_regclass('public.dataset_snapshots') IS NOT NULL
       AND to_regclass('public.dataset_snapshot_items') IS NOT NULL THEN
        INSERT INTO public.dataset_collection_records (
            company_id,
            data_source_id,
            dataset_id,
            dataset_code,
            resource_key,
            biz_date,
            item_key,
            item_key_values,
            item_hash,
            payload,
            record_status,
            first_seen_job_id,
            latest_seen_job_id,
            first_seen_at,
            latest_seen_at,
            created_at,
            updated_at
        )
        SELECT
            company_id,
            data_source_id,
            dataset_id,
            dataset_code,
            resource_key,
            biz_date,
            item_key,
            item_key_values,
            item_hash,
            payload,
            record_status,
            first_seen_job_id,
            latest_seen_job_id,
            first_seen_at,
            latest_seen_at,
            created_at,
            updated_at
        FROM (
            SELECT DISTINCT ON (snapshots.company_id, datasets.id, snapshot_biz_date.biz_date, items.item_key)
                snapshots.company_id,
                snapshots.data_source_id,
                datasets.id AS dataset_id,
                datasets.dataset_code,
                snapshots.resource_key,
                snapshot_biz_date.biz_date,
                items.item_key,
                jsonb_build_object('legacy_snapshot_item_key', items.item_key) AS item_key_values,
                LEFT(COALESCE(NULLIF(items.item_hash, ''), md5(items.item_payload::text)), 64) AS item_hash,
                COALESCE(items.item_payload, '{}'::jsonb) AS payload,
                'active' AS record_status,
                snapshots.sync_job_id AS first_seen_job_id,
                COALESCE(snapshots.published_by_job_id, snapshots.sync_job_id) AS latest_seen_job_id,
                items.created_at AS first_seen_at,
                COALESCE(snapshots.published_at, snapshots.updated_at, snapshots.created_at) AS latest_seen_at,
                items.created_at AS created_at,
                COALESCE(snapshots.published_at, snapshots.updated_at, snapshots.created_at) AS updated_at
            FROM public.dataset_snapshots snapshots
            JOIN public.data_source_datasets datasets
              ON datasets.company_id = snapshots.company_id
             AND datasets.data_source_id = snapshots.data_source_id
             AND datasets.resource_key = snapshots.resource_key
            JOIN public.dataset_snapshot_items items ON items.snapshot_id = snapshots.id
            LEFT JOIN public.sync_jobs snapshot_jobs ON snapshot_jobs.id = snapshots.sync_job_id
            CROSS JOIN LATERAL (
                SELECT COALESCE(
                    NULLIF(snapshot_jobs.request_payload ->> 'biz_date', ''),
                    to_char(COALESCE(snapshots.published_at, snapshots.created_at), 'YYYY-MM-DD')
                ) AS biz_date
            ) snapshot_biz_date
            WHERE snapshots.is_published = TRUE
              AND snapshots.snapshot_status = 'published'
              AND NULLIF(items.item_key, '') IS NOT NULL
            ORDER BY snapshots.company_id,
                     datasets.id,
                     snapshot_biz_date.biz_date,
                     items.item_key,
                     snapshots.published_at DESC NULLS LAST,
                     snapshots.created_at DESC,
                     items.created_at DESC,
                     items.id DESC
        ) migrated
        ON CONFLICT (company_id, dataset_id, biz_date, item_key)
        DO UPDATE SET
            data_source_id = EXCLUDED.data_source_id,
            dataset_code = EXCLUDED.dataset_code,
            resource_key = EXCLUDED.resource_key,
            item_key_values = EXCLUDED.item_key_values,
            item_hash = EXCLUDED.item_hash,
            payload = EXCLUDED.payload,
            record_status = 'active',
            latest_seen_job_id = EXCLUDED.latest_seen_job_id,
            latest_seen_at = EXCLUDED.latest_seen_at,
            updated_at = EXCLUDED.updated_at;
    END IF;
END $$;

DROP TABLE IF EXISTS public.dataset_snapshot_items CASCADE;
DROP TABLE IF EXISTS public.dataset_snapshots CASCADE;
DROP TABLE IF EXISTS public.raw_ingestion_records CASCADE;
DROP TABLE IF EXISTS public.raw_ingestion_batches CASCADE;
DROP TABLE IF EXISTS public.sync_checkpoints CASCADE;

COMMIT;

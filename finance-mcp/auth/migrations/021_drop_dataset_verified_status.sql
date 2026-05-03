DROP INDEX IF EXISTS public.idx_data_source_datasets_business_filter;

ALTER TABLE IF EXISTS public.data_source_datasets
    DROP CONSTRAINT IF EXISTS data_source_datasets_verified_status_check;

ALTER TABLE IF EXISTS public.data_source_datasets
    DROP COLUMN IF EXISTS verified_status;

UPDATE public.data_source_datasets
SET meta = jsonb_set(
        COALESCE(meta, '{}'::jsonb),
        '{catalog_profile}',
        COALESCE(meta->'catalog_profile', '{}'::jsonb) - 'verified_status',
        true
    )
WHERE COALESCE(meta, '{}'::jsonb) ? 'catalog_profile'
  AND COALESCE(meta->'catalog_profile', '{}'::jsonb) ? 'verified_status';

UPDATE public.data_source_datasets
SET meta = jsonb_set(
        COALESCE(meta, '{}'::jsonb),
        '{semantic_profile}',
        COALESCE(meta->'semantic_profile', '{}'::jsonb) - 'verified_status',
        true
    )
WHERE COALESCE(meta, '{}'::jsonb) ? 'semantic_profile'
  AND COALESCE(meta->'semantic_profile', '{}'::jsonb) ? 'verified_status';

CREATE INDEX IF NOT EXISTS idx_data_source_datasets_business_filter
    ON public.data_source_datasets USING btree (company_id, business_object_type, publish_status);

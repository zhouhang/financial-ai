-- Platform OAuth datasets should remain manual/on-demand. Remove historical
-- automatic collection schedule metadata so finance-cron will not auto-pull
-- ecommerce authorization datasets.
UPDATE public.data_source_datasets d
SET
    sync_strategy = (
        COALESCE(d.sync_strategy, '{}'::jsonb)
        - 'schedule_type'
        - 'schedule_expr'
        - 'schedule_expression'
    ),
    extract_config = (
        COALESCE(d.extract_config, '{}'::jsonb)
        - 'schedule_type'
        - 'schedule_expr'
        - 'schedule_expression'
        - 'schedule_time'
        - 'time'
        - 'schedule'
    ),
    meta = (
        COALESCE(d.meta, '{}'::jsonb)
        #- '{catalog_profile,collection_config,schedule_type}'
        #- '{catalog_profile,collection_config,schedule_expr}'
        #- '{catalog_profile,collection_config,schedule_expression}'
        #- '{catalog_profile,collection_config,schedule_time}'
        #- '{catalog_profile,collection_config,time}'
        #- '{catalog_profile,collection_config,schedule}'
    ),
    updated_at = CURRENT_TIMESTAMP
FROM public.data_sources s
WHERE s.id = d.data_source_id
  AND s.company_id = d.company_id
  AND s.source_kind = 'platform_oauth'
  AND (
      COALESCE(d.sync_strategy->>'schedule_type', '') <> ''
      OR COALESCE(d.sync_strategy->>'schedule_expr', '') <> ''
      OR COALESCE(d.sync_strategy->>'schedule_expression', '') <> ''
      OR COALESCE(d.extract_config->>'schedule_type', '') <> ''
      OR COALESCE(d.extract_config->>'schedule_expr', '') <> ''
      OR COALESCE(d.extract_config->>'schedule_expression', '') <> ''
      OR COALESCE(d.extract_config->>'schedule_time', '') <> ''
      OR COALESCE(d.extract_config->>'time', '') <> ''
      OR d.extract_config ? 'schedule'
      OR COALESCE(d.meta #>> '{catalog_profile,collection_config,schedule_type}', '') <> ''
      OR COALESCE(d.meta #>> '{catalog_profile,collection_config,schedule_expr}', '') <> ''
      OR COALESCE(d.meta #>> '{catalog_profile,collection_config,schedule_expression}', '') <> ''
      OR COALESCE(d.meta #>> '{catalog_profile,collection_config,schedule_time}', '') <> ''
      OR COALESCE(d.meta #>> '{catalog_profile,collection_config,time}', '') <> ''
      OR (d.meta #> '{catalog_profile,collection_config,schedule}') IS NOT NULL
  );
